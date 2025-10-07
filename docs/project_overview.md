# EasyShop 项目结构与关键机制说明

## 版本同步说明
当前 `work` 分支未配置任何远程仓库，因此无法执行 `git pull`。如需获取最新代码，请先通过 `git remote add` 配置上游地址，再执行同步命令。

## 目录结构与文件职责
下表按目录列出了项目的主要内容，并在需要时标注“（可选）”以说明该功能在现有用例中未覆盖或依赖外部服务。

### 根目录
- `run.py`：测试入口脚本，依据 `conf/setting.py` 中的 `REPORT_TYPE` 决定运行 Allure 还是 TMReport，触发 `pytest` 执行并生成报告，同时在生成 Allure 报告时复制 `environment.xml` 并调用 `allure serve` 打开临时服务。【F:run.py†L1-L18】
- `conftest.py`：Pytest 会话级钩子与夹具，负责清空 `extract.yaml`、删除旧的 Allure 结果文件、统计执行摘要并按需发送邮件报告。【F:conftest.py†L1-L113】
- `pytest.ini`：Pytest 配置文件，约束文件/类/函数的发现规则，并设定告警处理策略。【F:pytest.ini†L1-L12】
- `environment.xml`：在报告中展示测试环境参数的 XML 描述文件，会在执行后被复制到 Allure 结果目录。【F:environment.xml†L1-L26】
- `extract.yaml`：存放接口间参数关联（提取数据与 Cookie）的共享存储，在每次测试前会被清空。【F:extract.yaml†L1-L18】【F:conftest.py†L17-L22】
- `requirements.txt`：Python 依赖声明。

### `base/`
- `api_util.py`：针对“单接口多用例”场景的执行器，负责读取 YAML 测试数据、拼接请求、调用 `SendRequest` 发送请求、处理提取与断言并输出 Allure 附件。【F:base/api_util.py†L1-L183】
- `api_util_list.py`：面向“业务流/多个 baseInfo 一次执行”场景的执行器，与 `api_util.py` 类似但支持批量 `testCase` 处理，广泛用于冒烟场景。【F:base/api_util_list.py†L1-L194】
- `generate_id.py`：生成测试模块与用例编号，以保证 Allure 报告的展示顺序。【F:base/generate_id.py†L1-L22】
- `remove_file.py`：删除指定后缀文件或整个目录，供日志与报告清理使用。【F:base/remove_file.py†L1-L33】

### `common/`
- `assertions.py`：封装多种断言方式（包含、相等、不相等、任意值、数据库（可选）），集中管理断言失败时的日志与 Allure 附件。【F:common/assertions.py†L1-L213】
- `requests_util.py`：HTTP 请求发送核心封装，整合 Session 重试策略、请求/响应日志、Allure 附件、文件上传与 Cookie 提取功能。【F:common/requests_util.py†L1-L210】
- `parser_yaml.py`：YAML 读写工具，支持根据 `missing_fields` / `support` 生成缺失字段和不支持请求方式的派生用例，同时提供写入 `extract.yaml` 的能力。【F:common/parser_yaml.py†L1-L229】
- `extract_util.py`：数据提取工具，读取 `extract.yaml`、组合随机/顺序数据、生成时间戳、读取 CSV 辅助数据等。【F:common/extract_util.py†L1-L63】
- `log_util.py`：日志模块，配置日志目录、滚动文件与控制台输出，并在初始化时执行过期日志清理。【F:common/log_util.py†L1-L57】
- `email_util.py`（可选）：按照配置发送带附件的测试总结邮件，默认使用 SMTP/SSL 或 STARTTLS。【F:common/email_util.py†L1-L92】
- `jenkins_util.py`（可选）：封装 Jenkins API 调用，用于读取构建信息与报告统计。【F:common/jenkins_util.py†L1-L74】
- `connection.py`（可选）：提供 MySQL、Redis、ClickHouse、MongoDB、SSH 等外部资源的连接封装，便于在测试或清理阶段使用数据库/消息服务。【F:common/connection.py†L1-L213】
- `parser_csv.py`（可选）：使用 Pandas 读取 CSV 数据列，用于数据驱动场景。【F:common/parser_csv.py†L1-L17】
- `parser_xml.py`（可选）：读取 XML 标签及属性，辅助需要 XML 配置的测试。【F:common/parser_xml.py†L1-L40】
- `two_dimension_data.py`（可选）：把二维列表渲染为表格字符串，通常用于命令行展示数据库查询结果。【F:common/two_dimension_data.py†L1-L53】

