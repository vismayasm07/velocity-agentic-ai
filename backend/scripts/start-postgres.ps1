$ErrorActionPreference = "Stop"

$workspaceRoot = Resolve-Path "$PSScriptRoot\..\.."
$postgresBin = Join-Path $workspaceRoot ".local\postgresql-dist\pgsql\bin"
$dataDirectory = Join-Path $workspaceRoot ".local\pgdata"
$logFile = Join-Path $dataDirectory "server.log"

& "$postgresBin\pg_ctl.exe" -D $dataDirectory status *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL is already running on port 5432."
    exit 0
}

& "$postgresBin\pg_ctl.exe" -D $dataDirectory -l $logFile -o '"-p 5432"' start
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "PostgreSQL started on port 5432."