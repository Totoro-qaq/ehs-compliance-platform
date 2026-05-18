# EHS 合规评价后端

基于 **FastAPI** 的 EHS（环境、健康与安全）合规评价 API：上传评价材料、异步调用 **Dify 工作流** 做分析，结果写入数据库。成功/失败响应统一为 **JSON 信封**（`success` / `code` / `message` / `data` / `details`）。

## 技术栈

| 组件 | 用途 |
|------|------|
| FastAPI + Uvicorn | HTTP API |
| MySQL + SQLAlchemy 2 + Alembic | 持久化 |
| Redis | Celery Broker / Result Backend |
| Celery | 异步评价任务（PDF/文本抽取 → Dify） |
| Dify | 工作流（阻塞 `workflows/run`） |
| PyJWT + passlib | B 端登录 JWT |

## 目录结构（摘要）

```
├── main.py                 # ASGI 入口：create_app()
├── app/
│   ├── api/v1/             # 路由：认证、公司、评价任务、管理员
│   ├── core/               # 配置、数据库、安全、异常
│   ├── dao/                # 数据访问
│   ├── models/             # ORM
│   ├── schemas/            # Pydantic
│   ├── services/           # 业务 + Dify 调用
│   ├── tasks/worker.py     # Celery 应用与任务
│   └── middleware/         # JSON 信封中间件
├── alembic/                # 迁移
├── fixtures/ehs/           # 样例文本与期望的 Dify 输出 JSON 形态
├── scripts/                # E2E、Celery、运维脚本
├── docker-compose.yml      # 仅 Redis（本地开发）
├── requirements.txt
└── .env                    # 本地配置（勿提交仓库，见 .gitignore）
```

## 环境要求

- **Python** 3.11+（推荐 3.12/3.13）
- **MySQL** 8.x（或其它兼容版本），已创建数据库
- **Redis**（可用本项目 `docker-compose.yml` 拉起）
- **Dify**：云版 `https://api.dify.ai/v1` 或 **自建**（如 `http://localhost/v1`），并准备好 **工作流 API Key**

### 可选：PDF / 图片 / 老 Word 解析依赖

仅当需要解析 **PDF / 扫描件 / 图片 / `.doc`** 时才需要安装；纯 `.txt` / `.docx` 走纯 Python 路径，**不依赖**下列组件。

| 依赖 | 用途 | 安装建议 |
|------|------|----------|
| poppler-utils | `pdf2image` 渲染 PDF 页面 | Windows 推荐用 Docker 路线，或下载 poppler 加入 `PATH` |
| Tesseract / PaddleOCR | 图片或扫描件 OCR | 见 `requirements.txt` 实际启用项 |
| antiword | 解析旧版 `.doc` | Windows 上无官方包；推荐 Docker 路线 |

> 在 Windows 本机自行安装上述系统依赖较繁琐，**最省心的方式是使用项目自带的 Dockerfile / docker-compose**（见下文「Docker 用法」），镜像已预装 `poppler-utils`、`antiword` 和 OCR 运行库。

## 快速开始

### 1. 获取代码与依赖

```bash
cd ehs_system
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. MySQL：建库并迁移

在 MySQL 中创建数据库（名称与 `.env` 中 `MYSQL_DB` 一致，默认 `ehs_system`），然后：

```bash
alembic upgrade head
```

若 Alembic 报连接失败，先检查 `.env` 里 MySQL 主机、端口、用户、密码与库名。

### 3. 配置环境变量

在**项目根目录**从模板复制一份 `.env`（**不要将含密钥的 `.env` 提交到 Git**）：

```bash
# Linux/macOS
cp .env.example .env
# Windows PowerShell
Copy-Item .env.example .env
```

随后按下表与 `.env.example` 内注释修改各项；至少需要填写 MySQL 连接、`JWT_SECRET`、`BOOTSTRAP_ADMIN_PASSWORD`、`DIFY_API_KEY` / `DIFY_BASE_URL`。

**最小可运行示例**（按需修改）：

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DB=ehs_system

CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1

JWT_SECRET=请使用足够长的随机字符串
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=符合复杂度要求的密码

DIFY_API_KEY=app-你的-Dify-API-Key
DIFY_BASE_URL=https://api.dify.ai/v1
# 自建示例: http://localhost/v1

# 与工作流「结束」节点输出变量名一致，且值为含 risks、summary 的 JSON（见下文）
DIFY_WORKFLOW_RESULT_KEY=result
# 与工作流「开始」中文本变量名一致
DIFY_WORKFLOW_INPUT_TEXT_KEY=document_text
```

### 4. 启动 Redis

