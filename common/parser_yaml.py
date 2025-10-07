import yaml
import traceback
import os
from copy import deepcopy

from common.log_util import logs
from conf.config_util import OperationConfig
from conf.setting import FILE_PATH
from yaml.scanner import ScannerError

try:
    _REQUEST_METHOD_CANDIDATES = OperationConfig().get_request_methods()
except Exception:
    logs.error('加载REQUEST_METHODS配置失败，使用默认请求方式集合')
    _REQUEST_METHOD_CANDIDATES = ['GET', 'POST', 'DELETE', 'PUT', 'TRACE']


def _expand_missing_field_cases(test_case):
    """根据missing_fields配置生成多条缺失字段的用例"""

    case_copy = deepcopy(test_case)
    missing_fields = case_copy.pop('missing_fields', None)
    if not missing_fields:
        return [case_copy]

    if not isinstance(missing_fields, list):
        missing_fields = [missing_fields]

    payload_keys = ['data', 'json', 'params']
    expanded_cases = []

    for item in missing_fields:
        field_name = None
        mode = 'remove'
        value = None
        container = None

        if isinstance(item, dict):
            field_name = item.get('field')
            mode = item.get('mode', mode)
            value = item.get('value')
            container = item.get('container') or item.get('target')
            label = item.get('label')
        else:
            field_name = item
            label = None

        if not field_name:
            logs.error('missing_fields配置中缺少field，请检查yaml文件！')
            continue

        variant = deepcopy(case_copy)
        case_name = variant.get('case_name', '')
        field_label = str(label or field_name)
        if '{field}' in case_name:
            variant['case_name'] = case_name.replace('{field}', field_label)
        else:
            variant['case_name'] = f"{case_name}[{field_label}]" if case_name else field_label

        payload_key = container
        if payload_key is None:
            for key in payload_keys:
                if key in variant:
                    payload_key = key
                    break

        if payload_key is None:
            payload_key = 'data'

        payload_data = deepcopy(variant.get(payload_key, {})) if isinstance(variant.get(payload_key), dict) else {}

        if mode == 'empty':
            payload_data[field_name] = '' if value is None else value
        elif mode == 'null':
            payload_data[field_name] = None
        elif value is not None:
            payload_data[field_name] = value
        else:
            payload_data.pop(field_name, None)

        variant[payload_key] = payload_data
        expanded_cases.append(variant)

    return expanded_cases or [case_copy]


def _expand_method_cases(test_case):
    """根据support字段自动生成不支持请求方式的用例"""

    case_copy = deepcopy(test_case)
    support_value = case_copy.pop('support', None)
    if support_value is None:
        return [case_copy]

    if isinstance(support_value, str):
        support_methods = {support_value.strip().upper()} if support_value.strip() else set()
    elif isinstance(support_value, (list, tuple, set)):
        support_methods = {str(item).strip().upper() for item in support_value if str(item).strip()}
    else:
        logs.error('support字段仅支持字符串或列表，请检查yaml文件！')
        support_methods = set()

    supported = support_methods or set()
    method_pool = [method for method in _REQUEST_METHOD_CANDIDATES if method]
    unsupported_methods = [method for method in method_pool if method not in supported]

    results = [case_copy]
    base_name = case_copy.get('case_name', '')

    for method in unsupported_methods:
        variant = deepcopy(case_copy)
        variant.pop('extract', None)
        variant.pop('extract_list', None)
        variant['method'] = method
        if method.upper() in {'GET', 'DELETE'} and 'params' not in variant:
            for payload_key in ('json', 'data'):
                payload_value = variant.get(payload_key)
                if isinstance(payload_value, dict):
                    variant['params'] = deepcopy(payload_value)
                    variant.pop(payload_key, None)
                    break
        label = f"{base_name}-不支持的请求方式[{method}]" if base_name else f"不支持的请求方式[{method}]"
        variant['case_name'] = label
        variant['validation'] = [{'contains': {'status_code': 405}}]
        results.append(variant)

    return results


