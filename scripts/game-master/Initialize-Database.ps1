[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$localConfig = Join-Path $Workspace "config\database.local.json"
if (-not (Test-Path -LiteralPath $localConfig)) {
    Copy-Item -LiteralPath (Join-Path $Workspace "config\database.example.json") -Destination $localConfig
}

python (Join-Path $Workspace "services\api\src\database_cli.py") import-existing
if ($LASTEXITCODE -ne 0) {
    throw "Die Datenbankinitialisierung ist fehlgeschlagen."
}
