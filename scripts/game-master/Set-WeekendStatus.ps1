[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Config = "config/weekends/tip-round-2026-03-07.json",
    [Parameter(Mandatory = $true)]
    [ValidateSet("OPEN", "CLOSED", "ARCHIVED", "CANCELLED")]
    [string]$Status,
    [string]$PythonCommand = "python"
)

. (Join-Path $PSScriptRoot "Workflow.Common.ps1")

$configPath = Resolve-WorkspacePath -Path $Config -MustExist
$weekend = Read-WeekendConfig -ConfigPath $Config
$statusManager = Resolve-WorkspacePath -Path "services/results-importer/src/manage_weekend_status.py" -MustExist

if ($Status -eq "OPEN") {
    $reviewer = Resolve-WorkspacePath -Path "services/results-importer/src/review_weekend.py" -MustExist
    $reviewReport = Resolve-WorkspacePath -Path $weekend.reviewReport
    if ($PSCmdlet.ShouldProcess($reviewReport, "Tipprunde vor dem Öffnen erneut prüfen")) {
        Invoke-PythonStep -PythonCommand $PythonCommand -Label "Tipprunde prüfen" -Arguments @(
            $reviewer, $configPath, "--output", $reviewReport
        )
    }
}

if ($PSCmdlet.ShouldProcess($weekend.id, "Status auf $Status setzen")) {
    Invoke-PythonStep -PythonCommand $PythonCommand -Label "Wochenendstatus ändern" -Arguments @(
        $statusManager, $configPath, $Status
    )
}

Write-Host "`nNeuer Status: $Status" -ForegroundColor Green
