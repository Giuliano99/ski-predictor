$ErrorActionPreference = "Stop"

$utf8Encoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8Encoding
$OutputEncoding = $utf8Encoding
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$script:WorkspaceRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$script:StoragePrefix = "storage://"

function Get-ExternalStorageRoot {
    $settingsPath = Join-Path $script:WorkspaceRoot "config\local-storage.json"
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        throw "Der externe Datenspeicher ist nicht eingerichtet. Kopiere config/local-storage.example.json nach config/local-storage.json und trage den Ordner ein."
    }
    $settings = Get-Content -Raw -Encoding UTF8 -LiteralPath $settingsPath | ConvertFrom-Json
    if ($settings.provider -ne "local-folder" -or [string]::IsNullOrWhiteSpace([string]$settings.root)) {
        throw "config/local-storage.json enthält keine gültige local-folder-Konfiguration."
    }
    $root = [System.IO.Path]::GetFullPath([string]$settings.root)
    if (-not [System.IO.Path]::IsPathRooted($root)) {
        throw "Der externe Datenordner muss als absoluter Pfad angegeben werden."
    }
    return $root
}

function Resolve-WorkspacePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$MustExist
    )

    $allowedRoot = $script:WorkspaceRoot
    $candidate = if ($Path.StartsWith($script:StoragePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $allowedRoot = Get-ExternalStorageRoot
        Join-Path $allowedRoot $Path.Substring($script:StoragePrefix.Length)
    }
    elseif ([System.IO.Path]::IsPathRooted($Path)) {
        $Path
    }
    else {
        Join-Path $script:WorkspaceRoot $Path
    }
    $resolved = [System.IO.Path]::GetFullPath($candidate)
    if ([System.IO.Path]::IsPathRooted($Path) -and -not $Path.StartsWith($script:StoragePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $externalRoot = Get-ExternalStorageRoot
        $workspacePrefix = $script:WorkspaceRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        $externalPrefix = $externalRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        if ($resolved.StartsWith($externalPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            $allowedRoot = $externalRoot
        }
        elseif (-not $resolved.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Pfad liegt außerhalb des Repositories und des Datenspeichers: $Path"
        }
    }
    $rootPrefix = $allowedRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Pfad liegt außerhalb des erlaubten Speicherbereichs: $Path"
    }
    if ($MustExist -and -not (Test-Path -LiteralPath $resolved)) {
        throw "Datei oder Ordner fehlt: $resolved"
    }
    return $resolved
}

function ConvertTo-PortablePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolved = [System.IO.Path]::GetFullPath($Path)
    $workspacePrefix = $script:WorkspaceRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if ($resolved.StartsWith($workspacePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return [System.IO.Path]::GetRelativePath($script:WorkspaceRoot, $resolved).Replace("\", "/")
    }
    $externalRoot = Get-ExternalStorageRoot
    $externalPrefix = $externalRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if ($resolved.StartsWith($externalPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $script:StoragePrefix + [System.IO.Path]::GetRelativePath($externalRoot, $resolved).Replace("\", "/")
    }
    throw "Pfad liegt außerhalb des Repositories und des Datenspeichers: $Path"
}

function Read-WeekendConfig {
    param([Parameter(Mandatory = $true)][string]$ConfigPath)

    $resolvedConfig = Resolve-WorkspacePath -Path $ConfigPath -MustExist
    $config = Get-Content -Raw -Encoding UTF8 -LiteralPath $resolvedConfig | ConvertFrom-Json
    if ($config.schemaVersion -ne 1 -or -not $config.id -or -not $config.seasonId) {
        throw "Ungueltige Wochenendkonfiguration: schemaVersion, id und seasonId werden benoetigt."
    }
    return $config
}

function Invoke-PythonStep {
    param(
        [Parameter(Mandatory = $true)][string]$PythonCommand,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )

    Write-Host "`n[$Label]" -ForegroundColor Cyan
    & $PythonCommand @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label ist mit Exitcode $LASTEXITCODE fehlgeschlagen."
    }
}

function Copy-GeneratedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Write-Utf8Json {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $json = $Value | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}
