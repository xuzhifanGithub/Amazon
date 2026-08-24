#!/usr/bin/env python3
"""Append detailed combat-mobility features to an existing gen217 cache."""

from __future__ import annotations

import argparse
from dataclasses import fields
import io
from pathlib import Path
import sys
import tarfile

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.ai.value_fit import (  # noqa: E402
    BOARD_AREA,
    BOARD_SIZE,
    FEATURE_NAMES,
    FitRows,
    _queen_distances,
    _queen_geometry,
    combat_detail_features,
    save_rows,
)


DETAIL_NAMES = FEATURE_NAMES[-4:]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--selfplay-tar", type=Path, required=True)
    parser.add_argument("--output-cache", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=2048)
    return parser.parse_args()


def combat_details_from_npz(
    npz: np.lib.npyio.NpzFile, chunk_size: int
) -> np.ndarray:
    packed = npz["binaryInputNCHWPacked"]
    global_input = npz["globalInputNC"]
    global_targets = npz["globalTargetsNC"]
    complete_turn = (global_input[:, 0] == 0.0) & (global_input[:, 1] == 0.0)
    complete_turn &= global_targets[:, 25] > 0.0
    complete_turn &= global_targets[:, 60] > 0.0
    selected = np.flatnonzero(complete_turn)

    chunks: list[np.ndarray] = []
    for start in range(0, selected.size, chunk_size):
        row_indices = selected[start : start + chunk_size]
        planes = np.unpackbits(packed[row_indices, :4, :], axis=2)[
            :, :, :BOARD_AREA
        ].reshape(-1, 4, BOARD_SIZE, BOARD_SIZE)
        current = planes[:, 1].astype(np.bool_)
        opponent = planes[:, 2].astype(np.bool_)
        obstacles = planes[:, 3].astype(np.bool_)
        open_mask = ~(current | opponent | obstacles)
        current_reachable = open_mask & (_queen_distances(open_mask, current) < 127)
        opponent_reachable = open_mask & (
            _queen_distances(open_mask, opponent) < 127
        )
        current_combat = _queen_geometry(
            open_mask, current, contested_destination_mask=opponent_reachable
        )[4]
        opponent_combat = _queen_geometry(
            open_mask, opponent, contested_destination_mask=current_reachable
        )[4]
        chunks.append(combat_detail_features(current_combat, opponent_combat))
    return np.concatenate(chunks, axis=0)


def main() -> int:
    args = parse_args()
    with np.load(args.source_cache) as source:
        old_names = tuple(str(name) for name in source["feature_names"].tolist())
        expected_names = FEATURE_NAMES[: -len(DETAIL_NAMES)]
        if old_names != expected_names:
            raise SystemExit("source cache does not contain the expected old schema")
        cached_fields = {
            field.name: np.asarray(source[field.name])
            for field in fields(FitRows)
            if field.name != "features"
        }
        old_features = np.asarray(source["features"])

    detail_chunks: list[np.ndarray] = []
    with tarfile.open(args.selfplay_tar, "r") as archive:
        members = sorted(
            (
                member
                for member in archive.getmembers()
                if "/tdata/" in member.name and member.name.endswith(".npz")
            ),
            key=lambda member: member.name,
        )
        if not members:
            raise SystemExit("self-play archive contains no tdata NPZ files")
        for index, member in enumerate(members, start=1):
            extracted = archive.extractfile(member)
            if extracted is None:
                raise OSError(f"could not read {member.name}")
            with np.load(io.BytesIO(extracted.read())) as npz:
                details = combat_details_from_npz(npz, args.chunk_size)
            detail_chunks.append(details)
            print(
                f"[{index:02d}/{len(members):02d}] {Path(member.name).name}: "
                f"{details.shape[0]} rows",
                flush=True,
            )

    details = np.concatenate(detail_chunks, axis=0)
    if details.shape[0] != old_features.shape[0]:
        raise SystemExit(
            f"row mismatch: old cache {old_features.shape[0]}, archive {details.shape[0]}"
        )
    rows = FitRows(
        features=np.column_stack((old_features, details)),
        **cached_fields,
    )
    save_rows(args.output_cache, rows)
    print(f"Saved {rows.features.shape} feature cache: {args.output_cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
