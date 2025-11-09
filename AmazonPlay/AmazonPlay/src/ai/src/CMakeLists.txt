# 指定 CMake 的最低版本要求
cmake_minimum_required(VERSION 3.10)

# 定义项目名称和版本
project(amazon_ai LANGUAGES CXX VERSION 1.0)

# =========================================================
# ⚠️ 关键修正区域：解决 MinGW/GCC 找不到 OpenMP 的问题
# =========================================================
# 检查当前编译器是否为 GCC（即 TDM-GCC/MinGW）
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU")
    # 强制设置 OpenMP 所需的编译标志和链接库名称
    # 这样可以绕过 FindOpenMP 模块的自动搜索失败
    set(OpenMP_CXX_FLAGS "-fopenmp" CACHE STRING "" FORCE)
    set(OpenMP_CXX_LIB_NAMES "gomp" CACHE STRING "" FORCE)
    set(OpenMP_gomp_LIBRARY "gomp" CACHE STRING "" FORCE)
endif()
# =========================================================


# 找到 pybind11 库。
find_package(pybind11 CONFIG REQUIRED)

# 找到 OpenMP 库。现在它会使用我们设置的标志和库名称
find_package(OpenMP REQUIRED)

# 添加你的源代码文件。
set(SOURCE_FILES
    cmcts.cpp
)

# 使用 pybind11_add_module 宏来创建 Python 模块。
pybind11_add_module(amazon_ai ${SOURCE_FILES})

# 链接 OpenMP 库。
target_link_libraries(amazon_ai PRIVATE OpenMP::OpenMP_CXX)