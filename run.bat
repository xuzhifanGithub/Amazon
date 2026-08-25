@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run] .venv was not found. Creating it now ...
    call setup_env.bat --no-pause
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" main.py
set "RUN_STATUS=%ERRORLEVEL%"
if not "%RUN_STATUS%"=="0" (
    echo.
    echo [run] Application exited with code %RUN_STATUS%.
    pause
)
endlocal & exit /b %RUN_STATUS%

:failed
echo [run] Environment setup failed.
pause
endlocal & exit /b 1
