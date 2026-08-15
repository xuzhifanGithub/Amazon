## 变更说明

请简要说明解决的问题、实现方式和用户可见变化。

## 验证

- [ ] `python -m compileall -q main.py src tests`
- [ ] `python -m pytest -q`
- [ ] `git diff --check`
- [ ] 涉及模型或发布资源时，已运行 `python scripts/check_release.py`

## 检查项

- [ ] 未提交本机路径、日志、缓存、密钥或训练检查点
- [ ] 新游戏、悔棋、AI 对 AI 与程序退出流程未被破坏
- [ ] 界面变化已在 Windows 下实际检查
