[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Config = "config/weekends/tip-round-2026-03-07.json",
    [string]$PythonCommand = "python"
)

. (Join-Path $PSScriptRoot "Workflow.Common.ps1")

$configPath = Resolve-WorkspacePath -Path $Config -MustExist
$weekend = Read-WeekendConfig -ConfigPath $Config
$currentStatus = if ($weekend.status) { [string]$weekend.status } else { "DRAFT" }
if ($currentStatus -ne "DRAFT" -and -not $WhatIfPreference) {
    throw "Eine Tipprunde kann nur im Status DRAFT neu vorbereitet werden. Aktueller Status: $currentStatus."
}
$questionsFile = Resolve-WorkspacePath -Path $weekend.questionsFile -MustExist
$extractor = Resolve-WorkspacePath -Path "services/results-importer/src/extract_start_list.py" -MustExist
$generator = Resolve-WorkspacePath -Path "services/results-importer/src/generate_tip_round.py" -MustExist
$reviewer = Resolve-WorkspacePath -Path "services/results-importer/src/review_weekend.py" -MustExist
$normalizedStartLists = @()

if ($weekend.startListsDirectory) {
    $startListDirectory = Resolve-WorkspacePath -Path $weekend.startListsDirectory -MustExist
    $startListPdfs = @(Get-ChildItem -LiteralPath $startListDirectory -Filter "*.pdf" -File | Sort-Object Name)
    if ($startListPdfs.Count -eq 0) {
        throw "Im Startlisten Ordner wurden keine PDFs gefunden: $startListDirectory"
    }

    $processedDirectoryReference = [IO.Path]::GetDirectoryName([string]$weekend.tipRound.output).Replace("\", "/")
    $discoveredStartLists = foreach ($pdf in $startListPdfs) {
        [ordered]@{
            pdf = ConvertTo-PortablePath -Path $pdf.FullName
            output = "$processedDirectoryReference/$($pdf.BaseName).json"
        }
    }
    $weekend.startLists = @($discoveredStartLists)

    if ($PSCmdlet.ShouldProcess($configPath, "$($startListPdfs.Count) Startlisten automatisch eintragen")) {
        Write-Utf8Json -Value $weekend -Path $configPath
    }
}

if (@($weekend.startLists).Count -eq 0) {
    throw "In der Wochenendkonfiguration fehlen Startlisten."
}

foreach ($startList in $weekend.startLists) {
    $pdf = Resolve-WorkspacePath -Path $startList.pdf -MustExist
    $output = Resolve-WorkspacePath -Path $startList.output
    $normalizedStartLists += $output
    if ($PSCmdlet.ShouldProcess($output, "Startliste aus $pdf extrahieren")) {
        Invoke-PythonStep -PythonCommand $PythonCommand -Label "Startliste: $([System.IO.Path]::GetFileName($pdf))" -Arguments @(
            $extractor, $pdf, "--output", $output
        )
    }
}

$tipRoundOutput = Resolve-WorkspacePath -Path $weekend.tipRound.output
$websiteOutput = Resolve-WorkspacePath -Path $weekend.tipRound.websiteOutput
$generatorArguments = @($generator) + $normalizedStartLists + @("--questions", $questionsFile, "--output", $tipRoundOutput)
$generatorArguments += @("--season-id", [string]$weekend.seasonId)
$generatorArguments += @("--status", [string]$(if ($weekend.status) { $weekend.status } else { "DRAFT" }))
if ($weekend.tipRound.title) {
    $generatorArguments += @("--title", [string]$weekend.tipRound.title)
}
if ($weekend.tipRound.testWeekendDate) {
    $generatorArguments += @("--test-weekend-date", [string]$weekend.tipRound.testWeekendDate)
}

if ($PSCmdlet.ShouldProcess($tipRoundOutput, "Tipprunde erzeugen")) {
    Invoke-PythonStep -PythonCommand $PythonCommand -Label "Tipprunde erzeugen" -Arguments $generatorArguments
    if ($weekend.tipRound.testMode) {
        $tipRound = Get-Content -Raw -Encoding UTF8 -LiteralPath $tipRoundOutput | ConvertFrom-Json
        $tipRound | Add-Member -NotePropertyName testMode -NotePropertyValue $true -Force
        if (-not $tipRound.subtitle.StartsWith("Offener Testmodus")) {
            $tipRound.subtitle = "Offener Testmodus | $($tipRound.subtitle)"
        }
        Write-Utf8Json -Value $tipRound -Path $tipRoundOutput
    }
    Copy-GeneratedFile -Source $tipRoundOutput -Destination $websiteOutput
}

$reviewReport = if ($weekend.reviewReport) {
    Resolve-WorkspacePath -Path $weekend.reviewReport
}
else {
    Resolve-WorkspacePath -Path "output/reports/review-$($weekend.id).md"
}

if ($PSCmdlet.ShouldProcess($reviewReport, "Prüfbericht erzeugen")) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $reviewReport) -Force | Out-Null
    Invoke-PythonStep -PythonCommand $PythonCommand -Label "Wochenende prüfen" -Arguments @(
        $reviewer, $configPath, "--output", $reviewReport
    )
}

Write-Host "`nVorbereitung abgeschlossen: $($weekend.id)" -ForegroundColor Green
Write-Host "Website-Datei: $websiteOutput"
Write-Host "Prüfbericht: $reviewReport"
