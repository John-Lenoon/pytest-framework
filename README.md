# mall-swarm Pytest API 自动化测试框架

> **开源与来源声明**
>
> 本项目是面向 [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm)
> 的独立 Pytest 接口自动化测试框架。被测系统的业务设计、接口路径、初始化数据及
> 商标等权利归上游项目及其作者所有，使用时请遵守上游仓库中的许可证和声明文件。
> 本仓库只包含测试代码、框架组件、测试数据、Mock Server 和 CI 配置，
> **不包含 mall-swarm 后端源码，也不是上游官方仓库或官方测试套件**。

本项目用于对 mall-swarm 微服务电商后端进行接口回归、业务链路验证和数据库双重校验。
框架同时提供不依赖真实后端的离线自测，新读者可先在几分钟内验证项目是否可运行。

## 项目亮点

- 真实 API 回归：登录认证、商品、搜索、购物车、订单及跨接口业务链路。
- 双运行模式：`framework_tests/` 离线验证框架，`tests/` 访问真实 mall-swarm。
- YAML 场景编排：Pydantic 严格校验、变量渲染、JSONPath 提取和跨步骤上下文传递。
- 通用断言：`eq`、`rv`、`contains`、`regex`、`exists`、`db_eq` 等。
- 数据库校验：SQLAlchemy + PyMySQL，仅允许单条只读 SQL，可比对 API 和 MySQL 数据。
- 测试工程化：fixture 分层、参数化、marker 分组、xdist 并行、Ruff 静态检查。
- 可观测性：Allure 请求/响应附件与敏感字段脱敏，pytest-html 单文件报告。
- CI/CD：GitHub Actions、Jenkins、JUnit/Allure 产物和可选钉钉通知。
- 数据隔离：尽量遵循“自建、自校验、自清理”，不对写请求自动重试。

## 被测后端基线

本 README 按当前被测后端项目文档整理。该代码在上游 mall-swarm 基础上做过版本升级和
认证改造，因此与上游仓库其他分支可能存在差异：

| 类别 | 当前基线 |
| --- | --- |
| Java | 17 |
| Spring Boot | 3.5.14 |
| Spring Cloud | 2025.0.2 |
| Spring Cloud Alibaba | 2025.0.0.0 |
| 认证授权 | Sa-Token + JWT + Redis |
| 服务发现/配置 | Nacos |
| 数据与中间件 | MySQL、Redis、MongoDB、RabbitMQ、Elasticsearch、MinIO |

> 当前后端代码未启用 Sentinel 和 Seata，本测试项目也不将其列为运行前置条件。

### 服务与端口

| 模块 | 默认端口 | 职责 | 测试访问方式 |
| --- | ---: | --- | --- |
| `mall-gateway` | 8201 | 路由、鉴权、CORS、文档聚合 | 所有真实用例的唯一入口 |
| `mall-auth` | 8401 | 按 `clientId` 分发统一登录 | `/mall-auth/**` |
| `mall-admin` | 8080 | 商品、订单、营销、会员、RBAC | `/mall-admin/**` |
| `mall-portal` | 8085 | 首页、商品、购物车、下单、支付、会员 | `/mall-portal/**` |
| `mall-search` | 8081 | Elasticsearch 商品搜索 | `/mall-search/**` |
| `mall-demo` | 8082 | OpenFeign 调用演示 | 非核心测试目标 |
| `mall-monitor` | 8101 | Spring Boot Admin 监控 | 非业务 API |
| `mall-common` / `mall-mbg` | - | 公共库 / MyBatis Generator 代码 | 不是可启动服务 |

网关会移除服务名前缀后再转发。例如：

```text
GET http://localhost:8201/mall-portal/home/content
                              | StripPrefix=1
                              v
                        mall-portal:/home/content
```

## 快速开始：离线验证框架

此模式使用仓库内的 Flask Mock Server，不需要启动 mall-swarm、MySQL 或任何中间件。
建议使用 Python 3.11 或 3.12，以下命令均在本仓库根目录执行。

### Windows PowerShell

```powershell
py -3 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest framework_tests -m framework -n 2
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest framework_tests -m framework -n 2
```

离线自测通过只代表框架组件正常，不代表 mall-swarm 后端的业务接口已通过。

## 准备 mall-swarm 测试环境

### 1. 初始化后端与中间件

