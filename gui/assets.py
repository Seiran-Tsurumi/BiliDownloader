"""资源路径与图标：源码运行与 PyInstaller 打包后（sys._MEIPASS）都能找到 assets。"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def asset_path(name):
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / "assets" / name


def app_icon():
    return QIcon(str(asset_path("logo.png")))