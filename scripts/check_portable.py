"""Verify that a portable build contains every runtime AI resource."""
from __future__ import annotations

from pathlib import Path
import sys


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python scripts/check_portable.py <portable-directory>")
        return 2
    root = Path(args[0]).resolve()
    ai = root / "src" / "ai"
    required = [
        root / "Amazons.exe",
        ai / "native" / "libgomp_64-1.dll",
        ai / "kataAmazonEngineCuda" / "amazons.exe",
        ai / "kataAmazonEngineCuda" / "gen012_model.bin.gz",
        ai / "kataAmazonEngineCuda" / "engine.cfg",
        ai / "kataAmazonEngineCuda" / "hint.cfg",
        ai / "kataAmazonEngine" / "kataAmazon.exe",
        ai / "kataAmazonEngine" / "weights" / "amazons10x10.bin.gz",
        ai / "kataAmazonEngine" / "engine.cfg",
        ai / "kataAmazonEngine" / "hint.cfg",
    ]
    native_modules = list((ai / "native").glob("amazon_ai*.pyd"))
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if len(native_modules) != 2:
        missing.append("src/ai/native/amazon_ai*.pyd（需要两个匹配当前 Python 的模块）")
    if missing:
        print("Portable build is incomplete:")
        print("\n".join(missing))
        return 1
    pointers = []
    for path in required:
        with path.open("rb") as handle:
            if handle.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                pointers.append(str(path.relative_to(root)))
    if pointers:
        print("Portable build contains Git LFS pointers instead of real resources:")
        print("\n".join(pointers))
        return 1
    print("Portable build resource check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