1. 按上游项目说明准备 Java 17、Maven、Nacos、MySQL、Redis、RabbitMQ、MongoDB、Elasticsearch 和 MinIO。
2. 导入 mall-swarm 后端仓库中的 `document/sql/mall.sql`，默认数据库名为 `mall`。
3. 在 Nacos 中导入或创建各服务的 `mall-xxx-dev.yaml`，使其指向当前测试环境。
4. 如需执行 ES 搜索用例，确保 Elasticsearch 已启动，并通过
   `POST /mall-search/esProduct/importAll` 初始化 `pms` 商品索引。

Nacos 中的远程配置优先级高于各服务本地 `application.yml`。修改数据库、Redis 或其他连接信息后未生效时，
应先检查 Nacos 中实际发布的配置，不要把真实密码写入本仓库。

### 2. 构建并启动后端

以下命令应在 **mall-swarm 后端仓库**根目录执行：

```bash
mvn package -DskipTests -Ddocker.skip=true
```

`-Ddocker.skip=true` 用于跳过上游 POM 中的 Docker 发布步骤，避免本地构建尝试连接上游作者的镜像服务。
可通过 IDE 运行各 `MallXxxApplication`，或在构建后执行：

```bash
java -jar mall-monitor/target/mall-monitor-1.0-SNAPSHOT.jar
java -jar mall-gateway/target/mall-gateway-1.0-SNAPSHOT.jar
java -jar mall-auth/target/mall-auth-1.0-SNAPSHOT.jar
java -jar mall-admin/target/mall-admin-1.0-SNAPSHOT.jar
java -jar mall-portal/target/mall-portal-1.0-SNAPSHOT.jar
java -jar mall-search/target/mall-search-1.0-SNAPSHOT.jar
```

建议启动顺序为 `monitor -> gateway -> auth -> admin -> portal -> search`。服务实际可任意顺序启动，
但 Nacos 和各业务中间件必须先就绪。

### 3. 检查环境

| 检查项 | 默认地址 |
| --- | --- |
| 网关健康状态 | `http://localhost:8201/actuator/health` |
| 网关聚合接口文档 | `http://localhost:8201/doc.html` |
| Nacos 控制台 | `http://localhost:8848/nacos` |
| mall-monitor | `http://localhost:8101` |

执行搜索、购物车或订单测试前，还应确认对应的 Elasticsearch、Redis、RabbitMQ 和数据库数据已就绪。

## 运行真实 API 测试

所有请求默认访问 `http://localhost:8201`，由 mall-gateway 转发。请不要把
`PYTEST_BASE_URL` 配置成 `mall-admin` 或 `mall-portal` 的裸端口，否则会绕过网关鉴权。

```bash
# 核心冒烟用例
python -m pytest tests -m smoke

# 按业务模块执行
python -m pytest tests -m login
python -m pytest tests -m product
python -m pytest tests -m search
python -m pytest tests -m cart
python -m pytest tests -m order

# 完整回归
python -m pytest tests

# 并行冒烟；共享账号的测试环境需先评估并发安全性
python -m pytest tests -m smoke -n auto
```

常用 marker：

| marker | 范围 |
| --- | --- |
| `smoke` | 每个模块的核心场景 |
| `login` / `permission` | 登录、Sa-Token 鉴权、401/403 |
| `product` / `search` | 商品查询和 ES 搜索 |
| `cart` / `order` | 购物车、下单、取消及清理 |
| `flow` | 跨接口业务链路 |
| `validation` / `boundary` | 参数校验和边界值 |
| `es` | 依赖 Elasticsearch 的用例 |
| `database` | API 与 MySQL 双重校验 |
| `framework` / `mock` | 离线框架能力验证 |

## 配置与密钥

默认配置位于 [`config/settings.yaml`](config/settings.yaml)，环境变量的优先级更高。
默认账号仅用于兼容 mall 初始化数据，CI 和共享环境应使用专用测试账号。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PYTEST_BASE_URL` | `http://localhost:8201` | mall-gateway 地址 |
| `PYTEST_TIMEOUT` | `15` | 单次请求超时（秒） |
| `PYTEST_RETRY` | `1` | 仅幂等读请求的连接重试次数 |
| `PYTEST_MEMBER_USERNAME` | `test` | 前台会员账号 |
| `PYTEST_MEMBER_PASSWORD` | `123456` | 前台会员密码 |
| `PYTEST_ADMIN_USERNAME` | `admin` | 后台管理员账号 |
| `PYTEST_ADMIN_PASSWORD` | `macro123` | 后台管理员密码 |
| `PYTEST_DB_ENABLED` | `false` | 是否启用 MySQL 校验 |
| `PYTEST_DB_HOST` / `PYTEST_DB_PORT` | `localhost` / `3306` | MySQL 地址 |
| `PYTEST_DB_USER` / `PYTEST_DB_PASSWORD` | `root` / 空 | MySQL 凭据 |
| `PYTEST_DB_NAME` | `mall` | 数据库名 |