### `conf/`
- `setting.py`：全局设置（日志级别、接口超时时间、报告类型、各类文件路径等）。【F:conf/setting.py†L1-L33】
- `config.ini`：项目环境配置，包含接口地址、数据库、Redis、邮件、Jenkins、报告类型与请求方式候选集合等参数。【F:conf/config.ini†L1-L39】
- `config_util.py`：INI 配置读写工具，便于获取不同 Section 的设置并解析请求方式候选值。【F:conf/config_util.py†L1-L63】

### `data/`
- `loginName.yaml`：登录接口的基线用例，供 `testcase/conftest.py` 在会话前置登录使用。【F:data/loginName.yaml†L1-L17】
- `login_data.csv`（可选）：示例登录数据文件，可配合 `extract_util` 或自定义脚本使用。【F:data/login_data.csv†L1-L3】

### `report/`
- `temp/`：Allure 原始结果输出目录，运行 `pytest` 时生成 JSON/附件，并由 `run.py` 传递给 `allure serve`。
- `allureReport/`：历史导出的静态 Allure 报告（`index.html`、`data/` 等），可直接在浏览器中查看。
- `tmreport/`（可选）：当切换到 TMReport 模式时生成的 HTML 报告存放目录。
- `results.xml`：`--junitxml` 生成的 JUnit 报告快照。

### `testcase/`
- `conftest.py`：测试集夹具，包含统一的日志起止标记、登录前置（调用 `loginName.yaml`）以及数据库清理示例（当前留空）。【F:testcase/conftest.py†L1-L33】
- `ProductManager/`：商品与订单相关的接口 YAML 与测试脚本。
  - `test_product.py`：四个单接口用例，按顺序执行列表、详情、下单、支付流程。【F:testcase/ProductManager/test_product.py†L1-L30】
  - `getProductList.yaml`：商品列表接口用例，演示 `support` 请求方式与列表提取数据。【F:testcase/ProductManager/getProductList.yaml†L1-L15】
  - `productDetail.yaml`：商品详情接口用例，使用 `extract` 到的商品 ID。【F:testcase/ProductManager/productDetail.yaml†L1-L15】
  - `commitOrder.yaml`：提交订单用例，提取订单号和用户 ID，为后续支付使用。【F:testcase/ProductManager/commitOrder.yaml†L1-L19】
  - `orderPay.yaml`：订单支付用例，调用 `timestamp()` 生成时间戳。【F:testcase/ProductManager/orderPay.yaml†L1-L15】
- `UserManager/`：用户管理接口 YAML 与测试脚本。
  - `test_user.py`：四个单接口用例，涵盖新增/修改/删除/查询流程。【F:testcase/UserManager/test_user.py†L1-L31】
  - `addUser.yaml`：新增用户场景及缺失字段派生用例示例。【F:testcase/UserManager/addUser.yaml†L1-L30】
  - `updateUser.yaml`：修改用户场景与缺失字段用例。【F:testcase/UserManager/updateUser.yaml†L1-L27】
  - `deleteUser.yaml`：删除用户场景与异常分支。【F:testcase/UserManager/deleteUser.yaml†L1-L23】
  - `queryUser.yaml`：查询用户场景，演示 `missing_fields` 多模式派生与 `support` 中声明支持 GET/POST，但派生器会自动生成不支持方式的用例。【F:testcase/UserManager/queryUser.yaml†L1-L24】
