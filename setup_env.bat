@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD="
if not defined KATA_AMAZON_PIP_INDEX set "KATA_AMAZON_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"

where py >nul 2>&1
if not errorlevel 1 py -3.13 -c "import sys" >nul 2>&1 && set "PYTHON_CMD=py -3.13"
if not defined PYTHON_CMD py -3.12 -c "import sys" >nul 2>&1 && set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD py -3.11 -c "import sys" >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD py -3.10 -c "import sys" >nul 2>&1 && set "PYTHON_CMD=py -3.10"

if not defined PYTHON_CMD where python >nul 2>&1
if not defined PYTHON_CMD python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1 && set "PYTHON_CMD=python"

if not defined PYTHON_CMD goto :no_python

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating .venv with %PYTHON_CMD% ...
    call %PYTHON_CMD% -m venv ".venv"
    if errorlevel 1 goto :venv_failed
)

echo [setup] Installing dependencies ...
call ".venv\Scripts\python.exe" -m pip install --index-url "%KATA_AMAZON_PIP_INDEX%" --upgrade pip
if errorlevel 1 goto :install_failed
call ".venv\Scripts\python.exe" -m pip install --index-url "%KATA_AMAZON_PIP_INDEX%" -r requirements.txt
if errorlevel 1 goto :install_failed

echo.
echo [setup] Environment is ready. Run run.bat to start the application.
echo [setup] To activate it in this terminal, run: call activate_env.bat
set "SETUP_STATUS=0"
goto :finish

:no_python
echo [setup] Python 3.10-3.13 was not found.
echo [setup] Install 64-bit Python and enable "Add Python to PATH".
set "SETUP_STATUS=1"
goto :finish

:venv_failed
echo [setup] Failed to create .venv.
set "SETUP_STATUS=1"
goto :finish

:install_failed
echo [setup] Dependency installation failed. Review the pip error above.
set "SETUP_STATUS=1"

:finish
if /i not "%~1"=="--no-pause" pause
endlocal & exit /b %SETUP_STATUS%
