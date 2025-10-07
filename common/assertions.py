import traceback
import allure
import jsonpath
import operator

from common.log_util import logs
from common.connection import ConnectMysql


class Assertions:
    """"
    接口断言模式，支持
    1）响应文本字符串包含模式断言
    2）响应结果相等断言
    3）响应结果不相等断言
    4）数据库断言

    """

    def contains_assert(self, value, response, headers):
        """ 字符串包含断言模式，断言预期结果的字符串是否包含在接口的响应信息中
        :param value: 预期结果，yaml文件的预期结果值
        :param response: 接口实际响应结果
        :param headers: 响应头信息
        :return: 返回结果的状态标识
        """
        flag = 0
        headers = headers or {}

        def _lookup_header(header_key):
            # 大小写不敏感地在 headers 里找某个键
            header_value = None
            try:
                if isinstance(headers, dict) and header_key in headers:
                    header_value = headers[header_key]
                elif hasattr(headers, 'get'):
                    header_value = headers.get(header_key)
                    if header_value is None:
                        header_value = headers.get(str(header_key).lower())
                        if header_value is None:
                            header_value = headers.get(str(header_key).upper())
            except Exception:
                header_value = None
            if header_value is None and isinstance(headers, dict):
                for h_key, h_value in headers.items():
                    if str(h_key).lower() == str(header_key).lower():
                        header_value = h_value
                        break
            return header_value

        for assert_key, assert_value in value.items():
            resp_list = []
            if isinstance(response, (dict, list)):
                # 在整个 JSON 树找同名 key
                jsonpath_result = jsonpath.jsonpath(response, "$..%s" % assert_key)
                if jsonpath_result and isinstance(jsonpath_result, list):
                    resp_list = jsonpath_result
            if not resp_list:
                header_value = _lookup_header(assert_key)
                if header_value is not None:
                    resp_list = [header_value]

            if resp_list:
                target = resp_list[0] if len(resp_list) == 1 else resp_list
                if isinstance(target, list) and target and isinstance(target[0], str):
                    target = ''.join(target)
                expected = None if (isinstance(assert_value, str) and assert_value.upper() == 'NONE') else assert_value
                if isinstance(target, (list, tuple, set)):
                    match = expected in target
                else:
                    match = str(expected) in str(target)
                if not match:
                    flag += 1
                    allure.attach(f"预期包含：{expected}\n实际：{target}", '包含断言：失败',
                                  attachment_type=allure.attachment_type.TEXT)
                    logs.error(f"包含断言失败：预期包含【{expected}】，实际【{target}】")
            else:
                flag += 1
                allure.attach(f"未找到断言目标键：{assert_key}", '包含断言：失败',
                              attachment_type=allure.attachment_type.TEXT)
                logs.error(f"包含断言失败：未找到键【{assert_key}】")
        return flag

    def equal_assert(self, expected_results, actual_results):
        """
        相等断言模式
        :param expected_results: 预期结果，yaml文件validation值
        :param actual_results: 接口实际响应结果
        :return:
        """
        flag = 0
        if isinstance(actual_results, dict) and isinstance(expected_results, dict):
            # 找出实际结果与预期结果共同的key
            common_keys = list(expected_results.keys() & actual_results.keys())[0]
            # 根据相同的key去实际结果中获取，并重新生成一个实际结果的字典
            new_actual_results = {common_keys: actual_results[common_keys]}
            eq_assert = operator.eq(new_actual_results, expected_results)
            if eq_assert:
                logs.info(f"相等断言成功：接口实际结果：{new_actual_results}，等于预期结果：" + str(expected_results))
                allure.attach(f"预期结果：{str(expected_results)}\n实际结果：{new_actual_results}", '相等断言结果：成功',
                              attachment_type=allure.attachment_type.TEXT)
            else:
                flag += 1
                logs.error(f"相等断言失败：接口实际结果{new_actual_results}，不等于预期结果：" + str(expected_results))
                allure.attach(f"预期结果：{str(expected_results)}\n实际结果：{new_actual_results}", '相等断言结果：失败',
                              attachment_type=allure.attachment_type.TEXT)
        else:
            raise TypeError('相等断言--类型错误，预期结果和接口实际响应结果必须为字典类型！')
        return flag

    def not_equal_assert(self, expected_results, actual_results, statuc_code=None):
        """
        不相等断言模式
        :param expected_results: 预期结果，yaml文件validation值
        :param actual_results: 接口实际响应结果
        :return:
        """
        flag = 0
        if isinstance(actual_results, dict) and isinstance(expected_results, dict):
            # 找出实际结果与预期结果共同的key
            common_keys = list(expected_results.keys() & actual_results.keys())[0]
            # 根据相同的key去实际结果中获取，并重新生成一个实际结果的字典
            new_actual_results = {common_keys: actual_results[common_keys]}
            eq_assert = operator.ne(new_actual_results, expected_results)
            if eq_assert:
                logs.info(f"不相等断言成功：接口实际结果：{new_actual_results}，不等于预期结果：" + str(expected_results))
                allure.attach(f"预期结果：{str(expected_results)}\n实际结果：{new_actual_results}", '不相等断言结果：成功',
                              attachment_type=allure.attachment_type.TEXT)
            else:
                flag += 1
                logs.error(f"不相等断言失败：接口实际结果{new_actual_results}，等于预期结果：" + str(expected_results))
                allure.attach(f"预期结果：{str(expected_results)}\n实际结果：{new_actual_results}", '不相等断言结果：失败',
                              attachment_type=allure.attachment_type.TEXT)
        else:
            raise TypeError('不相等断言--类型错误，预期结果和接口实际响应结果必须为字典类型！')
        return flag

    def assert_mysql_data(self, expected_results):
        """
        数据库断言
        :param expected_results: 预期结果，yaml文件的SQL语句
        :return: 返回flag标识，0表示正常，非0表示测试不通过
        """
        flag = 0
        conn = ConnectMysql()
        db_value = conn.query_all(expected_results)
        if db_value is not None:
            logs.info("数据库断言成功")
        else:
            flag += 1
            logs.error("数据库断言失败，请检查数据库是否存在该数据！")
        return flag

    def assert_result(self, expected, response, headers=None):
        """
        断言，通过断言all_flag标记，all_flag==0表示测试通过，否则为失败
        :param expected: 预期结果
        :param response: 实际响应结果
        :param status_code: 响应实际code码
        :param headers: 响应头信息
        :return:
        """
        all_flag = 0
        try:
            logs.info("yaml文件预期结果：%s" % expected)
            # logs.info("实际结果：%s" % response)
            # all_flag = 0
            for yq in expected:
                for key, value in yq.items():
                    if key == "contains":
                        flag = self.contains_assert(value, response, headers=headers)
                        all_flag += flag
                    elif key == "eq":
                        flag = self.equal_assert(value, response)
                        all_flag += flag
                    elif key == 'ne':
                        flag = self.not_equal_assert(value, response)
                        all_flag += flag
                    elif key == 'db':
                        flag = self.assert_mysql_data(value)
                        all_flag += flag
                    else:
                        logs.error("不支持此种断言方式")

        except Exception as exceptions:
            logs.error('接口断言异常，请检查yaml预期结果值是否正确填写!')
            raise exceptions

        if all_flag == 0:
            logs.info("测试成功")
            assert True
        else:
            logs.error("测试失败")
            assert False
