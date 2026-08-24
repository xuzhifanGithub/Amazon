#!/usr/bin/env python3
"""Play head-to-head games between two independently loaded MCTS modules."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


INITIAL_RED = [60, 69, 93, 96]
INITIAL_BLUE = [3, 6, 30, 39]
DIRECTIONS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-a", type=Path)
    parser.add_argument("--module-b", type=Path)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=0.05)
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--parallel-games", type=int, default=1)
    parser.add_argument(
        "--engine-threads",
        type=int,
        help="OpenMP thread cap per active engine; auto-sized for parallel games",
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--module-dir", type=Path)
    return parser.parse_args()


def worker(module_dir: Path) -> int:
    module_dir = module_dir.resolve()
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(module_dir))
    sys.path.insert(0, str(module_dir))
    import amazon_ai

    engine = amazon_ai.AmazonasAI()
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("command") == "quit":
            return 0
        board = np.asarray(request["board"], dtype=np.int32).reshape(10, 10)
        result = engine.uct_search(
            board,
            request["queens"],
            int(request["side"]),
            float(request["seconds"]),
            False,
        )
        print(
            json.dumps(
                {
                    "from": result.From,
                    "to": result.To,
                    "stone": result.Stone,
                    "attempt": result.attempt,
                    "value": result.value,
                    "pro": result.pro,
                }
            ),
            flush=True,
        )
    return 0


class EngineProcess:
    def __init__(self, module_dir: Path, engine_threads: int | None = None):
        environment = os.environ.copy()
        environment["PATH"] = str(module_dir.resolve()) + os.pathsep + environment["PATH"]
        if engine_threads is not None:
            environment["OMP_NUM_THREADS"] = str(engine_threads)
            environment["OMP_THREAD_LIMIT"] = str(engine_threads)
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                "--module-dir",
                str(module_dir.resolve()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=environment,
        )

    def move(
        self,
        board: np.ndarray,
        queens: list[list[int]],
        side: int,
        seconds: float,
    ) -> dict[str, float | int]:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        request = {
            "board": board.ravel().tolist(),
            "queens": queens,
            "side": side,
            "seconds": seconds,
        }
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            raise RuntimeError(f"MCTS worker exited with {self.process.poll()}")
        return json.loads(response)

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        assert self.process.stdin is not None
        self.process.stdin.write('{"command":"quit"}\n')
        self.process.stdin.flush()
        self.process.wait(timeout=10)


def has_move(board: np.ndarray, queens: list[list[int]], side: int) -> bool:
    side_index = 0 if side == 1 else 1
    for position in queens[side_index]:
        row, column = divmod(position, 10)
        for row_delta, column_delta in DIRECTIONS:
            next_row = row + row_delta
            next_column = column + column_delta
            if (
                0 <= next_row < 10
                and 0 <= next_column < 10
                and board[next_row, next_column] == 0
            ):
                return True
    return False


def ray_is_clear(board: np.ndarray, start: int, end: int) -> bool:
    start_row, start_column = divmod(start, 10)
    end_row, end_column = divmod(end, 10)
    row_difference = end_row - start_row
    column_difference = end_column - start_column
    if row_difference == 0 and column_difference != 0:
        step = (0, 1 if column_difference > 0 else -1)
    elif column_difference == 0 and row_difference != 0:
        step = (1 if row_difference > 0 else -1, 0)
    elif abs(row_difference) == abs(column_difference) and row_difference != 0:
        step = (
            1 if row_difference > 0 else -1,
            1 if column_difference > 0 else -1,
        )
    else:
        return False
    row = start_row + step[0]
    column = start_column + step[1]
    while (row, column) != (end_row, end_column):
        if board[row, column] != 0:
            return False
        row += step[0]
        column += step[1]
    return board[end_row, end_column] == 0


def apply_move(
    board: np.ndarray,
    queens: list[list[int]],
    side: int,
    move: dict[str, float | int],
) -> None:
    side_index = 0 if side == 1 else 1
    start = int(move["from"])
    end = int(move["to"])
    stone = int(move["stone"])
    if start not in queens[side_index] or not ray_is_clear(board, start, end):
        raise ValueError(f"illegal queen move: {move}")
    board.flat[end] = board.flat[start]
    board.flat[start] = 0
    queens[side_index][queens[side_index].index(start)] = end
    if not ray_is_clear(board, end, stone):
        raise ValueError(f"illegal arrow move: {move}")
    board.flat[stone] = 3


def play_game(
    red_engine: EngineProcess,
    blue_engine: EngineProcess,
    seconds: float,
    max_turns: int,
) -> tuple[int, int, float, int, int]:
    board = np.zeros((10, 10), dtype=np.int32)
    queens = [INITIAL_RED.copy(), INITIAL_BLUE.copy()]
    board.flat[queens[0]] = 1
    board.flat[queens[1]] = 2
    side = 1
    red_attempts = 0
    blue_attempts = 0
    started = time.perf_counter()
    for turn in range(max_turns):
        if not has_move(board, queens, side):
            return -side, turn, time.perf_counter() - started, red_attempts, blue_attempts
        engine = red_engine if side == 1 else blue_engine
        move = engine.move(board, queens, side, seconds)
        if side == 1:
            red_attempts += int(move["attempt"])
        else:
            blue_attempts += int(move["attempt"])
        apply_move(board, queens, side, move)
        side = -side
    return 0, max_turns, time.perf_counter() - started, red_attempts, blue_attempts


def play_index(
    game_index: int,
    module_a: Path,
    module_b: Path,
    seconds: float,
    max_turns: int,
    engine_threads: int | None,
) -> tuple[int, str, int, float, int, int, int, int]:
    engine_a = EngineProcess(module_a, engine_threads)
    engine_b = EngineProcess(module_b, engine_threads)
    a_is_red = game_index % 2 == 0
    try:
        winner, turns, elapsed, red_attempts, blue_attempts = play_game(
            engine_a if a_is_red else engine_b,
            engine_b if a_is_red else engine_a,
            seconds,
            max_turns,
        )
    finally:
        engine_a.close()
        engine_b.close()

    if winner == 0:
        label = "draw"
    elif (winner == 1) == a_is_red:
        label = "A"
    else:
        label = "B"
    a_attempts = red_attempts if a_is_red else blue_attempts
    b_attempts = blue_attempts if a_is_red else red_attempts
    a_turns = (turns + 1) // 2 if a_is_red else turns // 2
    b_turns = turns // 2 if a_is_red else (turns + 1) // 2
    return (
        game_index,
        label,
        turns,
        elapsed,
        a_attempts,
        b_attempts,
        a_turns,
        b_turns,
    )


def compare(args: argparse.Namespace) -> int:
    if args.module_a is None or args.module_b is None:
        raise SystemExit("provide --module-a and --module-b")
    if args.games <= 0 or args.parallel_games <= 0:
        raise SystemExit("--games and --parallel-games must be positive")
    parallel_games = min(args.parallel_games, args.games)
    engine_threads = args.engine_threads
    if engine_threads is None and parallel_games > 1:
        engine_threads = max(1, (os.cpu_count() or 1) // parallel_games)
    print(
        f"running {args.games} games with parallel_games={parallel_games}, "
        f"engine_threads={engine_threads or 'default'}",
        flush=True,
    )

    wins = {"A": 0, "B": 0, "draw": 0}
    attempts_by_engine = {"A": 0, "B": 0}
    turns_by_engine = {"A": 0, "B": 0}
    with ThreadPoolExecutor(max_workers=parallel_games) as executor:
        futures = [
            executor.submit(
                play_index,
                game_index,
                args.module_a,
                args.module_b,
                args.seconds,
                args.max_turns,
                engine_threads,
            )
            for game_index in range(args.games)
        ]
        completed = 0
        for future in as_completed(futures):
            (
                game_index,
                label,
                turns,
                elapsed,
                a_attempts,
                b_attempts,
                a_turns,
                b_turns,
            ) = future.result()
            wins[label] += 1
            attempts_by_engine["A"] += a_attempts
            attempts_by_engine["B"] += b_attempts
            turns_by_engine["A"] += a_turns
            turns_by_engine["B"] += b_turns
            completed += 1
            print(
                f"completed {completed:02d}/{args.games}: "
                f"game={game_index + 1:02d} winner={label} "
                f"turns={turns} elapsed={elapsed:.2f}s",
                flush=True,
            )
    decisive = wins["A"] + wins["B"]
    win_rate = wins["A"] / decisive if decisive else float("nan")
    print(f"summary: {wins}, A decisive win rate={win_rate:.3%}")
    for label in ("A", "B"):
        attempts_per_move = attempts_by_engine[label] / max(turns_by_engine[label], 1)
        print(f"{label} estimated attempts/move={attempts_per_move:.1f}")
    return 0


def main() -> int:
    args = parse_args()
    if args.worker:
        if args.module_dir is None:
            raise SystemExit("worker requires --module-dir")
        return worker(args.module_dir)
    return compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
