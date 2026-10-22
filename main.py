"""BiliDownloader 桌面 GUI 入口。

用法:
    python main.py              启动图形界面
    python main.py --selftest   离屏冒烟测试：创建主窗口并立即关闭，退出码 0
"""

import os
import sys


def _ensure_project_root_on_path():
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)


def _selftest():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()
    print("[selftest] 主窗口创建并关闭成功")
    return 0


def main(argv=None):
    argv = sys.argv if argv is None else list(argv)
    _ensure_project_root_on_path()
    if "--selftest" in argv:
        return _selftest()

    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("BiliDownloader")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