```bash
docker compose up -d
# 验证: docker compose exec redis redis-cli ping  应返回 PONG
```

### 5. 启动 API（Uvicorn）

在**项目根目录**打开一个终端，长期保持运行：

```bash
cd /path/to/ehs_system
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Windows（PowerShell）示例：

```powershell
cd d:\python\ehs_system
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

- **`--reload`**：改代码自动重载（生产环境应去掉）。  
- 根健康检查：<http://127.0.0.1:8000/healthz>（**不**包信封）  
- Swagger：<http://127.0.0.1:8000/docs>  
- v1 健康检查：<http://127.0.0.1:8000/api/v1/healthz>（经中间件 **包信封**）

应用启动时会执行 `init_db()`：若不存在则插入**默认公司**（`DEFAULT_ORGANIZATION_ID`）；若配置了 `BOOTSTRAP_ADMIN_PASSWORD` 且该管理员用户名不存在，则创建 **ADMIN** 账号。

### 6. 启动 Celery Worker

评价任务依赖 **独立 Worker 进程**，请在**项目根目录**再开一个终端（与 API **共用同一份 `.env`**）：

```bash
cd /path/to/ehs_system
celery -A app.tasks.worker.celery_app worker -l info --pool=solo
```

Windows（PowerShell）等价于：

```powershell
cd d:\python\ehs_system
celery -A app.tasks.worker.celery_app worker -l info --pool=solo
```

或使用脚本（脚本内会先 `cd` 到仓库根）：

```powershell
.\scripts\run_celery_worker.ps1
```

**Windows** 务必使用 **`--pool=solo`**（仓库在 `win32` 上也会尽量默认 solo），不要用默认 **prefork**，否则易出现 billiard 多进程报错。

不设 Worker 或未连上 Redis 时，评价任务会长期停留在 **`PENDING`**。

### 6.1 启动 Celery Beat（定时任务调度）

生产环境需要额外启动 **Beat 进程**，用于调度文件清理等周期性任务：

```bash
celery -A app.tasks.worker.celery_app beat -l info
```

Windows（PowerShell）：

```powershell
cd d:\python\ehs_system
celery -A app.tasks.worker.celery_app beat -l info
```

Beat 当前注册的定时任务：

| 任务 | 周期 | 说明 |
|------|------|------|
| `cleanup_expired_uploads` | 每 24 小时 | 清理已软删除且超过保留期（`UPLOAD_RETENTION_DAYS`，默认 7 天）的上传文件 |

Beat 与 Worker 是独立进程，两者都需要运行。本地开发如不需要自动清理可不启动 Beat。

### 6.2 启动前端（可选）

仓库 `frontend/` 是一份零依赖的静态前端，仅在需要在浏览器中走 UI 联调时启动：

```bash
cd frontend
python -m http.server 5173
```

随后访问 <http://127.0.0.1:5173>。默认 API 基址为 `http://127.0.0.1:8000`，可在页面右上角设置中修改，值会写入浏览器 `localStorage`。详见 `frontend/README.md`。

### 7. 停止与重启

| 操作 | 做法 |
|------|------|
| **停止** | 在运行 Uvicorn 或 Celery 的终端里按 **`Ctrl+C`** |
| **重启** | 先 **`Ctrl+C`** 结束进程，再在**项目根目录**重新执行上面对应的**同一条启动命令** |

两者互不影响：可以只重启 Celery（例如只改了 Dify 配置或 Worker 代码），或只重启 Uvicorn。

**修改 `.env` 后**：除 `uvicorn --reload` 仅重载**代码**外，环境变量通常在进程启动时读取——**请重启 Uvicorn；Celery Worker 必须重启**后才会使用新的 `DIFY_*`、`CELERY_*` 等配置。

### 8. Windows：端口占用或残留进程（可选）

**8000 已被占用**（再次启动 Uvicorn 报错）时，可在 PowerShell 中查看并结束占用进程（将 `<PID>` 换成实际进程号）：

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Celery 未正常退出**、怀疑仍有 Worker 在跑时：

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -match 'celery' } |
  Select-Object ProcessId, CommandLine
