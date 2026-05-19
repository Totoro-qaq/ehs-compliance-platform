# Changelog / 变更日志

> All notable changes to this project will be documented in this file.
> 本文件记录项目所有值得注意的变更。
>
> Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/spec/v2.0.0.html)。
>
> Detailed per-release notes (auto-generated from PRs) are also published on the [GitHub Releases page](https://github.com/Totoro-qaq/ehs-compliance-platform/releases).
> 每次发布的详细 PR 列表也会同步到 [GitHub Releases](https://github.com/Totoro-qaq/ehs-compliance-platform/releases)。

---

## [Unreleased] / 未发布

### Added / 新增
- Bilingual community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, Issue & PR templates / 双语社区文件
- GitHub Actions: CI (ruff + pytest + alembic + frontend build), Release automation (tag-driven), Dependabot (monthly, patch-only) / GitHub Actions 流水线
- CodeQL static analysis workflow / CodeQL 静态分析
- Vue 3 frontend (`frontend-vue/`) replacing the legacy vanilla-JS prototype / Vue 3 前端替换旧版原型
- Request-id propagation through API and Celery worker / 请求 ID 在 API 与 Worker 之间贯通
- `requirements-dev.txt` for pytest / ruff (separated from runtime deps) / 开发依赖独立文件

### Changed / 变更
- Dify workflow client switched to `httpx` with explicit timeouts / Dify 客户端改用 httpx 并显式控制超时
- Logging setup unified across API and Worker / API 与 Worker 日志格式统一
- README rewritten with project status, badges, contribution links / README 重写并增加状态、徽章、贡献入口

### Removed / 移除
- Legacy `frontend/` (vanilla JS) directory in favor of `frontend-vue/` / 移除旧版 vanilla JS 前端

### Security / 安全
- Production-only config validator: refuses to start when dev defaults are detected (`JWT_SECRET`, `MYSQL_PASSWORD`, `CORS_ORIGINS=*`, `APP_DEBUG=true`, etc.) / 生产环境配置校验器：检测到开发期默认值即阻止启动

---

<!--
After cutting a release tag (e.g. v0.1.0), move the items above into a new
section like below, with the actual release date.
打 tag 后，把上面的条目挪到新的版本块中，并填写实际日期。

## [0.1.0] - 2026-XX-XX

### Added
- ...
-->
