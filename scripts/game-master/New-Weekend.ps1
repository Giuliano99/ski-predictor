[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$WeekendDate,
    [string]$SeasonId,
    [string]$Title,
    [bool]$TestMode = $true,
    [switch]$ProductionMode,
    [switch]$Force
)

. (Join-Path $PSScriptRoot "Workflow.Common.ps1")

if ($ProductionMode) {
    $TestMode = $false
}

function ConvertFrom-IsoDate {
    param([Parameter(Mandatory = $true)][string]$Value)

    $parsedDate = [datetime]::MinValue
    $valid = [datetime]::TryParseExact(
        $Value,
        "yyyy-MM-dd",
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None,
        [ref]$parsedDate
    )
    if (-not $valid) {
        throw "Ungültiges Datum '$Value'. Bitte JJJJ-MM-TT verwenden, zum Beispiel 2026-12-05."
    }
    return $parsedDate
}

if ([string]::IsNullOrWhiteSpace($WeekendDate)) {
    $WeekendDate = Read-Host "Erster Renntag (JJJJ-MM-TT)"
}

$firstRaceDate = ConvertFrom-IsoDate -Value $WeekendDate
$dateKey = $firstRaceDate.ToString("yyyy-MM-dd")
$weekendId = "tip-round-$dateKey"
$weekendFolder = "weekend-$dateKey"

if ([string]::IsNullOrWhiteSpace($SeasonId)) {
    $SeasonId = if ($firstRaceDate.Month -ge 7) {
        "{0}-{1}" -f $firstRaceDate.Year, ($firstRaceDate.Year + 1)
    }
    else {
        "{0}-{1}" -f ($firstRaceDate.Year - 1), $firstRaceDate.Year
    }
}
if ([string]::IsNullOrWhiteSpace($Title)) {
    $Title = "Rennwochenende ab {0}" -f $firstRaceDate.ToString("dd.MM.yyyy")
}

$daysSinceSaturday = (([int]$firstRaceDate.DayOfWeek - [int][DayOfWeek]::Saturday) + 7) % 7
$deadline = $firstRaceDate.Date.AddDays(-$daysSinceSaturday)
$timeZone = [TimeZoneInfo]::FindSystemTimeZoneById("W. Europe Standard Time")
$deadlineOffset = [DateTimeOffset]::new($deadline, $timeZone.GetUtcOffset($deadline))

$storageWeekendDirectory = "storage://saisons/$SeasonId/weekends/$dateKey"
$startListDirectory = "$storageWeekendDirectory/startlisten"
$resultsDirectory = "$storageWeekendDirectory/ergebnislisten"
$processedDirectory = "data/result-lists/processed/$weekendFolder"
$submissionsDirectory = "data/submissions/inbox/$weekendId"
$questionsFile = "data/questions/weekend-questions-$dateKey.md"
$configFile = "config/weekends/$weekendId.json"
$reviewReport = "output/reports/review-$weekendId.md"
$configPath = Resolve-WorkspacePath -Path $configFile
$questionsPath = Resolve-WorkspacePath -Path $questionsFile

foreach ($target in @($configPath, $questionsPath)) {
    if ((Test-Path -LiteralPath $target) -and -not $Force) {
        throw "Die Datei existiert bereits: $target. Verwende -Force nur, wenn sie bewusst ersetzt werden soll."
    }
}

foreach ($relativeDirectory in @(
    $startListDirectory,
    $resultsDirectory,
    $processedDirectory,
    $submissionsDirectory,
    "data/submissions/processed",
    "output/reports"
)) {
    $directoryPath = Resolve-WorkspacePath -Path $relativeDirectory
    if ($PSCmdlet.ShouldProcess($directoryPath, "Ordner anlegen")) {
        New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
    }
}

$dateLabel = $firstRaceDate.ToString("dd.MM.yyyy")
$questionTemplate = @"
# Fragen für $Title

> Passe die Vorschläge nach dem Import der Startlisten an. Jede Frage muss klar sagen, für welches Rennen oder welche Rennen sie gilt.

## Wie viele Podiumsplätze erreicht Oberhaching in allen Rennen des Wochenendes ab $dateLabel?
ID: weekend-podium-count
Typ: ANZAHL
Auswertung: PODIUMSPLAETZE
Rennen: ALLE
Hinweis: Alle Rennen und alle Wertungsgruppen des Wochenendes ab $dateLabel
Minimum: 0
Maximum: 100

## Wer erzielt das beste Ergebnis in allen Rennen des Wochenendes ab $dateLabel?
ID: weekend-best-result
Typ: PERSON
Auswertung: BESTES_ERGEBNIS
Rennen: ALLE
Hinweis: Pro Person zählt nur das beste offizielle Ergebnis aus beiden Tagen des Wochenendes ab $dateLabel
Personen: ALLE

