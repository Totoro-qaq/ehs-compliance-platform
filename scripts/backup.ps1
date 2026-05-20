param(
    [string]$BackupDir = ".\backups",
    [string]$ComposeProject = "",
    [string]$MysqlService = "mysql",
    [string]$MysqlDatabase = "",
    [string]$MysqlUser = "",
    [string]$MysqlPassword = "",
    [string]$UploadsDir = ".\uploads"
)

$ErrorActionPreference = "Stop"

function Get-EnvValue([string]$Name, [string]$Default = "") {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    return $value
}

function New-ComposeArgs {
    $args = @("compose")
    if (-not [string]::IsNullOrWhiteSpace($ComposeProject)) {
        $args += @("-p", $ComposeProject)
    }
    return $args
}

$MysqlDatabase = if ($MysqlDatabase) { $MysqlDatabase } else { Get-EnvValue "MYSQL_DB" "ehs_system" }
$MysqlUser = if ($MysqlUser) { $MysqlUser } else { Get-EnvValue "MYSQL_USER" "root" }
$MysqlPassword = if ($MysqlPassword) { $MysqlPassword } else { Get-EnvValue "MYSQL_PASSWORD" "changeme" }

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$targetDir = Join-Path $BackupDir $timestamp
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

$dbOut = Join-Path $targetDir "mysql-$MysqlDatabase.sql"
$uploadsOut = Join-Path $targetDir "uploads.zip"

Write-Host "Backing up MySQL database '$MysqlDatabase' to $dbOut"
$composeArgs = New-ComposeArgs
$dumpArgs = $composeArgs + @(
    "exec", "-T", $MysqlService,
    "sh", "-c",
    "mysqldump -u`"$MysqlUser`" -p`"$MysqlPassword`" --single-transaction --routines --triggers `"$MysqlDatabase`""
)
& docker @dumpArgs | Set-Content -Encoding UTF8 -Path $dbOut

if (Test-Path -LiteralPath $UploadsDir) {
    Write-Host "Compressing uploads from $UploadsDir to $uploadsOut"
    Compress-Archive -Path (Join-Path $UploadsDir "*") -DestinationPath $uploadsOut -Force
} else {
    Write-Host "Uploads directory not found: $UploadsDir"
}

$manifest = [ordered]@{
    created_at = (Get-Date).ToString("o")
    mysql_database = $MysqlDatabase
    mysql_service = $MysqlService
    uploads_dir = $UploadsDir
    files = @(
        (Split-Path -Leaf $dbOut),
        (Split-Path -Leaf $uploadsOut)
    )
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path (Join-Path $targetDir "manifest.json")

Write-Host "Backup complete: $targetDir"
