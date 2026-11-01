"""飞机模式（Telegram）标签页逻辑自测（tg_dl 未就绪/测试时使用内置 stub）。

用法:
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe gui/tests/test_tg_gui.py

覆盖验收点：
  * mode_tabs 四个标签页，第四页为“飞机模式”（对象名 tg_tab），B站/万能/视图打包控件仍可访问
  * tg_* 控件对象名、按钮文本、placeholder、条数微调、类型下拉数据、密码框 EchoMode
  * 扫码登录：qr_ready 后 tg_qr_label 有 QPixmap（矩阵由 stub 生成）、成功后状态“已登录，会话已保存”
  * 登录在后台线程；TgConfig 透传（api_id/api_hash/session_path=default_session_path()/proxy）
  * 日志不打印完整 API Hash；password_required 提示填写两步验证密码后重试
  * 预览频道：失败提示、成功填充标题/用户名/总数/各类型数量
  * 下载在后台线程；完成弹窗含保存目录与文件数；阶段映射（下载媒体/完成）；取消流程
  * 代理透传：手动 / 自动检测 / 不使用（系统网络）
  * 退出登录：调用 logout(config)、状态回到未登录并清空二维码
  * 设置持久化（新窗口恢复 tg_* 设置）
  * TG_COMPLIANCE_TEXT 与其它合规文本均不同
  * 飞机模式标签页 chiikawa 主题离屏截图
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BILIDOWNLOADER_SETTINGS"] = os.path.join(
    tempfile.mkdtemp(prefix="bili_tg_settings_"), "settings.json"
)

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from gui.tests import stub_page_dl as page_stub  # noqa: E402
from gui.tests import stub_tg_dl as stub  # noqa: E402
from gui.tests import stub_uni_dl as uni_stub  # noqa: E402

sys.modules["tg_dl"] = stub  # 必须在导入 gui.main_window 之前注入
sys.modules["page_dl"] = page_stub
sys.modules["uni_dl"] = uni_stub

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

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

API_ID = "1234567"
API_HASH = "0123456789abcdef0123456789abcdef"
DETECTED_PROXY = "http://127.0.0.1:7890"

TG_OBJECT_NAMES = [
    "tg_api_id_edit",
    "tg_api_hash_edit",
    "tg_login_button",
    "tg_logout_button",
    "tg_status_label",
    "tg_qr_label",
    "tg_channel_edit",
    "tg_list_button",
    "tg_media_info_label",
    "tg_limit_spin",
    "tg_types_combo",
    "tg_save_dir_edit",
    "tg_browse_button",
    "tg_password_edit",
    "tg_start_button",
    "tg_cancel_button",
    "tg_progress_bar",
    "tg_stage_label",
    "tg_percent_label",
    "tg_speed_label",
    "tg_status_log",
    "tg_compliance_label",
]


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


def qr_has_pixmap(window):
    pixmap = window.tg_qr_label.pixmap()
    return pixmap is not None and not pixmap.isNull()


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

    print("== 标签页与既有控件 ==")
    check("mode_tabs 四个标签页", window.mode_tabs.count() == 4,
          f"count={window.mode_tabs.count()}")
    check("tab0 标题为 B站专属", window.mode_tabs.tabText(0) == "B站专属")
    check("tab1 标题为 万能下载", window.mode_tabs.tabText(1) == "万能下载")
    check("tab2 标题为 视图打包", window.mode_tabs.tabText(2) == "视图打包")
    check("tab3 标题为 飞机模式", window.mode_tabs.tabText(3) == "飞机模式")
    check("第四页对象名为 tg_tab", window.mode_tabs.widget(3).objectName() == "tg_tab",
          window.mode_tabs.widget(3).objectName())
    check("tg_dl 可选导入就绪", mw._TG_READY is True, str(mw._TG_IMPORT_ERROR))
    for attr in ("input_edit", "quality_combo", "save_dir_edit", "download_button",
                 "cancel_button", "progress_bar", "status_log", "cookie_action"):
        check(f"B站控件 {attr} 仍可访问", hasattr(window, attr))
    for attr in ("uni_input_edit", "uni_parse_button", "uni_download_button",
                 "uni_save_dir_edit", "uni_status_log", "uni_proxy_combo", "uni_proxy_edit"):
        check(f"万能控件 {attr} 仍可访问", hasattr(window, attr))
    for attr in ("pack_input_edit", "pack_parse_button", "pack_start_button",
                 "pack_cancel_button", "pack_save_dir_edit", "pack_status_log"):
        check(f"视图打包控件 {attr} 仍可访问", hasattr(window, attr))

    print("== 飞机模式控件对象名与默认状态 ==")
    for attr in TG_OBJECT_NAMES:
        widget = getattr(window, attr, None)
        check(f"控件 {attr} 存在且 objectName 正确",
              widget is not None and widget.objectName() == attr)
    check("tg_login_button 文本为 扫码登录", window.tg_login_button.text() == "扫码登录")
    check("tg_logout_button 文本为 退出登录", window.tg_logout_button.text() == "退出登录")
    check("tg_list_button 文本为 预览频道", window.tg_list_button.text() == "预览频道")
    check("tg_start_button 文本为 开始下载", window.tg_start_button.text() == "开始下载")
    check("tg_cancel_button 文本为 取消", window.tg_cancel_button.text() == "取消")
    check("tg_status_label 初始文本为 未登录", window.tg_status_label.text() == "未登录")
    check("tg_api_id_edit placeholder 为 API ID（数字）",
          window.tg_api_id_edit.placeholderText() == "API ID（数字）",
          window.tg_api_id_edit.placeholderText())
    check("tg_api_hash_edit placeholder 为 API Hash",
          window.tg_api_hash_edit.placeholderText() == "API Hash",
          window.tg_api_hash_edit.placeholderText())
    check("tg_channel_edit placeholder 含 @频道 与 t.me 链接",
          "@频道" in window.tg_channel_edit.placeholderText()
          and "t.me" in window.tg_channel_edit.placeholderText())
    check("tg_no_save_check 存在且默认未勾选", not window.tg_no_save_check.isChecked())
    check("tg_no_save_check 文本含 不保存 API 凭据",
          "不保存 API 凭据" in window.tg_no_save_check.text())
    check("tg_password_edit 为 Password EchoMode",
          window.tg_password_edit.echoMode() == mw.QLineEdit.Password)
    check("tg_password_edit placeholder 含 两步验证密码",
          "两步验证密码" in window.tg_password_edit.placeholderText())
    check("tg_qr_label 最小尺寸不小于 240x240",
          window.tg_qr_label.minimumWidth() >= 240 and window.tg_qr_label.minimumHeight() >= 240,
          f"{window.tg_qr_label.minimumWidth()}x{window.tg_qr_label.minimumHeight()}")
    check("tg_qr_label 初始无二维码 pixmap", not qr_has_pixmap(window))
    check("tg_limit_spin 范围 0..1000000",
          window.tg_limit_spin.minimum() == 0 and window.tg_limit_spin.maximum() == 1000000)
    check("tg_limit_spin 默认 0", window.tg_limit_spin.value() == 0)
    check("tg_limit_spin 后缀为  条（0=全部）",
          window.tg_limit_spin.suffix() == " 条（0=全部）", window.tg_limit_spin.suffix())
    check("tg_types_combo 五项且数据为 None/photo/video/document/audio",
          window.tg_types_combo.count() == 5
          and [window.tg_types_combo.itemData(i) for i in range(5)]
          == [None, "photo", "video", "document", "audio"],
          str([window.tg_types_combo.itemData(i) for i in range(5)]))
    check("tg_types_combo 文本为 全部媒体/图片/视频/文件/音频",
          [window.tg_types_combo.itemText(i) for i in range(5)]
          == ["全部媒体", "图片", "视频", "文件", "音频"])
    check("tg_types_combo 默认全部媒体", window.tg_types_combo.currentData() is None)
    check("tg_save_dir_edit 只读", window.tg_save_dir_edit.isReadOnly())
    check("tg_media_info_label 初始为 尚未预览", window.tg_media_info_label.text() == "尚未预览")
    check("tg_cancel_button 默认禁用", not window.tg_cancel_button.isEnabled())
    check("tg_progress_bar 初始 0", window.tg_progress_bar.value() == 0)

    print("== 合规声明 ==")
    check("TG_COMPLIANCE_TEXT != COMPLIANCE_TEXT", mw.TG_COMPLIANCE_TEXT != mw.COMPLIANCE_TEXT)
    check("TG_COMPLIANCE_TEXT != UNI_COMPLIANCE_TEXT",
          mw.TG_COMPLIANCE_TEXT != mw.UNI_COMPLIANCE_TEXT)
    check("TG_COMPLIANCE_TEXT != PACK_COMPLIANCE_TEXT",
          mw.TG_COMPLIANCE_TEXT != mw.PACK_COMPLIANCE_TEXT)
    check("tg_compliance_label 文本为 TG_COMPLIANCE_TEXT",
          window.tg_compliance_label.text() == mw.TG_COMPLIANCE_TEXT)
    labels = [lbl.text() for lbl in window.findChildren(QLabel) if lbl.text() == mw.COMPLIANCE_TEXT]
    check("COMPLIANCE_TEXT 原文在窗口中数量仍为 1", len(labels) == 1)
    check("TG_COMPLIANCE_TEXT 含 飞机模式 与 Telethon",
          "飞机模式" in mw.TG_COMPLIANCE_TEXT and "Telethon" in mw.TG_COMPLIANCE_TEXT)

    print("== 登录参数校验 ==")
    window.mode_tabs.setCurrentIndex(3)
    calls["errors"].clear()
    window.tg_login_button.click()
    app.processEvents()
    check("未填 API ID 点登录 -> show_error",
          bool(calls["errors"]) and "API ID" in calls["errors"][0][1])
    check("未填 API ID 未调用 qr_login", stub.STATE["qr_login_calls"] == 0)
    window.tg_api_id_edit.setText("not-a-number")
    window.tg_api_hash_edit.setText(API_HASH)
    calls["errors"].clear()
    window.tg_login_button.click()
    app.processEvents()
    check("API ID 非数字 -> 提示必须是数字",
          bool(calls["errors"]) and "必须是数字" in calls["errors"][0][1])
    check("API ID 非数字未调用 qr_login", stub.STATE["qr_login_calls"] == 0)

    print("== 扫码登录 ==")
    stub.reset_state()
    stub.STATE["login_sleep_seconds"] = 0.02
    window.tg_api_id_edit.setText(API_ID)
    window.tg_api_hash_edit.setText(API_HASH)
    window.tg_password_edit.clear()
    calls["errors"].clear()
    window.tg_login_button.click()
    app.processEvents()
    check("登录中 tg_login_button 禁用", not window.tg_login_button.isEnabled())
    check("登录中 tg_login_button 文本为 登录中…", window.tg_login_button.text() == "登录中…")
    check("登录中 tg_status_label 为 等待扫码…", window.tg_status_label.text() == "等待扫码…")
    ok = wait_until(lambda: qr_has_pixmap(window), 10.0, what="二维码 pixmap 显示")
    check("qr_ready 后 tg_qr_label 有 QPixmap", ok)
    check("二维码矩阵由 stub 生成（qr_matrix 已调用）", stub.STATE["qr_matrix_calls"] > 0,
          f"calls={stub.STATE['qr_matrix_calls']}")
    pixmap = window.tg_qr_label.pixmap()
    check("二维码 pixmap 适配 240x240 标签区且不溢出",
          pixmap is not None and 100 <= pixmap.width() <= 240
          and pixmap.width() == pixmap.height(),
          f"{pixmap.width() if pixmap else 0}x{pixmap.height() if pixmap else 0}")
    ok = wait_until(lambda: window.tg_status_label.text() == "已登录，会话已保存",
                    10.0, what="登录成功状态")
    check("登录成功后 tg_status_label 为 已登录，会话已保存", ok)
    check("登录后 tg_login_button 恢复可用", window.tg_login_button.isEnabled())
    check("登录后 tg_login_button 文本复位", window.tg_login_button.text() == "扫码登录")
    check("登录在后台线程执行",
          stub.STATE["qr_thread_id"] is not None
          and stub.STATE["qr_thread_id"] != MAIN_THREAD_ID,
          f"login={stub.STATE['qr_thread_id']} ui={MAIN_THREAD_ID}")
    config = stub.STATE["last_config"]
    check("TgConfig 透传 api_id", config is not None and config.api_id == int(API_ID),
          str(getattr(config, "api_id", None)))
    check("TgConfig 透传 api_hash", config is not None and config.api_hash == API_HASH)
    check("TgConfig.session_path 取 default_session_path()",
          config is not None and config.session_path == stub.default_session_path(),
          str(getattr(config, "session_path", None)))
    check("登录透传 timeout=180", stub.STATE["last_timeout"] == 180,
          str(stub.STATE["last_timeout"]))
    check("未填密码时透传 password=None", stub.STATE["last_password"] is None,
          str(stub.STATE["last_password"]))
    log_text = window.tg_status_log.toPlainText()
    check("日志不包含完整 API Hash", API_HASH not in log_text)
    check("日志包含脱敏后的 hash 前缀", API_HASH[:4] in log_text)
    check("日志含扫码登录成功", "扫码登录成功" in log_text)

    print("== on_qr 回调兼容（核心可回传矩阵） ==")
    stub.reset_state()
    stub.STATE["qr_two_args"] = True
    stub.STATE["login_sleep_seconds"] = 0.02
    window.tg_logout_button.click()
    app.processEvents()
    check("重新登录前二维码已清空", not qr_has_pixmap(window))
    window.tg_login_button.click()
    ok = wait_until(lambda: qr_has_pixmap(window)
                    and window.tg_status_label.text() == "已登录，会话已保存",
                    10.0, what="二参数 on_qr 登录")
    check("核心以 on_qr(url, matrix) 回调时二维码仍渲染", ok)
    check("二参数回调时不再重复调用 qr_matrix（矩阵由核心提供）",
          stub.STATE["qr_matrix_calls"] == 1, f"calls={stub.STATE['qr_matrix_calls']}")
    stub.STATE["qr_two_args"] = False

    print("== 两步验证密码 ==")
    stub.reset_state()
    stub.STATE["password_required"] = True
    calls["errors"].clear()
    window.tg_password_edit.setText("123456")
    window.tg_login_button.click()
    ok = wait_until(lambda: bool(calls["errors"]), 10.0, what="两步验证错误弹窗")
    check("password_required 触发错误弹窗", ok)
    check("弹窗提示填写两步验证密码",
          bool(calls["errors"]) and "两步验证密码" in calls["errors"][0][1],
          calls["errors"][0][1] if calls["errors"] else "")
    check("日志提示填写两步密码后重试",
          "两步验证密码" in window.tg_status_log.toPlainText())
    check("两步验证后 tg_status_label 回到未登录", window.tg_status_label.text() == "未登录")
    check("两步验证后 tg_login_button 恢复", window.tg_login_button.isEnabled())
    check("已填写的两步密码透传 stub", stub.STATE["last_password"] == "123456",
          str(stub.STATE["last_password"]))
    stub.STATE["password_required"] = False
    window.tg_password_edit.clear()

    print("== 退出登录 ==")
    stub.reset_state()
    window.tg_logout_button.click()
    app.processEvents()
    check("退出登录调用 logout(config)", stub.STATE["logout_calls"] == 1,
          f"calls={stub.STATE['logout_calls']}")
    check("logout 收到 TgConfig", stub.STATE["last_logout_config"] is not None)
    check("退出登录后 tg_status_label 为 未登录", window.tg_status_label.text() == "未登录")
    check("退出登录清空二维码 pixmap", not qr_has_pixmap(window))
    check("退出登录写入日志", "已退出登录" in window.tg_status_log.toPlainText())

    print("== 预览频道 ==")
    stub.reset_state()
    window.tg_channel_edit.setText("")
    calls["errors"].clear()
    window.tg_list_button.click()
    app.processEvents()
    check("未填频道点预览 -> 提示请输入频道",
          bool(calls["errors"]) and "请输入频道" in calls["errors"][0][1])
    check("未填频道未调用 list_channel_media", stub.STATE["list_calls"] == 0)
    calls["errors"].clear()
    window.tg_channel_edit.setText("garbage-input")
    window.tg_list_button.click()
    ok = wait_until(lambda: bool(calls["errors"]), 10.0, what="预览失败弹窗")
    check("非法频道 -> 错误弹窗（TgInputError 文本）",
          ok and "无法解析频道" in calls["errors"][0][1])
    check("预览失败写入日志", "预览失败" in window.tg_status_log.toPlainText())
    check("预览失败后 tg_media_info_label 为 预览失败",
          window.tg_media_info_label.text() == "预览失败")
    check("预览失败后 tg_list_button 恢复", window.tg_list_button.isEnabled())

    window.tg_limit_spin.setValue(0)
    window.tg_channel_edit.setText(stub.CHANNEL)
    calls["errors"].clear()
    window.tg_list_button.click()
    ok = wait_until(lambda: window.tg_media_info_label.text().startswith("标题："),
                    10.0, what="预览结果填充")
    check("预览成功填充 tg_media_info_label", ok)
    info_text = window.tg_media_info_label.text()
    check("媒体信息含 标题/用户名/总数",
          all(key in info_text for key in ("标题：", "用户名：", "总数：")), info_text)
    check("媒体信息含各类型数量 图片/视频/文件/音频",
          all(key in info_text for key in ("图片：", "视频：", "文件：", "音频：")), info_text)
    check("媒体信息标题取自 stub 频道信息", stub.CHANNEL_TITLE in info_text)
    check("媒体信息总数取自 stub（7 项）", "总数：7" in info_text, info_text)
    check("媒体信息各类数量正确（3/2/1/1）",
          "图片：3" in info_text and "视频：2" in info_text
          and "文件：1" in info_text and "音频：1" in info_text, info_text)
    check("预览成功写入日志", "预览成功" in window.tg_status_log.toPlainText())
    check("预览在后台线程执行",
          stub.STATE["list_thread_id"] is not None
          and stub.STATE["list_thread_id"] != MAIN_THREAD_ID,
          f"list={stub.STATE['list_thread_id']} ui={MAIN_THREAD_ID}")
    check("预览透传频道", stub.STATE["last_channel"] == stub.CHANNEL,
          str(stub.STATE["last_channel"]))
    check("预览默认 media_types=None（统计全部类型）",
          stub.STATE["last_media_types"] is None, str(stub.STATE["last_media_types"]))
    check("预览透传 tg_limit_spin 的条数", stub.STATE["last_list_limit"] == 0,
          str(stub.STATE["last_list_limit"]))
    check("预览后 tg_list_button 文本复位", window.tg_list_button.text() == "预览频道")

    print("== 代理透传 ==")
    stub.reset_state()
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("manual"))
    window.uni_proxy_edit.setText(" socks5://127.0.0.1:7891 ")
    app.processEvents()
    before_detect = stub.STATE["detect_proxy_calls"]
    before_list = stub.STATE["list_calls"]
    window.tg_list_button.click()
    ok = wait_until(lambda: window.tg_list_button.isEnabled()
                    and stub.STATE["list_calls"] > before_list, 10.0, what="手动代理预览")
    proxy = getattr(stub.STATE["last_config"], "proxy", "missing")
    check("手动代理写入 TgConfig(proxy=...)（去首尾空格）",
          ok and proxy == "socks5://127.0.0.1:7891", str(proxy))
    check("手动代理不触发本地代理探测",
          stub.STATE["detect_proxy_calls"] == before_detect,
          str(stub.STATE["detect_proxy_calls"]))

    stub.STATE["detected_proxy"] = DETECTED_PROXY
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("auto"))
    app.processEvents()
    before_list = stub.STATE["list_calls"]
    window.tg_list_button.click()
    ok = wait_until(lambda: window.tg_list_button.isEnabled()
                    and stub.STATE["list_calls"] > before_list, 10.0, what="自动检测代理预览")
    proxy = getattr(stub.STATE["last_config"], "proxy", "missing")
    check("自动检测代理写入 TgConfig(proxy=...)", ok and proxy == DETECTED_PROXY, str(proxy))
    check("自动检测模式调用了本地代理探测", stub.STATE["detect_proxy_calls"] > 0,
          str(stub.STATE["detect_proxy_calls"]))

    stub.STATE["detected_proxy"] = None
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("none"))
    app.processEvents()
    before_list = stub.STATE["list_calls"]
    window.tg_list_button.click()
    ok = wait_until(lambda: window.tg_list_button.isEnabled()
                    and stub.STATE["list_calls"] > before_list, 10.0, what="不使用代理预览")
    proxy = getattr(stub.STATE["last_config"], "proxy", "missing")
    check("不使用代理时 TgConfig(proxy=None)", ok and proxy is None, str(proxy))
    check("不使用代理写入日志“代理：系统网络”",
          "代理：系统网络" in window.tg_status_log.toPlainText())
    window.uni_proxy_combo.setCurrentIndex(window.uni_proxy_combo.findData("auto"))
    app.processEvents()

    print("== 下载流程 ==")
    tmpdir = tempfile.mkdtemp(prefix="tg_gui_test_")
    window.tg_save_dir_edit.setText(tmpdir)
    stub.reset_state()
    stub.STATE["download_sleep_seconds"] = 0.001
    window.tg_types_combo.setCurrentIndex(window.tg_types_combo.findData("video"))
    window.tg_limit_spin.setValue(2)
    calls["successes"].clear()
    calls["errors"].clear()
    window.tg_start_button.click()
    app.processEvents()
    check("下载中 tg_start_button 禁用", not window.tg_start_button.isEnabled())
    check("下载中 tg_cancel_button 可用", window.tg_cancel_button.isEnabled())
    ok = wait_until(lambda: bool(calls["successes"]), 20.0, what="下载完成弹窗")
    check("下载完成触发成功弹窗", ok)
    check("下载在后台线程执行",
          stub.STATE["download_thread_id"] is not None
          and stub.STATE["download_thread_id"] != MAIN_THREAD_ID,
          f"download={stub.STATE['download_thread_id']} ui={MAIN_THREAD_ID}")
    check("下载透传 save_dir", stub.STATE["last_save_dir"] == tmpdir,
          str(stub.STATE["last_save_dir"]))
    check("下载透传 media_types=video",
          stub.STATE["last_download_media_types"] == "video",
          str(stub.STATE["last_download_media_types"]))
    check("下载透传 limit=2", stub.STATE["last_download_limit"] == 2,
          str(stub.STATE["last_download_limit"]))
    check("下载透传 cancel 回调", stub.STATE["last_cancel_hook"] is True)
    message = calls["successes"][0][2] if calls["successes"] else ""
    check("完成弹窗显示保存目录", tmpdir in message, message)
    check("完成弹窗显示文件数（返回列表长度）", "2 个文件" in message, message)
    check("完成弹窗携带输出目录",
          bool(calls["successes"]) and Path(calls["successes"][0][3]) == Path(tmpdir),
          str(calls["successes"][0][3]) if calls["successes"] else "")
    check("完成后进度条 100%", window.tg_progress_bar.value() == 100)
    check("完成后 tg_stage_label 为 完成", window.tg_stage_label.text() == "完成")
    check("完成后 tg_percent_label 为 100%", window.tg_percent_label.text() == "100%")
    check("完成后 tg_cancel_button 禁用", not window.tg_cancel_button.isEnabled())
    check("完成后 tg_start_button 恢复", window.tg_start_button.isEnabled())
    tg_log = window.tg_status_log.toPlainText()
    check("阶段日志含“下载媒体”（stage 映射）", "下载媒体" in tg_log)
    check("完成日志含文件数与保存目录",
          "下载完成：共 2 个文件" in tg_log and tmpdir in tg_log)

    print("== 取消流程 ==")
    stub.reset_state()
    stub.STATE["download_sleep_seconds"] = 0.1
    calls["cancelled"].clear()
    calls["successes"].clear()
    window.tg_start_button.click()
    ok = wait_until(lambda: stub.STATE["download_started"].is_set(), 5.0, what="下载启动")
    check("下载已启动", ok)
    if ok:
        window.tg_cancel_button.click()
    ok = wait_until(lambda: bool(calls["cancelled"]), 10.0, what="取消提示出现")
    check("取消弹窗出现", ok)
    check("取消后 tg_stage_label 为 已取消", window.tg_stage_label.text() == "已取消")
    check("取消后 tg_start_button 恢复", window.tg_start_button.isEnabled())
    check("取消后 tg_cancel_button 禁用", not window.tg_cancel_button.isEnabled())
    check("取消后未触发成功弹窗", not calls["successes"])

    print("== 截图 ==")
    window.mode_tabs.setCurrentIndex(3)
    # 截图前再扫码登录一次，让快照里包含 QPainter 真实渲染的二维码
    stub.reset_state()
    stub.STATE["login_sleep_seconds"] = 0.05
    window.tg_login_button.click()
    qr_ok = wait_until(lambda: qr_has_pixmap(window), 10.0, what="截图前二维码显示")
    wait_until(lambda: window.tg_status_label.text() == "已登录，会话已保存",
               10.0, what="截图前登录完成")
    check("截图前重新登录并显示二维码", qr_ok)
    app.processEvents()
    artifacts = Path(__file__).resolve().parent / "artifacts"
    artifacts.mkdir(exist_ok=True)
    shot = artifacts / "tg_chiikawa.png"
    saved = window.grab().save(str(shot))
    check("飞机模式标签页 chiikawa 离屏截图保存",
          bool(saved) and shot.exists() and shot.stat().st_size > 0, f"路径={shot}")
    print(f"  截图路径：{shot}")

    print("== 设置持久化 ==")
    window.tg_api_id_edit.setText("7654321")
    window.tg_api_hash_edit.setText("fedcba9876543210fedcba9876543210")
    window.tg_channel_edit.setText("@saved_channel")
    window.tg_save_dir_edit.setText(tmpdir)
    window.tg_limit_spin.setValue(25)
    window.tg_types_combo.setCurrentIndex(window.tg_types_combo.findData("audio"))
    app.processEvents()
    second = mw.MainWindow()
    second.show()
    app.processEvents()
    check("重启后恢复 tg_api_id", second.tg_api_id_edit.text() == "7654321",
          second.tg_api_id_edit.text())
    check("重启后恢复 tg_api_hash",
          second.tg_api_hash_edit.text() == "fedcba9876543210fedcba9876543210")
    check("重启后恢复 tg_channel", second.tg_channel_edit.text() == "@saved_channel")
    check("重启后恢复 tg_save_dir", second.tg_save_dir_edit.text() == tmpdir)
    check("重启后恢复 tg_limit", second.tg_limit_spin.value() == 25,
          str(second.tg_limit_spin.value()))
    check("重启后恢复 tg_types", second.tg_types_combo.currentData() == "audio",
          str(second.tg_types_combo.currentData()))
    second.close()
    second.deleteLater()
    app.processEvents()

    print("== 不保存 API 凭据 ==")
    window.tg_no_save_check.setChecked(True)
    window.tg_api_id_edit.setText("8888888")
    window.tg_api_hash_edit.setText("0123456789abcdef0123456789abcdef")
    app.processEvents()
    third = mw.MainWindow()
    third.show()
    app.processEvents()
    check("不保存凭据：新窗口 API ID 为空", third.tg_api_id_edit.text() == "",
          third.tg_api_id_edit.text())
    check("不保存凭据：新窗口 API Hash 为空", third.tg_api_hash_edit.text() == "",
          third.tg_api_hash_edit.text())
    check("不保存凭据：checkbox 恢复为勾选", third.tg_no_save_check.isChecked())
    third.close()
    third.deleteLater()
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
