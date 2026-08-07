#!/usr/bin/env bash
# 用项目自带的 .venv 启动亚马逊棋 GUI。
set -e
cd "$(dirname "$0")"

if [ -x ".venv/Scripts/python.exe" ]; then
    VENV_PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
    VENV_PY=".venv/bin/python"
else
    echo "[run] 未找到虚拟环境，请先运行 ./setup_env.sh。"
    exit 1
fi

"$VENV_PY" main.py
