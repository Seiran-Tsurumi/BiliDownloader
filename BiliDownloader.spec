# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 构建配置：--onefile --windowed --name BiliDownloader。

构建命令（见 build_exe.bat）：
    .venv\Scripts\python -m PyInstaller BiliDownloader.spec --noconfirm
"""

from PyInstaller.utils.hooks import collect_all

# 收集 imageio_ffmpeg 内嵌的 ffmpeg 二进制（get_ffmpeg_exe() 依赖包内相对路径）
datas, binaries, hiddenimports = collect_all("imageio_ffmpeg")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # GUI 仅使用 QtCore/QtWidgets/QtGui，排除未用的大模块以减小体积；
    # 若 exe 冒烟失败，删除 excludes 后重新构建。
    excludes=[
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BiliDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
