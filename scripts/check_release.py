"""Fast resource preflight used locally and by CI."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "src" / "ai"


def main() -> int:
    required = [
        AI / "native" / "amazon_ai.cp311-win_amd64.pyd",
        AI / "native" / "amazon_ai.cp313-win_amd64.pyd",
        AI / "native" / "amazon_ai_test.cp311-win_amd64.pyd",
        AI / "native" / "amazon_ai_test.cp313-win_amd64.pyd",
        AI / "native" / "libgomp_64-1.dll",
        AI / "kataAmazonEngineCuda" / "amazons.exe",
        AI / "kataAmazonEngineCuda" / "amazon10x10_xzf.bin.gz",
        AI / "kataAmazonEngineCuda" / "engine.cfg",
        AI / "kataAmazonEngineCuda" / "hint.cfg",
        AI / "kataAmazonEngine" / "kataAmazon.exe",
        AI / "kataAmazonEngine" / "weights" / "amazons10x10.bin.gz",
        AI / "kataAmazonEngine" / "engine.cfg",
        AI / "kataAmazonEngine" / "hint.cfg",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print("Missing packaged AI resources:")
        print("\n".join(missing))
        return 1
    lfs_pointers = []
    for path in required:
        with path.open("rb") as handle:
            if handle.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                lfs_pointers.append(str(path.relative_to(ROOT)))
    if lfs_pointers:
        print("Git LFS resources were not downloaded:")
        print("\n".join(lfs_pointers))
        return 1
    print("AI resource preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
