//第一次配置（Configure）：在当前cpp目录下打开终端，运行mkdir build：
//cd build
//cmake ..                        ////cmake .. -DCMAKE_PREFIX_PATH="C:\Users\lenovo\AppData\Roaming\Python\Python311\site-packages\pybind11"
//build 目录下运行cmake --build . --config Release



cmake .. -G "MinGW Makefiles" -DCMAKE_C_COMPILER="D:/TDM-GCC-64/bin/gcc.exe" -DCMAKE_CXX_COMPILER="D:/TDM-GCC-64/bin/g++.exe" -DCMAKE_PREFIX_PATH="C:/Users/lenovo/AppData/Roaming/Python/Python311/site-packages/pybind11" -DCMAKE_BUILD_TYPE=Release
