#!/usr/bin/env python3
"""Fit the near-zero-cost phase-aware stack for the deployed evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.value_blend_fit import (  # noqa: E402
    fit_calibrated_blend,
    load_legacy_header,
    predict_legacy,
    write_cpp_header,
    write_json,
)
from src.ai.value_fit import load_rows, predict_formula_value  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-cache", type=Path, required=True)
    parser.add_argument("--rich-model", type=Path, required=True)
    parser.add_argument("--legacy-header", type=Path, required=True)
    parser.add_argument("--degree", type=int, default=3)
    parser.add_argument("--regularization", type=float, default=1e-4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    args = parser.parse_args()

    rows = load_rows(args.feature_cache)
    rich_document = json.loads(args.rich_model.read_text(encoding="utf-8"))
    rich_value = predict_formula_value(rows.features, rich_document)
    legacy_value = predict_legacy(rows.features, load_legacy_header(args.legacy_header))
    document, metrics = fit_calibrated_blend(
        rows,
        rich_value,
        legacy_value,
        degree=args.degree,
        regularization=args.regularization,
    )
    write_json(document, args.output)
    write_cpp_header(document, args.header)
    for split in ("train", "validation", "test"):
        fitted = metrics[split]
        current = metrics[f"current_50_50_{split}"]
        print(
            f"{split:10s} fitted rmse={fitted['weighted_rmse']:.6f} "
            f"spearman={fitted['spearman']:.6f} sign={fitted['sign_accuracy']:.3%}; "
            f"50/50 rmse={current['weighted_rmse']:.6f} "
            f"spearman={current['spearman']:.6f} sign={current['sign_accuracy']:.3%}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