# 确认后：Stop-Process -Id <PID> -Force
```

### 9. 本机联调推荐顺序

1. 启动 **Redis**（`docker compose up -d`）  
2. 启动 **Uvicorn**  
3. 启动 **Celery Worker**  
4. 启动 **Celery Beat**（生产必须，本地可选）  
5. 再测接口或运行 `scripts/e2e_pipeline.py`

## Docker 用法

仓库内同时提供 `Dockerfile` 与 `docker-compose.yml`，按需选用：

| 场景 | 命令 | 说明 |
|------|------|------|
| 仅起 Redis（本机跑 API/Worker） | `docker compose up -d redis` | 「快速开始」默认走这条路线，最贴近开发体验 |
| 仅起 Redis + MySQL | `docker compose up -d redis mysql` | 不想本机装 MySQL 时使用 |
| 整套容器化（API + Worker + Redis + MySQL） | `docker compose up -d --build` | 适合演示或需要 PDF/OCR/antiword 等系统依赖时；镜像基于 `Dockerfile` 构建 |

整套启动时，`api` 与 `worker` 容器共用根目录 `.env`，并由 compose 覆盖 `MYSQL_HOST=mysql`、`REDIS_URL=redis://redis:6379/0` 等；首次启动需要在 `api` 容器内执行：

```bash
docker compose exec api alembic upgrade head
```

> Beat 进程目前未在 compose 中声明，如需自动清理上传文件请额外启动（参考 6.1）。

## 测试

测试基于 **pytest**，配置位于 `pytest.ini`：

```bash
# 运行全部测试
pytest

# 仅运行某个文件
pytest tests/test_assessment.py

# 关键字过滤
pytest -k "auth and not register"
```

测试默认从 `tests/conftest.py` 装载夹具；如需独立的测试库，请在执行前覆盖 `MYSQL_DB` 等环境变量，避免污染开发库。

## 环境变量说明

配置由 `pydantic-settings` 从 **环境变量** 与 **根目录 `.env`** 加载；字段名对应环境变量为 **全大写下划线**（与下表一致）。

| 环境变量 | 说明 | 默认（节选） |
|----------|------|----------------|
| `APP_NAME` | 应用展示名 | EHS Compliance API |
| `APP_ENV` | 环境标识 | dev |
| `APP_DEBUG` | 调试 | true |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB` | MySQL | 127.0.0.1:3306, root, ehs_system |
| `JWT_SECRET` | JWT 签名密钥 | （务必修改） |
| `JWT_EXPIRE_MINUTES` | JWT 有效期（分钟） | 1440 |
| `BOOTSTRAP_ADMIN_USERNAME` | 首次自动创建的管理员用户名 | admin |
| `BOOTSTRAP_ADMIN_PASSWORD` | 非空则在无此用户时创建管理员 | 空 |
| `ADMIN_API_KEY` | 管理接口可选 `X-Admin-Key` | 空 |
| `CORS_ORIGINS` | CORS，逗号分隔或 `*` | * |
| `REDIS_URL` | 通用 Redis（预留） | redis://127.0.0.1:6379/0 |
| `CELERY_BROKER_URL` | Celery 消息代理 | redis://127.0.0.1:6379/0 |
| `CELERY_RESULT_BACKEND` | Celery 结果后端 | redis://127.0.0.1:6379/1 |
| `DIFY_API_KEY` | Dify 应用 API Key（Bearer） | 空（Worker 调用前须配置） |
| `DIFY_BASE_URL` | Dify API 根（**含** `/v1`） | https://api.dify.ai/v1 |
| `DIFY_WORKFLOW_RESULT_KEY` | 工作流 **outputs** 里存放 EHS JSON 的变量名 | result |
| `DIFY_WORKFLOW_INPUT_TEXT_KEY` | 工作流 **inputs** 里文档正文的变量名 | document_text |
| `DEFAULT_ORGANIZATION_ID` | 默认公司 UUID | 00000000-0000-4000-8000-000000000001 |
| `HTTP_USER_AGENT` | 出站请求 User-Agent（Dify 等） | 内置浏览器 UA |
| `UPLOAD_DIR` | 上传文件目录（按日期自动分子目录） | ./uploads |
| `MAX_UPLOAD_BYTES` | 单文件最大字节 | 52428800 |
| `UPLOAD_RETENTION_DAYS` | 软删除任务文件保留天数，超期由 Beat 清理 | 7 |
| `LOG_DIR` / `LOG_FILE` / `LOG_WORKER_FILE` / `LOG_LEVEL` 等 | 日志 | ./logs |

**注意**：`DIFY_API_KEY` / `DIFY_BASE_URL` 会去首尾空白及成对引号，**云与自建地址不要与 Key 混用**。

## Dify 工作流约定

1. **开始节点**  
   - 必须有与 `DIFY_WORKFLOW_INPUT_TEXT_KEY` 一致的文本变量（默认 `document_text`）。  
   - Worker 还会传入 `filename`。  
   - 若你在画布里使用其它变量名，请在 `.env` 修改 `DIFY_WORKFLOW_INPUT_TEXT_KEY`。

2. **结束 / 输出**  
   - 输出变量名须与 `DIFY_WORKFLOW_RESULT_KEY` 一致（如 `result` 或 `result_json`）。  
   - **值**解析后须为含 **`risks`（数组）** 与 **`summary`（字符串）** 的对象，结构与 `EHSAssessmentResult` 一致。  
   - 参考仓库内 **`fixtures/ehs/sample_result_json.json`**。  
   - 代码会尝试解析 **裸 JSON**、**markdown 代码块包裹的 JSON**、以及 **多包一层** 的嵌套对象；LLM 仍须尽量输出合法 JSON。

3. **blocking 模式**  
   调用 `POST {DIFY_BASE_URL}/workflows/run`，`response_mode=blocking`。

## 常用 API 路径（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register`、`/auth/login` | 注册 / 登录，返回 `data.access_token` |
| GET/POST | `/organizations`、`/organizations/{id}` | 公司（需登录，权限见接口说明） |
| POST | `/assessment` | 创建评价任务（multipart：`file`，可选 `organization_id`） |
| GET | `/assessment` | 分页列表 |
| GET / DELETE | `/assessment/{task_id}` | 详情 / 软删 |
| — | `/admin/*` | 系统管理：JWT 且角色 ADMIN，或 `X-Admin-Key` |

