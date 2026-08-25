@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    call setup_env.bat --no-pause
    if errorlevel 1 exit /b 1
)

call ".venv\Scripts\activate.bat"
