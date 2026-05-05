$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

Get-Process -Name "Office_Tool" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

python -m PyInstaller --clean --noconfirm Office_Tool.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$packageDir = Join-Path $PSScriptRoot "package"
$sourceDir = Join-Path $PSScriptRoot "dist\Office_Tool"
$zipPath = Join-Path $packageDir "Office_Tool_windows.zip"

if (!(Test-Path $packageDir)) {
    New-Item -ItemType Directory -Path $packageDir | Out-Null
}

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

$archiveSource = Join-Path $sourceDir "*"
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Compress-Archive -Path $archiveSource -DestinationPath $zipPath
        break
    }
    catch {
        if ($attempt -eq 5) {
            throw
        }
        Start-Sleep -Seconds 2
        if (Test-Path $zipPath) {
            Remove-Item -LiteralPath $zipPath -Force
        }
    }
}

Write-Host "Built package:"
Write-Host $sourceDir
Write-Host $zipPath