除少数健康检查等路径外，成功 JSON 多经 **`ApiEnvelope`** 包装；错误同样为信封 + 对应 HTTP 状态码。

## 脚本工具

| 脚本 | 用途 |
|------|------|
| `scripts/e2e_pipeline.py` | 端到端自检：Redis、Celery、Dify、健康检查、登录、上传 fixture、轮询任务 |
| `scripts/run_celery_worker.ps1` | Windows 下启动 Worker（solo） |
| `scripts/upsert_bootstrap_admin.py` | 维护/重置引导管理员 |
| `scripts/create_db.py` / `scripts/init_demo_companies.py` | 建库/演示数据（按仓库说明使用） |
| `scripts/pack_handover.ps1` | 打包仓库为可外发的 zip，自动剔除 `.env` / 缓存 / 日志 / 上传内容 / 虚拟环境等 |

E2E 示例：

```bash
python scripts/e2e_pipeline.py --base-url http://127.0.0.1:8000
```

Dify 探针失败时默认会提前退出；详见脚本内 `--help` 与 `--continue-after-dify-failure`。

## 常见问题

### 数据库审计时间用的哪里的时钟？

各表继承 `ModelBase` 的 **`created_at`**、**`updated_at`** 以及软删 **`deleted_at`**，均按 **北京时间（`Asia/Shanghai`）** 的墙钟写入 MySQL `DATETIME`（列类型仍为**不带时区**的 naive，数值即东八区本地时间）。通用 `update_by_id`、软删/恢复及评价结果落库等路径会**显式刷新** `updated_at`，避免漏更新。**JWT 签发用的 `iat`/`exp` 仍为 UTC**，与库表审计字段无关。

### 评价任务一直 `PENDING`

- Redis 是否启动？`CELERY_BROKER_URL` 是否正确？  
- Celery Worker 是否在**项目根目录**启动且能连上同一 Redis？  
- 创建接口若返回 **503**、`TASK_ENQUEUE_FAILED`，多为**入队失败**（看 `details`）。

### 任务 `FAILED`：Dify 401

- `DIFY_API_KEY` 无效或与 `DIFY_BASE_URL` 环境不一致；在 Dify 控制台**重新生成 Key**，更新 `.env`，**重启 Worker**。

### 任务 `FAILED`：Dify 400（如 document_text 长度）

- 工作流开始节点对输入长度有限制，在 Dify 画布中**调大限制**或缩短测试文本。

### 任务 `FAILED`：无法解析 EHS 结构

- 结束节点输出变量名是否与 `DIFY_WORKFLOW_RESULT_KEY` 一致？  
- 输出 JSON 是否含 **`risks` / `summary`**？对照 `fixtures/ehs/sample_result_json.json`。

### Windows 上 Celery 报错 `ValueError: not enough values to unpack`

- 勿使用默认 **prefork** 多进程池；使用 **`--pool=solo`** 或当前仓库 `worker.py` 内对 Windows 的默认配置。

### FastAPI 与 URL 尾斜杠

- 应用设置了 `redirect_slashes=False`，并已为部分 GET 注册了带 `/` 的等价路由；若 404，检查路径是否与 OpenAPI 一致。

## 许可证

内部项目，未对外开源。如需复用或对外分发，请先与项目维护者确认。
