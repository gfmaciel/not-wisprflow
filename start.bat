@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 (
    echo [not-wisprflow] Cannot open app directory.
    pause
    exit /b 1
)
rem Prefer the same environment where dependencies were installed.
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" /D "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launcher.py"
    exit /b 0
)
if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" /D "%~dp0" "%~dp0venv\Scripts\pythonw.exe" "%~dp0launcher.py"
    exit /b 0
)
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
echo Install Python for Windows or create .venv in this directory.
pause
exit /b 1
