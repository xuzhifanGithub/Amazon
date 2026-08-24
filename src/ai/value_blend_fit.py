"""Fit a cheap phase-aware stack of the deployed rich and legacy values."""

from __future__ import annotations

import json
from pathlib import Path
import re

import numpy as np

from .value_fit import FitRows, regression_metrics, split_buckets


def _cpp_array(header: str, name: str) -> np.ndarray:
    match = re.search(
        rf"\b{name}\b[^=]*=\s*\{{(.*?)\}};", header, flags=re.DOTALL
    )
    if match is None:
        raise ValueError(f"could not find {name} in legacy header")
    values = re.findall(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?",
        match.group(1),
    )
    return np.asarray([float(value) for value in values], dtype=np.float64)


def _cpp_scalar(header: str, name: str) -> float:
    match = re.search(
        rf"\b{name}\b\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*;",
        header,
    )
    if match is None:
        raise ValueError(f"could not find scalar {name} in legacy header")
    return float(match.group(1))


def load_legacy_header(path: str | Path) -> dict[str, np.ndarray]:
    header = Path(path).read_text(encoding="utf-8")
    divisors = _cpp_array(header, "INPUT_DIVISORS")
    mean = _cpp_array(header, "INPUT_MEAN")
    scale = _cpp_array(header, "INPUT_SCALE")
    hidden_bias = _cpp_array(header, "HIDDEN_BIAS")
    output_weights = _cpp_array(header, "OUTPUT_WEIGHTS")
    hidden_weights = _cpp_array(header, "HIDDEN_WEIGHTS").reshape(
        hidden_bias.size, divisors.size
    )
    output_bias = np.asarray([_cpp_scalar(header, "OUTPUT_BIAS")])
    return {
        "input_divisors": divisors,
        "input_mean": mean,
        "input_scale": scale,
        "hidden_weights": hidden_weights,
        "hidden_bias": hidden_bias,
        "output_weights": output_weights,
        "output_bias": output_bias,
    }


def predict_legacy(features: np.ndarray, model: dict[str, np.ndarray]) -> np.ndarray:
    # The deployed legacy model consumes t1, t2, mobility, and phase w.
    raw = features[:, [0, 1, 4, 5]] / model["input_divisors"]
    inputs = (raw - model["input_mean"]) / model["input_scale"]
    hidden = np.maximum(
        inputs @ model["hidden_weights"].T + model["hidden_bias"], 0.0
    )
    logits = hidden @ model["output_weights"] + model["output_bias"][0]
    return np.tanh(0.5 * logits)


def _value_logit(values: np.ndarray) -> np.ndarray:
    return 2.0 * np.arctanh(np.clip(values, -0.999999, 0.999999))


def blend_design_matrix(
    phase: np.ndarray,
    rich_value: np.ndarray,
    legacy_value: np.ndarray,
    degree: int,
) -> np.ndarray:
    basis = np.column_stack([phase**power for power in range(degree + 1)])
    return np.column_stack(
        (basis, basis * _value_logit(rich_value)[:, None], basis * _value_logit(legacy_value)[:, None])
    )


def predict_calibrated_blend(
    phase: np.ndarray,
    rich_value: np.ndarray,
    legacy_value: np.ndarray,
    document: dict,
) -> np.ndarray:
    matrix = blend_design_matrix(
        phase, rich_value, legacy_value, int(document["phase_degree"])
    )
    coefficients = np.asarray(document["coefficients"], dtype=np.float64).ravel()
    return np.tanh(0.5 * (matrix @ coefficients))


