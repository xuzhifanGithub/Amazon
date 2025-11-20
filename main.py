# main.py

import sys
import os
from PyQt6.QtWidgets import QApplication

# 从 src 目录导入核心组件
from src.core.simulator import AmazonsSimulator
from src.gui.amazon_main_window import AmazonsMainWindow


def main():
    """
    主函数，用于初始化并运行亚马逊棋（Game of the Amazons）游戏应用。
    """
    # 初始化 PyQt6 应用程序
    app = QApplication(sys.argv)

    # 确保资源路径（如 assets 文件夹）是相对于脚本位置的
    # 这对于打包成可执行文件或在不同环境下运行至关重要
    try:
        base_path = sys._MEIPASS  # PyInstaller 创建的临时文件夹
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))

    os.chdir(base_path)

    # 创建游戏模拟器实例
    simulator = AmazonsSimulator(size=10)

    # 创建主窗口实例
    main_window = AmazonsMainWindow(simulator)

    # 显示主窗口
    main_window.show()

    # 进入应用程序的事件循环
    sys.exit(app.exec())


if __name__ == '__main__':
    # 当该脚本作为主程序运行时，调用 main 函数
    main()