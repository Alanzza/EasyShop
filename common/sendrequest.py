# -*- coding: utf-8 -*-
import json
import time
import requests
import urllib3
import pytest
import allure

from typing import Any, Dict, Optional

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from conf import setting
from common.recordlog import logs
from common.parser_yaml import ReadYamlData


class SendRequest:
    """
    统一的请求发送封装：
    - 仅暴露 run_main() 和 send_request() 两个入口
    - 统一返回 requests.Response（不再混用自定义字典返回）
    - 集中处理：日志、Allure 附件、超时、SSL、重试、文件上传、Cookie 落盘、异常转换
    - 与旧代码兼容：run_main(...) 仍然接收参数名 file（会映射到 requests 的 files）
    """

    def __init__(
        self,
        cookie: Optional[Dict[str, Any]] = None,
        retries: int = 2,
        backoff_factor: float = 0.3,
        status_forcelist: Optional[tuple] = (429, 500, 502, 503, 504),
        respect_retry_after_header: bool = True,
    ):
        self.cookie = cookie or {}
        self.read = ReadYamlData()

        # 预置 Session + 重试策略（对 GET/POST/PUT/DELETE…通用）
        self.session = self._build_session(
            retries=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            respect_retry_after_header=respect_retry_after_header,
        )

    @staticmethod
    def _build_session(
        retries: int,
        backoff_factor: float,
        status_forcelist: Optional[tuple],
        respect_retry_after_header: bool,
    ) -> requests.Session:
        """构建带重试的 Session"""
        session = requests.Session()
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=False,  # 对所有方法生效（urllib3>=1.26 可用 set；False 表示不过滤）
            respect_retry_after_header=respect_retry_after_header,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    @staticmethod
    def _attach_request_to_allure(
        method: str,
        url: str,
        headers: Optional[Dict[str, Any]],
        cookies: Optional[Dict[str, Any]],
        files: Optional[Dict[str, Any]],
        kwargs: Dict[str, Any],
    ) -> None:
        """把请求关键要素写到 Allure 报告"""
        try:
            payload = {
                "method": method,
                "url": url,
                "headers": headers,
                "cookies": cookies,
                "files": list(files.keys()) if isinstance(files, dict) else None,
                "kwargs": kwargs,  # 可能包含 data/json/params 等
            }
            allure.attach(
                json.dumps(payload, ensure_ascii=False, indent=2),
                name="请求详情",
                attachment_type=allure.attachment_type.JSON,
            )
        except Exception:
            # 附件失败不影响主流程
            pass

    @staticmethod
    def _attach_response_to_allure(resp: requests.Response) -> None:
        """把响应写到 Allure 报告"""
        try:
            # Body（优先 JSON 美化）
            try:
                body = resp.json()
                allure.attach(
                    json.dumps(body, ensure_ascii=False, indent=2),
                    name="响应Body(JSON)",
                    attachment_type=allure.attachment_type.JSON,
                )
            except Exception:
                allure.attach(
                    resp.text or "",
                    name="响应Body(原文)",
                    attachment_type=allure.attachment_type.TEXT,
                )
        except Exception:
            pass

    @staticmethod
    def _close_files(files: Optional[Dict[str, Any]]) -> None:
        """
        尽力关闭 files 里的文件句柄：
        - 支持 {'field': fileobj} 或 {'field': (filename, fileobj, content_type)}
        """
        if not isinstance(files, dict):
            return
        for v in files.values():
            try:
                # 可能是 fileobj
                if hasattr(v, "close"):
                    v.close()
                    continue
                # 可能是 (filename, fileobj[, content_type])
                if isinstance(v, (list, tuple)) and len(v) >= 2 and hasattr(v[1], "close"):
                    v[1].close()
            except Exception:
                # 关闭失败不影响主流程
                pass

    def send_request(
        self,
        *,
        method: str,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        verify: bool = False,
        allow_redirects: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """
        直接发送请求（底层统一入口）
        :return: requests.Response
        """
        timeout = timeout or getattr(setting, "API_TIMEOUT", 30)

        # 记录与 Allure 附件
        try:
            logs.info("请求方式：%s", method)
            logs.info("请求地址：%s", url)
            logs.info("请求头：%s", headers)
            logs.info("Cookie：%s", cookies)
            if kwargs:
                logs.info("请求参数：%s", json.dumps(kwargs, ensure_ascii=False))
            self._attach_request_to_allure(method, url, headers, cookies, files, kwargs)
        except Exception:
            pass

        start_ts = time.time()
        try:
            resp = self.session.request(
                method=method,
                url=url,
                headers=headers,
                cookies=cookies,
                files=files,
                timeout=timeout,
                verify=verify,
                allow_redirects=allow_redirects,
                **kwargs,  # data/json/params 等
            )

            # 记录 Cookie（若有 set-cookie）
            try:
                set_cookie = requests.utils.dict_from_cookiejar(resp.cookies)
                if set_cookie:
                    cookie_block = {"Cookie": set_cookie}
                    self.read.write_yaml_data(cookie_block)
                    logs.info("响应Set-Cookie写入extract.yaml：%s", cookie_block)
            except Exception:
                pass

            # 响应日志 & Allure
            try:
                logs.info("响应码：%s", resp.status_code)
                logs.info("响应耗时：%ss", round(resp.elapsed.total_seconds(), 3) if resp.elapsed else None)
                logs.info("响应文本：%s", resp.text if resp.text else "<空响应体>")
                self._attach_response_to_allure(resp)
            except Exception:
                pass

            return resp

        except requests.exceptions.ConnectionError:
            logs.error("ConnectionError--连接异常")
            pytest.fail("接口请求异常：连接异常（可能连接过多或目标不可达）")
            raise
        except requests.exceptions.HTTPError as e:
            logs.error("HTTPError：%s", str(e))
            pytest.fail(f"接口请求异常：HTTP错误 {str(e)}")
            raise
        except requests.exceptions.RequestException as e:
            logs.error("RequestException：%s", str(e))
            pytest.fail("接口请求异常：RequestException，请检查系统或用例数据是否正常！")
            raise
        finally:
            # 若由上层传入文件对象，这里兜底关闭，避免句柄泄露
            try:
                self._close_files(files)
            except Exception:
                pass
            logs.info("请求总耗时：%.3fs", time.time() - start_ts)

    def run_main(
        self,
        name: str,
        url: str,
        case_name: str,
        header: Optional[Dict[str, Any]],
        method: str,
        cookies: Optional[Dict[str, Any]] = None,
        file: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """
        二次封装request的入口。
        - 参数名 `file` 沿用旧代码；内部统一映射到 requests 的 `files`
        - kwargs 里期望含有 data/json/params 三类之一
        """
        try:
            logs.info("接口名称：%s", name)
            logs.info("测试用例名称：%s", case_name)
        except Exception:
            pass

        # 兼容旧参数：优先使用 files，否则回退旧的 file
        files_payload = files if files is not None else file

        # 统一把请求参数作为一个 JSON 附件
        try:
            if kwargs:
                allure.attach(
                    json.dumps(kwargs, ensure_ascii=False, indent=2),
                    name="请求参数",
                    attachment_type=allure.attachment_type.JSON,
                )
                logs.info("请求参数：%s", json.dumps(kwargs, ensure_ascii=False))
        except Exception:
            pass

        # 透传到底层 send_request
        resp = self.send_request(
            method=method,
            url=url,
            headers=header,
            cookies=cookies,
            files=files_payload,
            timeout=getattr(setting, "API_TIMEOUT", 30),
            verify=False,
            **kwargs,
        )
        return resp
