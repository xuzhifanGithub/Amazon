@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [build] Missing .venv. Run setup_env.bat first.
    exit /b 1
)

call ".venv\Scripts\python.exe" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [build] Missing PyInstaller. Run:
    echo .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    exit /b 1
)

echo [build] Building the self-contained portable directory...
call ".venv\Scripts\python.exe" scripts\check_release.py
if errorlevel 1 exit /b 1

call ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean amazons_portable.spec
if errorlevel 1 exit /b 1

call ".venv\Scripts\python.exe" scripts\check_portable.py dist\Amazons
if errorlevel 1 exit /b 1

echo [build] Complete: dist\Amazons\Amazons.exe
endlocal
