# EHS Compliance Evaluation Platform

[![CI](https://github.com/Totoro-qaq/ehs-compliance-platform/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/Totoro-qaq/ehs-compliance-platform/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![Vue 3](https://img.shields.io/badge/Vue-3.5-42b883)](https://vuejs.org/)
[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange)](#项目状态--project-status)

> ⚠️ **项目状态 / Project Status**：当前为 **Alpha**（实验性），核心流程已可跑通，但 API 与数据模型仍可能调整，不建议直接用于生产。Project is in **Alpha**: end-to-end pipeline works, but APIs and data models may still change before the first stable release.

> **免责声明 / Disclaimer**：本仓库不内置、不随附、不承诺提供任何正式法规、标准原文、生产限值库、SQL 数据包或可直接用于合规判定的数据集。仓库中的样例、测试数据和开发脚本仅用于功能演示与本地验证，不构成法律、职业卫生、安全、环保或其他专业合规意见。使用者应自行通过主管部门、标准出版机构、国家标准公开服务平台或其他官方/授权渠道获取合法有效的法规、标准和限值数据，并自行负责导入、校验、版本管理、适用性复核和最终合规判断。
>
> This repository does not include, ship, or promise any official regulations, standard documents, production limit libraries, SQL dumps, or datasets ready for compliance decisions. Samples, test data, and development scripts are for local validation only. Users must obtain legally valid regulations, standards, and limit data through official or authorized channels, then import, verify, version, and review applicability themselves.

基于 **FastAPI + Vue + Celery + Dify** 的 EHS（环境、健康与安全）合规评价系统。系统支持资料上传、异步文本解析、Dify 工作流分析、检测合规判定、Agent 助手、RAGFlow 只读检索壳、报告章节流水线与 Markdown / TXT / DOCX / DOC 导出。

An **EHS compliance evaluation platform** built with **FastAPI, Vue, Celery, and Dify**. It supports document upload, asynchronous text extraction, Dify workflow analysis, detection compliance calculation, an Agent assistant, a read-only RAGFlow search shell, a report section pipeline, and Markdown / TXT / DOCX / DOC export.

参与贡献请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。安全漏洞请按 [SECURITY.md](SECURITY.md) 流程上报。
See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing. Report security issues via [SECURITY.md](SECURITY.md).

## 中文说明

### 技术栈

| 组件 | 用途 |
|------|------|
| FastAPI + Uvicorn | 后端 HTTP API |
| Vue 3 + Vite + Pinia | 前端界面 |
| MySQL + SQLAlchemy 2 + Alembic | 数据持久化与迁移 |
| Redis | Celery Broker / Result Backend |
| Celery | 异步评价任务 |
| Dify Workflow API | EHS 文档智能分析 |
| Ollama / mock provider | Agent 助手模型 provider |
| RAGFlow API（可选） | 标准、导则只读检索壳 |
| PyJWT + passlib | 登录认证与密码哈希 |

### 目录结构

```text
├── main.py                 # FastAPI ASGI 入口
├── app/
│   ├── api/v1/             # 路由：认证、组织、评价、检测、Agent、RAGFlow、报告流水线
│   ├── core/               # 配置、数据库、安全、日志、上传策略
│   ├── dao/                # 数据访问层
│   ├── models/             # SQLAlchemy ORM
│   ├── schemas/            # Pydantic Schema
│   ├── services/           # 业务逻辑、Dify 调用、文档解析
│   ├── tasks/              # Celery Worker 与清理任务
│   └── middleware/         # JSON 信封中间件
├── alembic/                # 数据库迁移
├── fixtures/               # 示例输入与期望输出
├── frontend-vue/           # Vue 前端
├── scripts/                # 开发、运维、E2E 脚本
├── docker-compose.yml
├── requirements.txt
└── .env.example            # 环境变量模板
```

### 快速开始

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# 如需运行测试或代码检查，再装一次开发依赖
pip install -r requirements-dev.txt
```

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

启动 Redis：

```bash
docker compose up -d redis
```

执行数据库迁移：

```bash
alembic upgrade head
```

### 权限模型与演示租户

账户角色分三层：

| 角色 | 权限边界 |
|------|----------|
| `ADMIN` | 系统最高管理员；可查看和管理所有公司、系统管理接口、限值库和标准清单导入 |
| `ORG_ADMIN` | 公司管理员；只能查看本公司数据，可维护本公司资料，并可处理本公司评价任务 |
| `USER` | 公司员工；只能查看本公司数据，任务变更默认限制在本人创建的数据 |

演示公司与账号可用脚本初始化：

```powershell
$env:DEMO_ACCOUNT_PASSWORD = 'change-me-locally'
python scripts/init_demo_companies.py
```

该脚本只写入演示公司和演示账号，不会扫描、上传、解析或导入标准/导则原文。`.env`、上传目录、标准原文目录、RAG 缓存和本地 MinIO/Milvus 数据目录均已在 `.gitignore` 中排除。

检测合规限值库需由使用者自行维护。本仓库不内置、不提供正式法规限值库、标准原文、SQL 数据包或 seed 数据。实际使用前，请通过官方或授权渠道获取合法有效的标准和限值数据，并由管理员在系统中自行导入、校验和维护。演示 CSV 位于 `fixtures/detection/`，只用于验证导入流程。

启动 API：

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

启动 Celery Worker：

```bash
celery -A app.tasks.worker.celery_app worker -l info --pool=solo
```

前端开发：

```bash
cd frontend-vue
npm install
npm run dev
```

登录后进入顶部导航「检测合规」或访问 `/detection`，可上传 CSV / XLSX / XLSM 结构化数据，也可通过解析预览导入 PDF / DOCX / DOC / TXT / ZIP 报告文件；确认入库后可运行合规判定，并由管理员维护限值库。页面内置职业卫生、噪声、高温三个样例按钮，方便本地演示。

检测报告详情抽屉支持初始化报告章节、查看导出就绪状态、管理员审批或退回章节，并可下载 Markdown / TXT / DOCX / DOC。导出前必须满足：章节完整、引用来源校验通过、所有章节已批准。

前端环境变量：

```bash
cd frontend-vue
cp .env.example .env.local
```

| 变量 | 说明 | 示例 |
|------|------|------|
| `VITE_API_BASE` | 后端 API 根地址，不带 `/api/v1` | `http://127.0.0.1:8000` |

### 后端环境变量说明

| 变量 | 说明 | 默认值 / 示例 |
|------|------|---------------|
| `APP_NAME` | FastAPI 应用名称 | `EHS Compliance API` |
| `APP_ENV` | 运行环境；`prod` / `production` / `live` 会启用生产校验 | `dev` |
| `APP_DEBUG` | 是否开启调试模式，生产必须为 `false` | `true` |
| `MYSQL_HOST` | MySQL 主机 | `127.0.0.1` |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_USER` | MySQL 用户 | `root` |
| `MYSQL_PASSWORD` | MySQL 密码 | 空 |
| `MYSQL_DB` | MySQL 数据库名 | `ehs_system` |
| `REDIS_URL` | 通用 Redis 地址，预留配置 | `redis://127.0.0.1:6379/0` |
| `CELERY_BROKER_URL` | Celery 消息代理 | `redis://127.0.0.1:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery 结果后端 | `redis://127.0.0.1:6379/1` |
| `JWT_SECRET` | JWT 签名密钥，生产环境必须使用强随机值 | `change-me-in-production-use-long-random-secret` |
| `JWT_EXPIRE_MINUTES` | JWT 有效期，单位分钟 | `60` |
| `ADMIN_API_KEY` | 管理接口可选 `X-Admin-Key` | 空 |
| `AUTH_CAPTCHA_REQUIRED` | 登录时是否强制校验图形验证码 | `true` |
| `BOOTSTRAP_ADMIN_USERNAME` | 首次启动时自动创建的管理员用户名 | `admin` |
| `BOOTSTRAP_ADMIN_PASSWORD` | 首次启动时自动创建管理员的密码；为空则不创建 | 空 |
| `CORS_ORIGINS` | CORS 允许来源，逗号分隔；生产不要使用 `*` | `*` |
| `DEFAULT_ORGANIZATION_ID` | 默认组织 UUID | `00000000-0000-4000-8000-000000000001` |
| `DIFY_API_KEY` | Dify Workflow API Key | 空 |
| `DIFY_BASE_URL` | Dify API 根地址，必须包含 `/v1` | `https://api.dify.ai/v1` |
| `DIFY_WORKFLOW_RESULT_KEY` | Dify 输出中存放 EHS JSON 的变量名 | `result` |
| `DIFY_WORKFLOW_INPUT_TEXT_KEY` | Dify 输入中文档正文的变量名 | `document_text` |
| `DIFY_RETRY_MAX_ATTEMPTS` | Dify 可恢复错误最大尝试次数，含首次请求 | `3` |
| `DIFY_RETRY_INITIAL_DELAY_SECONDS` | Dify 重试初始退避秒数 | `2` |
| `DIFY_RETRY_MAX_DELAY_SECONDS` | Dify 重试最大退避秒数 | `10` |
| `DIFY_RETRY_JITTER_SECONDS` | Dify 重试随机抖动秒数 | `0.5` |
| `DIFY_RETRY_ON_TIMEOUT` | 是否对阻塞超时自动重试；默认关闭以避免重复扣费 | `false` |
| `AGENT_LLM_PROVIDER` | Agent 模型 provider；支持 `ollama`、`mock` | `ollama` |
| `OLLAMA_BASE_URL` | 本地 Ollama 服务地址 | `http://127.0.0.1:11434` |
| `OLLAMA_CHAT_MODEL` | Agent 使用的 Ollama chat 模型 | `qwen2.5:7b` |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | Agent 单次模型请求超时秒数 | `120` |
| `AGENT_RUNTIME_MAX_TOOL_CALLS` | Agent 单轮最大工具调用次数 | `12` |
| `AGENT_RUNTIME_TIMEOUT_SECONDS` | Agent 单轮运行超时秒数 | `30` |
| `RAGFLOW_BASE_URL` | RAGFlow API 根地址；为空时只读检索壳禁用 | 空 |
| `RAGFLOW_API_KEY` | RAGFlow API Key | 空 |
| `RAGFLOW_DATASET_IDS` | 允许检索的数据集 ID，逗号分隔 | 空 |
| `RAGFLOW_TIMEOUT_SECONDS` | RAGFlow 请求超时秒数 | `30` |
| `HTTP_USER_AGENT` | 调用 Dify 等外部 HTTP 服务时使用的 User-Agent | 内置浏览器 UA |
| `PDF_OCR_ENABLED` | 是否启用扫描 PDF OCR；默认关闭以减小镜像和内存占用 | `false` |
| `UPLOAD_DIR` | 上传文件根目录 | `./uploads` |
| `MAX_UPLOAD_BYTES` | 单文件最大字节数 | `52428800` |
| `UPLOAD_RETENTION_DAYS` | 软删除文件保留天数，超期由定时任务清理 | `7` |
| `SSE_HEARTBEAT_INTERVAL` | SSE 进度推送心跳间隔，单位秒 | `15` |
| `LOG_DIR` | 日志目录 | `./logs` |
| `LOG_FILE` | API 日志文件名 | `ehs_api.log` |
| `LOG_WORKER_FILE` | Worker 日志文件名 | `ehs_worker.log` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_MAX_BYTES` | 单个日志文件最大字节数 | `10485760` |
| `LOG_BACKUP_COUNT` | 轮转日志保留数量 | `5` |

生产环境启动时会执行配置校验：禁止默认弱密钥、空 Dify Key、通配 CORS、`APP_DEBUG=true` 等不安全配置。

### Dify 工作流与重试策略

当前实现使用阻塞模式调用：

```text
POST {DIFY_BASE_URL}/workflows/run
response_mode=blocking
```

工作流输入：

| 输入 | 说明 |
|------|------|
| `DIFY_WORKFLOW_INPUT_TEXT_KEY` 对应变量 | 文档正文，默认 `document_text` |
| `filename` | 原始文件名 |

工作流输出：

| 输出 | 说明 |
|------|------|
| `DIFY_WORKFLOW_RESULT_KEY` 对应变量 | 包含 `risks` 与 `summary` 的 EHS JSON，默认 `result` |

当前重试策略：

- `run_workflow_blocking()` 对单次 Dify 请求设置默认 `600s` 超时。
- 发生 HTTP 错误、超时、网络错误、非 JSON 响应或结果结构校验失败时，会抛出 `DifyWorkflowError`。
- Celery Worker 捕获该错误后，将评价任务标记为 `FAILED`，进度置为 `100`，并把错误摘要写入 `error_message`。
- 当前代码会对可恢复错误执行有限重试：`429`、`500`、`502`、`503`、`504` 和临时网络错误。
- 不自动重试 `400`、`401`、`403`、非 JSON 响应、输出 JSON 结构错误或 schema 校验失败；这些通常需要先修正配置、Key、工作流变量或提示词。
- 阻塞超时默认不自动重试，因为 Dify 侧可能仍在执行，重复请求可能造成重复扣费或重复工作流运行。如确需开启，可设置 `DIFY_RETRY_ON_TIMEOUT=true`。
- 重试使用指数退避与随机抖动，默认最多 `3` 次尝试；两次重试等待约为 `2s -> 4s`，并受 `DIFY_RETRY_MAX_DELAY_SECONDS` 限制。
- 日志会记录 `attempt`、`max_attempts`、`retryable`、`status_code` 和 `elapsed_ms`，便于排查外部服务波动。

### Agent 与 RAGFlow

- Agent 助手提供工作台快捷问答和完整会话页，支持会话列表、消息历史、软删除和清空当前账号会话。
- 工作台总结、轻量问候、检测任务概览等固定场景优先走规则化快速摘要，避免无意义调用 LLM。
- 开放式问题通过 provider 抽象调用模型；默认 provider 为本地 Ollama，可在测试或联调时切换为 `mock`。
- Agent 工具调用受 schema、权限策略、只读副作用检查、单轮工具调用数和运行超时限制保护。
- RAGFlow 当前只做只读检索壳：`RAGFLOW_*` 未配置时接口返回禁用原因，不会从仓库加载或提交真实标准、法规、导则内容。
- Agent memory 可记录经人工确认或来自 RAGFlow chunk 的引用记忆，用于后续报告章节引用校验。

### 轻量可观测性

- 每个 API 请求都会设置或透传 `X-Request-Id`，并返回给客户端。
- 支持 W3C `traceparent` 头；未传入时后端会生成新的 `trace_id` 与 `span_id`。
- API 日志、Worker 日志和 Dify 出站调用日志均包含 `request_id`、`trace_id`、`span_id`，可串联一次上传、异步任务和外部调用。
- API 响应会返回 `X-Process-Time-Ms`，用于快速定位慢请求。
- Worker 会把评价任务关键状态写入 `assessment_timeline_events`，包括状态、进度、提示信息和相对任务开始的 `elapsed_ms`。
- 任务详情与列表响应会返回 `timeline` 和派生的 `waterfall` 字段；前端任务详情抽屉会展示处理耗时瀑布图，用于快速判断耗时集中在解析、Dify 分析、校验还是结果保存阶段。
- 升级已有数据库时需执行 Alembic 迁移 `0004_assessment_timeline_events`。
- Dify 出站请求会携带 `traceparent`，便于未来接入 OpenTelemetry Collector、Jaeger 或 Tempo。
- 当前未引入完整 OpenTelemetry Collector，目的是降低小服务器部署成本；需要 APM 时可在此基础上继续接入自动埋点。

### 日志策略

- API 与 Worker 均使用统一日志格式：时间、级别、`request_id`、`trace_id`、`span_id`、logger 名、源码路径、行号、消息。
- 日志同时输出到控制台和文件。
- API 默认写入 `logs/ehs_api.log`。
- Worker 默认写入 `logs/ehs_worker.log`。
- 文件日志使用 `RotatingFileHandler` 按大小轮转，默认单文件 `10 MB`，保留 `5` 个历史文件。
- 日志文件编码为 UTF-8，适合记录中文错误信息。
- `.gitignore` 应排除 `logs/`，生产环境应由宿主机、容器卷或日志平台持久化。

### 上传文件存储策略

- 上传根目录由 `UPLOAD_DIR` 控制，默认 `./uploads`。
- 文件按日期分目录保存，格式为：

```text
uploads/YYYY/MM/DD/{uuid}_{safe_original_name}.{ext}
```

- 支持扩展名：`.pdf`、`.txt`、`.doc`、`.docx`、`.csv`。
- 原始文件名会经过安全校验，禁止路径穿越、空文件名和不支持的扩展名。
- `.pdf`、`.doc`、`.docx` 会校验 magic bytes，降低伪造扩展名风险。
- 默认轻量镜像只解析 PDF 文本层；扫描版 PDF 需要使用 OCR 镜像并设置 `PDF_OCR_ENABLED=true`。
- 单文件大小受 `MAX_UPLOAD_BYTES` 限制，默认 `50 MB`。
- 数据库任务表保存文件路径、展示文件名、状态、解析文本、结果 JSON 和错误信息。
- 软删除任务不会立即删除磁盘文件；文件保留 `UPLOAD_RETENTION_DAYS` 天，Celery Beat 中的清理任务每日清理过期上传文件。
- `.gitignore` 应排除 `uploads/`，生产环境建议使用持久化磁盘、对象存储或挂载卷。

### 检测报告流水线

- 内置报告章节模板，支持按检测报告初始化缺失章节。
- 每个章节可保存草稿内容和引用 memory，后端会校验引用是否属于当前租户且处于可用状态。
- 管理员可将章节标记为 `APPROVED` 或 `REJECTED`，普通用户可查看章节和导出阻塞原因。
- readiness 检查会阻塞缺章、引用未通过、任一章节未批准的报告导出。
- 支持导出 `markdown`、`txt`、`docx`、`doc`；其中 `docx` 为真实 OOXML zip，`doc` 为 Word 可打开的 HTML `.doc`。

### 常用 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/healthz` | 健康检查 |
| `GET` | `/api/v1/healthz` | API v1 健康检查 |
| `GET` | `/api/v1/readyz` | 就绪检查，验证数据库与 Redis |
| `POST` | `/api/v1/auth/register` | 注册 |
| `POST` | `/api/v1/auth/login` | 登录 |
| `GET / POST` | `/api/v1/organizations` | 组织列表 / 创建 |
| `POST` | `/api/v1/assessment` | 上传文件并创建评价任务 |
| `GET` | `/api/v1/assessment` | 查询评价任务列表 |
| `GET / DELETE` | `/api/v1/assessment/{task_id}` | 查询 / 软删除任务 |
| `POST` | `/api/v1/assessment/{task_id}/requeue` | 重新分析失败任务 |
| `GET` | `/api/v1/assessment/{task_id}/progress` | SSE 任务进度 |
| `GET / POST` | `/api/v1/detection/reports` | 检测报告列表 / 上传结构化检测数据 |
| `GET` | `/api/v1/detection/reports/{report_id}` | 检测报告详情 |
| `POST` | `/api/v1/detection/reports/{report_id}/calculate` | 运行检测合规判定 |
| `GET` | `/api/v1/detection/reports/{report_id}/results` | 查询检测合规判定结果 |
| `GET / POST / PUT / DELETE` | `/api/v1/detection/limits` | 法规限值库查询与维护 |
| `POST` | `/api/v1/agent/chat` | Agent 快捷聊天 |
| `GET / POST / DELETE` | `/api/v1/agent/sessions` | Agent 会话列表 / 创建 / 清空 |
| `GET` | `/api/v1/agent/sessions/{session_id}/messages` | 查询 Agent 会话消息 |
| `GET / PATCH / DELETE` | `/api/v1/agent/memories` | Agent memory 查询与维护 |
| `GET` | `/api/v1/ragflow/health` | RAGFlow 只读检索壳健康检查 |
| `GET` | `/api/v1/ragflow/chunks/search` | 检索授权 RAGFlow chunk |
| `GET` | `/api/v1/ragflow/clauses/search` | 按标准号与条款检索 RAGFlow chunk |
| `GET` | `/api/v1/report-pipeline/templates` | 查询报告章节模板 |
| `POST` | `/api/v1/report-pipeline/reports/{report_id}/bootstrap-sections` | 初始化报告章节 |
| `GET` | `/api/v1/report-pipeline/reports/{report_id}/sections` | 查询报告章节 |
| `GET` | `/api/v1/report-pipeline/reports/{report_id}/readiness` | 查询报告导出就绪状态 |
| `PATCH` | `/api/v1/report-pipeline/sections/{section_id}/review` | 审批或退回报告章节 |
| `GET` | `/api/v1/report-pipeline/reports/{report_id}/export?format=markdown|txt|docx|doc` | 导出报告文件 |
| `*` | `/api/v1/admin/*` | 管理接口 |

失败任务可以在前端任务列表或详情抽屉中点击「重新分析」。后端只允许 `FAILED` 状态重新投递，普通用户只能操作自己创建的任务。

### 备份与恢复

```powershell
.\scripts\backup.ps1
.\scripts\restore.ps1 -BackupPath .\backups\20260520-120000
```

- 备份脚本会导出 MySQL，并压缩 `uploads/`。
- 恢复脚本会导入 SQL，并默认恢复 `uploads.zip`。
- 执行前请确认 Docker Compose 中的 MySQL 服务正在运行。

### 测试与检查

```bash
python -m pytest -q
python -m ruff check .
cd frontend-vue
npm run lint
npm run build
```

### 前端部署

前端是独立的 Vite 应用，生产构建产物位于 `frontend-vue/dist/`：

```bash
cd frontend-vue
npm install
npm run build
```

部署建议：

- 用 Nginx、Caddy、静态网站托管或对象存储托管 `dist/`。
- 构建前通过 `VITE_API_BASE` 指向后端域名，例如 `https://api.example.com`。
- 当前路由使用 hash history，刷新页面不需要额外 rewrite 配置。
- 后端 `CORS_ORIGINS` 需要包含前端域名，生产环境不要使用 `*`。
- 前端只保存 JWT，不保存 Dify Key、数据库密码等后端密钥。

### 小服务器与 OCR

- 默认 Docker 镜像使用 `runtime` target，不安装 PaddleOCR/PaddlePaddle，适合小服务器和文本层 PDF。
- 如需扫描 PDF OCR，可使用覆盖文件启动 Worker：
```bash
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build worker
```
- OCR Worker 会安装 `requirements-ocr.txt` 并挂载 `paddle_models`，首次运行会下载模型，磁盘和内存占用会明显增加。

## English

### Stack

| Component | Purpose |
|-----------|---------|
| FastAPI + Uvicorn | Backend HTTP API |
| Vue 3 + Vite + Pinia | Frontend application |
| MySQL + SQLAlchemy 2 + Alembic | Persistence and migrations |
| Redis | Celery broker and result backend |
| Celery | Asynchronous assessment jobs |
| Dify Workflow API | AI-powered EHS document analysis |
| Ollama / mock provider | Agent assistant model provider |
| RAGFlow API (optional) | Read-only standard and guideline search shell |
| PyJWT + passlib | Authentication and password hashing |

### Project Layout

```text
├── main.py                 # FastAPI ASGI entrypoint
├── app/
│   ├── api/v1/             # Auth, organizations, assessments, detection, Agent, RAGFlow, report pipeline routes
│   ├── core/               # Config, database, security, logging, upload policy
│   ├── dao/                # Data access layer
│   ├── models/             # SQLAlchemy ORM models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business services, Dify client, document parsing
│   ├── tasks/              # Celery worker and scheduled cleanup tasks
│   └── middleware/         # JSON envelope middleware
├── alembic/                # Database migrations
├── fixtures/               # Sample inputs and expected outputs
├── frontend-vue/           # Vue frontend
├── scripts/                # Development, operations, and E2E scripts
├── docker-compose.yml
├── requirements.txt
└── .env.example            # Environment variable template
```

### Quick Start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# Install dev tools (pytest / ruff) only when you need to run tests or lint
pip install -r requirements-dev.txt
```

Create a local `.env` file:

```powershell
Copy-Item .env.example .env
```

Start Redis:

```bash
docker compose up -d redis
```

Run migrations:

```bash
alembic upgrade head
```

### Roles and Demo Tenants

The account model has three levels:

| Role | Scope |
|------|-------|
| `ADMIN` | System owner; can view and manage all companies, system admin APIs, regulatory limits, and standard manifest imports |
| `ORG_ADMIN` | Company admin; scoped to one company, can maintain that company profile and manage that company's assessment tasks |
| `USER` | Company employee; scoped to one company, with task mutations limited to data they created by default |

Initialize demo companies and accounts with:

```powershell
$env:DEMO_ACCOUNT_PASSWORD = 'change-me-locally'
python scripts/init_demo_companies.py
```

The script only writes demo companies and demo accounts. It reads `DEMO_ACCOUNT_PASSWORD` only to hash demo account passwords and does not print credentials. It does not scan, upload, parse, or import standard/source documents. `.env`, uploads, local standard document folders, RAG caches, and local MinIO/Milvus data folders are excluded by `.gitignore`.

Maintain detection compliance regulatory limits yourself. This repository does not include or provide an official regulatory limit library, standard documents, SQL dumps, or seed data. Before real use, obtain legally valid standards and limit data from official or authorized channels, then import, verify, and maintain them in the system. Demo CSV files under `fixtures/detection/` are only for validating the import workflow.

Start the API:

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Start the Celery worker:

```bash
celery -A app.tasks.worker.celery_app worker -l info --pool=solo
```

Start the frontend:

```bash
cd frontend-vue
npm install
npm run dev
```

After signing in, open "检测合规" in the top navigation or visit `/detection`. The page supports CSV / XLSX / XLSM structured upload plus PDF / DOCX / DOC / TXT / ZIP document import through parsing preview. After confirming parsed rows, you can run compliance calculation and maintain regulatory limits as an admin. Built-in sample buttons cover occupational health, noise, and high-temperature WBGT workflows.

The detection report drawer can bootstrap report sections, show export readiness, let admins approve or reject sections, and download Markdown / TXT / DOCX / DOC. Export is blocked until required sections exist, citations pass validation, and all sections are approved.

Frontend environment variable:

```bash
cd frontend-vue
cp .env.example .env.local
```

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_BASE` | Backend API base URL, without `/api/v1` | `http://127.0.0.1:8000` |

### Backend Environment Variables

| Variable | Description | Default / Example |
|----------|-------------|-------------------|
| `APP_NAME` | FastAPI application name | `EHS Compliance API` |
| `APP_ENV` | Runtime environment; `prod`, `production`, or `live` enables production validation | `dev` |
| `APP_DEBUG` | Debug mode; must be `false` in production | `true` |
| `MYSQL_HOST` | MySQL host | `127.0.0.1` |
| `MYSQL_PORT` | MySQL port | `3306` |
| `MYSQL_USER` | MySQL user | `root` |
| `MYSQL_PASSWORD` | MySQL password | empty |
| `MYSQL_DB` | MySQL database name | `ehs_system` |
| `REDIS_URL` | General Redis URL, reserved for shared use | `redis://127.0.0.1:6379/0` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://127.0.0.1:6379/0` |
| `CELERY_RESULT_BACKEND` | Celery result backend | `redis://127.0.0.1:6379/1` |
| `JWT_SECRET` | JWT signing secret; use a strong random value in production | `change-me-in-production-use-long-random-secret` |
| `JWT_EXPIRE_MINUTES` | JWT lifetime in minutes | `60` |
| `ADMIN_API_KEY` | Optional `X-Admin-Key` for admin APIs | empty |
| `AUTH_CAPTCHA_REQUIRED` | Whether login must validate image captcha | `true` |
| `BOOTSTRAP_ADMIN_USERNAME` | Bootstrap admin username | `admin` |
| `BOOTSTRAP_ADMIN_PASSWORD` | Bootstrap admin password; empty disables auto-creation | empty |
| `CORS_ORIGINS` | Allowed CORS origins, comma-separated; avoid `*` in production | `*` |
| `DEFAULT_ORGANIZATION_ID` | Default organization UUID | `00000000-0000-4000-8000-000000000001` |
| `DIFY_API_KEY` | Dify Workflow API key | empty |
| `DIFY_BASE_URL` | Dify API base URL, including `/v1` | `https://api.dify.ai/v1` |
| `DIFY_WORKFLOW_RESULT_KEY` | Output variable that contains the EHS JSON | `result` |
| `DIFY_WORKFLOW_INPUT_TEXT_KEY` | Input variable that receives document text | `document_text` |
| `DIFY_RETRY_MAX_ATTEMPTS` | Maximum attempts for recoverable Dify failures, including the first request | `3` |
| `DIFY_RETRY_INITIAL_DELAY_SECONDS` | Initial Dify retry backoff in seconds | `2` |
| `DIFY_RETRY_MAX_DELAY_SECONDS` | Maximum Dify retry backoff in seconds | `10` |
| `DIFY_RETRY_JITTER_SECONDS` | Random jitter added to Dify retry delay in seconds | `0.5` |
| `DIFY_RETRY_ON_TIMEOUT` | Whether blocking timeouts are retried automatically; disabled by default to avoid duplicate billing | `false` |
| `AGENT_LLM_PROVIDER` | Agent model provider; supports `ollama` and `mock` | `ollama` |
| `OLLAMA_BASE_URL` | Local Ollama service URL | `http://127.0.0.1:11434` |
| `OLLAMA_CHAT_MODEL` | Ollama chat model used by the Agent | `qwen2.5:7b` |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | Timeout for one Agent model request, in seconds | `120` |
| `AGENT_RUNTIME_MAX_TOOL_CALLS` | Maximum Agent tool calls per turn | `12` |
| `AGENT_RUNTIME_TIMEOUT_SECONDS` | Agent runtime timeout per turn, in seconds | `30` |
| `RAGFLOW_BASE_URL` | RAGFlow API base URL; empty disables the read-only search shell | empty |
| `RAGFLOW_API_KEY` | RAGFlow API key | empty |
| `RAGFLOW_DATASET_IDS` | Allowed dataset IDs, comma-separated | empty |
| `RAGFLOW_TIMEOUT_SECONDS` | RAGFlow request timeout, in seconds | `30` |
| `HTTP_USER_AGENT` | User-Agent used for outbound HTTP requests | built-in browser UA |
| `PDF_OCR_ENABLED` | Whether scanned-PDF OCR is enabled; disabled by default to reduce image size and memory usage | `false` |
| `UPLOAD_DIR` | Upload root directory | `./uploads` |
| `MAX_UPLOAD_BYTES` | Maximum upload size in bytes | `52428800` |
| `UPLOAD_RETENTION_DAYS` | Retention days for soft-deleted upload files | `7` |
| `SSE_HEARTBEAT_INTERVAL` | SSE heartbeat interval in seconds | `15` |
| `LOG_DIR` | Log directory | `./logs` |
| `LOG_FILE` | API log file name | `ehs_api.log` |
| `LOG_WORKER_FILE` | Worker log file name | `ehs_worker.log` |
| `LOG_LEVEL` | Log level | `INFO` |
| `LOG_MAX_BYTES` | Maximum size of one log file | `10485760` |
| `LOG_BACKUP_COUNT` | Number of rotated log files to keep | `5` |

When `APP_ENV` is production-like, startup validation blocks unsafe defaults such as weak secrets, empty Dify keys, wildcard CORS, and `APP_DEBUG=true`.

### Dify Workflow and Retry Policy

The current implementation calls Dify in blocking mode:

```text
POST {DIFY_BASE_URL}/workflows/run
response_mode=blocking
```

Workflow inputs:

| Input | Description |
|-------|-------------|
| Variable named by `DIFY_WORKFLOW_INPUT_TEXT_KEY` | Document body text, default `document_text` |
| `filename` | Original filename |

Workflow output:

| Output | Description |
|--------|-------------|
| Variable named by `DIFY_WORKFLOW_RESULT_KEY` | EHS JSON containing `risks` and `summary`, default `result` |

Retry policy:

- `run_workflow_blocking()` uses a default request timeout of `600s`.
- HTTP errors, timeouts, network errors, non-JSON responses, and schema validation failures are raised as `DifyWorkflowError`.
- The Celery worker catches the error, marks the assessment task as `FAILED`, sets progress to `100`, and stores a short error message in `error_message`.
- The code retries recoverable failures only: `429`, `500`, `502`, `503`, `504`, and temporary network errors.
- It does not retry `400`, `401`, `403`, non-JSON responses, invalid output JSON, or schema validation failures; these usually require fixing configuration, API keys, workflow variables, or prompts first.
- Blocking timeouts are not retried by default because Dify may still be running. Replaying the request can cause duplicate billing or duplicate workflow execution. Set `DIFY_RETRY_ON_TIMEOUT=true` only when that tradeoff is acceptable.
- Retries use exponential backoff with jitter. The default is up to `3` attempts, with retry waits around `2s -> 4s`, capped by `DIFY_RETRY_MAX_DELAY_SECONDS`.
- Logs include `attempt`, `max_attempts`, `retryable`, `status_code`, and `elapsed_ms` to make upstream instability easier to diagnose.

### Agent and RAGFlow

- The Agent assistant supports quick workbench questions and a full chat page with session list, message history, soft delete, and clearing current-account sessions.
- Fixed scenarios such as workbench summaries, lightweight greetings, and detection task summaries prefer rule-based fast summaries to avoid unnecessary LLM calls.
- Open-ended questions use the model provider abstraction. The default provider is local Ollama, and tests or integration checks can switch to `mock`.
- Agent tool calls are protected by schemas, permission policy, read-only side-effect checks, per-turn tool-call limits, and runtime timeout.
- RAGFlow is currently a read-only search shell. If `RAGFLOW_*` is not configured, the API returns the disabled reason and does not load or commit real standards, regulations, or guideline content from the repository.
- Agent memory can store manually verified memories or citation memories derived from RAGFlow chunks for later report-section citation validation.

### Lightweight Observability

- Every API request receives or propagates `X-Request-Id`, and the response echoes it back.
- The API supports the W3C `traceparent` header. If no header is provided, the backend creates a new `trace_id` and `span_id`.
- API logs, Worker logs, and Dify outbound call logs include `request_id`, `trace_id`, and `span_id`, so one upload can be followed across the HTTP request, Celery task, and external Dify call.
- API responses include `X-Process-Time-Ms` for quick slow-request triage.
- The worker records key assessment state changes in `assessment_timeline_events`, including status, progress, message, and `elapsed_ms` relative to task start.
- Assessment list/detail responses include `timeline` and derived `waterfall` fields. The frontend task drawer renders a processing-time waterfall so slow work can be attributed to parsing, Dify analysis, validation, or result persistence.
- Existing databases must apply Alembic migration `0004_assessment_timeline_events`.
- Dify outbound requests propagate `traceparent`, which keeps the path open for future OpenTelemetry Collector, Jaeger, or Tempo integration.
- A full OpenTelemetry Collector is intentionally not included yet to keep small-server deployment light. APM auto-instrumentation can be added on top of this context propagation later.

### Logging Policy

- API and Worker logs share one format: timestamp, level, `request_id`, `trace_id`, `span_id`, logger name, source path, line number, and message.
- Logs are written to both console and file.
- API logs default to `logs/ehs_api.log`.
- Worker logs default to `logs/ehs_worker.log`.
- File logs rotate by size using `RotatingFileHandler`; the default is `10 MB` per file and `5` backups.
- Log files use UTF-8 encoding and can store Chinese messages correctly.
- Exclude `logs/` from Git. In production, persist logs with host volumes, container volumes, or a log platform.

### Upload File Storage Policy

- The upload root is controlled by `UPLOAD_DIR`, defaulting to `./uploads`.
- Files are stored by date:

```text
uploads/YYYY/MM/DD/{uuid}_{safe_original_name}.{ext}
```

- Supported extensions: `.pdf`, `.txt`, `.doc`, `.docx`, `.csv`.
- Original filenames are validated to prevent path traversal, empty names, and unsupported extensions.
- `.pdf`, `.doc`, and `.docx` files are checked with magic bytes to reduce extension spoofing.
- The lightweight image parses PDF text layers only. Scanned PDFs require the OCR image and `PDF_OCR_ENABLED=true`.
- Single-file size is limited by `MAX_UPLOAD_BYTES`, defaulting to `50 MB`.
- The database stores file path, display filename, task status, parsed text, result JSON, and error message.
- Soft-deleting a task does not immediately delete its file. Files are retained for `UPLOAD_RETENTION_DAYS`, and a Celery Beat cleanup task removes expired uploads daily.
- Exclude `uploads/` from Git. For production, prefer persistent disks, object storage, or mounted volumes.

### Detection Report Pipeline

- Built-in section templates can initialize missing sections for a detection report.
- Each section can store draft content and citation memory IDs. The backend validates that citations belong to the current tenant and are usable.
- Admins can mark sections as `APPROVED` or `REJECTED`; regular users can view sections and export blocking reasons.
- Readiness checks block export when required sections are missing, citations have not passed validation, or any section has not been approved.
- Supported export formats are `markdown`, `txt`, `docx`, and `doc`. `docx` is a real OOXML zip file, while `doc` is Word-compatible HTML with a `.doc` extension.

### Common APIs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Health check |
| `GET` | `/api/v1/healthz` | API v1 health check |
| `GET` | `/api/v1/readyz` | Readiness check for database and Redis |
| `POST` | `/api/v1/auth/register` | Register |
| `POST` | `/api/v1/auth/login` | Login |
| `GET / POST` | `/api/v1/organizations` | List / create organizations |
| `POST` | `/api/v1/assessment` | Upload a file and create an assessment task |
| `GET` | `/api/v1/assessment` | List assessment tasks |
| `GET / DELETE` | `/api/v1/assessment/{task_id}` | Get / soft-delete a task |
| `POST` | `/api/v1/assessment/{task_id}/requeue` | Requeue a failed task |
| `GET` | `/api/v1/assessment/{task_id}/progress` | SSE task progress |
| `GET / POST` | `/api/v1/detection/reports` | List reports / upload structured detection data |
| `GET` | `/api/v1/detection/reports/{report_id}` | Get detection report details |
| `POST` | `/api/v1/detection/reports/{report_id}/calculate` | Run detection compliance calculation |
| `GET` | `/api/v1/detection/reports/{report_id}/results` | List detection compliance results |
| `GET / POST / PUT / DELETE` | `/api/v1/detection/limits` | Query and maintain regulatory limits |
| `POST` | `/api/v1/agent/chat` | Agent quick chat |
| `GET / POST / DELETE` | `/api/v1/agent/sessions` | List / create / clear Agent sessions |
| `GET` | `/api/v1/agent/sessions/{session_id}/messages` | List Agent session messages |
| `GET / PATCH / DELETE` | `/api/v1/agent/memories` | Query and maintain Agent memories |
| `GET` | `/api/v1/ragflow/health` | RAGFlow read-only search shell healthcheck |
| `GET` | `/api/v1/ragflow/chunks/search` | Search authorized RAGFlow chunks |
| `GET` | `/api/v1/ragflow/clauses/search` | Search RAGFlow chunks by standard code and clause |
| `GET` | `/api/v1/report-pipeline/templates` | List report section templates |
| `POST` | `/api/v1/report-pipeline/reports/{report_id}/bootstrap-sections` | Bootstrap report sections |
| `GET` | `/api/v1/report-pipeline/reports/{report_id}/sections` | List report sections |
| `GET` | `/api/v1/report-pipeline/reports/{report_id}/readiness` | Check report export readiness |
| `PATCH` | `/api/v1/report-pipeline/sections/{section_id}/review` | Approve or reject a report section |
| `GET` | `/api/v1/report-pipeline/reports/{report_id}/export?format=markdown|txt|docx|doc` | Export report file |
| `*` | `/api/v1/admin/*` | Admin APIs |

Failed tasks can be requeued from the task list or the detail drawer. The backend only accepts `FAILED` tasks, and non-admin users can only requeue tasks they created.

### Backup and Restore

```powershell
.\scripts\backup.ps1
.\scripts\restore.ps1 -BackupPath .\backups\20260520-120000
```

- The backup script exports MySQL and compresses `uploads/`.
- The restore script imports the SQL dump and restores `uploads.zip` by default.
- Make sure the MySQL service from Docker Compose is running before restoring.

### Checks

```bash
python -m pytest -q
python -m ruff check .
cd frontend-vue
npm run lint
npm run build
```

### Frontend Deployment

The frontend is a standalone Vite application. Production assets are generated in `frontend-vue/dist/`:

```bash
cd frontend-vue
npm install
npm run build
```

Deployment notes:

- Serve `dist/` with Nginx, Caddy, static hosting, or object storage.
- Set `VITE_API_BASE` before building, for example `https://api.example.com`.
- The app uses hash history, so page refreshes do not require extra rewrite rules.
- Backend `CORS_ORIGINS` must include the frontend origin. Do not use `*` in production.
- The frontend stores JWT only. Backend secrets such as Dify keys and database passwords must stay on the server.

### Small Servers and OCR

- The default Docker image uses the `runtime` target and does not install PaddleOCR/PaddlePaddle. This is better for small servers and text-layer PDFs.
- To process scanned PDFs with OCR, start the worker with the override file:
```bash
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build worker
```
- The OCR worker installs `requirements-ocr.txt` and mounts `paddle_models`. The first run downloads models and uses noticeably more disk and memory.

## License

本项目已在 GitHub 开源，采用 MIT License，详见 [LICENSE](LICENSE)。

This project is open source on GitHub under the MIT License. See [LICENSE](LICENSE).
