"""Distill gen217's three-stage Amazons search policy into a tiny CPU MLP.

The KataGo-derived teacher represents a complete Amazons turn as three policy
decisions: choose a queen, choose its destination, and choose the arrow square.
This module keeps that factorization so the native MCTS can cheaply shortlist
complete moves instead of evaluating every legal (from, to, arrow) triple.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
import tarfile

import numpy as np

try:
    from .value_fit import BOARD_AREA, BOARD_SIZE, DIRECTIONS, split_buckets
except ImportError:  # Direct script execution via scripts/fit_mcts_policy.py.
    from value_fit import BOARD_AREA, BOARD_SIZE, DIRECTIONS, split_buckets


INPUT_PLANE_COUNT = 5
STAGE_COUNT = 3
INPUT_SIZE = INPUT_PLANE_COUNT * BOARD_AREA + STAGE_COUNT
POLICY_SIZE = BOARD_AREA


@dataclass(frozen=True)
class PolicyRows:
    inputs: np.ndarray
    targets: np.ndarray
    legal: np.ndarray
    stages: np.ndarray
    game_hash_chunks: np.ndarray


def _legal_mask(planes: np.ndarray, stage: int) -> np.ndarray:
    current = planes[1].reshape(BOARD_SIZE, BOARD_SIZE).astype(bool)
    occupied = planes[1:4].any(axis=0).reshape(BOARD_SIZE, BOARD_SIZE)
    result = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=bool)

    if stage == 0:
        for position in np.flatnonzero(current.ravel()):
            row, column = divmod(int(position), BOARD_SIZE)
            for row_delta, column_delta in DIRECTIONS:
                next_row = row + row_delta
                next_column = column + column_delta
                if (
                    0 <= next_row < BOARD_SIZE
                    and 0 <= next_column < BOARD_SIZE
                    and not occupied[next_row, next_column]
                ):
                    result[row, column] = True
                    break
        return result.ravel()

    marker_plane = 4 if stage == 1 else 5
    markers = np.flatnonzero(planes[marker_plane].ravel())
    if markers.size != 1:
        return result.ravel()
    row, column = divmod(int(markers[0]), BOARD_SIZE)
    for row_delta, column_delta in DIRECTIONS:
        next_row = row + row_delta
        next_column = column + column_delta
        while (
            0 <= next_row < BOARD_SIZE
            and 0 <= next_column < BOARD_SIZE
            and not occupied[next_row, next_column]
        ):
            result[next_row, next_column] = True
            next_row += row_delta
            next_column += column_delta
    return result.ravel()


def rows_from_npz(npz: np.lib.npyio.NpzFile) -> PolicyRows:
    packed = npz["binaryInputNCHWPacked"]
    global_input = npz["globalInputNC"]
    global_targets = npz["globalTargetsNC"]
    target_counts = np.maximum(npz["policyTargetsNCMove"][:, 0, :POLICY_SIZE], 0)
    stages = np.where(
        global_input[:, 0] > 0.0,
        1,
        np.where(global_input[:, 1] > 0.0, 2, 0),
    ).astype(np.uint8)
    selected = np.flatnonzero(
        (global_targets[:, 25] > 0.0)
        & (global_targets[:, 26] > 0.0)
        & (target_counts.sum(axis=1) > 0)
    )
    unpacked = np.unpackbits(packed[selected, :6, :], axis=2)[
        :, :, :BOARD_AREA
    ].astype(np.uint8)
    selected_stages = stages[selected]

    # Planes 1-3 are current queens, opponent queens, and arrows. Planes 4-5
    # mark the chosen queen (stage 1) or moved queen (stage 2).
    spatial = unpacked[:, 1:6, :]
    stage_one_hot = np.eye(STAGE_COUNT, dtype=np.uint8)[selected_stages]
    inputs = np.concatenate((spatial.reshape(selected.size, -1), stage_one_hot), axis=1)
    legal = np.empty((selected.size, POLICY_SIZE), dtype=bool)
    for output_index, stage in enumerate(selected_stages):
        legal[output_index] = _legal_mask(unpacked[output_index], int(stage))

    targets = target_counts[selected].astype(np.int16)
    target_outside_legal = (targets > 0) & ~legal
    if np.any(target_outside_legal):
        raise ValueError("teacher policy contains a target outside the legal mask")
    return PolicyRows(
        inputs=inputs,
        targets=targets,
        legal=legal,
        stages=selected_stages,
        game_hash_chunks=global_targets[selected, 41:47].astype(np.uint64),
    )


def _concatenate(rows: list[PolicyRows], field: str) -> np.ndarray:
    return np.concatenate([getattr(item, field) for item in rows], axis=0)


def load_rows_from_selfplay_tar(
    archive: str | Path,
    max_files: int | None = None,
    progress: bool = True,
) -> PolicyRows:
    archive = Path(archive)
    result: list[PolicyRows] = []
    with tarfile.open(archive, "r") as tar:
        members = sorted(
            (
                member
                for member in tar.getmembers()
                if member.isfile()
                and "/tdata/" in member.name
                and member.name.endswith(".npz")
            ),
            key=lambda member: member.name,
        )
        if max_files is not None:
            members = members[:max_files]
        if not members:
            raise ValueError(f"no tdata NPZ files found in {archive}")
        for index, member in enumerate(members, start=1):
            extracted = tar.extractfile(member)
            if extracted is None:
                raise OSError(f"could not read {member.name}")
            with np.load(io.BytesIO(extracted.read())) as npz:
                item = rows_from_npz(npz)
            result.append(item)
            if progress:
                counts = np.bincount(item.stages, minlength=STAGE_COUNT)
                print(
                    f"[{index:02d}/{len(members):02d}] {Path(member.name).name}: "
                    f"{item.inputs.shape[0]} rows, stages={counts.tolist()}",
                    flush=True,
                )
    return PolicyRows(
        inputs=_concatenate(result, "inputs"),
        targets=_concatenate(result, "targets"),
        legal=_concatenate(result, "legal"),
        stages=_concatenate(result, "stages"),
        game_hash_chunks=_concatenate(result, "game_hash_chunks"),
    )


def save_rows(path: str | Path, rows: PolicyRows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        inputs=rows.inputs,
        targets=rows.targets,
        legal=np.packbits(rows.legal, axis=1),
        stages=rows.stages,
        game_hash_chunks=rows.game_hash_chunks,
    )


def load_rows(path: str | Path) -> PolicyRows:
    with np.load(path) as npz:
        return PolicyRows(
            inputs=npz["inputs"],
            targets=npz["targets"],
            legal=np.unpackbits(npz["legal"], axis=1)[:, :POLICY_SIZE].astype(bool),
            stages=npz["stages"],
            game_hash_chunks=npz["game_hash_chunks"],
        )


def _transform_batch(spatial, targets, legal, transforms):
    import torch

    output_spatial = torch.empty_like(spatial)
    output_targets = torch.empty_like(targets)
    output_legal = torch.empty_like(legal)
    target_grid = targets.reshape(-1, BOARD_SIZE, BOARD_SIZE)
    legal_grid = legal.reshape(-1, BOARD_SIZE, BOARD_SIZE)
    for transform in range(8):
        selected = transforms == transform
        if not torch.any(selected):
            continue
        grids = spatial[selected]
        target_part = target_grid[selected]
        legal_part = legal_grid[selected]
        if transform >= 4:
            grids = torch.flip(grids, dims=(-1,))
            target_part = torch.flip(target_part, dims=(-1,))
            legal_part = torch.flip(legal_part, dims=(-1,))
        rotations = transform % 4
        if rotations:
            grids = torch.rot90(grids, rotations, dims=(-2, -1))
            target_part = torch.rot90(target_part, rotations, dims=(-2, -1))
            legal_part = torch.rot90(legal_part, rotations, dims=(-2, -1))
        output_spatial[selected] = grids
        output_targets[selected] = target_part.reshape(-1, POLICY_SIZE)
        output_legal[selected] = legal_part.reshape(-1, POLICY_SIZE)
    return output_spatial, output_targets, output_legal


def policy_metrics(model, rows: PolicyRows, indices: np.ndarray, device, batch_size=8192):
    import torch

    sums = {
        stage: {
            "rows": 0,
            "cross_entropy": 0.0,
            "top1": 0.0,
            "mass3": 0.0,
            "mass5": 0.0,
            "mass8": 0.0,
            "mass12": 0.0,
        }
        for stage in range(STAGE_COUNT)
    }
    model.eval()
    with torch.no_grad():
        for start in range(0, indices.size, batch_size):
            batch = indices[start : start + batch_size]
            inputs = torch.from_numpy(rows.inputs[batch].astype(np.float32)).to(device)
            counts = torch.from_numpy(rows.targets[batch].astype(np.float32)).to(device)
            legal = torch.from_numpy(rows.legal[batch]).to(device)
            stages = rows.stages[batch]
            target = counts / counts.sum(dim=1, keepdim=True)
            logits = model(inputs).masked_fill(~legal, -1.0e9)
            log_prob = torch.log_softmax(logits, dim=1)
            order = torch.argsort(logits, dim=1, descending=True)
            teacher_best = torch.argmax(target, dim=1)
            for stage in range(STAGE_COUNT):
                stage_mask_np = stages == stage
                if not np.any(stage_mask_np):
                    continue
                stage_mask = torch.from_numpy(stage_mask_np).to(device)
                stage_target = target[stage_mask]
                stage_order = order[stage_mask]
                count = int(stage_target.shape[0])
                bucket = sums[stage]
                bucket["rows"] += count
                bucket["cross_entropy"] += float(
                    (-(stage_target * log_prob[stage_mask]).sum(dim=1)).sum().cpu()
                )
                bucket["top1"] += float(
                    (stage_order[:, 0] == teacher_best[stage_mask]).sum().cpu()
                )
                bucket["mass3"] += float(
                    torch.gather(stage_target, 1, stage_order[:, :3]).sum().cpu()
                )
                bucket["mass5"] += float(
                    torch.gather(stage_target, 1, stage_order[:, :5]).sum().cpu()
                )
                bucket["mass8"] += float(
                    torch.gather(stage_target, 1, stage_order[:, :8]).sum().cpu()
                )
                bucket["mass12"] += float(
                    torch.gather(stage_target, 1, stage_order[:, :12]).sum().cpu()
                )
    return {
        str(stage): {
            key: (value if key == "rows" else value / bucket["rows"])
            for key, value in bucket.items()
        }
        for stage, bucket in sums.items()
        if bucket["rows"] > 0
    }


def train_policy_mlp(
    rows: PolicyRows,
    hidden_size: int = 64,
    epochs: int = 6,
    batch_size: int = 4096,
    learning_rate: float = 1.0e-3,
    seed: int = 217,
):
    import torch

    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(max(1, min(16, torch.get_num_threads())))
    device = torch.device("cpu")

    class PolicyMLP(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.trunk = torch.nn.Sequential(
                torch.nn.Linear(INPUT_SIZE, hidden_size),
                torch.nn.ReLU(),
                torch.nn.Linear(hidden_size, hidden_size),
                torch.nn.ReLU(),
            )
            self.heads = torch.nn.ModuleList(
                torch.nn.Linear(hidden_size, POLICY_SIZE)
                for _ in range(STAGE_COUNT)
            )

        def forward(self, inputs):
            hidden = self.trunk(inputs)
            all_logits = torch.stack([head(hidden) for head in self.heads], dim=1)
            stages = torch.argmax(inputs[:, -STAGE_COUNT:], dim=1)
            return all_logits[torch.arange(inputs.shape[0], device=inputs.device), stages]

    model = PolicyMLP().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1.0e-5)
    buckets = split_buckets(rows.game_hash_chunks)
    train_indices = np.flatnonzero(buckets < 90)
    validation_indices = np.flatnonzero(buckets >= 90)
    print(
        f"policy rows train={train_indices.size} validation={validation_indices.size} "
        f"hidden={hidden_size}",
        flush=True,
    )

    for epoch in range(1, epochs + 1):
        model.train()
        permutation = np.random.permutation(train_indices)
        loss_sum = 0.0
        for start in range(0, permutation.size, batch_size):
            batch = permutation[start : start + batch_size]
            flat = torch.from_numpy(rows.inputs[batch].astype(np.float32)).to(device)
            spatial = flat[:, : INPUT_PLANE_COUNT * BOARD_AREA].reshape(
                -1, INPUT_PLANE_COUNT, BOARD_SIZE, BOARD_SIZE
            )
            stage_features = flat[:, INPUT_PLANE_COUNT * BOARD_AREA :]
            counts = torch.from_numpy(rows.targets[batch].astype(np.float32)).to(device)
            legal = torch.from_numpy(rows.legal[batch]).to(device)
            transforms = torch.randint(0, 8, (flat.shape[0],), device=device)
            spatial, counts, legal = _transform_batch(
                spatial, counts, legal, transforms
            )
            augmented = torch.cat((spatial.reshape(flat.shape[0], -1), stage_features), dim=1)
            target = counts / counts.sum(dim=1, keepdim=True)
            logits = model(augmented).masked_fill(~legal, -1.0e9)
            loss = -(target * torch.log_softmax(logits, dim=1)).sum(dim=1).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach().cpu()) * batch.size
        metrics = policy_metrics(model, rows, validation_indices, device)
        print(
            f"epoch {epoch:02d}/{epochs}: train_ce={loss_sum / permutation.size:.6f} "
            f"validation={json.dumps(metrics, ensure_ascii=False)}",
            flush=True,
        )
    return model, policy_metrics(model, rows, validation_indices, device)


def save_model(path: str | Path, model, hidden_size: int, metrics: dict) -> None:
    state = model.state_dict()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        input_size=np.asarray(INPUT_SIZE),
        hidden_size=np.asarray(hidden_size),
        policy_size=np.asarray(POLICY_SIZE),
        hidden1_weights=state["trunk.0.weight"].cpu().numpy(),
        hidden1_bias=state["trunk.0.bias"].cpu().numpy(),
        hidden2_weights=state["trunk.2.weight"].cpu().numpy(),
        hidden2_bias=state["trunk.2.bias"].cpu().numpy(),
        output_weights=np.stack(
            [state[f"heads.{stage}.weight"].cpu().numpy() for stage in range(STAGE_COUNT)]
        ),
        output_bias=np.stack(
            [state[f"heads.{stage}.bias"].cpu().numpy() for stage in range(STAGE_COUNT)]
        ),
        metrics_json=np.asarray(json.dumps(metrics, ensure_ascii=False)),
    )


def _format_cpp_array(values: np.ndarray, columns: int = 8) -> str:
    flat = np.asarray(values, dtype=np.float32).ravel()
    chunks = []
    for start in range(0, flat.size, columns):
        chunks.append(
            "    " + ", ".join(f"{float(value):.9g}f" for value in flat[start : start + columns])
        )
    return ",\n".join(chunks)


def export_cpp_header(model_path: str | Path, output_path: str | Path) -> None:
    with np.load(model_path) as model:
        input_size = int(model["input_size"])
        hidden_size = int(model["hidden_size"])
        policy_size = int(model["policy_size"])
        arrays = {
            name: model[name]
            for name in (
                "hidden1_weights",
                "hidden1_bias",
                "hidden2_weights",
                "hidden2_bias",
                "output_weights",
                "output_bias",
            )
        }
    names = {
        "hidden1_weights": "HIDDEN1_WEIGHTS",
        "hidden1_bias": "HIDDEN1_BIAS",
        "hidden2_weights": "HIDDEN2_WEIGHTS",
        "hidden2_bias": "HIDDEN2_BIAS",
        "output_weights": "OUTPUT_WEIGHTS",
        "output_bias": "OUTPUT_BIAS",
    }
    declarations = []
    for key, values in arrays.items():
        declarations.append(
            f"inline constexpr float {names[key]}[{values.size}] = {{\n"
            f"{_format_cpp_array(values)}\n}};"
        )
    text = f"""#pragma once

// Generated by policy_fit.py from gen217 three-stage MCTS visit targets.
namespace gen217_policy {{
inline constexpr int INPUT_SIZE = {input_size};
inline constexpr int HIDDEN_SIZE = {hidden_size};
inline constexpr int POLICY_SIZE = {policy_size};

{chr(10).join(declarations)}
}}  // namespace gen217_policy
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
