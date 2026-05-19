# ============================================================
# scripts/dev_up.ps1
# 一键拉起 EHS 本地开发环境（Windows / PowerShell）
#
# 默认动作：
#   1) 校验仓库根存在 .env（无则提示从 .env.example 复制）
#   2) docker compose up -d redis  （可选: -WithMySQL 时同时启动 mysql）
#   3) alembic upgrade head        （-SkipMigrate 可跳过）
#   4) 在新窗口启动 Uvicorn (--reload)
#   5) 在新窗口启动 Celery Worker (--pool=solo)
#   6) -WithBeat   附加启动 Celery Beat
#   7) -WithFront  附加启动前端静态服务（端口 5173）
#
# 用法：
#   pwsh -File scripts/dev_up.ps1
#   pwsh -File scripts/dev_up.ps1 -WithMySQL -WithBeat -WithFront
#   pwsh -File scripts/dev_up.ps1 -SkipMigrate
# ============================================================

[CmdletBinding()]
param(
    [switch]$WithMySQL,
    [switch]$WithBeat,
    [switch]$WithFront,
    [switch]$SkipMigrate,
    [int]$ApiPort   = 8000,
    [int]$FrontPort = 5173
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
Write-Host "[dev_up] 仓库根: $RepoRoot" -ForegroundColor Cyan

# ---------- 1) 检查 .env ----------
if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot '.env'))) {
    if (Test-Path -LiteralPath (Join-Path $RepoRoot '.env.example')) {
        Write-Host "[dev_up] 未找到 .env，已为你示范命令；请先复制并填好密钥后重试：" -ForegroundColor Yellow
        Write-Host "         Copy-Item .env.example .env" -ForegroundColor Yellow
    } else {
        Write-Host "[dev_up] 仓库根缺少 .env 与 .env.example，无法继续。" -ForegroundColor Red
    }
    exit 1
}

# ---------- 2) docker compose 起 Redis（可选 MySQL） ----------
$composeServices = @('redis')
if ($WithMySQL) { $composeServices += 'mysql' }
Write-Host "[dev_up] 启动依赖容器: $($composeServices -join ', ')" -ForegroundColor Cyan
docker compose up -d @composeServices | Out-Host

# 简单等一下 Redis 就绪
$ready = $false
1..15 | ForEach-Object {
    if ($ready) { return }
    try {
        $ping = docker compose exec -T redis redis-cli ping 2>$null
        if ($ping -match 'PONG') { $ready = $true }
    } catch { }
    if (-not $ready) { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
    Write-Host "[dev_up] Redis 未在 15s 内就绪，继续但稍后服务可能报错。" -ForegroundColor Yellow
} else {
    Write-Host "[dev_up] Redis: PONG" -ForegroundColor Green
}

# ---------- 3) Alembic 迁移 ----------
if (-not $SkipMigrate) {
    Write-Host "[dev_up] 执行 alembic upgrade head" -ForegroundColor Cyan
    try {
        alembic upgrade head | Out-Host
    } catch {
        Write-Host "[dev_up] alembic 失败：$_" -ForegroundColor Red
        Write-Host "         请检查 .env 中 MYSQL_* 是否正确，或加 -SkipMigrate 跳过。" -ForegroundColor Yellow
        exit 1
    }
}

# ---------- 工具：在新窗口运行命令并保持打开 ----------
function Start-DevWindow {
    param(
        [Parameter(Mandatory)] [string]$Title,
        [Parameter(Mandatory)] [string]$Command
    )
    $full = "`$Host.UI.RawUI.WindowTitle = '$Title'; Set-Location '$RepoRoot'; $Command"
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoExit', '-NoProfile', '-Command', $full) | Out-Null
    Write-Host "[dev_up] 已开新窗口: $Title" -ForegroundColor Green
}

# ---------- 4) Uvicorn ----------
Start-DevWindow -Title 'EHS Uvicorn' `
    -Command "python -m uvicorn main:app --reload --host 127.0.0.1 --port $ApiPort"

# ---------- 5) Celery Worker ----------
Start-DevWindow -Title 'EHS Celery Worker' `
    -Command 'celery -A app.tasks.worker.celery_app worker -l info --pool=solo'

# ---------- 6) Celery Beat（可选） ----------
if ($WithBeat) {
    Start-DevWindow -Title 'EHS Celery Beat' `
        -Command 'celery -A app.tasks.worker.celery_app beat -l info'
}

# ---------- 7) 前端（可选） ----------
if ($WithFront) {
    $frontCmd = "Set-Location '$RepoRoot\frontend'; python -m http.server $FrontPort"
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoExit', '-NoProfile', '-Command',
            "`$Host.UI.RawUI.WindowTitle = 'EHS Frontend'; $frontCmd") | Out-Null
    Write-Host "[dev_up] 已开新窗口: EHS Frontend  -> http://127.0.0.1:$FrontPort" -ForegroundColor Green
}

Write-Host ''
Write-Host "[dev_up] 完成。常用入口：" -ForegroundColor Cyan
Write-Host "   API   : http://127.0.0.1:$ApiPort/docs"
Write-Host "   健康  : http://127.0.0.1:$ApiPort/healthz"
if ($WithFront) {
    Write-Host "   前端  : http://127.0.0.1:$FrontPort"
}
Write-Host ''
Write-Host "停止：在各窗口按 Ctrl+C；如需停容器：docker compose down" -ForegroundColor DarkGray
