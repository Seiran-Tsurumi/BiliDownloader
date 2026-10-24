"""应用设置持久化：保存位置、代理、加速、主题等；Cookie 绝不落盘。"""

import json
import os
from pathlib import Path

DEFAULT_PROXY_URL = "http://127.0.0.1:12334"

DEFAULTS = {
    "bili_save_dir": "",
    "uni_save_dir": "",
    "proxy_mode": "auto",
    "proxy_url": DEFAULT_PROXY_URL,
    "accelerator": False,
    "theme": "chiikawa",
}


def settings_path():
    """设置文件路径：环境变量 BILIDOWNLOADER_SETTINGS 优先（测试隔离用）。"""
    override = os.environ.get("BILIDOWNLOADER_SETTINGS")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "BiliDownloader" / "settings.json"


def load_settings():
    """读取设置；文件缺失/损坏时返回默认值。"""
    data = dict(DEFAULTS)
    try:
        raw = settings_path().read_text(encoding="utf-8")
        loaded = json.loads(raw)
    except Exception:
        return data
    if isinstance(loaded, dict):
        for key in DEFAULTS:
            if key in loaded:
                data[key] = loaded[key]
    return data


def save_settings(data):
    """原子写入设置文件；失败静默（不影响下载主流程）。"""
    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:
        return False