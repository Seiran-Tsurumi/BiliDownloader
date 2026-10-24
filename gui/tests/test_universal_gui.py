"""万能下载标签页逻辑自测（uni_dl 未就绪/测试时使用内置 stub）。

用法:
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe gui/tests/test_universal_gui.py

覆盖验收点：
  * mode_tabs 两个标签页存在，B站控件仍可访问
  * 垃圾输入解析失败 -> notify.show_error 被调用
  * stub 解析成功填充 uni_meta_label 且日志含“解析成功”
  * 下载在后台线程、完成弹窗收到路径列表
  * 取消流程
  * 默认主题 chiikawa；三个主题 QAction 触发后 app.styleSheet() 含对应标记
  * 万能合规声明文本 != COMPLIANCE_TEXT
  * 万能标签页 chiikawa 主题离屏截图
  * 加速复选框默认不勾选（内置分块下载）；uni_dl.has_accelerator() 为 False 时禁用并回退提示
  * 代理下拉框默认 auto、uni_proxy_edit 仅手动模式可用
  * 代理/加速参数透传到 parse_input / download_video
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BILIDOWNLOADER_SETTINGS"] = os.path.join(
    tempfile.mkdtemp(prefix="bili_uni_settings_"), "settings.json"
)

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.tests import stub_uni_dl as stub  # noqa: E402

sys.modules["uni_dl"] = stub  # 必须在导入 gui.main_window 之前注入

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QTabWidget  # noqa: E402

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

UNI_OBJECT_NAMES = [
    "uni_input_edit",
    "uni_parse_button",
    "uni_quality_combo",
    "uni_format_edit",
    "uni_save_dir_edit",
    "uni_browse_button",
    "uni_cookie_browser_combo",
    "uni_cookie_file_edit",
    "uni_cookie_file_button",
    "uni_progress_bar",
    "uni_stage_label",
    "uni_percent_label",
    "uni_speed_label",
    "uni_status_log",
    "uni_download_button",
    "uni_cancel_button",
    "uni_meta_label",
    "uni_accel_check",
    "uni_proxy_combo",
    "uni_proxy_edit",
]

DETECTED_PROXY = "http://127.0.0.1:7890"


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

    print("== 标签页与对象名 ==")
    check("mode_tabs 存在", isinstance(window.mode_tabs, QTabWidget))
    check("mode_tabs 两个标签页", window.mode_tabs.count() == 2)
    check("tab0 标题为 B站专属", window.mode_tabs.tabText(0) == "B站专属")
    check("tab1 标题为 万能下载", window.mode_tabs.tabText(1) == "万能下载")
    for attr in ("input_edit", "quality_combo", "save_dir_edit", "download_button",
                 "cancel_button", "progress_bar", "stage_label", "percent_label",
                 "speed_label", "status_log", "cookie_action"):
        check(f"B站控件 {attr} 仍可访问", hasattr(window, attr))
    for attr in UNI_OBJECT_NAMES:
        check(f"万能控件 {attr} 存在", hasattr(window, attr))
    check("uni_parse_button 文本为 解析", window.uni_parse_button.text() == "解析")
    check("uni_download_button 文本为 下载", window.uni_download_button.text() == "下载")
    check("uni_cancel_button 文本为 取消", window.uni_cancel_button.text() == "取消")
    check("uni_input placeholder 提示任意网站/播放列表",
          "任意网站视频页链接" in window.uni_input_edit.placeholderText() and "播放列表" in window.uni_input_edit.placeholderText())
    check("uni_format placeholder 提示自定义格式串", "自定义 yt-dlp 格式串" in window.uni_format_edit.placeholderText())
    check("uni_quality_combo 4 项且第一项默认",
          window.uni_quality_combo.count() == 4 and window.uni_quality_combo.currentIndex() == 0)
    check("cookie 浏览器首项为 不登录", window.uni_cookie_browser_combo.itemText(0) == "不登录")

    print("== 加速与代理控件 ==")
    stub.STATE["detected_proxy"] = DETECTED_PROXY
    check("uni_accel_check 默认不勾选（默认走内置分块下载）", not window.uni_accel_check.isChecked())
    check("uni_accel_check 文本含 多线程加速/aria2c/8 连接",
          all(k in window.uni_accel_check.text() for k in ("多线程加速", "aria2c", "8")))
    check("有 aria2c 时 uni_accel_check 可用", window.uni_accel_check.isEnabled())
    check("uni_proxy_combo 三项且数据为 auto/none/manual",
          window.uni_proxy_combo.count() == 3
          and [window.uni_proxy_combo.itemData(i) for i in range(3)] == ["auto", "none", "manual"])
    check("uni_proxy_combo 默认 auto", window.uni_proxy_combo.currentData() == "auto")
    check("uni_proxy_edit 默认禁用", not window.uni_proxy_edit.isEnabled())
    check("uni_proxy_edit 默认值 127.0.0.1:12334", window.uni_proxy_edit.text() == "http://127.0.0.1:12334")
    check("uni_proxy_edit placeholder 含默认代理与 socks5",
          "127.0.0.1:12334" in window.uni_proxy_edit.placeholderText()
          and "socks5://" in window.uni_proxy_edit.placeholderText())
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("manual"))
    app.processEvents()
    check("切到手动后 uni_proxy_edit 启用", window.uni_proxy_edit.isEnabled())
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("none"))
    app.processEvents()
    check("切到不使用时 uni_proxy_edit 禁用", not window.uni_proxy_edit.isEnabled())
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("auto"))
    app.processEvents()
    check("切回自动检测后 uni_proxy_edit 禁用", not window.uni_proxy_edit.isEnabled())

    print("== 主题 ==")
    check("默认主题为 chiikawa", window._current_theme == "chiikawa")
    check("默认样式表含 chiikawa 标记", "/* theme:chiikawa */" in app.styleSheet())
    for name in ("chiikawa", "light", "dark"):
        getattr(window, f"theme_action_{name}").trigger()
        app.processEvents()
        check(f"主题 {name} 触发后样式表含标记", f"/* theme:{name} */" in app.styleSheet())
        check(f"主题 {name} 记录到 _current_theme", window._current_theme == name)
    window.theme_action_chiikawa.trigger()
    app.processEvents()

    print("== 合规声明 ==")
    check("UNI_COMPLIANCE_TEXT != COMPLIANCE_TEXT", mw.UNI_COMPLIANCE_TEXT != mw.COMPLIANCE_TEXT)
    check("万能合规标签文本为 UNI_COMPLIANCE_TEXT",
          window.uni_compliance_label.text() == mw.UNI_COMPLIANCE_TEXT)
    labels = [lbl.text() for lbl in window.findChildren(QLabel) if lbl.text() == mw.COMPLIANCE_TEXT]
    check("COMPLIANCE_TEXT 原文在窗口中数量仍为 1", len(labels) == 1)

    print("== 垃圾输入解析失败 ==")
    window.mode_tabs.setCurrentIndex(1)
    window.uni_input_edit.setText("garbage-input")
    calls["errors"].clear()
    window.uni_parse_button.click()
    ok = wait_until(lambda: bool(calls["errors"]), what="show_error 被调用")
    check("垃圾输入点解析 -> show_error 被调用", ok)
    check("错误弹窗收到 UniInputError 文本",
          bool(calls["errors"]) and "无法从" in calls["errors"][0][1])
    check("错误弹窗 parent 为主窗口", bool(calls["errors"]) and calls["errors"][0][0] is window)
    check("解析失败写入万能状态日志", "解析失败" in window.uni_status_log.toPlainText())
    check("垃圾输入未触发下载", stub.STATE["download_count"] == 0)

    print("== 合法解析 ==")
    calls["errors"].clear()
    stub.STATE["parse_proxy"] = "sentinel"
    stub.STATE["detect_proxy_calls"] = 0
    window.uni_input_edit.setText("https://example.com/watch?v=abc123")
    window.uni_parse_button.click()
    ok = wait_until(lambda: "标题：" in window.uni_meta_label.text(), what="uni_meta_label 填充")
    check("解析成功填充 uni_meta_label", ok)
    check("uni_meta_label 含 标题/UP主/时长/条目数",
          all(k in window.uni_meta_label.text() for k in ("标题：", "UP主：", "时长：", "条目数：")))
    check("日志含 解析成功", "解析成功" in window.uni_status_log.toPlainText())
    check("解析在后台线程执行",
          stub.STATE["parse_thread_id"] is not None and stub.STATE["parse_thread_id"] != MAIN_THREAD_ID,
          f"parse={stub.STATE['parse_thread_id']} ui={MAIN_THREAD_ID}")
    check("解析后下载按钮启用", window.uni_download_button.isEnabled())
    check("auto 模式解析透传 stub 检测到的代理",
          stub.STATE["parse_proxy"] == DETECTED_PROXY, f"proxy={stub.STATE['parse_proxy']}")
    check("auto 模式调用 detect_local_proxy", stub.STATE["detect_proxy_calls"] > 0,
          f"calls={stub.STATE['detect_proxy_calls']}")

    print("== 代理模式透传 ==")
    stub.STATE["parse_proxy"] = "sentinel"
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("manual"))
    window.uni_proxy_edit.setText(" socks5://127.0.0.1:7891 ")
    window.uni_parse_button.click()
    ok = wait_until(lambda: window.uni_parse_button.isEnabled() and stub.STATE["parse_proxy"] != "sentinel",
                    10.0, what="手动代理解析")
    check("手动代理透传 parse_input（去首尾空格）",
          ok and stub.STATE["parse_proxy"] == "socks5://127.0.0.1:7891",
          f"proxy={stub.STATE['parse_proxy']}")
    stub.STATE["parse_proxy"] = "sentinel"
    stub.STATE["detected_proxy"] = None
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("auto"))
    window.uni_parse_button.click()
    ok = wait_until(lambda: window.uni_parse_button.isEnabled() and stub.STATE["parse_proxy"] != "sentinel",
                    10.0, what="系统网络解析")
    check("auto 未检测到本地代理时 parse_input 收到 None",
          ok and stub.STATE["parse_proxy"] is None, f"proxy={stub.STATE['parse_proxy']}")
    check("未检测到本地代理写入万能日志",
          "未检测到本地代理，使用系统网络" in window.uni_status_log.toPlainText())
    stub.STATE["detected_proxy"] = DETECTED_PROXY
    stub.STATE["parse_proxy"] = "sentinel"
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("none"))
    window.uni_parse_button.click()
    ok = wait_until(lambda: window.uni_parse_button.isEnabled() and stub.STATE["parse_proxy"] != "sentinel",
                    10.0, what="不使用代理解析")
    check("不使用代理时 parse_input 收到 None", ok and stub.STATE["parse_proxy"] is None,
          f"proxy={stub.STATE['parse_proxy']}")
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("auto"))
    app.processEvents()

    print("== 下载线程与完成状态 ==")
    tmpdir = tempfile.mkdtemp(prefix="uni_gui_test_")
    window.uni_save_dir_edit.setText(tmpdir)
    stub.STATE["download_sleep_seconds"] = 0.001
    stub.STATE["download_started"].clear()
    calls["successes"].clear()
    window.uni_download_button.click()
    ok = wait_until(lambda: stub.STATE["download_thread_id"] is not None, what="下载开始")
    check("下载在后台线程执行", ok and stub.STATE["download_thread_id"] != MAIN_THREAD_ID,
          f"download={stub.STATE['download_thread_id']} ui={MAIN_THREAD_ID}")
    check("下载透传 accelerator=False（默认内置下载）", stub.STATE["last_accelerator"] is False,
          f"accelerator={stub.STATE['last_accelerator']}")
    check("下载透传 auto 代理（= stub 检测值）", stub.STATE["last_proxy"] == DETECTED_PROXY,
          f"proxy={stub.STATE['last_proxy']}")
    ok = wait_until(lambda: bool(calls["successes"]), 15.0, what="show_success 被调用")
    check("下载完成触发成功弹窗", ok)
    check("成功弹窗收到路径列表",
          bool(calls["successes"]) and "example-video.mp4" in calls["successes"][0][2])
    check("完成后进度条 100%", window.uni_progress_bar.value() == 100)
    check("完成后阶段文本 完成", window.uni_stage_label.text() == "完成")
    check("完成后百分比 100%", window.uni_percent_label.text() == "100%")
    check("完成后取消按钮禁用", not window.uni_cancel_button.isEnabled())
    check("成功弹窗携带输出目录",
          bool(calls["successes"]) and str(Path(tmpdir)) == str(Path(calls["successes"][0][3])))
    check("完成路径写入日志", "example-video.mp4" in window.uni_status_log.toPlainText())

    print("== 输入变更使旧解析失效 ==")
    calls["errors"].clear()
    window.uni_input_edit.setText("https://example.com/watch?v=second")
    app.processEvents()
    check("输入变化后旧解析结果清空", window.uni_meta_label.text() == "尚未解析")
    check("输入变化后下载按钮禁用", not window.uni_download_button.isEnabled())
    window._on_uni_download_clicked()
    ok = wait_until(lambda: bool(calls["errors"]), 5.0, what="下载拒绝提示")
    check("未重新解析时点击下载 -> 提示链接已更改", ok and "链接已更改" in calls["errors"][0][1])
    check("未重新解析时未触发下载", stub.STATE["download_count"] == 1,
          f"count={stub.STATE['download_count']}")
    calls["errors"].clear()
    window.uni_parse_button.click()
    ok = wait_until(lambda: window.uni_download_button.isEnabled(), 10.0, what="重新解析后下载可用")
    check("重新解析后下载按钮恢复", ok)

    print("== 取消流程 ==")
    stub.reset_state()
    calls["cancelled"].clear()
    calls["successes"].clear()
    stub.STATE["download_sleep_seconds"] = 0.05
    stub.STATE["download_started"].clear()
    window.uni_download_button.click()
    ok = wait_until(lambda: stub.STATE["download_started"].is_set(), 5.0, what="下载启动")
    check("下载中取消按钮可用", ok and window.uni_cancel_button.isEnabled())
    if ok:
        window.uni_cancel_button.click()
    ok2 = wait_until(lambda: bool(calls["cancelled"]), 5.0, what="取消提示出现")
    check("取消弹窗出现", ok2)
    check("取消后阶段文本 已取消", window.uni_stage_label.text() == "已取消")
    check("取消后下载按钮恢复", window.uni_download_button.isEnabled())
    check("取消后未触发成功弹窗", not calls["successes"])

    print("== 截图 ==")
    window.mode_tabs.setCurrentIndex(1)
    app.processEvents()
    artifacts = Path(__file__).resolve().parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    shot = artifacts / "universal_chiikawa.png"
    saved = window.grab().save(str(shot))
    check("万能标签页 chiikawa 离屏截图保存",
          bool(saved) and shot.exists() and shot.stat().st_size > 0, f"路径={shot}")
    print(f"  截图路径：{shot}")

    print("== 设置持久化 ==")
    window.uni_save_dir_edit.setText(tmpdir)
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("manual"))
    window.uni_proxy_edit.setText("http://127.0.0.1:12334")
    window.uni_accel_check.setChecked(True)
    app.processEvents()
    third = mw.MainWindow()
    third.show()
    app.processEvents()
    check("重启后恢复万能存储位置", third.uni_save_dir_edit.text() == tmpdir)
    check("重启后恢复代理模式与地址",
          third.uni_proxy_combo.currentData() == "manual"
          and third.uni_proxy_edit.text() == "http://127.0.0.1:12334")
    check("重启后恢复加速开关", third.uni_accel_check.isChecked())
    third.close()
    third.deleteLater()
    app.processEvents()

    print("== 无 aria2c 时禁用加速 ==")
    stub.STATE["has_accelerator"] = False
    second = mw.MainWindow()
    second.show()
    app.processEvents()
    check("has_accelerator=False 时 uni_accel_check 禁用", not second.uni_accel_check.isEnabled())
    check("has_accelerator=False 时 uni_accel_check 未勾选", not second.uni_accel_check.isChecked())
    check("has_accelerator=False 时日志提示回退内置下载",
          "未找到 aria2c，使用内置单连接分块下载" in second.uni_status_log.toPlainText(),
          second.uni_status_log.toPlainText()[-120:])
    second.close()
    second.deleteLater()
    app.processEvents()
    stub.STATE["has_accelerator"] = True

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
