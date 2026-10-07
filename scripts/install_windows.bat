@echo off
rem Double-click or run from the project folder. Runs the PowerShell installer without changing
rem the system execution policy (Windows blocks unsigned scripts from downloaded zips).
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1"
pause
