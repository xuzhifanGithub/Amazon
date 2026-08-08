# Native MCTS modules

This directory contains the small prebuilt Windows modules used at runtime:

- `amazon_ai.cp311-win_amd64.pyd`
- `amazon_ai.cp313-win_amd64.pyd`
- `libgomp_64-1.dll`

Generated CMake build trees are intentionally excluded from the repository.
To rebuild, use the `CMakeLists.txt` file in `src/ai/src`, then copy the
resulting module and runtime DLL here.

The portable build selects the module matching its build-time Python version
and bundles it together with `libgomp_64-1.dll`.
