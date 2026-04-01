param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $repoRoot "logs"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $logDir "host-ui-$timestamp.stdout.log"
$stderrLog = Join-Path $logDir "host-ui-$timestamp.stderr.log"
$latestLogInfo = Join-Path $logDir "host-ui-latest.txt"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Content -Path $stdoutLog -Value "" -Encoding utf8
Set-Content -Path $stderrLog -Value "" -Encoding utf8
Set-Content -Path $latestLogInfo -Value @(
    "stdout=$stdoutLog"
    "stderr=$stderrLog"
) -Encoding utf8

$vendorPythonPath = @(
    (Join-Path $repoRoot ".deps_ui")
    (Join-Path $repoRoot ".deps_legacy")
    (Join-Path $repoRoot ".deps")
    (Join-Path $repoRoot "src")
) -join ";"

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $vendorPythonPath
} else {
    $env:PYTHONPATH = "$vendorPythonPath;$($env:PYTHONPATH)"
}

$candidateSpecs = @()
if (-not [string]::IsNullOrWhiteSpace($env:SOPOTEK_PYTHON_EXE)) {
    $candidateSpecs += @{
        Name = "SOPOTEK_PYTHON_EXE"
        FilePath = $env:SOPOTEK_PYTHON_EXE
        Arguments = @()
    }
}
$candidateSpecs += @(
    @{
        Name = "Python 3.14"
        FilePath = "C:\Python314\python.exe"
        Arguments = @()
    },
    @{
        Name = ".venv"
        FilePath = (Join-Path $repoRoot ".venv\Scripts\python.exe")
        Arguments = @()
    },
    @{
        Name = "py -3.14"
        FilePath = "py.exe"
        Arguments = @("-3.14")
    },
    @{
        Name = "py -3"
        FilePath = "py.exe"
        Arguments = @("-3")
    },
    @{
        Name = "python"
        FilePath = "python.exe"
        Arguments = @()
    }
)

$probeCode = "import PySide6, qasync, keyring, sqlalchemy; print('ok')"
$selected = $null

foreach ($candidate in $candidateSpecs) {
    try {
        $cmd = Get-Command $candidate.FilePath -ErrorAction Stop
        & $cmd.Source @($candidate.Arguments + @("-c", $probeCode)) *> $null
        if ($LASTEXITCODE -eq 0) {
            $selected = @{
                Name = $candidate.Name
                FilePath = $cmd.Source
                Arguments = $candidate.Arguments
            }
            break
        }
    } catch {
        continue
    }
}

if ($null -eq $selected) {
    Write-Error "No compatible Python runtime was found. Install the desktop dependencies or set SOPOTEK_PYTHON_EXE."
}

if ($DryRun) {
    Write-Host "Repo root: $repoRoot"
    Write-Host "Python: $($selected.FilePath) $($selected.Arguments -join ' ')"
    Write-Host "PYTHONPATH: $env:PYTHONPATH"
    Write-Host "stdout log: $stdoutLog"
    Write-Host "stderr log: $stderrLog"
    exit 0
}

$process = Start-Process `
    -FilePath $selected.FilePath `
    -ArgumentList @($selected.Arguments + @("main.py")) `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Start-Sleep -Seconds 3
$process.Refresh()

if ($process.HasExited) {
    Write-Host "Sopotek Trading AI exited during startup. Recent stderr:"
    if (Test-Path $stderrLog) {
        Get-Content $stderrLog | Select-Object -Last 40
    }
    exit 1
}

Write-Host "Sopotek Trading AI launched with $($selected.Name)."
Write-Host "Window title should appear as 'Sopotek Trading AI'."
Write-Host "Logs: $stdoutLog and $stderrLog"
