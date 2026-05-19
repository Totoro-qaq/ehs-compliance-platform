# 在项目根目录执行：本地已用 docker compose 启动 Redis 后，再开此 Worker。
# Windows 建议 --pool=solo（prefork 在部分环境下易出问题）
Set-Location $PSScriptRoot/..
celery -A app.tasks.worker.celery_app worker -l info --pool=solo
