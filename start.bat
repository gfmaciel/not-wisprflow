@echo off
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
    start "" /D "%~dp0" pythonw.exe "%~dp0launcher.py"
    exit /b 0
)
where pyw.exe >nul 2>nul
if not errorlevel 1 (
    start "" /D "%~dp0" pyw.exe -3 "%~dp0launcher.py"
    exit /b 0
)
echo [not-wisprflow] Python windowless launcher not found.
echo Install Python for Windows or activate the virtual environment.
pause
exit /b 1
