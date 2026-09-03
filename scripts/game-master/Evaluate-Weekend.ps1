[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Config = "config/weekends/tip-round-2026-03-07.json",
    [string]$PythonCommand = "python",
    [switch]$SkipSeason
)

. (Join-Path $PSScriptRoot "Workflow.Common.ps1")

$configPath = Resolve-WorkspacePath -Path $Config -MustExist
$weekend = Read-WeekendConfig -ConfigPath $Config
$tipRound = Resolve-WorkspacePath -Path $weekend.tipRound.websiteOutput -MustExist
$submissionsDir = Resolve-WorkspacePath -Path $weekend.submissionsDir -MustExist
$resultExtractor = Resolve-WorkspacePath -Path "services/results-importer/src/extract_result_list.py" -MustExist
$resultMatcher = Resolve-WorkspacePath -Path "services/results-importer/src/match_result_lists.py" -MustExist
$resultReviewer = Resolve-WorkspacePath -Path "services/results-importer/src/review_results.py" -MustExist
$statusManager = Resolve-WorkspacePath -Path "services/results-importer/src/manage_weekend_status.py" -MustExist
$weekendEvaluator = Resolve-WorkspacePath -Path "services/results-importer/src/evaluate_submissions.py" -MustExist
$seasonAggregator = Resolve-WorkspacePath -Path "services/results-importer/src/aggregate_season.py" -MustExist
$normalizedResults = @()

$currentStatus = if ($weekend.status) { [string]$weekend.status } else { "DRAFT" }
if ($currentStatus -notin @("CLOSED", "EVALUATED") -and -not $WhatIfPreference) {
    throw "Die Auswertung benötigt eine geschlossene Tipprunde. Aktueller Status: $currentStatus. Verwende zuerst Set-WeekendStatus.ps1 -Status CLOSED."
}

$resultReviewReport = if ($weekend.resultReviewReport) {
    Resolve-WorkspacePath -Path $weekend.resultReviewReport
}
else {
    Resolve-WorkspacePath -Path "output/reports/results-$($weekend.id).md"
}

if ($weekend.resultsDirectory) {
    $resultsDirectory = Resolve-WorkspacePath -Path $weekend.resultsDirectory -MustExist
    $processedDirectory = Split-Path -Parent (Resolve-WorkspacePath -Path $weekend.tipRound.output)
    $matchPlan = Join-Path $processedDirectory "result-match-plan.json"
    $startListPaths = @($weekend.startLists | ForEach-Object { Resolve-WorkspacePath -Path $_.output -MustExist })
    if ($startListPaths.Count -eq 0) {
        throw "Für die Ergebniszuordnung fehlen normalisierte Startlisten."
    }
    if ($PSCmdlet.ShouldProcess($matchPlan, "Ergebnislisten automatisch den Startlisten zuordnen")) {
        Invoke-PythonStep -PythonCommand $PythonCommand -Label "Ergebnislisten zuordnen" -Arguments (@(
            $resultMatcher,
            "--results-dir", $resultsDirectory,
            "--start-lists"
        ) + $startListPaths + @(
            "--processed-dir", $processedDirectory,
            "--output", $matchPlan,
            "--report", $resultReviewReport
        ))
        $plan = Get-Content -Raw -Encoding UTF8 -LiteralPath $matchPlan | ConvertFrom-Json
        $weekend.results = @($plan.matches)
        Write-Utf8Json -Value $weekend -Path $configPath
    }
}

if (@($weekend.results).Count -eq 0 -and -not $WhatIfPreference) {
    throw "Keine Ergebnislisten konfiguriert. Lege die PDFs in resultsDirectory ab."
}

