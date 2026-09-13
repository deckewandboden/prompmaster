param()

$ErrorActionPreference = "Stop"

$Commit = "d36033bdfc87ee5dbacd8459c8cca919ec2f2b45"
$ExpectedArchiveHash = "dda92890a920cc0c659bbdcd44b3a29192ca539178137ff308881daf45c6bb09"
$Project = Join-Path $env:USERPROFILE ".codex\.chatgpt-projects\g-p-6a9bc9d40244819194fa6e2dc5d637ac\promptmaster-commercial\frontend"
$Desktop = [Environment]::GetFolderPath("Desktop")
$OutDir = Join-Path $Desktop "PromptMaster-v13-EXAKT"
$Worktree = Join-Path $env:TEMP ("promptmaster-v13-" + [guid]::NewGuid().ToString("N"))
$SourceZip = Join-Path $OutDir "PromptMaster-v13-SOURCE-EXAKT-d36033.zip"
$DeployTar = Join-Path $OutDir "promptmaster-depth-v13.tar.gz"
$Manifest = Join-Path $OutDir "V13-MASTERINFO.txt"

Write-Host ""
Write-Host "PromptMaster v13 – EXAKTER EXPORT" -ForegroundColor Cyan
Write-Host "Commit: $Commit"
Write-Host ""

if (-not (Test-Path $Project)) {
    throw "Originalprojekt nicht gefunden: $Project"
}

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    $candidates = @(
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe",
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\bin\git.exe",
        "C:\Program Files\Git\cmd\git.exe"
    )
    $gitPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $gitPath) { throw "Git wurde nicht gefunden." }
} else {
    $gitPath = $git.Source
}

# WICHTIG: Safe-directory nur für diesen einzelnen Aufruf, KEINE globale Änderung.
$ProjectGit = ($Project -replace "\\","/")
$gitArgsPrefix = @("-c", "safe.directory=$ProjectGit", "-C", $Project)

function GitProject {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
    & $gitPath @gitArgsPrefix @Args
    if ($LASTEXITCODE -ne 0) {
        throw "Git-Befehl fehlgeschlagen: git $($Args -join ' ')"
    }
}

# Tatsächlich prüfen, ob .git existiert, statt bei Git-Sicherheitsfehler falsch zu behaupten,
# es sei kein Repository.
if (-not (Test-Path (Join-Path $Project ".git"))) {
    throw "Im dokumentierten Projektordner fehlt .git: $Project"
}

$inside = (GitProject rev-parse --is-inside-work-tree | Select-Object -Last 1).Trim()
if ($inside -ne "true") {
    throw "Der dokumentierte Projektordner ist kein gültiges Git-Repository."
}

GitProject cat-file -e "$Commit^{commit}" | Out-Null

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (Test-Path $SourceZip) { Remove-Item $SourceZip -Force }

# Exakter Source-Export direkt aus dem Git-Objektbestand.
& $gitPath @gitArgsPrefix archive --format=zip --output=$SourceZip $Commit
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $SourceZip)) {
    throw "Git-Source-Export fehlgeschlagen."
}

# Temporärer Worktree exakt auf v13.
& $gitPath @gitArgsPrefix worktree add --detach $Worktree $Commit
if ($LASTEXITCODE -ne 0) {
    throw "v13-Worktree konnte nicht erstellt werden."
}

