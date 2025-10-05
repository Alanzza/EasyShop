# -*- coding: utf-8 -*-
import time

import pytest

from common.parser_yaml import ReadYamlData
from base.removefile import remove_file
from common.dingRobot import send_dd_msg
from conf.setting import dd_msg

import warnings

yfd = ReadYamlData()


@pytest.fixture(scope="session", autouse=True)
def clear_extract():
    # 禁用HTTPS告警，ResourceWarning
    warnings.simplefilter('ignore', ResourceWarning)

    yfd.clear_yaml_data()
    remove_file("./report/temp", ['json', 'txt', 'attach', 'properties'])


# === 在会话开始时记录时间 ===
def pytest_sessionstart(session):
    session.config._custom_session_start_time = time.time()


def generate_test_summary(terminalreporter):
    """生成测试结果摘要字符串"""
    total = terminalreporter._numcollected
    passed = len(terminalreporter.stats.get('passed', []))
    failed = len(terminalreporter.stats.get('failed', []))
    error = len(terminalreporter.stats.get('error', []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    # pytest 8 不支持terminalreporter._sessionstarttime
    # duration = time.time() - terminalreporter._sessionstarttime

    start_time = (
            getattr(terminalreporter, "_sessionstarttime", None)
            or getattr(terminalreporter, "_session_start_time", None)
            or getattr(terminalreporter.config, "_custom_session_start_time", None)
    )
    if start_time:
        duration = time.time() - start_time
    else:
        duration = 0.0

    summary = f"""
    自动化测试结果 (请着重关注测试失败的接口)：
    测试用例总数：{total}
    测试通过数：{passed}
    测试失败数：{failed}
    错误数量：{error}
    跳过执行数量：{skipped}
    执行总时长：{duration}
    """
    print(summary)
    return summary


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """自动收集pytest框架执行的测试结果并打印摘要信息"""
    summary = generate_test_summary(terminalreporter)
    if dd_msg:
        send_dd_msg(summary)
