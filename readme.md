# EasyShop 自动化接口测试项目

### 项目简介
- EasyShop 是一个针对购物网站接口的 Python 自动化测试项目，采用 Pytest 作为测试框架，Allure 作为报告工具。
- 项目支持单接口多用例和业务流测试，具备数据提取、断言封装、日志管理、邮件通知等功能。
- 支持自动生成反例用例功能，能够针对“必填字段缺失”与“非法请求方法”两类场景自动构造测试，节省测试用例设计与维护的时间成本。

### 项目运行与配置文件信息
- `run.py`：测试入口脚本，依据 `conf/setting.py` 中的 `REPORT_TYPE` 决定运行 Allure 或 TMReport，触发 `pytest` 执行并生成报告，同时在生成 Allure 报告时复制 `environment.xml` 并调用 `allure serve` 打开临时服务。
- `conftest.py`：Pytest 会话级钩子与夹具，负责清空 `extract.yaml`、删除旧的 Allure 结果文件、统计执行摘要并按需发送邮件报告。
- `pytest.ini`：Pytest 配置文件，约束文件/类/函数的发现规则，并设定告警处理策略。
- `environment.xml`：在报告中展示测试环境参数的 XML 描述文件，会在执行后被复制到 Allure 结果目录。
- `extract.yaml`：存放接口间参数关联（提取数据与 Cookie）的共享存储，在每次测试前会被清空。
- `requirements.txt`：Python 依赖包声明。