- `SmokeTest/`：业务流冒烟测试。
  - `test_business_scenario.py`：调用 `base/api_util_list.py` 执行整条业务链条。【F:testcase/SmokeTest/test_business_scenario.py†L1-L16】
  - `BusinessScenario.yml`：冒烟链路各环节的 YAML 配置，串联列表、详情、下单、支付与状态校验。【F:testcase/SmokeTest/BusinessScenario.yml†L1-L49】

### `base/` 与 `testcase/` 交互
- 测试脚本通过 `get_testcase_yaml` 读取 YAML，结合 `RequestBase.specification_yaml` 或 `RequestBase.handler_yaml_list` 发送请求。
- 所有接口执行都会把提取到的数据写入 `extract.yaml`，供后续用例复用。

## 日志体系说明
1. **初始化与目录创建**：`common/log_util.py` 在模块导入时读取 `conf/setting.py` 的日志目录配置，若不存在则创建目录并以 `test.<日期>.log` 命名日志文件。【F:common/log_util.py†L1-L18】
2. **过期日志清理**：`LogUtil.handle_overdue_log()` 会在实例化时执行，删除 30 天前创建的日志文件，实现简单的定期清理机制。【F:common/log_util.py†L20-L36】
3. **日志记录**：`output_logging()` 配置 `RotatingFileHandler`（大小 5MB，最多 7 个备份）和控制台 `StreamHandler`，设置统一格式与日志级别，最终暴露 `logs` 供全局引用。【F:common/log_util.py†L37-L57】
4. **写日志方式**：业务代码导入 `logs` 后直接调用 `logs.info()/error()` 等方法即可写入。所有封装（请求、断言、fixture 等）均使用此日志器。

## Allure 报告机制
1. **配置入口**：`conf/setting.py` 的 `REPORT_TYPE` 默认为 `allure`，`run.py` 依据此值调用 `pytest.main`，带上 `--alluredir=./report/temp` 与 `--clean-alluredir` 参数生成 Allure 原始结果，并输出一份 `results.xml`。【F:conf/setting.py†L17-L25】【F:run.py†L6-L12】
2. **环境信息**：执行完成后把根目录下的 `environment.xml` 复制到 `report/temp`，供 Allure 显示环境标签。【F:run.py†L13-L14】
3. **报告生成**：`run.py` 在命令结束后调用 `allure serve ./report/temp` 启动临时服务实时查看报告。若需持久化，可通过 Allure 的 `generate` 命令输出到 `report/allureReport`，项目中已保留一份静态资源目录以供参考。
4. **目录角色**：
   - `report/temp/`：存放最新一次运行产生的 JSON、附件与环境文件，是 `allure serve` 的输入目录。
   - `report/allureReport/`：静态报告输出目录，包含 `index.html`、`data/`、`history/` 等资源，可离线浏览。
5. **旧报告清理**：
   - `pytest` 启动参数 `--clean-alluredir` 会在每次执行前自动清空 `report/temp`。
   - 会话级夹具 `clear_extract()` 进一步调用 `base/remove_file.remove_file`，删除 `report/temp` 中残留的 JSON/TXT/附件/`properties` 文件，确保结果目录干净。【F:conftest.py†L13-L22】【F:base/remove_file.py†L1-L26】
   - 若生成静态报告到 `report/allureReport/`，需要手动清理或覆盖；当前脚本不会自动删除历史静态文件。

## 运行时流程概览
1. 会话开始时，`testcase/conftest.py` 触发登录接口以准备共享 token，并打印日志分隔符。【F:testcase/conftest.py†L8-L26】
2. `extract.yaml` 被清空，随后每个用例在执行后写入新提取数据。【F:conftest.py†L17-L22】【F:common/parser_yaml.py†L152-L181】
3. 测试执行过程中，`common/requests_util.py` 负责发送请求、记录日志、附加 Allure 附件并捕获异常。【F:common/requests_util.py†L1-L210】
4. 用例完成后，`pytest_terminal_summary` 汇总结果并根据配置决定是否发送邮件，附件会在发送后自动删除（若存在）。【F:conftest.py†L62-L110】

以上内容覆盖了项目结构、日志体系与 Allure 报告生成的核心逻辑，可作为理解与维护 EasyShop 接口自动化平台的参考资料。
