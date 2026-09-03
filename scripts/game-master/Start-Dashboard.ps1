[CmdletBinding()]
param(
    [int]$Port = 4175,
    [string]$PythonCommand = "python",
    [switch]$NoBrowser
)

. (Join-Path $PSScriptRoot "Workflow.Common.ps1")

$dashboard = Resolve-WorkspacePath -Path "services/api/src/server.py" -MustExist
$arguments = @($dashboard, "--port", [string]$Port, "--start-page", "spielleiter")
if ($NoBrowser) {
    $arguments += "--no-browser"
}

Write-Host "Spielleiter-Oberfläche wird gestartet ..." -ForegroundColor Cyan
& $PythonCommand @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Die Spielleiter-Oberfläche konnte nicht gestartet werden."
}
