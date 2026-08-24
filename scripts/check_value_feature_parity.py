#!/usr/bin/env python3
"""Compare Python training features with the compiled C++ evaluator."""

from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import sys
import tarfile

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.ai.value_fit import BOARD_AREA, FEATURE_NAMES, evaluate_feature_batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-dir", required=True, type=Path)
    parser.add_argument("--selfplay-tar", required=True, type=Path)
    parser.add_argument(
        "--model-json",
        type=Path,
        default=REPOSITORY_ROOT / "src" / "ai" / "value_model_gen217.json",
    )
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument(
        "--model-features-only",
        action="store_true",
        help="ignore compiled-out features that the selected model does not consume",
    )
    parser.add_argument("--blend-json", type=Path)
    parser.add_argument(
        "--legacy-header",
        type=Path,
        default=REPOSITORY_ROOT / "src" / "ai" / "src" / "value_model_gen217_legacy.h",
    )
    args = parser.parse_args()

    module_dir = args.module_dir.resolve()
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(module_dir))
    sys.path.insert(0, str(module_dir))
    import amazon_ai

    with tarfile.open(args.selfplay_tar, "r") as archive:
        member = next(
            item
            for item in archive.getmembers()
            if "/tdata/" in item.name and item.name.endswith(".npz")
        )
        extracted = archive.extractfile(member)
        if extracted is None:
            raise OSError(f"could not read {member.name}")
        with np.load(io.BytesIO(extracted.read())) as npz:
            complete_turn = (npz["globalInputNC"][:, 0] == 0.0) & (
                npz["globalInputNC"][:, 1] == 0.0
            )
            selected = np.flatnonzero(complete_turn)[: args.samples]
            planes = np.unpackbits(
                npz["binaryInputNCHWPacked"][selected, :4, :], axis=2
            )[:, :, :BOARD_AREA].reshape(-1, 4, 10, 10)

    expected = evaluate_feature_batch(planes[:, 1], planes[:, 2], planes[:, 3])
    engine = amazon_ai.AmazonasAI()
    actual = np.empty_like(expected)
    value_error = 0.0
    from src.ai.value_fit import predict_formula_value, predict_relu_value
    import json

    model_document = json.loads(args.model_json.read_text(encoding="utf-8"))
    if model_document["model_type"] == "relu_mlp":
        model = {
            name: np.asarray(model_document[name], dtype=np.float64)
            for name in (
                "input_mean",
                "input_scale",
                "hidden_weights",
                "hidden_bias",
                "output_weights",
                "output_bias",
            )
        }
        expected_values = predict_relu_value(expected, model)
    elif model_document["model_type"] == "phase_formula":
        expected_values = predict_formula_value(expected, model_document)
    else:
        raise ValueError(f"unsupported model type: {model_document['model_type']}")
    result_value_name = "rich_value"
    if args.blend_json is not None:
        from src.ai.value_blend_fit import (
            load_legacy_header,
            predict_calibrated_blend,
            predict_legacy,
        )

        blend_document = json.loads(args.blend_json.read_text(encoding="utf-8"))
        legacy_values = predict_legacy(
            expected, load_legacy_header(args.legacy_header)
        )
        expected_values = predict_calibrated_blend(
            np.clip(expected[:, 5] / 92.0, 0.0, 1.0),
            expected_values,
            legacy_values,
            blend_document,
        )
        result_value_name = "value"
    for index, plane in enumerate(planes):
        board = np.zeros((10, 10), dtype=np.int32)
        board[plane[1].astype(bool)] = 1
        board[plane[2].astype(bool)] = 2
        board[plane[3].astype(bool)] = 3
        queens = [
            np.flatnonzero(plane[1]).tolist(),
            np.flatnonzero(plane[2]).tolist(),
        ]
        result = engine.evaluate_features(board, queens, 1)
        actual[index] = [result[name] for name in FEATURE_NAMES]
        value_error = max(
            value_error, abs(result[result_value_name] - expected_values[index])
        )

    feature_error = np.max(np.abs(actual - expected), axis=0)
    checked_names = set(FEATURE_NAMES)
    if args.model_features_only:
        checked_names = set(model_document.get("coefficient_feature_names", ()))
        phase_name = model_document.get("phase_name")
        if phase_name:
            checked_names.add(phase_name)
    for name, error in zip(FEATURE_NAMES, feature_error):
        if name in checked_names:
            print(f"{name:34s} max_abs_error={error:.3e}")
    print(f"value                    max_abs_error={value_error:.3e}")
    checked_errors = np.asarray(
        [error for name, error in zip(FEATURE_NAMES, feature_error) if name in checked_names]
    )
    if float(checked_errors.max(initial=0.0)) > 1e-9 or value_error > 1e-9:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
