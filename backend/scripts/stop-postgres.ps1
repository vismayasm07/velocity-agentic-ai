$ErrorActionPreference = "Stop"

$workspaceRoot = Resolve-Path "$PSScriptRoot\..\.."
$postgresBin = Join-Path $workspaceRoot ".local\postgresql-dist\pgsql\bin"
$dataDirectory = Join-Path $workspaceRoot ".local\pgdata"

& "$postgresBin\pg_ctl.exe" -D $dataDirectory status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PostgreSQL is not running."
    exit 0
}

& "$postgresBin\pg_ctl.exe" -D $dataDirectory stop -m fast
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "PostgreSQL stopped."