foreach ($result in $weekend.results) {
    $pdf = Resolve-WorkspacePath -Path $result.pdf -MustExist
    $startList = Resolve-WorkspacePath -Path $result.startList -MustExist
    $output = Resolve-WorkspacePath -Path $result.output
    $normalizedResults += $output
    if ($PSCmdlet.ShouldProcess($output, "Ergebnis aus $pdf extrahieren")) {
        Invoke-PythonStep -PythonCommand $PythonCommand -Label "Ergebnis: $([System.IO.Path]::GetFileName($pdf))" -Arguments @(
            $resultExtractor, $pdf, "--start-list", $startList, "--output", $output
        )
    }
}

$submissionFiles = @(Get-ChildItem -LiteralPath $submissionsDir -Filter "*.json" -File)
if ($PSCmdlet.ShouldProcess($resultReviewReport, "Ergebnisse vor der Auswertung prüfen")) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $resultReviewReport) -Force | Out-Null
    Invoke-PythonStep -PythonCommand $PythonCommand -Label "Ergebnisse prüfen" -Arguments @(
        $resultReviewer, $configPath, "--output", $resultReviewReport
    )
}

$weekendOutput = Resolve-WorkspacePath -Path $weekend.weekendEvaluation.output
$weekendWebsiteOutput = Resolve-WorkspacePath -Path $weekend.weekendEvaluation.websiteOutput
if ($PSCmdlet.ShouldProcess($weekendOutput, "$($submissionFiles.Count) Tippabgaben auswerten")) {
    Invoke-PythonStep -PythonCommand $PythonCommand -Label "Wochenendwertung" -Arguments (@(
        $weekendEvaluator, $tipRound
    ) + $normalizedResults + @(
        "--submissions-dir", $submissionsDir,
        "--season-id", [string]$weekend.seasonId,
        "--output", $weekendOutput,
        "--website-output", $weekendWebsiteOutput
    ))
}

if (-not $SkipSeason) {
    $configuredPattern = [string]$weekend.seasonLeaderboard.weekendPattern
    $patternDirectory = Resolve-WorkspacePath -Path (Split-Path -Parent $configuredPattern) -MustExist
    $patternName = Split-Path -Leaf $configuredPattern
    $weekendItems = @(Get-ChildItem -Path $patternDirectory -Filter $patternName -File | Sort-Object FullName)
    $weekendFiles = @()
    foreach ($weekendItem in $weekendItems) {
        $bundle = Get-Content -Raw -Encoding UTF8 -LiteralPath $weekendItem.FullName | ConvertFrom-Json
        if ([string]$bundle.seasonId -eq [string]$weekend.seasonId) {
            $weekendFiles += $weekendItem.FullName
        }
    }
    if ($weekendFiles.Count -eq 0) {
        throw "Keine Wochenendauswertungen fuer die Saison gefunden: $configuredPattern"
    }
    $seasonOutput = Resolve-WorkspacePath -Path $weekend.seasonLeaderboard.output
    $seasonWebsiteOutput = Resolve-WorkspacePath -Path $weekend.seasonLeaderboard.websiteOutput
    if ($PSCmdlet.ShouldProcess($seasonOutput, "$($weekendFiles.Count) Wochenenden zur Saisonwertung aggregieren")) {
        Invoke-PythonStep -PythonCommand $PythonCommand -Label "Saisonwertung" -Arguments (@(
            $seasonAggregator
        ) + $weekendFiles + @(
            "--output", $seasonOutput,
            "--website-output", $seasonWebsiteOutput
        ))
    }
}

if ($PSCmdlet.ShouldProcess($weekend.id, "Wochenendstatus auf EVALUATED setzen")) {
    Invoke-PythonStep -PythonCommand $PythonCommand -Label "Wochenende abschließen" -Arguments @(
        $statusManager, (Resolve-WorkspacePath -Path $Config -MustExist), "EVALUATED"
    )
}

Write-Host "`nAuswertung abgeschlossen: $($weekend.id)" -ForegroundColor Green
Write-Host "Tippabgaben: $($submissionFiles.Count)"
Write-Host "Website aktualisiert: $weekendWebsiteOutput"
Write-Host "Ergebnis-Prüfbericht: $resultReviewReport"
