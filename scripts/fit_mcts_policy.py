#!/usr/bin/env python3
"""Fit and export the small gen217 policy used to shortlist native MCTS moves."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "ai"))

from policy_fit import (  # noqa: E402
    export_cpp_header,
    load_rows,
    load_rows_from_selfplay_tar,
    save_model,
    save_rows,
    train_policy_mlp,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=4096)
    args = parser.parse_args()

    if args.cache.exists():
        print(f"loading policy cache {args.cache}", flush=True)
        rows = load_rows(args.cache)
    else:
        if args.archive is None:
            parser.error("--archive is required when --cache does not exist")
        rows = load_rows_from_selfplay_tar(args.archive, max_files=args.max_files)
        save_rows(args.cache, rows)
        print(f"saved policy cache {args.cache}", flush=True)

    model, metrics = train_policy_mlp(
        rows,
        hidden_size=args.hidden_size,
        epochs=args.epochs,
        batch_size=args.batch_size,
    )
    save_model(args.model, model, args.hidden_size, metrics)
    export_cpp_header(args.model, args.header)
    print(f"saved model {args.model}", flush=True)
    print(f"saved header {args.header}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
