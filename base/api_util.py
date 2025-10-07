import json
import re
from copy import deepcopy
from json.decoder import JSONDecodeError

import allure
import jsonpath

from common.assertions import Assertions
from common.extract_util import ExtractUtil
from common.parser_yaml import get_testcase_yaml, YmalParser
from common.log_util import logs
from common.requests_util import SendRequest
from conf.config_util import OperationConfig
from conf.setting import FILE_PATH


def replace_load_yaml(data):
    """yaml数据替换解析，例如将需要从extract.yaml文件中提取的参数进行替换"""
    str_data = data
    if not isinstance(data, str): # 序列化
        str_data = json.dumps(data, ensure_ascii=False)
        # print('从yaml文件获取的原始数据：', str_data)
    for i in range(str_data.count('${')):
        if '${' in str_data and '}' in str_data:
            start_index = str_data.index('$')
            end_index = str_data.index('}', start_index)
            ref_all_params = str_data[start_index:end_index + 1]
            # 取出yaml文件的函数名
            func_name = ref_all_params[2:ref_all_params.index("(")]
            # 取出函数里面的参数
            func_params = ref_all_params[ref_all_params.index("(") + 1:ref_all_params.index(")")]
            # 传入替换的参数获取对应的值,类的反射----getattr,setattr,del....
            extract_data = getattr(ExtractUtil(), func_name)(*func_params.split(',') if func_params else "")
            # 如果提取的数据是列表，转换成字符串
            if extract_data and isinstance(extract_data, list):
                extract_data = ','.join(e for e in extract_data)
            # 将yaml文件的数据替换成实际数据
            str_data = str_data.replace(ref_all_params, str(extract_data))

    # 还原数据（反序列化）
    if data and isinstance(data, dict):
        data = json.loads(str_data)
    else:
        data = str_data
    return data


def allure_attach_response(response):
    if isinstance(response, dict):
        allure_response = json.dumps(response, ensure_ascii=False, indent=4)
    else:
        allure_response = response
    return allure_response


def safe_to_int(s: str):
    """仅在纯数字时转 int，否则原样返回字符串"""
    try:
        return int(s) if isinstance(s, str) and s.isdigit() else s
    except Exception:
        return s