## Wie viele Top 10 Ergebnisse erzielt Oberhaching am [TAG] im [DISZIPLIN] des [RENNNAME] in der [ALTERSKLASSE]?
ID: race-top-ten-count
Typ: ANZAHL
Auswertung: TOP_10
Grenze: 10
Rennen: [RENNNAME]
Renndatum: [JJJJ-MM-TT]
Altersklasse: [ALTERSKLASSE]
Hinweis: Es zählt ausschließlich das genannte Rennen am [TAG]
Minimum: 0
Maximum: 20

## Wer ist am [TAG] im [DISZIPLIN] des [RENNNAME] besser: [PERSON 1] oder [PERSON 2]?
ID: race-head-to-head
Typ: DUELL
Auswertung: DIREKTVERGLEICH
Rennen: [RENNNAME]
Renndatum: [JJJJ-MM-TT]
Hinweis: Es zählt ausschließlich das genannte Rennen am [TAG]
Personen: [PERSON 1] | [PERSON 2]

## Welche Platzierung erreicht [PERSON] am [TAG] im [DISZIPLIN] des [RENNNAME] in der [ALTERSKLASSE]?
ID: race-placement
Typ: PLATZIERUNG
Auswertung: PLATZIERUNG
Rennen: [RENNNAME]
Renndatum: [JJJJ-MM-TT]
Altersklasse: [ALTERSKLASSE]
Hinweis: Es zählt ausschließlich das genannte Rennen am [TAG]
Person: [PERSON]
Minimum: 1
Maximum: 60

## Wie lautet am [TAG] im [DISZIPLIN] des [RENNNAME] die interne Reihenfolge der [ALTERSKLASSE UND WERTUNGSGRUPPE]?
ID: race-internal-ranking
Typ: REIHENFOLGE
Auswertung: INTERNE_REIHENFOLGE
Rennen: [RENNNAME]
Renndatum: [JJJJ-MM-TT]
Hinweis: Es zählt ausschließlich das genannte Rennen am [TAG]. Für einen Vergleich nach Platzierung dürfen nur Personen derselben offiziellen Wertungsgruppe eingetragen werden.
Personen: [PERSON 1] | [PERSON 2] | [PERSON 3]
Positionen: 3
"@

$weekendConfig = [ordered]@{
    schemaVersion = 1
    id = $weekendId
    seasonId = $SeasonId
    status = "DRAFT"
    statusHistory = @([ordered]@{
        status = "DRAFT"
        changedAt = [DateTimeOffset]::UtcNow.ToString("o")
    })
    questionsFile = $questionsFile
    startListsDirectory = $startListDirectory
    startLists = @()
    tipRound = [ordered]@{
        title = $Title
        output = "$processedDirectory/tip-round.json"
        websiteOutput = "apps/web/src/data/tip-round.local.json"
        testMode = $TestMode
    }
    resultsDirectory = $resultsDirectory
    results = @()
    submissionsDir = $submissionsDirectory
    weekendEvaluation = [ordered]@{
        output = "data/submissions/processed/weekend-$weekendId.json"
        websiteOutput = "apps/web/src/data/weekend-evaluation.local.json"
    }
    seasonLeaderboard = [ordered]@{
        weekendPattern = "data/submissions/processed/weekend-*.json"
        output = "data/submissions/processed/season-$SeasonId.json"
        websiteOutput = "apps/web/src/data/season-leaderboard.local.json"
    }
    reviewReport = $reviewReport
    resultReviewReport = "output/reports/results-$weekendId.md"
}

if ($PSCmdlet.ShouldProcess($questionsPath, "Fragenvorlage anlegen")) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $questionsPath) -Force | Out-Null
    [IO.File]::WriteAllText($questionsPath, $questionTemplate, [Text.UTF8Encoding]::new($false))
}
if ($PSCmdlet.ShouldProcess($configPath, "Wochenendkonfiguration anlegen")) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $configPath) -Force | Out-Null
    Write-Utf8Json -Value $weekendConfig -Path $configPath
}

Write-Host ""
Write-Host "Das Wochenende wurde angelegt: $Title" -ForegroundColor Green
Write-Host "1. Startlisten nach $startListDirectory kopieren"
Write-Host "2. Fragen in $questionsFile anpassen"
Write-Host "3. Vorbereitung starten:"
Write-Host "   .\scripts\game-master\Prepare-Weekend.ps1 -Config $configFile"
Write-Host "4. Prüfbericht öffnen: $reviewReport"