def fit_calibrated_blend(
    rows: FitRows,
    rich_value: np.ndarray,
    legacy_value: np.ndarray,
    degree: int = 3,
    regularization: float = 1e-4,
    max_iterations: int = 60,
) -> tuple[dict, dict]:
    phase = np.clip(rows.features[:, 5] / 92.0, 0.0, 1.0)
    matrix = blend_design_matrix(phase, rich_value, legacy_value, degree)
    buckets = split_buckets(rows.game_hash_chunks)
    masks = {
        "train": buckets < 80,
        "validation": (buckets >= 80) & (buckets < 90),
        "test": buckets >= 90,
    }
    train = masks["train"]
    x = matrix[train]
    target = np.clip(0.5 * (rows.target[train] + 1.0), 1e-6, 1.0 - 1e-6)
    weight = rows.sample_weight[train]
    normalizer = float(weight.sum())
    column_scale = np.sqrt(np.average(x * x, axis=0, weights=weight))
    column_scale[column_scale < 1e-8] = 1.0
    x = x / column_scale
    coefficients = np.zeros(x.shape[1], dtype=np.float64)
    penalty = np.ones_like(coefficients)
    penalty[: degree + 1] = 0.0

    def sigmoid(logits: np.ndarray) -> np.ndarray:
        result = np.empty_like(logits)
        positive = logits >= 0
        result[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
        exponent = np.exp(logits[~positive])
        result[~positive] = exponent / (1.0 + exponent)
        return result

    def objective(candidate: np.ndarray) -> float:
        logits = x @ candidate
        loss = np.logaddexp(0.0, logits) - target * logits
        return float(weight @ loss / normalizer) + 0.5 * regularization * float(
            np.sum((candidate * penalty) ** 2)
        )

    current = objective(coefficients)
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        logits = x @ coefficients
        probability = sigmoid(logits)
        gradient = x.T @ (weight * (probability - target)) / normalizer
        gradient += regularization * coefficients * penalty
        curvature = weight * probability * (1.0 - probability)
        hessian = x.T @ (x * curvature[:, None]) / normalizer
        diagonal = np.diag_indices_from(hessian)
        hessian[diagonal] += regularization * penalty + 1e-9
        step = np.linalg.solve(hessian, gradient)
        step_size = 1.0
        accepted = False
        while step_size >= 1.0 / 1024.0:
            candidate = coefficients - step_size * step
            candidate_objective = objective(candidate)
            if candidate_objective < current:
                coefficients = candidate
                current = candidate_objective
                accepted = True
                break
            step_size *= 0.5
        iterations = iteration
        if not accepted or np.max(np.abs(step_size * step)) < 1e-9:
            break

    fitted = coefficients / column_scale
    document = {
        "schema_version": 1,
        "model_type": "phase_value_stack",
        "phase_degree": degree,
        "phase_divisor": 92.0,
        "groups": ["bias", "rich_logit", "legacy_logit"],
        "coefficients": fitted.reshape(3, degree + 1).tolist(),
        "regularization": regularization,
        "iterations": iterations,
        "train_bce": current,
    }
    metrics = {}
    current_blend = 0.5 * (rich_value + legacy_value)
    for name, mask in masks.items():
        prediction = predict_calibrated_blend(
            phase[mask], rich_value[mask], legacy_value[mask], document
        )
        metrics[name] = regression_metrics(
            rows.target[mask], prediction, rows.sample_weight[mask]
        )
        metrics[f"current_50_50_{name}"] = regression_metrics(
            rows.target[mask], current_blend[mask], rows.sample_weight[mask]
        )
    document["metrics"] = metrics
    return document, metrics


def write_cpp_header(document: dict, output: str | Path) -> None:
    coefficients = np.asarray(document["coefficients"], dtype=np.float64)
    rows = ",\n".join(
        "    {" + ", ".join(format(value, ".17g") for value in row) + "}"
        for row in coefficients
    )
    degree = int(document["phase_degree"])
    text = f"""#pragma once

#include <algorithm>
#include <cmath>

namespace gen217_value_blend {{
static const int PHASE_DEGREE = {degree};
static const double PHASE_DIVISOR = {float(document['phase_divisor']):.17g};
static const double COEFFICIENTS[3][PHASE_DEGREE + 1] = {{
{rows}
}};

inline double polynomial(int group, double phase) {{
    double result = COEFFICIENTS[group][PHASE_DEGREE];
    for (int degree = PHASE_DEGREE - 1; degree >= 0; --degree)
        result = result * phase + COEFFICIENTS[group][degree];
    return result;
}}

inline double logit(double value) {{
    value = std::max(-0.999999, std::min(0.999999, value));
    return 2.0 * std::atanh(value);
}}

inline double evaluate(double rich, double legacy, double rawPhase) {{
    double phase = std::max(0.0, std::min(1.0, rawPhase / PHASE_DIVISOR));
    double combined = polynomial(0, phase)
        + polynomial(1, phase) * logit(rich)
        + polynomial(2, phase) * logit(legacy);
    return std::tanh(0.5 * combined);
}}
}}  // namespace gen217_value_blend
"""
    Path(output).write_text(text, encoding="utf-8")


def write_json(document: dict, output: str | Path) -> None:
    Path(output).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