class RequestBase:

    def __init__(self):
        self.run = SendRequest()
        self.conf = OperationConfig()
        self.yml_parser = YmalParser()
        self.asserts = Assertions()

    def specification_yaml(self, base_info, test_case):
        """
        接口测试用例执行函数
        :param base_info: yaml文件里面的baseInfo
        :param test_case: yaml文件里面的testCase
        :return:
        """
        try:
            # deepcopy，防止用例执行过程中（例如pop）修改原始数据
            if isinstance(base_info, dict):
                base_info = deepcopy(base_info)
            if isinstance(test_case, dict):
                test_case = deepcopy(test_case)
            # 请求参数类型，这些字段内容需要进行yaml数据替换
            params_type = ['data', 'json', 'params']
            # 取base url
            url_host = self.conf.get_section_for_data('api_envi', 'host')

            ''' 处理baseInfo '''
            # 提取接口基本信息（接口名称、URL、请求头）并添加 Allure 报告附件
            api_name = base_info['api_name']
            allure.attach(api_name, '接口名称', allure.attachment_type.TEXT)
            url = url_host + base_info['url']
            allure.attach(url, '接口地址', allure.attachment_type.TEXT)
            base_method = base_info.get('method')
            header = replace_load_yaml(base_info['header'])
            allure.attach(json.dumps(header, ensure_ascii=False, indent=2), '请求头', allure.attachment_type.TEXT)

            # 处理cookie
            cookie = None
            if base_info.get('cookies') is not None:
                cookie = eval(replace_load_yaml(base_info['cookies']))

            # 提取测试用例基本信息（用例名称、用例请求方法[可能与base method不同]）并添加 Allure 报告附件
            case_name = test_case.pop('case_name')
            allure.attach(case_name, '测试用例名称', allure.attachment_type.TEXT)
            case_method = test_case.pop('method', base_method) # 如果没有特指用例请求方法，则使用base method
            allure.attach(case_method, '请求方法', allure.attachment_type.TEXT)

            # 处理断言
            validation_raw = test_case.pop('validation', None)
            if validation_raw is not None:
                val = replace_load_yaml(validation_raw)
                validation = eval(val) if isinstance(val, str) else val # 断言内容可能是列表或字符串
            else:
                validation = []

            # 处理参数提取
            extract = test_case.pop('extract', None)
            extract_list = test_case.pop('extract_list', None)

            # 处理请求参数
            for key, value in test_case.items():
                if key in params_type: # data、json、params中的数据需要进行yaml数据替换
                    test_case[key] = replace_load_yaml(value)

            # 处理文件上传接口
            file, files = test_case.pop('files', None), None
            if file is not None:
                for fk, fv in file.items():
                    allure.attach(json.dumps(file), '导入文件')
                    files = {fk: open(fv, mode='rb')}

            # 使用二次封装的requests发请求
            res = self.run.run_main(name=api_name, url=url, case_name=case_name, header=header, method=case_method,
                                    file=files, cookies=cookie, **test_case)

            # 获取响应信息
            status_code = res.status_code
            raw_headers = getattr(res, 'headers', {})

            # 处理响应header并添加 Allure 报告附件
            response_headers = {}
            if raw_headers:
                for header_key, header_value in raw_headers.items():
                    response_headers[str(header_key)] = str(header_value)
            response_headers['status_code'] = str(status_code)
            try:
                res_body = res.json()
            except JSONDecodeError:
                res_body = None
            if response_headers:
                allure.attach(json.dumps(response_headers, ensure_ascii=False, indent=4),
                              '响应头', allure.attachment_type.TEXT)

            try:
                # 处理响应体，转为json（如可能，并提取所需extract数据）
                if res_body is not None:
                    res_json = res_body
                    if extract is not None:
                        self.extract_data(extract, res.text)
                    if extract_list is not None:
                        self.extract_data_list(extract_list, res.text)
                else:
                    res_json = {}
                # 处理断言
                self.asserts.assert_result(validation, res_json, status_code, headers=response_headers)
            except JSONDecodeError as js:
                logs.error('系统异常或接口未请求！')
                raise js
            except Exception as e:
                logs.error(e)
                raise e

        except Exception as e:
            raise e

    def extract_data(self, testcase_extarct, response):
        """
        提取接口的返回值，支持正则表达式和json提取器
        :param testcase_extarct: testcase文件yaml中的extract值
        :param response: 接口的实际返回值
        :return:
        """
        try:
            pattern_lst = [r'(\d+)', r'(\d*)', '(.*?)', '(.+?)']
            for key, value in testcase_extarct.items():
                extracted = None

                # ---- 正则提取 ----
                is_regex = any(pat in value for pat in pattern_lst) or bool(re.search(r'\(.+?\)', value))
                if is_regex and not value.strip().startswith('$'):
                    m = re.search(value, response, re.S)
                    if m:
                        grp = m.group(1)
                        # 若捕获到的是纯数字，尽量转成 int
                        extracted = safe_to_int(grp)
                        self.yml_parser.write_yaml_data({key: extracted})
                        continue  # 单值提取完成

                # ---- JSONPath 提取（以 $ 开头的表达式视为 JSONPath）----
                if '$' in value:
                    try:
                        parsed = json.loads(response)
                        jp = jsonpath.jsonpath(parsed, value)  # 命中返回 list，未命中返回 False/None
                        if isinstance(jp, list) and len(jp) > 0:
                            extracted = jp[0]
                            self.yml_parser.write_yaml_data({key: extracted})
                        else:
                            self.yml_parser.write_yaml_data({key: f'未提取到数据，JSONPath无结果: {value}'})
                    except Exception as e:
                        logs.error(f'JSONPath 提取失败: {e}')
                        self.yml_parser.write_yaml_data({key: f'未提取到数据，响应非JSON或JSONPath异常: {value}'})
        except Exception as e:
            logs.error(e)

    def extract_data_list(self, testcase_extract_list, response):
        """
        提取多个参数，支持正则表达式和json提取，提取结果以列表形式返回
        :param testcase_extract_list: yaml文件中的extract_list信息
        :param response: 接口的实际返回值,str类型
        :return:
        """
        try:
            for key, value in testcase_extract_list.items():
                # ---- 正则多值：任意捕获组都可（更通用），findall 返回列表 ----
                if bool(re.search(r'\(.+?\)', value)) and not value.strip().startswith('$'):
                    try:
                        ext_list = re.findall(value, response, re.S)
                        if ext_list:
                            # 尝试把纯数字元素转 int，其余保持原样
                            normalized = [safe_to_int(x) for x in ext_list]
                            self.yml_parser.write_yaml_data({key: normalized})
                            logs.info('正则提取到的参数：%s' % {key: normalized})
                    except Exception as e:
                        logs.error(f'正则提取异常: {e}')
                # ---- JSONPath 多值 ----
                if "$" in value:
                    try:
                        parsed = json.loads(response)
                        ext_json = jsonpath.jsonpath(parsed, value)
                        if isinstance(ext_json, list) and len(ext_json) > 0:
                            self.yml_parser.write_yaml_data({key: ext_json})
                            logs.info('json提取到参数：%s' % {key: ext_json})
                        else:
                            self.yml_parser.write_yaml_data({key: "未提取到数据，该接口返回结果可能为空"})
                            logs.info('json提取为空：%s' % {key: value})
                    except Exception as e:
                        logs.error(f'JSONPath 提取失败: {e}')
                        self.yml_parser.write_yaml_data({key: f'未提取到数据，响应非JSON或JSONPath异常: {value}'})
                        wrote = True
        except:
            logs.error('接口返回值提取异常，请检查yaml文件extract_list表达式是否正确！')
