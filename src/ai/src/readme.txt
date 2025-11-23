1.第一次配置（Configure）：在当前cpp目录下打开终端，运行mkdir build
2.运行进入build 目录命令cd build
3.运行cmake ..
或者更具体点cmake .. -DCMAKE_PREFIX_PATH="C:\Users\lenovo\AppData\Roaming\Python\Python311\site-packages\pybind11"
或者更具体点cmake .. -G "MinGW Makefiles" -DCMAKE_C_COMPILER="D:/TDM-GCC-64/bin/gcc.exe" -DCMAKE_CXX_COMPILER="D:/TDM-GCC-64/bin/g++.exe" -DCMAKE_PREFIX_PATH="C:/Users/lenovo/AppData/Roaming/Python/Python311/site-packages/pybind11" -DCMAKE_BUILD_TYPE=Release

4.运行cmake --build . --config Release