try {
    $deployBuilt = $false

    # Originale OpenAI-Sites-Packaging-Skripte suchen.
    $possibleScripts = @(
        (Join-Path $env:USERPROFILE ".codex\plugins\cache\openai-bundled\sites\0.1.57\skills\sites-hosting\scripts\package-site.sh"),
        (Join-Path $env:USERPROFILE ".codex\plugins\cache\openai-bundled\sites\0.1.58\skills\sites-hosting\scripts\package-site.sh"),
        (Join-Path $env:USERPROFILE ".codex\plugins\cache\openai-bundled\sites\0.1.59\skills\sites-hosting\scripts\package-site.sh")
    )
    $PackageScript = $possibleScripts | Where-Object { Test-Path $_ } | Select-Object -First 1

    $BashCandidates = @(
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\usr\bin\sh.exe",
        "C:\Program Files\Git\usr\bin\sh.exe",
        "C:\Program Files\Git\bin\bash.exe"
    )
    $Bash = $BashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($PackageScript -and $Bash) {
        Push-Location $Worktree
        try {
            if (Test-Path $DeployTar) { Remove-Item $DeployTar -Force }
            $scriptUnix = $PackageScript -replace "\\","/"
            $outUnix = $DeployTar -replace "\\","/"
            & $Bash -c "PATH=/usr/bin:`$PATH; export PATH; /usr/bin/sh.exe '$scriptUnix' . '$outUnix'"
            if ($LASTEXITCODE -eq 0 -and (Test-Path $DeployTar)) {
                $deployBuilt = $true
            }
        } finally {
            Pop-Location
        }
    }

    # Worktree selbst validieren, dort ebenfalls safe.directory nur lokal für den Aufruf.
    $WorktreeGit = ($Worktree -replace "\\","/")
    $commitResolved = (& $gitPath -c "safe.directory=$WorktreeGit" -C $Worktree rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Worktree-Commit konnte nicht geprüft werden." }

    $status = & $gitPath -c "safe.directory=$WorktreeGit" -C $Worktree status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "Worktree-Status konnte nicht geprüft werden." }

    if ($commitResolved -ne $Commit) {
        throw "Sicherheitsprüfung fehlgeschlagen: falscher Commit $commitResolved."
    }
    if ($status) {
        throw "Sicherheitsprüfung fehlgeschlagen: Worktree ist nicht sauber."
    }

    $sourceHash = (Get-FileHash -Algorithm SHA256 $SourceZip).Hash.ToLowerInvariant()

    $deployHash = ""
    $deployStatus = "Nicht erzeugt"
    if ($deployBuilt) {
        $deployHash = (Get-FileHash -Algorithm SHA256 $DeployTar).Hash.ToLowerInvariant()
        if ($deployHash -eq $ExpectedArchiveHash) {
            $deployStatus = "100% BYTEGENAU IDENTISCH mit dem ursprünglich veröffentlichten v13-Archiv"
        } else {
            $deployStatus = "Aus exakt demselben v13-Commit erzeugt; TAR-Hash weicht ab (Packaging-Metadaten/Zeitstempel können abweichen)"
        }
    }

    $info = @"
PROMPTMASTER COMMERCIAL – VERBINDLICHER MASTERSTAND V13
=======================================================

Git-Commit:
$Commit

Live-Version:
13

Originales veröffentlichtes Archiv:
promptmaster-depth-v13.tar.gz

Original SHA-256:
$ExpectedArchiveHash

Originale Archivgröße:
3.297.280 Bytes

Originale Dateianzahl:
28

Originalprojekt:
$Project

Erzeugter exakter Source-Export:
$SourceZip

SHA-256 Source-ZIP:
$sourceHash

Deployment-Paket:
$DeployTar

Deployment-Prüfung:
$deployStatus

Deployment SHA-256:
$deployHash

VALIDIERUNG:
- Source direkt aus Git-Objektbestand von Commit $Commit
- temporärer Worktree exakt auf diesem Commit
- Worktree sauber
- KEINE Rekonstruktion
- KEINE Designänderung
- KEINE globale safe.directory-Änderung
"@

    Set-Content -LiteralPath $Manifest -Value $info -Encoding UTF8

    Write-Host ""
    Write-Host "FERTIG." -ForegroundColor Green
    Write-Host "Ausgabeordner: $OutDir" -ForegroundColor Green
    Write-Host "Source-ZIP: $SourceZip"
    if ($deployBuilt) {
        Write-Host "Deploy-TAR: $DeployTar"
        Write-Host "TAR-Prüfung: $deployStatus"
    } else {
        Write-Host "Hinweis: Das originale Sites-Packaging-Skript wurde lokal nicht gefunden; der Source-ZIP ist trotzdem exakt v13." -ForegroundColor Yellow
    }
    Write-Host ""
    Start-Process explorer.exe $OutDir
}
finally {
    if (Test-Path $Worktree) {
        & $gitPath @gitArgsPrefix worktree remove --force $Worktree 2>$null
        if (Test-Path $Worktree) { Remove-Item -Recurse -Force $Worktree }
    }
}
