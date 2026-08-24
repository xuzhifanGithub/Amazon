#!/usr/bin/env python3
"""Fit the C++ MCTS scalar evaluator to KataAmazon self-play targets."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.ai.value_fit import (  # noqa: E402
    FEATURE_NAMES,
    FORMULA_DEFAULT_FEATURES,
    fit_formula_value_model,
    fit_logistic_value_model,
    fit_relu_value_model,
    load_rows,
    load_rows_from_selfplay_tar,
    mask_feature_rows,
    formula_model_document,
    model_document,
    relu_model_document,
    save_rows,
    write_model_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfplay-tar", type=Path)
    parser.add_argument("--feature-cache", type=Path)
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--regularization", type=float, default=1e-5)
    parser.add_argument(
        "--teacher-target",
        choices=("immediate", "td-fast", "td-medium", "td-slow", "outcome"),
        default="immediate",
        help="which KataAmazon value target to distill before optional NN blending",
    )
    parser.add_argument(
        "--raw-nn-weight",
        type=float,
        default=0.0,
        help=(
            "teacher blend: 0 uses immediate MCTS value, 1 uses gen217 raw "
            "neural value"
        ),
    )
    parser.add_argument(
        "--model-type",
        choices=("formula", "polynomial", "relu-mlp"),
        default="relu-mlp",
    )
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument(
        "--features",
        help="comma-separated feature names; omitted means all features",
    )
    parser.add_argument(
        "--formula-phase", choices=("w", "empty_count"), default="empty_count"
    )
    parser.add_argument("--formula-degree", type=int, default=3)
    parser.add_argument(
        "--formula-features",
        default=",".join(FORMULA_DEFAULT_FEATURES),
        help="comma-separated signed terms in the fitted phase formula",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "src" / "ai" / "value_model_gen217.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.raw_nn_weight <= 1.0:
        raise SystemExit("--raw-nn-weight must be between 0 and 1")
    if args.reuse_cache:
        if args.feature_cache is None or not args.feature_cache.is_file():
            raise SystemExit("--reuse-cache requires an existing --feature-cache")
        print(f"Loading feature cache: {args.feature_cache}")
        rows = load_rows(args.feature_cache)
    else:
        if args.selfplay_tar is None or not args.selfplay_tar.is_file():
            raise SystemExit("provide an existing --selfplay-tar")
        rows = load_rows_from_selfplay_tar(
            args.selfplay_tar, max_files=args.max_files
        )
        if args.feature_cache is not None:
            save_rows(args.feature_cache, rows)
            print(f"Saved feature cache: {args.feature_cache}")

    teacher_values = {
        "immediate": rows.target,
        "td-fast": rows.td_fast_value,
        "td-medium": rows.td_medium_value,
        "td-slow": rows.td_slow_value,
        "outcome": rows.outcome_value,
    }
    teacher_label = {
        "immediate": "immediate MCTS win-loss",
        "td-fast": "fast TD MCTS win-loss",
        "td-medium": "medium TD MCTS win-loss",
        "td-slow": "slow TD MCTS win-loss",
        "outcome": "final game outcome",
    }[args.teacher_target]
    if args.teacher_target != "immediate":
        rows = replace(rows, target=teacher_values[args.teacher_target])
        print(f"Teacher target: {teacher_label}")

    if args.raw_nn_weight > 0.0:
        raw_nn = np.clip(rows.raw_nn_value, -1.0, 1.0)
        rows = replace(
            rows,
            target=(1.0 - args.raw_nn_weight) * rows.target
            + args.raw_nn_weight * raw_nn,
        )
        print(
            "Teacher blend: "
            f"{1.0 - args.raw_nn_weight:.1%} {teacher_label} + "
            f"{args.raw_nn_weight:.1%} raw gen217 NN"
        )

    if args.features:
        enabled_names = {
            name.strip() for name in args.features.split(",") if name.strip()
        }
        rows = mask_feature_rows(rows, enabled_names)
        print("Enabled features: " + ", ".join(
            name for name in FEATURE_NAMES if name in enabled_names
        ))

    print(f"Fitting {rows.features.shape[0]} complete-turn positions")
    if args.model_type == "formula":
        formula_features = tuple(
            name.strip()
            for name in args.formula_features.split(",")
            if name.strip()
        )
        model, metrics = fit_formula_value_model(
            rows,
            phase_name=args.formula_phase,
            degree=args.formula_degree,
            coefficient_feature_names=formula_features,
            regularization=args.regularization,
        )
        document = formula_model_document(model, metrics, rows)
    elif args.model_type == "polynomial":
        coefficients, metrics = fit_logistic_value_model(
            rows, regularization=args.regularization
        )
        document = model_document(coefficients, metrics, rows)
    else:
        model, metrics = fit_relu_value_model(
            rows, hidden_size=args.hidden_size, epochs=args.epochs
        )
        document = relu_model_document(model, metrics, rows)
    if args.raw_nn_weight > 0.0:
        document["teacher_target"] = (
            f"{1.0 - args.raw_nn_weight:.6g} * {teacher_label} + "
            f"{args.raw_nn_weight:.6g} * raw gen217 NN win-loss"
        )
        document["raw_nn_teacher_weight"] = args.raw_nn_weight
    elif args.teacher_target != "immediate":
        document["teacher_target"] = teacher_label
    write_model_json(args.output, document)
    print(f"Saved model: {args.output}")
    for split in ("train", "validation", "test"):
        values = metrics[split]
        print(
            f"{split:10s} rows={values['rows']:6d} "
            f"rmse={values['weighted_rmse']:.5f} "
            f"spearman={values['spearman']:.5f} "
            f"sign={values['sign_accuracy']:.3%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
