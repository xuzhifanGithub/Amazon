"""Fast resource preflight used locally and by CI."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "src" / "ai"


def main() -> int:
    required = [
        AI / "kataAmazonEngineCuda" / "amazons.exe",
        AI / "kataAmazonEngineCuda" / "gen012_model.bin.gz",
        AI / "kataAmazonEngineCuda" / "engine.cfg",
        AI / "kataAmazonEngine" / "kataAmazon.exe",
        AI / "kataAmazonEngine" / "weights" / "amazons10x10.bin.gz",
        AI / "kataAmazonEngine" / "engine.cfg",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print("Missing packaged AI resources:")
        print("\n".join(missing))
        return 1
    print("AI resource preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