def get_testcase_yaml(file):
    testcase_list = []
    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if not data:
                return testcase_list

            if len(data) <= 1:
                yam_data = data[0]
                base_info = deepcopy(yam_data.get('baseInfo', {}))
                for ts in yam_data.get('testCase', []):
                    for expanded in _expand_missing_field_cases(ts):
                        for case_variant in _expand_method_cases(expanded):
                            testcase_list.append([deepcopy(base_info), case_variant])
                return testcase_list

            result = []
            for block in data:
                base_info = deepcopy(block.get('baseInfo', {}))
                cases = []
                for ts in block.get('testCase', []):
                    for expanded in _expand_missing_field_cases(ts):
                        cases.extend(_expand_method_cases(expanded))
                result.append({'baseInfo': base_info, 'testCase': cases})
            return result
    except UnicodeDecodeError:
        logs.error(f"[{file}]文件编码格式错误，--尝试使用utf-8编码解码YAML文件时发生了错误，请确保你的yaml文件是UTF-8格式！")
    except FileNotFoundError:
        logs.error(f'[{file}]文件未找到，请检查路径是否正确')
    except Exception as e:
        logs.error(f'获取【{file}】文件数据时出现未知错误: {str(e)}')


class YmalParser:
    """读写接口的YAML格式测试数据"""

    def __init__(self, yaml_file=None):
        if yaml_file is not None:
            self.yaml_file = yaml_file
        else:
            pass
        self.conf = OperationConfig()
        self.yaml_data = None

    @property
    def get_yaml_data(self):
        """
        获取测试用例yaml数据
        :param file: YAML文件
        :return: 返回list
        """
        # Loader=yaml.FullLoader表示加载完整的YAML语言，避免任意代码执行，无此参数控制台报Warning
        try:
            with open(self.yaml_file, 'r', encoding='utf-8') as f:
                self.yaml_data = yaml.safe_load(f)
                return self.yaml_data
        except Exception:
            logs.error(str(traceback.format_exc()))

    def write_yaml_data(self, value):
        """
        写入数据需为dict，allow_unicode=True表示写入中文，sort_keys按顺序写入
        写入YAML文件数据,主要用于接口关联
        :param value: 写入数据，必须用dict
        :return:
        """

        file = None
        file_path = FILE_PATH['EXTRACT']
        if not os.path.exists(file_path):
            os.system(file_path)
        try:
            file = open(file_path, 'a', encoding='utf-8')
            if isinstance(value, dict):
                write_data = yaml.dump(value, allow_unicode=True, sort_keys=False)
                file.write(write_data)
            else:
                logs.info('写入[extract.yaml]的数据必须为dict格式')
        except Exception:
            logs.error(str(traceback.format_exc()))
        finally:
            file.close()

    def clear_yaml_data(self):
        """
        清空extract.yaml文件数据
        :param filename: yaml文件名
        :return:
        """
        with open(FILE_PATH['EXTRACT'], 'w') as f:
            f.truncate()

    def get_extract_yaml(self, node_name, second_node_name=None):
        """
        用于读取接口提取的变量值
        :param node_name:
        :return:
        """
        if os.path.exists(FILE_PATH['EXTRACT']):
            pass
        else:
            logs.error('extract.yaml不存在')
            file = open(FILE_PATH['EXTRACT'], 'w')
            file.close()
            logs.info('extract.yaml创建成功！')
        try:
            with open(FILE_PATH['EXTRACT'], 'r', encoding='utf-8') as rf:
                ext_data = yaml.safe_load(rf)
                if second_node_name is None:
                    return ext_data[node_name]
                else:
                    return ext_data[node_name][second_node_name]
        except Exception as e:
            logs.error(f"【extract.yaml】没有找到：{node_name},--%s" % e)

    def get_testCase_baseInfo(self, case_info):
        """
        获取testcase yaml文件的baseInfo数据
        :param case_info: yaml数据，dict类型
        :return:
        """
        pass

    def get_method(self):
        """
        :param self:
        :return:
        """
        yal_data = self.get_yaml_data()
        metd = yal_data[0].get('method')
        return metd

    def get_request_params(self):
        """
        获取yaml测试数据中的请求参数
        :return:
        """
        data_list = []
        yaml_data = self.get_yaml_data()
        del yaml_data[0]
        for da in yaml_data:
            data_list.append(da)
        return data_list
