param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$ComposeProject = "",
    [string]$MysqlService = "mysql",
    [string]$MysqlDatabase = "",
    [string]$MysqlUser = "",
    [string]$MysqlPassword = "",
    [string]$UploadsDir = ".\uploads",
    [switch]$SkipUploads
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

if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "Backup path does not exist: $BackupPath"
}

$MysqlDatabase = if ($MysqlDatabase) { $MysqlDatabase } else { Get-EnvValue "MYSQL_DB" "ehs_system" }
$MysqlUser = if ($MysqlUser) { $MysqlUser } else { Get-EnvValue "MYSQL_USER" "root" }
$MysqlPassword = if ($MysqlPassword) { $MysqlPassword } else { Get-EnvValue "MYSQL_PASSWORD" "changeme" }

$sqlFile = Get-ChildItem -LiteralPath $BackupPath -Filter "mysql-*.sql" | Select-Object -First 1
if ($null -eq $sqlFile) {
    throw "No mysql-*.sql file found under $BackupPath"
}

Write-Host "Restoring MySQL database '$MysqlDatabase' from $($sqlFile.FullName)"
$composeArgs = New-ComposeArgs
$restoreArgs = $composeArgs + @(
    "exec", "-T", $MysqlService,
    "sh", "-c",
    "mysql -u`"$MysqlUser`" -p`"$MysqlPassword`" `"$MysqlDatabase`""
)
Get-Content -Raw -Encoding UTF8 -Path $sqlFile.FullName | & docker @restoreArgs

if (-not $SkipUploads) {
    $uploadsZip = Join-Path $BackupPath "uploads.zip"
    if (Test-Path -LiteralPath $uploadsZip) {
        Write-Host "Restoring uploads to $UploadsDir"
        New-Item -ItemType Directory -Path $UploadsDir -Force | Out-Null
        Expand-Archive -Path $uploadsZip -DestinationPath $UploadsDir -Force
    } else {
        Write-Host "uploads.zip not found; skipping uploads restore"
    }
}

Write-Host "Restore complete"
