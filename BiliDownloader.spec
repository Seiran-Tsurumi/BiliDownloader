# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 构建配置：--onefile --windowed --name BiliDownloader。

构建命令（见 build_exe.bat）：
    .venv\Scripts\python -m PyInstaller BiliDownloader.spec --noconfirm
"""

from PyInstaller.utils.hooks import collect_all


def _dedup_pairs(items):
    """按原顺序对 (src, dest) 二元组列表去重。"""
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# 收集 imageio_ffmpeg 内嵌的 ffmpeg 二进制（get_ffmpeg_exe() 依赖包内相对路径）
datas, binaries, hiddenimports = collect_all("imageio_ffmpeg")

# 收集 yt_dlp（uni_dl 万能下载依赖），与 imageio_ffmpeg 合并并去重
yt_datas, yt_binaries, yt_hiddenimports = collect_all("yt_dlp")
datas = _dedup_pairs(datas + yt_datas)
binaries = _dedup_pairs(binaries + yt_binaries)
hiddenimports = sorted(set(hiddenimports + yt_hiddenimports))

# 打包 aria2c（uni_dl 多线程加速依赖）与其许可证，运行时解包到 tools/aria2/
aria2_binaries = [("tools/aria2/aria2c.exe", "tools/aria2")]
aria2_datas = [("tools/aria2/COPYING", "tools/aria2")]
binaries = _dedup_pairs(binaries + aria2_binaries)
datas = _dedup_pairs(datas + aria2_datas)

# 打包 curl_cffi（浏览器 TLS 指纹伪装，绕过 Cloudflare 类反爬）及其 libcurl DLL
import glob
import importlib.util
import os

_cffi_spec = importlib.util.find_spec("curl_cffi")
if _cffi_spec is not None:
    cffi_datas, cffi_binaries, cffi_hiddenimports = collect_all("curl_cffi")
    datas = _dedup_pairs(datas + cffi_datas)
    binaries = _dedup_pairs(binaries + cffi_binaries)
    hiddenimports = sorted(set(hiddenimports + cffi_hiddenimports))
    _cffi_site = os.path.dirname(os.path.dirname(_cffi_spec.origin))
    cffi_libs = glob.glob(os.path.join(_cffi_site, "curl_cffi.libs", "*.dll"))
    binaries = _dedup_pairs(binaries + [(dll, ".") for dll in cffi_libs])

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
