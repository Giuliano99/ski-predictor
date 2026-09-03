[CmdletBinding()]
param(
    [int]$Port = 4175,
    [string]$PythonCommand = "python",
    [switch]$NoBrowser
)

. (Join-Path $PSScriptRoot "Workflow.Common.ps1")

$server = Resolve-WorkspacePath -Path "services/api/src/server.py" -MustExist
$arguments = @($server, "--port", [string]$Port)
if ($NoBrowser) {
    $arguments += "--no-browser"
}

Write-Host "Backend API wird gestartet ..." -ForegroundColor Cyan
& $PythonCommand @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Die Backend API konnte nicht gestartet werden."
}
