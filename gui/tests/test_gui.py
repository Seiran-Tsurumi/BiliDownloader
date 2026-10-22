"""gui 逻辑自测（核心 bili_dl 未就绪时使用内置 stub）。

用法:
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe gui/tests/test_gui.py

覆盖验收点：
  * 垃圾输入点下载 -> notify.show_error 被调用（monkeypatch 断言）
  * 合法 BV 解析成功 -> 画质下拉被填充且第一项为"最高可用"
  * 合规声明原文存在于窗口控件
  * 解析/下载任务不在 UI 线程（线程 id 断言）
另附：取消流程、完成状态、Cookie 对话框、主窗口 offscreen 截图。
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.tests import stub_bili_dl as stub  # noqa: E402

sys.modules["bili_dl"] = stub  # 必须在导入 gui.main_window 之前注入

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit  # noqa: E402

from gui import main_window as mw  # noqa: E402
from gui import notify  # noqa: E402

app = QApplication.instance() or QApplication([])

# offscreen 平台不自带字体，注册系统 CJK 字体让截图可渲染中文
for _font_path in (
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
):
    if Path(_font_path).exists():
        QFontDatabase.addApplicationFont(_font_path)
        print("已注册 CJK 字体:", _font_path)
        break

MAIN_THREAD_ID = threading.get_ident()
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    line = f"[{'PASS' if ok else 'FAIL'}] {name}"
    if detail and not ok:
        line += f"  (detail: {detail})"
    print(line)


def wait_until(cond, timeout=10.0, what="条件"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if cond():
            return True
        QTest.qWait(10)
    print(f"  [timeout] 等待超时: {what}")
    return False


def main():
    stub.reset_state()
    window = mw.MainWindow()
    window.show()
    app.processEvents()

    initial_save_dir = window.save_dir_edit.text()

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

    print("== 基础 UI 元素 ==")
    check("窗口标题", window.windowTitle() == mw.WINDOW_TITLE)
    check("输入框 placeholder", window.input_edit.placeholderText() == "粘贴视频播放页链接或 BV 号")
    check("默认保存目录为 Downloads/BiliDownloader", Path(initial_save_dir) == Path.home() / "Downloads" / "BiliDownloader")
    check("默认保存目录已自动创建", (Path.home() / "Downloads" / "BiliDownloader").is_dir())
    check("Cookie 设置入口可见", window.cookie_action.text().startswith("Cookie"))
    check("画质下拉初始禁用", not window.quality_combo.isEnabled())

    print("== 垃圾输入 ==")
    window.input_edit.setText("garbage-input-!!!")
    window.download_button.click()
    ok = wait_until(lambda: bool(calls["errors"]), what="show_error 被调用")
    check("垃圾输入点下载 -> show_error 被调用", ok)
    check("错误弹窗收到异常 message", bool(calls["errors"]) and "无效的输入" in calls["errors"][0][1] and "garbage-input-!!!" in calls["errors"][0][1])
    check("错误弹窗 parent 为主窗口", bool(calls["errors"]) and calls["errors"][0][0] is window)
    check("垃圾输入未触发下载", stub.STATE["download_count"] == 0)
    check("解析失败后画质下拉为空且禁用", window.quality_combo.count() == 0 and not window.quality_combo.isEnabled())

    print("== 合法 BV 解析 ==")
    calls["errors"].clear()
    window.input_edit.setText("BV1xx411c7mD")
    window.download_button.click()
    ok = wait_until(lambda: window.quality_combo.count() > 0, what="画质下拉被填充")
    check("合法 BV 解析成功 -> 画质下拉被填充", ok)
    check("第一项为“最高可用”", window.quality_combo.itemText(0) == "最高可用")
    check("第一项 userData 为 max", window.quality_combo.itemData(0) == "max")
    check("其余项为 Quality.desc 对应 qn", window.quality_combo.count() == 4 and window.quality_combo.itemText(1) == "1080P 高清" and window.quality_combo.itemData(1) == 80 and window.quality_combo.itemData(3) == 32)
    check("画质下拉解析后启用", window.quality_combo.isEnabled())
    check("解析不在 UI 线程（线程 id 断言）", stub.STATE["parse_thread_id"] is not None and stub.STATE["parse_thread_id"] != MAIN_THREAD_ID, f"parse={stub.STATE['parse_thread_id']} ui={MAIN_THREAD_ID}")
    check("解析成功写入状态日志", "解析成功" in window.status_log.toPlainText())

    print("== 下载线程与完成状态 ==")
    tmpdir = tempfile.mkdtemp(prefix="bili_gui_test_")
    window.save_dir_edit.setText(tmpdir)
    stub.STATE["download_sleep_seconds"] = 0.001
    stub.STATE["download_started"].clear()
    calls["successes"].clear()
    window.download_button.click()
    ok = wait_until(lambda: stub.STATE["download_thread_id"] is not None, what="下载开始")
    check("下载在后台线程执行（线程 id 不同）", ok and stub.STATE["download_thread_id"] != MAIN_THREAD_ID, f"download={stub.STATE['download_thread_id']} ui={MAIN_THREAD_ID}")
    ok = wait_until(lambda: bool(calls["successes"]), 15.0, what="show_success 被调用")
    check("下载完成触发成功弹窗", ok)
    check("完成后进度条 100%", window.progress_bar.value() == 100)
    check("完成后阶段文本“完成”", window.stage_label.text() == "完成")
    check("完成后百分比 100%", window.percent_label.text() == "100%")
    check("完成后取消按钮禁用", not window.cancel_button.isEnabled())
    check("成功弹窗携带输出目录", bool(calls["successes"]) and str(Path(tmpdir)) == str(Path(calls["successes"][0][3])))

    print("== 取消流程 ==")
    stub.reset_state()
    calls["cancelled"].clear()
    calls["successes"].clear()
    stub.STATE["download_sleep_seconds"] = 0.05
    stub.STATE["download_started"].clear()
    window.download_button.click()
    ok = wait_until(lambda: stub.STATE["download_started"].is_set(), 5.0, what="下载启动")
    check("下载中取消按钮可用", ok and window.cancel_button.isEnabled())
    if ok:
        window.cancel_button.click()
    ok2 = wait_until(lambda: bool(calls["cancelled"]), 5.0, what="取消提示出现")
    check("取消弹窗提示“已取消下载”", ok2 and calls["cancelled"][0][1] == "已取消下载")
    check("取消后阶段文本“已取消”", window.stage_label.text() == "已取消")
    check("取消后下载按钮恢复", window.download_button.isEnabled())
    check("取消后未触发成功弹窗", not calls["successes"])

    print("== Cookie 对话框 ==")
    cookie_info = {}

    def interact_cookie():
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            cookie_info["dlg_found"] = False
            return
        cookie_info["dlg_found"] = True
        note = dlg.findChild(QLabel, "cookie_note")
        editor = dlg.findChild(QPlainTextEdit, "cookie_edit")
        cookie_info["note"] = note.text() if note is not None else ""
        editor.setPlainText("SESSDATA=abc123; bili_jct=xyz789")
        dlg.accept()

    QTimer.singleShot(0, interact_cookie)
    window.cookie_action.trigger()
    check("Cookie 对话框弹出", cookie_info.get("dlg_found", False))
    check("对话框注明“Cookie 仅本次运行有效，用于解锁高画质，程序不会保存”", cookie_info.get("note") == "Cookie 仅本次运行有效，用于解锁高画质，程序不会保存")
    check("Cookie 仅存内存变量", window._cookie == "SESSDATA=abc123; bili_jct=xyz789")

    print("== 合规声明 ==")
    labels = [lbl.text() for lbl in window.findChildren(QLabel) if lbl.text() == mw.COMPLIANCE_TEXT]
    check("合规声明原文存在于窗口控件", len(labels) == 1)
    print("  合规声明原文：", mw.COMPLIANCE_TEXT)

    print("== 截图 ==")
    artifacts = Path(__file__).resolve().parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    shot = artifacts / "main_window.png"
    saved = window.grab().save(str(shot))
    check("主窗口 offscreen 截图保存", bool(saved) and shot.exists() and shot.stat().st_size > 0, f"路径={shot}")
    print(f"  截图路径：{shot}")

    window.close()
    app.processEvents()

    failed = [r for r in RESULTS if not r[1]]
    print()
    print(f"总结：{len(RESULTS) - len(failed)} 通过 / {len(failed)} 失败 / 共 {len(RESULTS)}")
    for name, _, detail in failed:
        print(f"  失败项：{name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
