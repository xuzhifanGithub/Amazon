# Native MCTS modules

This directory contains the small prebuilt Windows modules used at runtime:

- `amazon_ai.cp311-win_amd64.pyd`
- `amazon_ai.cp313-win_amd64.pyd`
- `amazon_ai_test.cp311-win_amd64.pyd`
- `amazon_ai_test.cp313-win_amd64.pyd`
- `libgomp_64-1.dll`

Generated CMake build trees are intentionally excluded from the repository.
To rebuild, use the `CMakeLists.txt` files in `src/ai/src` and `src/ai/src2`, then
copy the resulting modules and runtime DLL here.
