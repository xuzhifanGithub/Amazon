"""Versioned, portable Amazons game records."""
from __future__ import annotations

import json
from pathlib import Path


RECORD_VERSION = 1


def export_record(path: str, simulator) -> None:
    payload = {
        "format": "amazons",
        "version": RECORD_VERSION,
        "board_size": simulator.size,
        "turns": [[[int(r), int(c)] for r, c in turn] for turn in simulator.history_do_chess],
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_record(path: str, simulator) -> tuple:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取棋谱文件") from exc
    if not isinstance(payload, dict) or payload.get("format") != "amazons":
        raise ValueError("不是有效的 Amazons 棋谱")
    if payload.get("version") != RECORD_VERSION:
        raise ValueError("不支持的棋谱版本")
    if payload.get("board_size") != simulator.size:
        raise ValueError("棋谱棋盘尺寸不匹配")
    turns = payload.get("turns")
    if not isinstance(turns, list):
        raise ValueError("棋谱缺少回合列表")
    return simulator.validate_turns(turns)
