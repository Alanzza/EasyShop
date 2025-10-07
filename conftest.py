# -*- coding: utf-8 -*-
import datetime
import os
import shutil
import time
import warnings
from pathlib import Path
from typing import Optional

import pytest

from base.removefile import remove_file
from common.parser_yaml import ReadYamlData
from common.recordlog import logs
from common.sendmail import SendEmail
from conf import setting
from conf.operationConfig import OperationConfig

yfd = ReadYamlData()
config_reader = OperationConfig()


@pytest.fixture(scope="session", autouse=True)
def clear_extract():
    # 禁用HTTPS告警，ResourceWarning
    warnings.simplefilter('ignore', ResourceWarning)

    yfd.clear_yaml_data()
    remove_file("./report/temp", ['json', 'txt', 'attach', 'properties'])


# === 在会话开始时记录时间 ===
def pytest_sessionstart(session):
    session.config._custom_session_start_time = time.time()


def _parse_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _format_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    duration = datetime.timedelta(seconds=round(seconds))
    return str(duration)


def _get_session_start_time(terminalreporter):
    return (
        getattr(terminalreporter, "_sessionstarttime", None)
        or getattr(terminalreporter, "_session_start_time", None)
        or getattr(terminalreporter.config, "_custom_session_start_time", None)
    )


def _collect_report_nodeids(reports):
    node_ids = []
    for report in reports:
        node_id = getattr(report, "nodeid", "")
        if node_id:
            node_ids.append(node_id)
    return node_ids


def generate_test_summary(terminalreporter):
    """生成测试结果摘要字符串"""
    total = terminalreporter._numcollected
    passed_reports = terminalreporter.stats.get('passed', [])
    failed_reports = terminalreporter.stats.get('failed', [])
    error_reports = terminalreporter.stats.get('error', [])
    skipped_reports = terminalreporter.stats.get('skipped', [])

    start_time = _get_session_start_time(terminalreporter)
    duration_seconds = time.time() - start_time if start_time else 0.0
    duration = _format_duration(duration_seconds)

    summary_lines = [
        "自动化测试结果 (请着重关注测试失败的接口)：",
        f"测试用例总数：{total}",
        f"测试通过数：{len(passed_reports)}",
        f"测试失败数：{len(failed_reports)}",
        f"错误数量：{len(error_reports)}",
        f"跳过执行数量：{len(skipped_reports)}",
        f"执行总时长：{duration}",
    ]
    summary = "\n".join(summary_lines)
    print(summary)

    details = [summary, ""]
    for title, reports in (
        ("失败用例", failed_reports),
        ("错误用例", error_reports),
        ("跳过用例", skipped_reports),
    ):
        nodes = _collect_report_nodeids(reports)
        if nodes:
            details.append(f"{title}:")
            details.extend([f"- {node}" for node in nodes])
            details.append("")

    detail_text = "\n".join(line for line in details if line is not None)
    return detail_text.strip()


def _should_send_email() -> bool:
    return _parse_bool(config_reader.get_section_for_data('EMAIL', 'enable'))


def _build_report_attachment() -> Optional[str]:
    if setting.REPORT_TYPE == 'allure':
        allure_dir = Path(setting.FILE_PATH['TEMP'])
        if not allure_dir.exists() or not any(allure_dir.iterdir()):
            return None
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_base = allure_dir.parent / f"{allure_dir.name}_{timestamp}"
        archive_path = shutil.make_archive(str(archive_base), 'zip', allure_dir)
        return archive_path
    if setting.REPORT_TYPE == 'tm':
        report_file = Path(setting.FILE_PATH['TMR']) / 'testReport.html'
        if report_file.exists():
            return str(report_file)
    return None


def _send_summary_email(summary: str):
    if not _should_send_email():
        return

    attachment = _build_report_attachment()
    attachments = [attachment] if attachment else None
    subject = config_reader.get_section_for_data('EMAIL', 'subject') or '接口自动化测试报告'

    try:
        sender = SendEmail()
        sender.build_content(subject, summary, atta_file=attachments)
    except Exception as exc:  # pragma: no cover - 不影响测试用例执行
        logs.error('发送测试报告邮件失败: %s', exc, exc_info=True)
    finally:
        if attachment and attachment.endswith('.zip') and os.path.exists(attachment):
            try:
                os.remove(attachment)
            except OSError:
                logs.warning('临时报告压缩包删除失败: %s', attachment)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """自动收集pytest框架执行的测试结果并打印摘要信息"""
    summary = generate_test_summary(terminalreporter)
    _send_summary_email(summary)
