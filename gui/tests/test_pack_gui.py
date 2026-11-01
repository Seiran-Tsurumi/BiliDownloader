"""视图打包标签页逻辑自测（page_dl 未就绪/测试时使用内置 stub）。

用法:
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe gui/tests/test_pack_gui.py

覆盖验收点：
  * mode_tabs 四个标签页，第三页为“视图打包”（对象名 pack_tab），B站/万能控件仍可访问
  * pack_* 控件对象名与按钮文本（解析页面 / 开始打包 / 取消）
  * PACK_COMPLIANCE_TEXT 与 COMPLIANCE_TEXT、UNI_COMPLIANCE_TEXT 均不同
  * 垃圾输入解析失败 -> notify.show_error 被调用，日志含“解析失败”
  * stub 解析成功填充 pack_meta_label（标题/图片/视频/音频/其他）且日志含“解析成功”
  * 解析/打包都在后台线程；参数透传（save_dir / zip_output / proxy / cookie）
  * 打包完成弹窗收到 ZIP 路径且携带所在目录；阶段文本映射（下载媒体/打包 ZIP/完成）
  * 取消流程；输入变更后旧结果失效且未重新解析禁止打包
  * 设置持久化（新窗口恢复 pack_save_dir 与共用代理设置）
  * 视图打包标签页 chiikawa 主题离屏截图
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BILIDOWNLOADER_SETTINGS"] = os.path.join(
    tempfile.mkdtemp(prefix="bili_pack_settings_"), "settings.json"
)

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.tests import stub_page_dl as stub  # noqa: E402
from gui.tests import stub_uni_dl as uni_stub  # noqa: E402

sys.modules["page_dl"] = stub  # 必须在导入 gui.main_window 之前注入
sys.modules["uni_dl"] = uni_stub

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from gui import main_window as mw  # noqa: E402
from gui import notify  # noqa: E402
from gui import settings as gui_settings  # noqa: E402

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

PACK_OBJECT_NAMES = [
    "pack_input_edit",
    "pack_parse_button",
    "pack_meta_label",
    "pack_save_dir_edit",
    "pack_browse_button",
    "pack_cookie_file_edit",
    "pack_cookie_file_button",
    "pack_proxy_combo",
    "pack_proxy_edit",
    "pack_start_button",
    "pack_cancel_button",
    "pack_progress_bar",
    "pack_stage_label",
    "pack_percent_label",
    "pack_speed_label",
    "pack_status_log",
    "pack_compliance_label",
]

DETECTED_PROXY = "http://127.0.0.1:7890"
PAGE_URL = "https://example.com/album/1"
EXPECTED_ZIP_NAME = "视图打包.zip"


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


def parse_and_wait(window, text):
    """点击解析并等待本次解析结束。"""
    before = stub.STATE["parse_calls"]
    window.pack_input_edit.setText(text)
    app.processEvents()
    window.pack_parse_button.click()
    return wait_until(
        lambda: stub.STATE["parse_calls"] > before and window.pack_parse_button.isEnabled(),
        10.0, "解析结束",
    )


def main():
    stub.reset_state()
    uni_stub.reset_state()
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

    print("== 标签页与既有控件 ==")
    check("mode_tabs 四个标签页", window.mode_tabs.count() == 4,
          f"count={window.mode_tabs.count()}")
    check("tab0 标题为 B站专属", window.mode_tabs.tabText(0) == "B站专属")
    check("tab1 标题为 万能下载", window.mode_tabs.tabText(1) == "万能下载")
    check("tab2 标题为 视图打包", window.mode_tabs.tabText(2) == "视图打包")
    check("第三页对象名为 pack_tab",
          window.mode_tabs.widget(2).objectName() == "pack_tab",
          window.mode_tabs.widget(2).objectName())
    check("tab3 标题为 飞机模式", window.mode_tabs.tabText(3) == "飞机模式")
    check("page_dl 可选导入就绪", mw._PACK_READY is True, str(mw._PACK_IMPORT_ERROR))
    for attr in ("input_edit", "quality_combo", "save_dir_edit", "download_button",
                 "cancel_button", "progress_bar", "status_log", "cookie_action"):
        check(f"B站控件 {attr} 仍可访问", hasattr(window, attr))
    for attr in ("uni_input_edit", "uni_parse_button", "uni_download_button",
                 "uni_save_dir_edit", "uni_status_log", "uni_proxy_combo"):
        check(f"万能控件 {attr} 仍可访问", hasattr(window, attr))

    print("== 打包页控件对象名与默认状态 ==")
    for attr in PACK_OBJECT_NAMES:
        widget = getattr(window, attr, None)
        check(f"控件 {attr} 存在且 objectName 正确",
              widget is not None and widget.objectName() == attr)
    check("pack_parse_button 文本为 解析页面", window.pack_parse_button.text() == "解析页面")
    check("pack_start_button 文本为 开始打包", window.pack_start_button.text() == "开始打包")
    check("pack_cancel_button 文本为 取消", window.pack_cancel_button.text() == "取消")
    check("pack_input_edit placeholder 提示页面 URL",
          "页面 URL" in window.pack_input_edit.placeholderText())
    check("pack_meta_label 初始为 尚未解析", window.pack_meta_label.text() == "尚未解析")
    check("初始未解析时开始打包禁用", not window.pack_start_button.isEnabled())
    check("初始取消按钮禁用", not window.pack_cancel_button.isEnabled())
    check("默认保存目录为 Downloads/BiliDownloader",
          Path(window.pack_save_dir_edit.text()) == Path.home() / "Downloads" / "BiliDownloader")
    check("pack_proxy_combo 三项且数据为 auto/none/manual",
          window.pack_proxy_combo.count() == 3
          and [window.pack_proxy_combo.itemData(i) for i in range(3)]
          == ["auto", "none", "manual"])
    check("pack_proxy_combo 默认 auto", window.pack_proxy_combo.currentData() == "auto")
    check("pack_proxy_edit 默认禁用", not window.pack_proxy_edit.isEnabled())
    check("pack_proxy_edit 默认值 127.0.0.1:12348",
          window.pack_proxy_edit.text() == "http://127.0.0.1:12348")
    window.pack_proxy_combo.setCurrentIndex(window.pack_proxy_combo.findData("manual"))
    app.processEvents()
    check("切到手动后 pack_proxy_edit 启用", window.pack_proxy_edit.isEnabled())
    check("代理设置与万能页同步（共用 proxy_mode）",
          window.uni_proxy_combo.currentData() == "manual")
    window.pack_proxy_combo.setCurrentIndex(window.pack_proxy_combo.findData("auto"))
    app.processEvents()
    check("切回自动检测后 pack_proxy_edit 禁用", not window.pack_proxy_edit.isEnabled())

    print("== 合规声明 ==")
    check("PACK_COMPLIANCE_TEXT != COMPLIANCE_TEXT",
          mw.PACK_COMPLIANCE_TEXT != mw.COMPLIANCE_TEXT)
    check("PACK_COMPLIANCE_TEXT != UNI_COMPLIANCE_TEXT",
          mw.PACK_COMPLIANCE_TEXT != mw.UNI_COMPLIANCE_TEXT)
    check("打包合规标签文本为 PACK_COMPLIANCE_TEXT",
          window.pack_compliance_label.text() == mw.PACK_COMPLIANCE_TEXT)
    labels = [lbl.text() for lbl in window.findChildren(QLabel)
              if lbl.text() == mw.COMPLIANCE_TEXT]
    check("COMPLIANCE_TEXT 原文在窗口中数量仍为 1", len(labels) == 1)

    print("== 垃圾输入解析失败 ==")
    window.mode_tabs.setCurrentIndex(2)
    app.processEvents()
    calls["errors"].clear()
    window.pack_input_edit.setText("garbage-input")
    window.pack_parse_button.click()
    ok = wait_until(lambda: bool(calls["errors"]), 10.0, "show_error 被调用")
    check("垃圾输入点解析 -> show_error 被调用", ok)
    check("错误弹窗收到 PageInputError 中文文本",
          bool(calls["errors"]) and "无法从" in calls["errors"][0][1],
          calls["errors"][0][1] if calls["errors"] else "")
    check("错误弹窗 parent 为主窗口",
          bool(calls["errors"]) and calls["errors"][0][0] is window)
    check("解析失败写入打包状态日志", "解析失败" in window.pack_status_log.toPlainText())
    check("垃圾输入未触发打包", stub.STATE["download_calls"] == 0)
    check("解析失败后开始打包保持禁用", not window.pack_start_button.isEnabled())

    print("== 合法解析（auto 代理透传）==")
    calls["errors"].clear()
    stub.STATE["detected_proxy"] = DETECTED_PROXY
    stub.STATE["last_proxy"] = "sentinel"
    ok = parse_and_wait(window, PAGE_URL)
    ok = ok and wait_until(lambda: "标题：" in window.pack_meta_label.text(), 10.0,
                           "pack_meta_label 填充")
    check("解析成功填充 pack_meta_label", ok)
    meta = window.pack_meta_label.text()
    check("pack_meta_label 含 标题/图片/视频/音频/其他",
          all(k in meta for k in ("标题：", "图片：", "视频：", "音频：", "其他：")), meta)
    check("pack_meta_label 数量与 bundle 一致",
          "图片：3" in meta and "视频：2" in meta and "音频：1" in meta and "其他：0" in meta,
          meta)
    check("pack_meta_label 含页面标题", "测试页面：视图打包演示" in meta, meta)
    check("日志含 解析成功", "解析成功" in window.pack_status_log.toPlainText())
    check("解析在后台线程执行",
          stub.STATE["parse_thread_id"] is not None
          and stub.STATE["parse_thread_id"] != MAIN_THREAD_ID,
          f"parse={stub.STATE['parse_thread_id']} ui={MAIN_THREAD_ID}")
    check("解析后开始打包启用", window.pack_start_button.isEnabled())
    check("auto 模式解析透传探测到的代理",
          stub.STATE["last_proxy"] == DETECTED_PROXY, f"proxy={stub.STATE['last_proxy']}")
    check("auto 模式调用 detect_local_proxy", stub.STATE["detect_proxy_calls"] > 0,
          f"calls={stub.STATE['detect_proxy_calls']}")
    check("未选择 Cookie 文件时 cookie=None", stub.STATE["last_cookie"] is None,
          f"cookie={stub.STATE['last_cookie']}")

    print("== Cookie 文件与手动代理透传 ==")
    cookie_path = str(Path(tempfile.mkdtemp(prefix="pack_cookie_")) / "cookies.txt")
    Path(cookie_path).write_text("# Netscape HTTP Cookie File", encoding="utf-8")
    window.pack_cookie_file_edit.setText(cookie_path)
    app.processEvents()
    parse_and_wait(window, PAGE_URL)
    check("Cookie 文件以 {\"cookiefile\": 路径} 透传给 parse_page",
          stub.STATE["last_cookie"] == {"cookiefile": cookie_path},
          f"cookie={stub.STATE['last_cookie']}")
    window.pack_proxy_combo.setCurrentIndex(window.pack_proxy_combo.findData("manual"))
    window.pack_proxy_edit.setText(" socks5://127.0.0.1:7891 ")
    app.processEvents()
    stub.STATE["last_proxy"] = "sentinel"
    parse_and_wait(window, PAGE_URL)
    check("手动代理透传 parse_page（去首尾空格）",
          stub.STATE["last_proxy"] == "socks5://127.0.0.1:7891",
          f"proxy={stub.STATE['last_proxy']}")
    window.pack_proxy_combo.setCurrentIndex(window.pack_proxy_combo.findData("none"))
    window.pack_parse_button.click()
    ok = wait_until(lambda: window.pack_parse_button.isEnabled()
                    and stub.STATE["last_proxy"] is None, 10.0, "不使用代理解析")
    check("不使用代理时 parse_page 收到 None", ok, f"proxy={stub.STATE['last_proxy']}")
    window.pack_proxy_combo.setCurrentIndex(window.pack_proxy_combo.findData("auto"))
    app.processEvents()
    stub.STATE["detected_proxy"] = DETECTED_PROXY
    parse_and_wait(window, PAGE_URL)
    check("恢复 auto 后代理为探测值", stub.STATE["last_proxy"] == DETECTED_PROXY,
          f"proxy={stub.STATE['last_proxy']}")

    print("== 打包线程与完成状态 ==")
    tmpdir = tempfile.mkdtemp(prefix="pack_gui_test_")
    window.pack_save_dir_edit.setText(tmpdir)
    app.processEvents()
    stub.STATE["download_sleep_seconds"] = 0.001
    stub.STATE["download_started"].clear()
    calls["successes"].clear()
    window.pack_start_button.click()
    ok = wait_until(lambda: stub.STATE["download_thread_id"] is not None, 5.0, "打包开始")
    check("打包在后台线程执行",
          ok and stub.STATE["download_thread_id"] != MAIN_THREAD_ID,
          f"download={stub.STATE['download_thread_id']} ui={MAIN_THREAD_ID}")
    check("打包透传 save_dir", stub.STATE["last_save_dir"] == tmpdir,
          f"save_dir={stub.STATE['last_save_dir']}")
    check("打包透传 zip_output=True", stub.STATE["last_zip_output"] is True,
          f"zip_output={stub.STATE['last_zip_output']}")
    check("打包透传代理", stub.STATE["last_proxy"] == DETECTED_PROXY,
          f"proxy={stub.STATE['last_proxy']}")
    check("打包透传 Cookie 文件",
          stub.STATE["last_download_cookie"] == {"cookiefile": cookie_path},
          f"cookie={stub.STATE['last_download_cookie']}")
    check("打包透传 cancel 回调", bool(stub.STATE["last_cancel_hook"]))
    check("打包透传解析得到的 bundle", stub.STATE["last_bundle"] is stub.DEFAULT_BUNDLE)
    ok = wait_until(lambda: bool(calls["successes"]), 15.0, "show_success 被调用")
    check("打包完成触发成功弹窗", ok)
    expected_zip = str(Path(tmpdir) / EXPECTED_ZIP_NAME)
    check("成功弹窗收到 ZIP 路径",
          bool(calls["successes"]) and expected_zip in calls["successes"][0][2],
          calls["successes"][0][2] if calls["successes"] else "")
    check("成功弹窗标题为 打包完成",
          bool(calls["successes"]) and calls["successes"][0][1] == "打包完成")
    check("成功弹窗携带 ZIP 所在目录",
          bool(calls["successes"])
          and str(Path(tmpdir)) == str(Path(calls["successes"][0][3])),
          str(calls["successes"][0][3]) if calls["successes"] else "")
    check("ZIP 文件已生成", Path(expected_zip).is_file())
    check("完成后进度条 100%", window.pack_progress_bar.value() == 100)
    check("完成后阶段文本 完成", window.pack_stage_label.text() == "完成")
    check("完成后百分比 100%", window.pack_percent_label.text() == "100%")
    check("完成后取消按钮禁用", not window.pack_cancel_button.isEnabled())
    check("完成后开始打包恢复可用", window.pack_start_button.isEnabled())
    log_text = window.pack_status_log.toPlainText()
    check("阶段文本映射：下载媒体 / 打包 ZIP",
          "阶段：下载媒体" in log_text and "阶段：打包 ZIP" in log_text)
    check("完成路径写入日志", "打包完成" in log_text and expected_zip in log_text)

    print("== 截图 ==")
    window.mode_tabs.setCurrentIndex(2)
    app.processEvents()
    artifacts = Path(__file__).resolve().parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    shot = artifacts / "pack_chiikawa.png"
    saved = window.grab().save(str(shot))
    check("视图打包标签页 chiikawa 离屏截图保存",
          bool(saved) and shot.exists() and shot.stat().st_size > 0, f"路径={shot}")
    print(f"  截图路径：{shot}")

    print("== 取消流程 ==")
    stub.reset_state()
    stub.STATE["detected_proxy"] = DETECTED_PROXY
    calls["cancelled"].clear()
    calls["successes"].clear()
    stub.STATE["download_sleep_seconds"] = 0.05
    stub.STATE["download_started"].clear()
    window.pack_start_button.click()
    ok = wait_until(lambda: stub.STATE["download_started"].is_set(), 5.0, "打包启动")
    check("打包中取消按钮可用", ok and window.pack_cancel_button.isEnabled())
    if ok:
        window.pack_cancel_button.click()
    ok2 = wait_until(lambda: bool(calls["cancelled"]), 5.0, "取消提示出现")
    check("取消弹窗出现", ok2)
    check("取消提示为 已取消打包",
          bool(calls["cancelled"]) and "已取消打包" in calls["cancelled"][0][1],
          calls["cancelled"][0][1] if calls["cancelled"] else "")
    check("取消后阶段文本 已取消", window.pack_stage_label.text() == "已取消")
    check("取消后开始打包恢复可用", window.pack_start_button.isEnabled())
    check("取消后取消按钮禁用", not window.pack_cancel_button.isEnabled())
    check("取消后未触发成功弹窗", not calls["successes"])
    check("取消后日志记录清理", "已取消打包，临时文件已清理" in window.pack_status_log.toPlainText())

    print("== 输入变更使旧解析失效 ==")
    calls["errors"].clear()
    downloads_before = stub.STATE["download_calls"]
    window.pack_input_edit.setText("https://example.com/album/2")
    app.processEvents()
    check("输入变化后 meta_label 回 尚未解析", window.pack_meta_label.text() == "尚未解析")
    check("输入变化后开始打包禁用", not window.pack_start_button.isEnabled())
    check("输入变化后 bundle 清空", window._pack_bundle is None)
    window._on_pack_start_clicked()
    ok = wait_until(lambda: bool(calls["errors"]), 5.0, "打包拒绝提示")
    check("未重新解析时点击打包 -> 提示链接已更改",
          ok and "链接已更改" in calls["errors"][0][1] and "解析页面" in calls["errors"][0][1],
          calls["errors"][0][1] if calls["errors"] else "")
    check("未重新解析时未触发打包", stub.STATE["download_calls"] == downloads_before,
          f"count={stub.STATE['download_calls']}")
    calls["errors"].clear()
    parse_and_wait(window, PAGE_URL)
    check("重新解析后开始打包恢复", window.pack_start_button.isEnabled())

    print("== 打包失败提示 ==")
    calls["errors"].clear()
    stub.STATE["download_error"] = "模拟打包失败"
    stub.STATE["download_sleep_seconds"] = 0.001
    window.pack_start_button.click()
    ok = wait_until(lambda: bool(calls["errors"]), 10.0, "打包失败弹窗")
    check("打包失败触发错误弹窗", ok)
    check("失败弹窗收到 PageDownloadError 文本",
          bool(calls["errors"]) and "模拟打包失败" in calls["errors"][0][1],
          calls["errors"][0][1] if calls["errors"] else "")
    check("失败后阶段文本 打包失败", window.pack_stage_label.text() == "打包失败")
    check("失败后开始打包恢复可用", window.pack_start_button.isEnabled())
    check("失败后取消按钮禁用", not window.pack_cancel_button.isEnabled())
    check("失败写入日志", "打包失败" in window.pack_status_log.toPlainText())
    stub.STATE["download_error"] = None

    print("== 设置持久化 ==")
    second_dir = tempfile.mkdtemp(prefix="pack_gui_test2_")
    window.pack_save_dir_edit.setText(second_dir)
    window.pack_proxy_combo.setCurrentIndex(window.pack_proxy_combo.findData("manual"))
    window.pack_proxy_edit.setText("http://127.0.0.1:12348")
    app.processEvents()
    stored = gui_settings.load_settings()
    check("设置文件写入 pack_save_dir", stored.get("pack_save_dir") == second_dir,
          str(stored.get("pack_save_dir")))
    check("pack 代理模式复用 proxy_mode 键", stored.get("proxy_mode") == "manual",
          str(stored.get("proxy_mode")))
    check("pack 代理地址复用 proxy_url 键",
          stored.get("proxy_url") == "http://127.0.0.1:12348",
          str(stored.get("proxy_url")))
    second = mw.MainWindow()
    second.show()
    app.processEvents()
    check("重启后恢复 pack_save_dir",
          second.pack_save_dir_edit.text() == second_dir,
          second.pack_save_dir_edit.text())
    check("重启后恢复打包页代理模式与地址",
          second.pack_proxy_combo.currentData() == "manual"
          and second.pack_proxy_edit.text() == "http://127.0.0.1:12348")
    check("重启后打包页 meta 仍为 尚未解析", second.pack_meta_label.text() == "尚未解析")
    second.close()
    second.deleteLater()
    app.processEvents()

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
