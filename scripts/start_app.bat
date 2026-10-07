@echo off
rem Start the e-Factura Anomaly Audit app (opens in the browser at http://127.0.0.1:8501)
cd /d "%~dp0\.."
if not exist ".venv\Scripts\efactura-audit.exe" (
    echo Run scripts\install_windows.ps1 first.
    pause
    exit /b 1
)
rem usage: start_app.bat [-w C:\path\to\workspace]
".venv\Scripts\efactura-audit.exe" %* app
