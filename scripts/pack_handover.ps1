# ============================================================
# scripts/pack_handover.ps1
# 用途：将仓库打包为可交付给同事的压缩包，自动排除密钥、缓存、
#       日志、上传内容、虚拟环境等不应外发的文件。
#
# 用法（在仓库根目录或任意位置）：
#   pwsh -File scripts/pack_handover.ps1
#   pwsh -File scripts/pack_handover.ps1 -Output D:\handover\ehs.zip
#
# 默认输出：仓库父目录下的 ehs_system_handover_<yyyyMMdd_HHmm>.zip
# ============================================================

[CmdletBinding()]
param(
    [string]$Output
)

$ErrorActionPreference = 'Stop'

# 仓库根目录 = 本脚本所在目录的上一级
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RepoName = Split-Path -Leaf $RepoRoot

if (-not $Output) {
    $stamp  = Get-Date -Format 'yyyyMMdd_HHmm'
    $Output = Join-Path (Split-Path -Parent $RepoRoot) "${RepoName}_handover_${stamp}.zip"
}

# 排除规则（目录名 / 文件名 / 通配）
$ExcludeDirs = @(
    '.git', '.venv', 'venv', 'env', 'ENV',
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.idea', '.vscode',
    'logs', 'node_modules'
)
$ExcludeFiles = @(
    '.env', '.env.local', '.env.dev', '.env.prod',
    'celerybeat-schedule', 'celerybeat.pid',
    'repomix-output.xml',
    '.DS_Store', 'Thumbs.db', 'desktop.ini'
)
$ExcludeExt = @('.pyc', '.pyo', '.log', '.pid')

# 先复制到临时目录，再 Compress-Archive，避免 PS 自带压缩缺乏排除参数
$TempRoot = Join-Path $env:TEMP ("ehs_pack_" + [guid]::NewGuid().ToString('N'))
$StageDir = Join-Path $TempRoot $RepoName
New-Item -ItemType Directory -Path $StageDir -Force | Out-Null

Write-Host "[pack] 仓库根目录 : $RepoRoot"
Write-Host "[pack] 暂存目录   : $StageDir"
Write-Host "[pack] 输出文件   : $Output"
Write-Host "[pack] 复制中..."

Get-ChildItem -LiteralPath $RepoRoot -Recurse -Force | ForEach-Object {
    $item = $_
    $rel  = $item.FullName.Substring($RepoRoot.Length).TrimStart('\','/')

    # 命中任意排除目录
    foreach ($d in $ExcludeDirs) {
        if ($rel -split '[\\/]' -contains $d) { return }
    }
    # 命中排除文件名
    if ($ExcludeFiles -contains $item.Name) { return }
    # 命中扩展名
    if ($ExcludeExt -contains $item.Extension.ToLower()) { return }

    $dest = Join-Path $StageDir $rel
    if ($item.PSIsContainer) {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
    } else {
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Copy-Item -LiteralPath $item.FullName -Destination $dest -Force
    }
}

# uploads 目录保留结构、清空内容（避免泄露历史上传）
$uploads = Join-Path $StageDir 'uploads'
if (Test-Path -LiteralPath $uploads) {
    Get-ChildItem -LiteralPath $uploads -Recurse -Force |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Set-Content -LiteralPath (Join-Path $uploads '.gitkeep') -Value ''
}

# 安全检查：暂存目录里不该出现任何 .env
$leak = Get-ChildItem -LiteralPath $StageDir -Recurse -Force -Filter '.env' -ErrorAction SilentlyContinue
if ($leak) {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force
    throw "[pack] 检测到 .env 残留，已中止：$($leak.FullName -join '; ')"
}

# 输出已存在则覆盖
if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }

Write-Host "[pack] 压缩中..."
Compress-Archive -Path (Join-Path $StageDir '*') -DestinationPath $Output -Force

Remove-Item -LiteralPath $TempRoot -Recurse -Force

$size = (Get-Item -LiteralPath $Output).Length / 1MB
Write-Host ("[pack] 完成：{0}  ({1:N2} MB)" -f $Output, $size)