PowerShell 示例：

```powershell
$env:PYTEST_BASE_URL = "http://192.168.1.20:8201"
$env:PYTEST_MEMBER_USERNAME = "ci_member"
$env:PYTEST_MEMBER_PASSWORD = Read-Host "请输入测试会员密码"
python -m pytest tests -m login
```

Linux / macOS 示例：

```bash
PYTEST_BASE_URL=http://192.168.1.20:8201 \
PYTEST_MEMBER_USERNAME=ci_member \
PYTEST_MEMBER_PASSWORD="$CI_MEMBER_PASSWORD" \
python -m pytest tests -m login
```

### 启用 MySQL 双重校验

```bash
PYTEST_DB_ENABLED=true \
PYTEST_DB_HOST=127.0.0.1 \
PYTEST_DB_USER=root \
PYTEST_DB_PASSWORD="$MYSQL_PASSWORD" \
PYTEST_DB_NAME=mall \
python -m pytest tests/test_yaml_scenarios.py -m database
```

数据库客户端只接受单条 `SELECT`、`SHOW`、`DESCRIBE` 或 `EXPLAIN`，不允许通过 YAML 执行写入语句。

## mall-swarm 接口约定

### 统一认证

推荐通过 mall-auth 登录：

```http
POST /mall-auth/auth/login?clientId=admin-app&username=admin&password=******
POST /mall-auth/auth/login?clientId=portal-app&username=test&password=******
```

登录成功后响应 `data` 中包含 `token` 和 `tokenHead`，其他需要登录的请求携带：

```http
Authorization: Bearer <token>
```

`admin-app` 和 `portal-app` 的登录态相互独立，token 不能混用。测试套件同时覆盖统一认证入口以及
`/mall-admin/admin/login`、`/mall-portal/sso/login` 兼容接口。

### 统一响应

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {}
}
```

`code` 是响应体中的业务码，不等同于 HTTP 状态码：

| 业务码 | 含义 |
| ---: | --- |
| 200 | 成功 |
| 401 | 未登录或 token 过期 |
| 403 | 无权限 |
| 404 | 参数校验失败，不代表接口路径不存在 |
| 500 | 业务或服务器异常 |

分页请求统一使用 `pageNum` 和 `pageSize`；分页响应 `data` 包含 `pageNum`、`pageSize`、
`totalPage`、`total` 和 `list`。

## YAML 场景编排

场景执行链路：

```text
YAML -> Pydantic 配置校验 -> 参数渲染 -> HTTP 请求 -> JSONPath 提取
     -> 上下文传递 -> 通用断言 -> 可选 MySQL 校验
```

真实场景示例见 [`cases/mall/login.yaml`](cases/mall/login.yaml)。可以绕过 pytest，直接从命令行执行：

```bash
python scripts/run_yaml.py cases/mall/login.yaml
python scripts/run_yaml.py cases/mall/login.yaml \
  --base-url http://192.168.1.20:8201 \
  --var member_username=ci_member
```

YAML 支持普通变量和动态值：

```yaml
path: /api/orders/${order_id}
json:
  quantity: ${quantity}
  requestNo: ${{uuid}}
  timestamp: ${{timestamp}}
```

完整的“登录 -> 下单 -> 支付 -> 物流”变量传递示例位于
[`framework_tests/cases/mock_business_flow.yaml`](framework_tests/cases/mock_business_flow.yaml)。

## 报告

`pytest.ini` 默认生成自包含 HTML 报告：

```text
reports/report.html
```

生成 Allure 原始结果和可视化报告：

```bash
python -m pytest tests -m smoke --alluredir=allure-results
allure generate allure-results --clean -o allure-report
allure open allure-report
```

Allure 附件会对 `password`、`authCode`、`telephone`、`token`、`tokenHead` 和
`Authorization` 等字段脱敏，但报告仍不应提交到 Git。

## CI/CD

### GitHub Actions

[`API tests`](.github/workflows/api-tests.yml) 在推送到 `main`/`master` 或创建 Pull Request 时执行：

1. 安装 Python 3.12 与开发依赖。
2. 执行 `ruff check .`。
3. 运行离线 `framework_tests`。
4. 上传 JUnit、pytest-html 和 Allure 报告产物。

真实 mall E2E 只在手动 `workflow_dispatch` 时运行。需要在仓库 `Settings -> Secrets and variables -> Actions`
中配置：

```text
Secrets:
PYTEST_BASE_URL
PYTEST_MEMBER_USERNAME
PYTEST_MEMBER_PASSWORD
PYTEST_ADMIN_USERNAME
PYTEST_ADMIN_PASSWORD
PYTEST_DB_HOST
PYTEST_DB_PORT
PYTEST_DB_USER
PYTEST_DB_PASSWORD
PYTEST_DB_NAME

