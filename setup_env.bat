@echo off
REM 在项目内创建自带的 Python 虚拟环境 .venv 并安装依赖。
REM 复制整个项目到别处后，重新运行本脚本即可重建环境。
setlocal
cd /d "%~dp0"

if not exist ".venv" (
    echo [setup] 正在创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [setup] 创建虚拟环境失败，请确认已安装 Python 3.11+ 并在 PATH 中。
        exit /b 1
    )
)

echo [setup] 正在安装依赖 ...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [setup] 安装依赖失败。
    exit /b 1
)

echo [setup] 环境就绪。用 run.bat 启动游戏。
endlocal
