# Small Server Deployment Notes / 小服务器部署说明

## 中文

### 建议配置

- 最低可跑：2 vCPU、4 GB 内存、30 GB 磁盘。
- 更稳妥：2 vCPU、8 GB 内存、50 GB 磁盘，尤其是开启 PDF OCR 或批量上传时。
- 如果服务器内存较小，建议先使用文本层 PDF、TXT、DOCX。默认镜像不安装 OCR 依赖。

### 部署步骤

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

需要扫描 PDF OCR 时再启用覆盖配置：

```bash
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build worker
```

生产环境至少修改这些变量：

- `APP_ENV=prod`
- `APP_DEBUG=false`
- `MYSQL_PASSWORD`
- `JWT_SECRET`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `DIFY_API_KEY`
- `CORS_ORIGINS`

### 健康检查

- `/healthz`：只验证 API 进程是否存活，适合容器 healthcheck。
- `/api/v1/healthz`：v1 前缀下的浅层健康检查。
- `/api/v1/readyz`：验证数据库和 Redis；失败返回 `503`，适合负载均衡或反向代理接入前检查。

### Dify 重试策略

默认只重试可恢复错误：

- `429`
- `500`
- `502`
- `503`
- `504`
- 临时网络错误

默认不重试：

- `400`
- `401`
- `403`
- 非 JSON 响应
- 输出 JSON 结构错误
- schema 校验失败
- 阻塞超时

其中 Dify 工作流执行成功但输出 JSON 结构错误或 schema 校验失败时，评价任务会进入 `NEEDS_REVIEW`，保存 `risks=[]` 和模型原始文本摘要，供前端人工复核；HTTP、网络、鉴权、Dify API 非 JSON 等调用失败仍进入 `FAILED`。

阻塞超时可能表示 Dify 仍在执行。默认 `DIFY_RETRY_ON_TIMEOUT=false` 是为了避免重复扣费和重复工作流运行。

### 轻量可观测性

- API 会返回 `X-Request-Id` 和 `X-Process-Time-Ms`。
- 日志包含 `request_id`、`trace_id`、`span_id`。
- 上传请求、Celery Worker 和 Dify 调用可以通过同一个 `trace_id` 串起来。
- Worker 会把评价任务关键状态写入 `assessment_timeline_events`；任务详情响应包含 `timeline` 和派生的 `waterfall`，前端详情抽屉会展示处理耗时瀑布图。
- 已有数据库升级时需执行 Alembic 迁移 `0004_assessment_timeline_events`。
- 当前没有部署 OpenTelemetry Collector，避免小服务器增加额外内存和运维成本。

### 运维建议

- `uploads/`、`logs/`、MySQL 数据卷和 Redis 数据卷必须持久化。
- `.env` 不要提交到 Git，也不要放进镜像。
- 建议用 Nginx 或 Caddy 处理 HTTPS，再反代到 API 的 `8000` 端口。
- 定期备份 MySQL 数据和 `uploads/`。
- `.dockerignore` 已排除日志、上传文件、缓存、前端构建产物和本地密钥，避免构建上下文过大。
- 默认 `runtime` 镜像不包含 PaddleOCR/PaddlePaddle。OCR Worker 会额外挂载 `paddle_models`，首次运行会下载模型。

### 备份与恢复

```powershell
.\scripts\backup.ps1
.\scripts\restore.ps1 -BackupPath .\backups\20260520-120000
```

备份脚本依赖 Docker Compose 中的 MySQL 服务，会生成 SQL dump、`uploads.zip` 和 `manifest.json`。

## English

### Recommended Size

- Minimum runnable size: 2 vCPU, 4 TEST-STD, 30 TEST-STD
- Safer size: 2 vCPU, 8 TEST-STD, 50 TEST-STD, especially when PDF OCR or batch uploads are enabled.
- On small-memory servers, prefer text-layer PDFs, TXT, and DOCX first. The default image does not install OCR dependencies.

### Deployment Steps

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Enable the OCR override only when scanned PDFs are required:

```bash
docker compose -f docker-compose.yml -f docker-compose.ocr.yml up -d --build worker
```

At minimum, change these variables for production:

- `APP_ENV=prod`
- `APP_DEBUG=false`
- `MYSQL_PASSWORD`
- `JWT_SECRET`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `DIFY_API_KEY`
- `CORS_ORIGINS`

### Health Checks

- `/healthz`: shallow API liveness check, suitable for container healthchecks.
- `/api/v1/healthz`: shallow health check under the v1 prefix.
- `/api/v1/readyz`: checks database and Redis; returns `503` on dependency failure, suitable for reverse proxies or load balancers.

### Dify Retry Policy

By default, only recoverable failures are retried:

- `429`
- `500`
- `502`
- `503`
- `504`
- temporary network errors

The following are not retried by default:

- `400`
- `401`
- `403`
- non-JSON responses
- invalid output JSON
- schema validation failures
- blocking timeouts

When the Dify workflow succeeds but the final output has invalid JSON structure or fails schema validation, the assessment task is marked `NEEDS_REVIEW` with `risks=[]` and the raw model text stored for frontend manual review. HTTP, network, auth, and non-JSON Dify API failures still become `FAILED`.

A blocking timeout may mean Dify is still running. Keeping `DIFY_RETRY_ON_TIMEOUT=false` avoids duplicate billing and duplicate workflow execution.

### Lightweight Observability

- The API returns `X-Request-Id` and `X-Process-Time-Ms`.
- Logs include `request_id`, `trace_id`, and `span_id`.
- Upload requests, Celery workers, and Dify calls can be correlated with the same `trace_id`.
- The worker records key assessment states in `assessment_timeline_events`. Task detail responses include `timeline` and derived `waterfall`, and the frontend drawer renders the processing-time waterfall.
- Existing databases must apply Alembic migration `0004_assessment_timeline_events`.
- OpenTelemetry Collector is intentionally not deployed yet to keep memory usage and operations simple on small servers.

### Operations Notes

- Persist `uploads/`, `logs/`, MySQL data, and Redis data.
- Do not commit `.env`, and do not bake it into images.
- Use Nginx or Caddy for HTTPS, then reverse-proxy to API port `8000`.
- Back up MySQL data and `uploads/` regularly.
- `.dockerignore` excludes logs, uploads, caches, frontend build output, and local secrets to keep Docker build context small.
- The default `runtime` image does not include PaddleOCR/PaddlePaddle. The OCR worker mounts `paddle_models`, and the first run downloads models.

### Backup and Restore

```powershell
.\scripts\backup.ps1
.\scripts\restore.ps1 -BackupPath .\backups\20260520-120000
```

The backup script uses the MySQL service from Docker Compose and writes a SQL dump, `uploads.zip`, and `manifest.json`.
