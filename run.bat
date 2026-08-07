@echo off
REM 用项目自带的 .venv 启动亚马逊棋 GUI。
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [run] 未找到虚拟环境，请先运行 setup_env.bat。
    exit /b 1
)

".venv\Scripts\python.exe" main.py
endlocal
