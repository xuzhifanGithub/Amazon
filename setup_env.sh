#!/usr/bin/env bash
# 在项目内创建自带的 Python 虚拟环境 .venv 并安装依赖。
# 复制整个项目到别处后，重新运行本脚本即可重建环境。
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
    echo "[setup] 正在创建虚拟环境 .venv ..."
    "$PY" -m venv .venv
fi

# Windows 的 venv 用 Scripts/，其余用 bin/
if [ -x ".venv/Scripts/python.exe" ]; then
    VENV_PY=".venv/Scripts/python.exe"
else
    VENV_PY=".venv/bin/python"
fi

echo "[setup] 正在安装依赖 ..."
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r requirements.txt

echo "[setup] 环境就绪。用 ./run.sh 启动游戏。"
