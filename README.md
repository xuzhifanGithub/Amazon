# 亚马逊棋 (Game of the Amazons)

基于 PyQt6 的 10×10 亚马逊棋对弈程序，支持人机 / 机机对战，内置多种 AI：
MCTS(C++)，以及基于 **KataGo Amazons 分支**（KataGo 训练方法）的
神经网络引擎 **kataAmazon**，可显示实时胜率与候选着法提示。

## 快速开始

项目自带环境脚本。包含预编译 AI 与 OpenCL 引擎的完整功能版本目前正式支持
**Windows x64 + Python 3.11 / 3.13**：

Windows：

```bat
setup_env.bat   :: 创建 .venv 并安装依赖（首次）
run.bat         :: 启动游戏
```

### 自包含便携版

发布时可生成 `dist/Amazons/` 便携目录。该目录内包含 Python 运行时、PyQt6、NumPy、
MCTS 模块、KataGo 引擎、所需 DLL、XZF-gen028 模型和旧模型；目标电脑不需要另行安装
Python，也不需要在项目目录之外配置模型或引擎文件。

```bat
setup_env.bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
build_portable.bat
```

构建完成后直接复制整个 `dist\Amazons` 文件夹并运行其中的 `Amazons.exe`。不要只复制
单独的 exe，因为配套模型和引擎保存在同一便携目录内。GPU KataGo 仍需要目标 Windows
系统安装可用的显卡/OpenCL 驱动；这是硬件驱动，不能由应用安全替代。没有可用驱动时，
人类对局和项目内置的 MCTS 仍可使用。

Linux / macOS 可运行纯 Python GUI 和人人对弈；MCTS 与 kataAmazon 需要在目标平台
自行编译对应原生模块和引擎：

```bash
./setup_env.sh
./run.sh
```

需要本机已安装 Python 3.11—3.13（推荐 3.11 或 3.13，与预编译的 C++ MCTS 模块匹配）。
缺少某个原生模块、模型或配置时，对应 AI 菜单会自动禁用，程序仍可进行人人对弈。

## AI 引擎说明（kataAmazon）

- **引擎**（两套，均支持 `kata-genmove_analyze`）：
  - `src/ai/kataAmazonEngineCuda/amazons.exe`（**OpenCL/GPU**，**默认优先**）。搭配
    **XZF 正式冠军 gen028** 模型 `amazon10x10_xzf.bin.gz`。需要支持 OpenCL 的显卡及正确安装的驱动；
    随目录附带 `OpenCL.dll` / `libz.dll` / `libzip.dll` / `zlib.dll` / `zip.dll` /
    MSVC 运行库与 `engine.cfg`。首次运行会做一次 OpenCL 自动调优，结果缓存在
    目录内的 `KataGoData/opencltuning/`。
  - `src/ai/kataAmazonEngine/kataAmazon.exe`（原始 **OpenCL/GPU** 引擎，后备）。搭配旧模型
    `weights/amazons10x10.bin.gz`。
  - **默认自动选择**：`amazons_engine.py` 检测到 `kataAmazonEngineCuda/amazons.exe` 存在则用它，
    否则回退到原始引擎。GUI 菜单也可手动切换两者。
- **模型**：`src/ai/kataAmazonEngineCuda/amazon10x10_xzf.bin.gz`
  （当前装入服务器正式冠军 `gen028`；架构 `b20c256legacyv10`，20 残差块 / 256 通道；
  SHA-256 `bd2c04f20ce7c597269c62ac2d1ddf6c6acdafc5a5d8d913998f37efd681fac6`）。
  `gen028` 门控结果为对 `gen027` 23 胜 17 负；训练、门控与默认搜索均使用 600 visits。
- **通信**：以 GTP 子进程运行，用有超时边界的 `kata-genmove_analyze` 获取着法和胜率。
  对局着法只在规则层验证通过后提交到所有引擎；提示使用独立后台线程和当前历史快照，
  不会阻塞界面或继续分析旧棋盘。
- **可移植**：`src/ai/amazons_engine.py` 中所有运行资源都相对该文件计算，正常运行固定使用
  项目或便携目录内随附的引擎、模型与配置，不读取机器上的外部模型路径。

> 注意：XZF-gen028 模型由服务器导出模型兼容转换而来，**只能被配套的 `amazons.exe` 加载**。
> CUDA 版 `katago.exe` 会报 `unknown activation type`，原始 `kataAmazon.exe` 同样无法加载。
> 目录名 `kataAmazonEngineCuda` 是历史遗留，当前其中放的是 OpenCL 版引擎。
>
> 棋力参考：gen028 是该迭代训练线当前通过门控的正式冠军，但尚未单独完成与原始强模型的
> 基准对局；最近一次基准中 gen027 对原始强模型为 0:20。项目只保留界面中实际可选的
> XZF-gen028 与原始强模型后端，不携带未接入运行流程的试验引擎和重复权重。

## 功能

1. **集成新模型**：菜单「游戏 → 黑方/白方 → AI → XZF-gen028（GPU）★★」即可让其对弈。
2. **显示胜率**（仿照参考 Hex 项目）：
   - 右侧信息面板实时显示当前行动方的 AI 胜率百分比；
   - 状态栏显示胜率 / 搜索次数 / 局面估值。
3. **AI 提示**：菜单「显示 → 显示完整回合胜率」(Ctrl+H)，沿最佳着法显示
   `S（选子）→ M（移动）→ A（射箭）` 三个阶段的胜率；三个数值统一为原行动方视角。
   交互提示使用独立的低延迟配置（150/120 visits），正式对局仍使用 600/400 visits。

## 开发与测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

测试覆盖规则执行与悔棋、GTP 分析解析、三阶段视角换算、分析后棋盘恢复、
合法提交广播、过期提示丢弃以及 AI 失败回退。CMake 的临时 `build/` 目录不纳入仓库，
发布用预编译模块放在 `src/ai/native/`。

## 目录结构

```
main.py                         入口
requirements.txt                依赖
setup_env.(bat|sh) / run.(bat|sh)  自带环境脚本
src/
  core/simulator.py             亚马逊棋规则
  ai/
    amazons_engine.py           KataGo 引擎桥接（GTP + 胜率）
    amazon_ai_agent.py          AI 线程调度 + 异步提示查询
    results.py                  跨线程的类型化 AI/提示结果
    native/                     发布用预编译 MCTS 模块（不含 CMake 临时文件）
    kataAmazonEngineCuda/       XZF-gen028 + amazons.exe(OpenCL) + amazon10x10_xzf.bin.gz + dll + 配置（默认）
    kataAmazonEngine/           原始引擎 kataAmazon.exe(OpenCL) + weights/ + engine.cfg（后备）
  gui/
    amazon_board_widget.py      棋盘绘制（含提示圆环）
    amazon_main_window.py       主窗口（菜单 / 胜率显示 / 提示）
```