Variable:
PYTEST_DB_ENABLED   # true 或 false
```

GitHub 托管 Runner 无法访问开发者电脑的 `localhost`。`PYTEST_BASE_URL` 必须是 Runner 可达的
专用测试环境，或将 workflow 运行在能访问内网的 self-hosted Runner 上。

### Jenkins

[`Jenkinsfile`](Jenkinsfile) 默认只执行离线框架测试；设置参数 `RUN_E2E=true` 后执行真实 API。
Jenkins 中需使用以下 Credentials ID：

```text
mall-api-base-url
mall-member-username
mall-member-password
mall-admin-username
mall-admin-password
```

Linux Agent 需要 Python 3、venv、Bash 以及 Jenkins JUnit/Allure 插件。可选环境变量
`DINGTALK_WEBHOOK` 和 `DINGTALK_SECRET` 用于发送构建通知。

本地 Linux/macOS 也可直接调用 CI 脚本：

```bash
bash scripts/ci_test.sh framework
bash scripts/ci_test.sh e2e smoke auto
```

## 目录结构

```text
.
├── cases/                    # 真实 API YAML 场景
├── config/                   # Pydantic 配置模型和 settings.yaml
├── data/                     # Python 参数化数据
├── engine/                   # YAML 加载、渲染、提取、断言和执行
├── fixtures/                 # 会话、会员、商品、购物车和订单 fixture
├── framework_tests/          # 不依赖 mall-swarm 的框架自测
├── mock_server/              # 离线自测使用的 Flask Mock Server
├── scripts/                  # YAML CLI、CI 执行和钉钉通知
├── tests/                    # 真实 mall-swarm API 测试
├── utils/                    # HTTP、断言、Allure、日志、数据库工具
├── .github/workflows/        # GitHub Actions
├── Jenkinsfile               # Jenkins 声明式流水线
├── conftest.py
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

## 数据安全与已知限制

- `tests/` 会产生真实的购物车、会员和订单数据，只应在专用测试环境执行。
- 购物车 fixture 仅清理本用例创建的条目；未支付订单会尝试“取消 -> 删除”。
- 已支付待发货订单受 mall 业务规则限制，默认保留，需由测试环境定期清理。
- `fresh_member` 调用真实注册接口，目前不会删除已注册会员。
- ES 搜索依赖 `pms` 索引。未安装 IK 分词时，使用 `standard` 分词可能降低中文搜索质量。
- 后端不可达时，真实测试会在会话初始化阶段终止并给出环境检查提示。
- 并行执行会访问共享账号和数据，默认优先在串行模式建立可重复基线。

## 常见问题

**为什么执行真实用例时立即退出？**  
框架会先探测 mall-gateway。确认 `PYTEST_BASE_URL` 可访问，并检查 Nacos 中网关和相关服务已注册。

**为什么登录成功但后续请求返回 401？**  
确认请求头是 `Authorization: Bearer <token>`，且没有混用后台管理员和前台会员 token。

**为什么改了后端 `application.yml` 却没生效？**  
当前后端从 Nacos 导入 `mall-xxx-dev.yaml`，远程配置会覆盖本地同名项。

**为什么商品已写入 MySQL 但搜索不到？**  
搜索读取 Elasticsearch，MySQL 更改后需重新调用 `importAll` 或单条索引接口。

**为什么离线测试通过，真实回归仍然失败？**  
`framework_tests/` 只校验框架组件；`tests/` 才校验 mall-swarm 真实接口、初始化数据和中间件状态。

## 贡献与发布规则

- 不要提交 `.env`、真实账号密码、token、数据库凭据、测试报告或缓存文件。
- 新增真实业务用例时，优先使用对应 fixture 实现数据的创建、校验和清理。
- 新增通用框架能力时，同步在 `framework_tests/` 中补充离线回归。
- 提交前执行：

```bash
python -m ruff check .
python -m pytest framework_tests -m framework
python -m pytest tests --collect-only -q
```

本测试仓库当前未单独提供许可证文件，上游 mall-swarm 的许可证不会自动适用于本仓库的新增代码。
