# -*- coding: utf-8 -*-
# sys.path.insert(0, "..")


from common.requests_util import SendRequest
from common.parser_yaml import YmalParser
from common.log_util import logs
from conf.config_util import OperationConfig
from common.assertions import Assertions
from common.extract_util import ExtractUtil
import allure
import json
import jsonpath
import re
import traceback
from json.decoder import JSONDecodeError

assert_res = Assertions()


class RequestBase(object):
    def __init__(self):
        self.run = SendRequest()
        self.read = YmalParser()
        self.conf = OperationConfig()

    def handler_yaml_list(self, data_dict):
        """处理yaml文件测试用例请求参数为list情况，以数组形式"""
        try:
            for key, value in data_dict.items():
                if isinstance(value, list):
                    value_lst = ','.join(value).split(',')
                    data_dict[key] = value_lst
                return data_dict
        except Exception:
            logs.error(str(traceback.format_exc()))

    def replace_load(self, data):
        """yaml数据替换解析"""
        str_data = data
        if not isinstance(data, str):
            str_data = json.dumps(data, ensure_ascii=False)
        for i in range(str_data.count('${')):
            if '${' in str_data and '}' in str_data:
                # index检测字符串是否子字符串，并找到字符串的索引位置
                start_index = str_data.index('$')
                end_index = str_data.index('}', start_index)
                # yaml文件的参数，如：${get_yaml_data(loginname)}
                ref_all_params = str_data[start_index:end_index + 1]
                # 函数名，获取DebugUtil的方法
                func_name = ref_all_params[2:ref_all_params.index("(")]
                # 函数里的参数
                func_params = ref_all_params[ref_all_params.index("(") + 1:ref_all_params.index(")")]
                # 传入替换的参数获取对应的值,*func_params按,分割重新得到一个字符串
                extract_data = getattr(ExtractUtil(), func_name)(*func_params.split(',') if func_params else "")
                if extract_data and isinstance(extract_data, list):
                    extract_data = ','.join(e for e in extract_data)
                str_data = str_data.replace(ref_all_params, str(extract_data))
        # 还原数据
        if data and isinstance(data, dict):
            data = json.loads(str_data)
            self.handler_yaml_list(data)
        else:
            data = str_data
        return data

    def specification_yaml(self, case_info):
        """
        规范yaml测试用例的写法
        :param case_info: list类型,调试取case_info[0]-->dict
        :return:
        """
        params_type = ['params', 'data', 'json']
        cookie = None
        try:
            base_url = self.conf.get_section_for_data('api_envi', 'host')
            # base_url = self.replace_load(case_info['baseInfo']['url'])
            url = base_url + case_info["baseInfo"]["url"]
            allure.attach(url, '接口地址', allure.attachment_type.TEXT)
            api_name = case_info["baseInfo"]["api_name"]
            allure.attach(api_name, '接口名称', allure.attachment_type.TEXT)
            base_method = case_info["baseInfo"].get("method")
            header = self.replace_load(case_info["baseInfo"]["header"])
            allure.attach(str(header), '请求头信息', allure.attachment_type.TEXT)
            try:
                cookie = self.replace_load(case_info["baseInfo"]["cookies"])
                allure.attach(str(cookie), 'Cookie', allure.attachment_type.TEXT)
            except:
                pass
            for tc in case_info["testCase"]:
                case_name = tc.pop("case_name")
                allure.attach(case_name, '测试用例名称', allure.attachment_type.TEXT)
                case_method = tc.pop('method', base_method)
                allure.attach(str(case_method), '请求方法', allure.attachment_type.TEXT)
                # 断言结果解析替换
                validation_raw = tc.pop('validation', None)
                if validation_raw is not None:
                    val = self.replace_load(validation_raw)
                    validation = eval(val) if isinstance(val, str) else val
                    allure_validation = str([str(list(i.values())) for i in validation]) if validation else '[]'
                else:
                    validation = []
                    allure_validation = '[]'
                allure.attach(allure_validation, "预期结果", allure.attachment_type.TEXT)
                extract = tc.pop('extract', None)
                extract_lst = tc.pop('extract_list', None)
                for key, value in tc.items():
                    if key in params_type:
                        tc[key] = self.replace_load(value)
                file, files = tc.pop("files", None), None
                if file is not None:
                    for fk, fv in file.items():
                        allure.attach(json.dumps(file), '导入文件')
                        files = {fk: open(fv, 'rb')}
                res = self.run.run_main(name=api_name,
                                        url=url,
                                        case_name=case_name,
                                        header=header,
                                        cookies=cookie,
                                        method=case_method,
                                        file=files, **tc)
                res_text = res.text
                status_code = res.status_code
                raw_headers = getattr(res, 'headers', {})
                response_headers = {}
                if raw_headers:
                    for header_key, header_value in raw_headers.items():
                        response_headers[str(header_key)] = str(header_value)
                response_headers['status_code'] = str(status_code)
                try:
                    res_body = res.json()
                except JSONDecodeError:
                    res_body = None

                allure.attach(self.allure_attach_response(res_body if res_body is not None else res_text),
                              '接口响应信息', allure.attachment_type.TEXT)
                if response_headers:
                    allure.attach(json.dumps(response_headers, ensure_ascii=False, indent=4),
                                  '响应Headers', allure.attachment_type.TEXT)

                try:
                    if res_body is not None:
                        res_json = res_body
                        if extract is not None:
                            self.extract_data(extract, res_text)
                        if extract_lst is not None:
                            self.extract_data_list(extract_lst, res_text)
                    else:
                        res_json = {}
                    # 处理断言
                    assert_res.assert_result(validation, res_json, status_code, headers=response_headers)
                except JSONDecodeError as js:
                    logs.error("系统异常或接口未请求！")
                    raise js
                except Exception as e:
                    logs.error(str(traceback.format_exc()))
                    raise e
        except Exception as e:
            logs.error(e)
            raise e

    @classmethod
    def allure_attach_response(cls, response):
        if isinstance(response, dict):
            allure_response = json.dumps(response, ensure_ascii=False, indent=4)
        else:
            allure_response = response
        return allure_response

    def extract_data(self, testcase_extract, response):
        """
        提取接口的返回参数，支持正则表达式和json提取，提取单个参数
        :param testcase_extract: testcase文件yaml中的extract值
        :param response: 接口的实际返回值,str类型
        :return:
        """
        pattern_lst = ['(.+?)', '(.*?)', r'(\d+)', r'(\d*)']
        try:
            for key, value in testcase_extract.items():
                for pat in pattern_lst:
                    if pat in value:
                        ext_list = re.search(value, response)
                        if pat in [r'(\d+)', r'(\d*)']:
                            extract_date = {key: int(ext_list.group(1))}
                        else:
                            extract_date = {key: ext_list.group(1)}
                        logs.info('正则提取到的参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
                if "$" in value:
                    ext_json = jsonpath.jsonpath(json.loads(response), value)[0]
                    if ext_json:
                        extract_date = {key: ext_json}
                    else:
                        extract_date = {key: "未提取到数据，该接口返回结果可能为空"}
                    logs.info('json提取到参数：%s' % extract_date)
                    self.read.write_yaml_data(extract_date)
        except:
            logs.error('接口返回值提取异常，请检查yaml文件extract表达式是否正确！')

    def extract_data_list(self, testcase_extract_list, response):
        """
        提取多个参数，支持正则表达式和json提取，提取结果以列表形式返回
        :param testcase_extract_list: yaml文件中的extract_list信息
        :param response: 接口的实际返回值,str类型
        :return:
        """
        try:
            for key, value in testcase_extract_list.items():
                if "(.+?)" in value or "(.*?)" in value:
                    ext_list = re.findall(value, response, re.S)
                    if ext_list:
                        extract_date = {key: ext_list}
                        logs.info('正则提取到的参数：%s' % extract_date)
                        self.read.write_yaml_data(extract_date)
                if "$" in value:
                    # 增加提取判断，有些返回结果为空提取不到，给一个默认值
                    ext_json = jsonpath.jsonpath(json.loads(response), value)
                    if ext_json:
                        extract_date = {key: ext_json}
                    else:
                        extract_date = {key: "未提取到数据，该接口返回结果可能为空"}
                    logs.info('json提取到参数：%s' % extract_date)
                    self.read.write_yaml_data(extract_date)
        except:
            logs.error('接口返回值提取异常，请检查yaml文件extract_list表达式是否正确！')
