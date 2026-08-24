from pathlib import Path
import sys


ROOT = Path(SPECPATH)
AI = ROOT / "src" / "ai"
PY_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}"


def collect_backend(source: Path, destination: str, model: Path):
    """Collect runtime files only; omit logs, tuning caches, and spare weights."""
    binaries = [
        (str(path), destination)
        for path in source.iterdir()
        if path.is_file() and path.suffix.lower() in {".exe", ".dll"}
    ]
    datas = [
        (str(source / name), destination)
        for name in ("engine.cfg", "hint.cfg")
    ]
    datas.append((str(source / model), str(Path(destination) / model.parent)))
    return binaries, datas


binaries = []
datas = []
for pet_asset in (ROOT / "src" / "assets" / "line_dogs").glob("*.gif"):
    datas.append((str(pet_asset), "src/assets/line_dogs"))
for folder, destination, model in (
    (AI / "kataAmazonEngineCuda", "src/ai/kataAmazonEngineCuda", Path("amazon10x10_xzf.bin.gz")),
    (AI / "kataAmazonEngine", "src/ai/kataAmazonEngine", Path("weights/amazons10x10.bin.gz")),
):
    folder_binaries, folder_datas = collect_backend(folder, destination, model)
    binaries.extend(folder_binaries)
    datas.extend(folder_datas)

matching_module = AI / "native" / f"amazon_ai.{PY_TAG}-win_amd64.pyd"
if not matching_module.is_file():
    raise SystemExit(
        f"缺少 Python {sys.version_info.major}.{sys.version_info.minor} 对应的 MCTS .pyd 模块")
binaries.append((str(matching_module), "src/ai/native"))
for runtime_dll in (
    "libgomp-1.dll",
    "libwinpthread-1.dll",
    "libgcc_s_seh-1.dll",
    "libdl.dll",
):
    binaries.append((str(AI / "native" / runtime_dll), "src/ai/native"))

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT), str(AI / "native")],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Amazons",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    contents_directory=".",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Amazons",
)
