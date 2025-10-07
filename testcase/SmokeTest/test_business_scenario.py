import allure
import pytest

from common.parser_yaml import get_testcase_yaml
from base.api_util_list import RequestBase
from base.generate_id import m_id, c_id


# 这里调用apiutil_list一次处理多个base_info+test_case

@allure.feature(next(m_id) + '冒烟测试（业务场景）')
class TestEBusinessScenario:

    @allure.story(next(c_id) + '商品列表到下单支付流程')
    @pytest.mark.parametrize('case_info', get_testcase_yaml('./testcase/SmokeTest/BusinessScenario.yml'))
    def test_business_scenario(self, case_info):
        allure.dynamic.title(case_info['baseInfo']['api_name'])
        RequestBase().specification_yaml(case_info)
