# e-Factura Anomaly Audit — Windows installer. From the project folder, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Python { param([string[]]$PyArgs)
    if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 @PyArgs } else { & python @PyArgs }
}

$ok = Invoke-Python @("-c", "import sys; print(sys.version_info >= (3, 11))")
if ($ok -ne "True") {
    Write-Host "Python 3.11 or newer is required: https://www.python.org/downloads/ (tick 'Add python.exe to PATH')." -ForegroundColor Red
    exit 1
}

Write-Host "Creating virtual environment in .venv ..."
Invoke-Python @("-m", "venv", ".venv")
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
Write-Host "Installing e-Factura Anomaly Audit ..."
& .\.venv\Scripts\python.exe -m pip install . --quiet

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Start the app:       scripts\start_app.bat"
Write-Host "  Try the demo first:  .venv\Scripts\efactura-audit -w $env:USERPROFILE\efactura-demo demo"
Write-Host "  Local AI model:      install Ollama from https://ollama.com, run 'ollama pull qwen3:8b',"
Write-Host "                       then approve it: .venv\Scripts\efactura-audit test-model --model qwen3:8b"
