"""真实集成测试（bili_dl 核心就绪后运行，需要联网）。

用法:
    .venv/Scripts/python.exe gui/tests/integration_real.py

环境变量:
    BILI_TEST_BV   公开 BV 号（默认 BV1GJ411x7h7）
    BILI_TEST_QN   画质（默认 max）

流程：真实 parse_input/list_qualities/download_video 下载到临时目录，
断言产出 MP4 存在且主窗口 UI 状态为完成。核心未就绪时输出 SKIP 并以 0 退出。
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import bili_dl  # noqa: F401
except ImportError as exc:
    print(f"SKIP: bili_dl 核心未就绪（{exc}），待核心合入后重跑本脚本。")
    sys.exit(0)

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import main_window as mw  # noqa: E402
from gui import notify  # noqa: E402

BV = os.environ.get("BILI_TEST_BV", "BV1GJ411x7h7")

app = QApplication.instance() or QApplication([])
window = mw.MainWindow()
window.show()

tmpdir = tempfile.mkdtemp(prefix="bili_real_")
window.save_dir_edit.setText(tmpdir)

calls = {"errors": [], "successes": [], "cancelled": []}


def fake_error(parent, message):
    calls["errors"].append((parent, message))


def fake_success(parent, title, message, folder=None):
    calls["successes"].append((parent, title, message, folder))


def fake_cancelled(parent, message="已取消下载"):
    calls["cancelled"].append((parent, message))


notify.show_error = fake_error
notify.show_success = fake_success
notify.show_cancelled = fake_cancelled


def wait_until(cond, timeout, what):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if cond():
            return True
        QTest.qWait(20)
    print(f"  [timeout] 等待超时: {what}")
    return False


def main():
    print(f"真实集成测试：BV={BV} 保存目录={tmpdir}")
    window.input_edit.setText(BV)
    window.download_button.click()
    ok = wait_until(lambda: window.quality_combo.count() > 0 or bool(calls["errors"]), 60, "解析")
    if not ok or calls["errors"]:
        print(f"FAIL: 解析失败 {calls['errors']}")
        return 1
    print(f"解析成功：画质项 {[window.quality_combo.itemText(i) for i in range(window.quality_combo.count())]}")
    window.download_button.click()
    ok = wait_until(lambda: bool(calls["successes"]) or bool(calls["errors"]), 600, "下载")
    if calls["errors"] or not ok:
        print(f"FAIL: 下载失败 {calls['errors']}（超时={not ok}）")
        return 1
    folder = Path(calls["successes"][0][3])
    mp4s = sorted(folder.glob("*.mp4"))
    if not mp4s:
        print(f"FAIL: 目录 {folder} 中未找到 MP4，实际内容={list(folder.iterdir())}")
        return 1
    if window.progress_bar.value() != 100 or window.stage_label.text() != "完成":
        print(f"FAIL: UI 状态非完成（进度={window.progress_bar.value()} 阶段={window.stage_label.text()}）")
        return 1
    print(f"PASS: 真实下载成功 -> {mp4s[0]}（{mp4s[0].stat().st_size} bytes），UI 状态=完成")
    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
