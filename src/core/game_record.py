"""Versioned, portable Amazons game records."""
from __future__ import annotations

import json
from pathlib import Path


RECORD_VERSION = 1


def export_record(path: str, simulator, replay_snapshots=None) -> None:
    payload = {
        "format": "amazons",
        "version": RECORD_VERSION,
        "board_size": simulator.size,
        "turns": [[[int(r), int(c)] for r, c in turn] for turn in simulator.history_do_chess],
    }
    if not simulator.uses_standard_initial_position:
        payload["initial_position"] = {
            "current_player": int(simulator.initial_player),
            "board": [[int(value) for value in row]
                      for row in simulator.initial_board],
        }
    if replay_snapshots is not None:
        snapshots = list(replay_snapshots)
        if len(snapshots) != len(simulator.history_do_chess):
            raise ValueError("演示快照数量与棋谱回合数不一致")
        payload["replay_snapshots"] = snapshots
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_record(path: str, simulator, include_replay: bool = False,
                include_initial: bool = False):
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
    initial_position = payload.get("initial_position")
    initial_board = None
    initial_player = 1
    if initial_position is not None:
        if not isinstance(initial_position, dict):
            raise ValueError("棋谱自定义初始局面格式无效")
        initial_player = initial_position.get("current_player")
        try:
            initial_board = simulator.validate_initial_position(
                initial_position.get("board"), initial_player)
        except (TypeError, ValueError) as exc:
            raise ValueError("棋谱自定义初始局面格式无效") from exc
    normalized = simulator.validate_turns(
        turns, initial_board, initial_player)
    replay_snapshots = payload.get("replay_snapshots", [])
    if (not isinstance(replay_snapshots, list)
            or (replay_snapshots and len(replay_snapshots) != len(normalized))
            or not all(isinstance(item, dict) for item in replay_snapshots)):
        raise ValueError("棋谱演示快照格式无效")
    if include_replay and include_initial:
        return (normalized, tuple(replay_snapshots), initial_board,
                initial_player)
    if include_replay:
        return normalized, tuple(replay_snapshots)
    if include_initial:
        return normalized, initial_board, initial_player
    return normalized
