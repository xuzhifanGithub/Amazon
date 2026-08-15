# 贡献指南

感谢你改进亚马逊棋项目。为了让问题和合并请求更容易复现，请遵循以下约定。

## 开发环境

完整 AI 功能以 Windows x64、Python 3.11/3.13 和可用的 OpenCL 驱动为准。
克隆仓库前请安装 Git LFS，随后执行：

```bat
git lfs install
setup_env.bat
```

只开发规则或界面时，也可以在 Linux/macOS 使用 `setup_env.sh`，但预编译的 MCTS 和
KataGo Amazons 引擎可能不可用。

## 提交问题

- 使用仓库的 Bug 或功能建议模板。
- AI 问题请提供双方模型、visits、颜色、完整操作顺序和 `.amazons.json` 棋谱。
- 日志中可能包含本机路径，上传前请先脱敏。
- 安全问题不要创建公开 Issue，请按 `SECURITY.md` 私下报告。

## 提交代码

1. 从最新 `master` 创建主题分支。
2. 保持改动聚焦，不提交 `.venv/`、构建目录、日志、OpenCL 调优缓存或训练检查点。
3. 对行为变化补充测试，并运行：

```text
python -m compileall -q main.py src tests
python -m pytest -q
git diff --check
```

涉及引擎、模型或便携版资源时，还需要运行 `python scripts/check_release.py`。

## 模型与大文件

模型和预编译引擎由 Git LFS 管理。除非维护者明确要求，请不要直接向本仓库提交新模型、
训练数据、PyTorch checkpoint 或重复的引擎副本。允许在仓库外进行研究、微调和继续训练，
但原模型及衍生模型都必须遵守 `MODEL_USAGE.md` 的公平竞赛要求。
