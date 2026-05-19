# Contributing Guide / 贡献指南

> 本指南提供中英双语版本。English version is below the Chinese section.

---

## 中文版

感谢你对 **EHS Compliance Platform** 的兴趣！本项目是一个 EHS 合规评价系统，结合 FastAPI、Celery、Vue 与 Dify 工作流。我们欢迎任何形式的贡献：缺陷报告、文档改进、新功能、测试用例。

### 1. 行为准则

参与本项目即表示你同意遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。请保持友善、专业。

### 2. 本地开发环境

#### 2.1 系统依赖

- Python 3.11 或 3.13
- Node.js 20+（仅前端开发需要）
- Docker + Docker Compose（推荐用于快速起 MySQL 与 Redis）
- Linux/macOS 上需要 `antiword`、`poppler-utils`（解析 .doc / pdf）

#### 2.2 后端启动

```bash
# 1) 克隆 & 进入项目
git clone https://github.com/Totoro-qaq/ehs-compliance-platform.git
cd ehs-compliance-platform

# 2) 创建虚拟环境并安装依赖
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest + ruff

# 3) 复制环境变量模板并按需修改
cp .env.example .env

# 4) 启动依赖（MySQL + Redis）
docker compose up -d redis mysql

# 5) 数据库迁移
alembic upgrade head

# 6) 启动 API 与 Worker（两个终端）
uvicorn main:app --reload
celery -A app.tasks.worker:celery_app worker --loglevel=info
```

#### 2.3 前端启动

```bash
cd frontend-vue
npm install
npm run dev
```

### 3. 代码规范

#### 3.1 Python 代码

- **必须通过 ruff 检查**：`ruff check .`（CI 会阻塞）
- 命名：变量与函数 `snake_case`，类 `PascalCase`
- 必须提供完整的 **Type Hints**
- EHS 业务规则、国标判定相关逻辑**必须加中文注释**说明依据
- 严格分层：Router → Service → DAO，路由层不写业务逻辑
- 异步耗时操作（Dify、PDF 解析、OCR）必须走 Celery

#### 3.2 前端代码

- 必须通过 ESLint：`npm run lint`
- 组件文件 `PascalCase.vue`，工具与 store 文件 `camelCase.js`

### 4. 测试

```bash
pytest            # 完整跑一次
pytest -k auth    # 只跑认证相关
```

新增功能或修复 bug 时**必须补测试**。测试使用内存 SQLite，不依赖真实 MySQL/Redis。

### 5. 提交规范

#### 5.1 Commit Message

推荐使用 **Conventional Commits**：

| 类型 | 用途 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | bug 修复 |
| `docs:` | 仅文档变更 |
| `refactor:` | 重构（不改外部行为） |
| `test:` | 仅测试相关 |
| `ci:` | CI/CD 配置 |
| `chore:` | 构建、依赖等杂项 |

示例：`fix(assessment): 修复 Dify 超时未回写 FAILED 状态的问题`

#### 5.2 PR 流程

1. Fork 本仓库（外部贡献者）或基于 `develop` 拉取功能分支（内部贡献者）
2. 分支命名：`feat/xxx`、`fix/xxx`、`docs/xxx`
3. 提交前本地必须通过 `ruff check .` 与 `pytest`
4. 提 PR 到 `develop` 分支，PR 描述需说明：**做了什么、为什么、如何验证**
5. CI 必须全绿才会进入 review
6. 至少 1 名维护者 approve 后合并；冲突由 PR 作者负责解决

### 6. 报告问题

- **Bug**：请使用 Bug Report 模板，附最小复现步骤、期望与实际行为、日志截图
- **新功能建议**：请使用 Feature Request 模板，说明使用场景与价值
- **安全漏洞**：**不要在 Issue 公开**，请按 [SECURITY.md](SECURITY.md) 流程上报

---

## English Version

Thanks for your interest in **EHS Compliance Platform**! This project is an EHS compliance evaluation system built with FastAPI, Celery, Vue, and Dify workflows. We welcome any contribution: bug reports, documentation, features, tests.

### 1. Code of Conduct

By participating, you agree to abide by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be kind and professional.

### 2. Local Development

#### 2.1 System requirements

- Python 3.11 or 3.13
- Node.js 20+ (frontend only)
- Docker + Docker Compose (recommended for MySQL/Redis)
- `antiword` and `poppler-utils` on Linux/macOS for `.doc` / PDF parsing

#### 2.2 Backend setup

```bash
git clone https://github.com/Totoro-qaq/ehs-compliance-platform.git
cd ehs-compliance-platform

python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

cp .env.example .env
docker compose up -d redis mysql
alembic upgrade head

uvicorn main:app --reload
celery -A app.tasks.worker:celery_app worker --loglevel=info
```

#### 2.3 Frontend setup

```bash
cd frontend-vue
npm install
npm run dev
```

### 3. Code Style

#### 3.1 Python

- **Must pass ruff**: `ruff check .` (CI gate)
- Naming: `snake_case` for variables/functions, `PascalCase` for classes
- Full **type hints** required
- EHS business rules and national-standard checks **must include Chinese comments** with rationale
- Strict layering: Router → Service → DAO. No business logic in routers.
- Long-running operations (Dify, PDF parsing, OCR) must run inside Celery tasks.

#### 3.2 Frontend

- Must pass ESLint: `npm run lint`
- Components in `PascalCase.vue`; utilities and stores in `camelCase.js`

### 4. Testing

```bash
pytest
pytest -k auth
```

New features or bug fixes **must include tests**. Tests run on in-memory SQLite and do not require a real MySQL/Redis.

### 5. Commit & PR Conventions

#### 5.1 Commit messages

Use **Conventional Commits**:

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Refactor without behavior change |
| `test:` | Tests only |
| `ci:` | CI/CD config |
| `chore:` | Build, deps, misc |

Example: `fix(assessment): persist FAILED status when Dify call times out`

#### 5.2 Pull Request flow

1. Fork (external) or branch off `develop` (internal)
2. Branch naming: `feat/xxx`, `fix/xxx`, `docs/xxx`
3. Run `ruff check .` and `pytest` locally before opening a PR
4. Target `develop`. Describe **what changed, why, and how it was verified**
5. CI must be green before review
6. At least one maintainer approval is required to merge

### 6. Reporting Issues

- **Bugs**: use the Bug Report template; include minimal repro, expected vs actual, logs.
- **Feature requests**: use the Feature Request template; describe the use case and value.
- **Security**: **do not open a public issue**. Follow [SECURITY.md](SECURITY.md).
