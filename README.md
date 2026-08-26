<div align="center">

# 亚马逊棋 · Game of the Amazons

一款带有三套神经网络模型、三阶段胜率分析与桌面宠物的 PyQt6 亚马逊棋客户端。

[![Tests](https://github.com/xuzhifanGithub/amazonGame/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/xuzhifanGithub/amazonGame/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.13-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/完整功能-Windows%20x64-0078D4?logo=windows11&logoColor=white)
![Git LFS](https://img.shields.io/badge/models-Git%20LFS-F64935?logo=gitlfs&logoColor=white)

</div>

![亚马逊棋主界面](docs/images/main-window.png)

## 分支说明

- **`main`**：当前项目的开发分支，也是公开仓库的默认分支。
- **`master`**：保留早期亚马逊棋比赛程序与下载资料，仅作为历史归档，不承载当前版本开发。
  旧内容未被删除，可在 [历史 `master` 分支](https://github.com/xuzhifanGithub/Amazon/tree/master) 中继续查看。

## 项目亮点

- **五个 AI 选项**：基础 MCTS★、18 特征 MCTS★★、`amazon_L`★★★，以及
  `amazon_Z`★★★★ 和 `amazon_X`★★★★。
- **完整回合分析**：分别展示“选子 → 移动 → 射箭”的胜率、访问量和 Top-N 候选。
- **赛后棋局演示**：终局后可逐步查看每回合棋盘和当时的右侧分析信息；演示快照随
  `.amazons.json` 棋谱导出，重新导入后仍可回看。
- **自由摆盘**：可点击放置黑白皇后、障碍或擦除棋子，指定先行方后从任意合法局面开始；
  MCTS、`amazon_X`、`amazon_L`、`amazon_Z` 均可直接搜索完整自定义局面。
- **稳定的 AI 生命周期**：请求版本隔离、后台提示、引擎池复用，以及新游戏/悔棋时的旧结果丢弃。
- **可缩放主题界面**：四套棋盘主题、80%—140% 缩放和主题自适应右侧卡片。
- **便携资源布局**：模型、引擎、配置和依赖 DLL 均位于项目内部，不读取机器上的外部模型。
- **轻量桌面宠物**：右侧线条小狗拥有随机动作和简单互动，不影响棋局逻辑。

## 快速开始

项目自带环境脚本。由于模型和原生引擎通过 Git LFS 管理，首次克隆前请先安装
[Git LFS](https://git-lfs.com/) 并执行 `git lfs install`。完整功能版本目前正式支持
**Windows x64 + Python 3.10 / 3.11 / 3.13**：

Windows：

```bat
setup_env.bat   :: 创建 .venv 并安装依赖（首次）
run.bat         :: 启动游戏
call activate_env.bat  :: 可选：在当前终端激活 .venv
```

`setup_env.bat` 负责创建环境和安装依赖，本身不会把调用它的终端永久切换到 `.venv`；
需要激活时必须使用 `call activate_env.bat`。脚本默认使用清华 PyPI 镜像，可通过环境变量
`KATA_AMAZON_PIP_INDEX` 改成其他镜像。

### 自包含便携版

发布时可生成 `dist/Amazons/` 便携目录。该目录内包含 Python 运行时、PyQt6、NumPy、
MCTS 模块、KataGo 引擎、所需 DLL，以及 `amazon_X`、`amazon_Z`、`amazon_L` 三个模型；目标电脑不需要另行安装
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

需要本机安装 Python 3.10、3.11 或 3.13；三个版本均配有预编译的 C++ MCTS 模块。
缺少某个原生模块、模型或配置时，对应 AI 菜单会自动禁用，程序仍可进行人人对弈。

## AI 引擎说明

- **基础 MCTS★**：使用项目原始的分阶段四特征公式估值器，适合入门练习。
- **18 特征 MCTS★★**：搜索框架与基础 MCTS 相同，叶节点改用从 gen217 强模型
  蒸馏出的正式 18 特征估值器；两个 MCTS 档位分别由独立原生模块提供。
- **`amazon_X`（新模型，默认）**：
  - `src/ai/kataAmazonEngineCuda/amazons.exe`（**OpenCL/GPU**）。搭配
    模型文件 `amazon10x10_xzf.bin.gz`。需要支持 OpenCL 的显卡及正确安装的驱动；
    当前权重为 `gen223_b featurev1`，配套引擎会计算第一阶段新增输入特征。随目录附带
    OpenCL/zlib/MinGW 运行库与
    `engine.cfg`。首次运行会做一次 OpenCL 自动调优，结果缓存在
    目录内的 `KataGoData/opencltuning/`。
- **`amazon_L`（原始模型，后备）**：
  - 使用同一个可读取外部权重的 `src/ai/kataAmazonEngineCuda/amazons.exe`
    （**OpenCL/GPU**），加载 `src/ai/kataAmazonEngine/weights/amazons10x10.bin.gz`
    和该目录自己的 L 搜索配置。当前随包权重已恢复为最初的 L 模型（内部名
    `amazons8x-b20c256-s182755840-d39606896`），不是 `amazon18-s2161408-d449231`；
    以后直接替换此路径下的兼容模型会真实生效。旧模型偶尔会把亚马逊棋着法返回为
    `pass`，桥接层会改选搜索结果中访问量最高的合法坐标。
- **`amazon_Z`（服务器参考强模型）**：
  - 使用同一 OpenCL 引擎和稳定的 L 搜索配置，加载
    `src/ai/kataAmazonEngine/weights/amazon18-s2161408-d449231.bin.gz`。
    这是服务器历次评测中称为 Z 的原始强模型，SHA-256 为
    `49777c90faf12991ce18e74478ae80f19aec5930da1c8730dc12729740cb9431`。
- **默认自动选择**：`amazons_engine.py` 检测到 `amazon_X` 的完整资源则优先使用，
  否则依次回退到 `amazon_Z`、`amazon_L`；GUI 菜单可为黑白双方独立选择。
- **模型**：`src/ai/kataAmazonEngineCuda/amazon10x10_xzf.bin.gz`
  （`gen223_b featurev1`，架构 `b20c256legacyv10`，20 残差块 / 256 通道；
  SHA-256 `f32740014037c091ba564a586d9b6e05fb78d1e3fd4dae59e97c280c99af776a`）。
  `amazon_X` 的默认对局搜索配置使用 600 visits。菜单「AI 参数设置」提供默认均衡和
  最强棋力预设；最强棋力保持 1 秒公式 MCTS、600 visits KataGo，只为 X/Z/L
  启用接近正式模型评测的竞赛式搜索参数：零落子温度、关闭根噪声、原生策略温度、
  标准 cpuct/树搜索、固定网络推理方向，并关闭分差头搜索。自定义模式可在界面直接
  设置前后期落子温度、网络策略温度、网络方向随机化、cpuct、图搜索、根噪声、
  子树价值偏置和搜索线程数；设置窗口内另有
  “参数说明与参考值”页，列出各参数的作用、默认/最强值和常用范围。
- **通信**：以 GTP 子进程运行，用有超时边界的 `kata-genmove_analyze` 获取着法和胜率。
  对局着法只在规则层验证通过后提交到所有引擎；提示使用独立后台线程和当前历史快照，
  不会阻塞界面或继续分析旧棋盘。
- **可移植**：`src/ai/amazons_engine.py` 中所有运行资源都相对该文件计算，正常运行固定使用
  项目或便携目录内随附的引擎、模型与配置，不读取机器上的外部模型路径。

> 注意：featurev1 模型必须由本项目配套的 `amazons.exe` 推理。旧引擎即使能解析权重，
> 也不会计算新增输入特征，输出不可信；当前 `amazon_L` 使用最初会产生 `pass` 的原始 L
> 模型，并由当前桥接层修正非法 `pass` 返回。替换 L 权重时需自行确保配套引擎兼容其格式。
> 后续替换 XZF 权重时，应继续使用当前格式导出的模型，并保留内部模型名中的
> `featurev1` 标记；2022 旧引擎专用的“删 48 行元数据”权重不应与新版引擎混用。
> 目录名 `kataAmazonEngineCuda` 是历史遗留，当前其中放的是 OpenCL 版引擎。
> 项目只保留界面中实际可选的 `amazon_X`、`amazon_Z` 与 `amazon_L` 后端，不携带未接入运行流程的
> 试验引擎和重复权重。

## 功能

1. **五个 AI 对弈选项**：菜单「游戏 → 黑方/白方 → AI」可按 1—4 星为双方独立选择模型。
2. **显示胜率**（仿照参考 Hex 项目）：
   - 右侧信息面板实时显示当前行动方的 AI 胜率百分比；
   - 状态栏显示胜率 / 搜索次数 / 局面估值。
3. **AI 提示**：菜单「显示 → 显示完整回合胜率」(Ctrl+H)，沿最佳着法显示
   `S（选子）→ M（移动）→ A（射箭）` 三个阶段的胜率；三个数值统一为原行动方视角。
   交互提示使用独立的低延迟配置（150/120 visits），正式对局仍使用 600/400 visits。
4. **棋局演示**：棋局结束时可直接进入，或稍后使用「游戏 → 棋局演示」(Ctrl+P)。
   支持开局、上一步、下一步、终局导航，并同步恢复该步的模型、胜率、访问数、估值、
   分差和候选信息。导出的 JSON 棋谱会保存这些逐步快照，旧棋谱仍可按着法回放。
5. **自由摆盘**：使用「游戏 → 自由摆盘…」(Ctrl+B)，选择黑方皇后、白方皇后、
   障碍或橡皮擦后点击棋盘，并指定黑方或白方先行；双方各放置 4 枚皇后即可开始。
   自定义初始局面会写入 JSON 棋谱，重新导入后仍能继续对局或演示；X、L、Z 三个
   模型及两个 MCTS 档位均受支持。

## 开发与测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

也可以运行与 CI 一致的完整检查：

```bash
python -m compileall -q main.py src tests
python -m pytest -q
python scripts/check_release.py
git diff --check
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
    kataAmazonEngineCuda/       amazon_X + amazons.exe(OpenCL) + amazon10x10_xzf.bin.gz + dll + 配置（默认）
    kataAmazonEngine/           amazon_L/Z 权重 + 独立搜索配置（后备/参考）
  gui/
    amazon_board_widget.py      棋盘绘制（含提示圆环）
    amazon_main_window.py       主窗口（菜单 / 胜率显示 / 提示）
```

## 参与项目

提交问题前请先阅读 [贡献指南](CONTRIBUTING.md)。安全问题请按照
[安全策略](SECURITY.md) 私下报告；问题模板会引导你附上必要的系统和日志信息。

## 使用范围与模型政策

项目模型允许用于推理、研究、评测、教学，以及合法合规的微调和继续训练。严禁在赛事、
天梯、平台对局或其他竞争场景中违反规则使用本模型或其衍生模型，包括未按要求披露 AI、
代打、作弊、操纵排名或奖金。赛事规则明确允许的 AI 组别、研究赛和引擎赛不受此限制。

完整条款见 [模型使用政策](MODEL_USAGE.md)。本仓库当前未授予通用开源许可证，默认版权
保护适用；第三方引擎、运行库、字体和素材仍分别受其原始许可证及权利声明约束。
