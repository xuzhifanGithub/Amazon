# Native MCTS modules

This directory contains the small prebuilt Windows modules used at runtime:

- `amazon_ai.cp310-win_amd64.pyd`
- `amazon_ai.cp311-win_amd64.pyd`
- `amazon_ai.cp313-win_amd64.pyd`
- `amazon_ai_basic.cp310-win_amd64.pyd`
- `amazon_ai_basic.cp311-win_amd64.pyd`
- `amazon_ai_basic.cp313-win_amd64.pyd`
- `libgomp-1.dll`
- `libwinpthread-1.dll`
- `libgcc_s_seh-1.dll`
- `libdl.dll`

Generated CMake build trees are intentionally excluded from the repository.
To rebuild, use the `CMakeLists.txt` file in `src/ai/src`, then copy the
resulting module and runtime DLL here.

The portable build selects the module matching its build-time Python version
and bundles it together with the MinGW/OpenMP runtime DLLs listed above.

`amazon_ai` includes the gen217 18-feature value evaluator;
`amazon_ai_basic` preserves the original phase-dependent formula. Training,
feature definitions, parity checks, and benchmark results are documented in
`docs/GEN217_VALUE_DISTILLATION.md`.
