"""三套 QSS 主题：chiikawa 粉彩可爱风 / 纯白 / 纯黑。

每套 QSS 首行都带 /* theme:<name> */ 标记，测试据此断言 app.styleSheet()。
chiikawa 主题为纯 QSS 实现，不使用任何图片资源，也不使用受版权保护的角色形象。
"""

CHIIKAWA_QSS = """/* theme:chiikawa */
QWidget {
    background-color: #FFF6EC;
    color: #5B4A4F;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #FFF6EC;
}
QTabWidget::pane {
    border: 2px solid #FFD9E3;
    border-radius: 12px;
    background-color: #FFFDF9;
    top: -1px;
}
QTabBar::tab {
    background-color: #FFE8EF;
    color: #B36B7F;
    border: 1px solid #FFD9E3;
    border-bottom: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 7px 22px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background-color: #FFD3E0;
    color: #7C4A5B;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #A8D8F0;
    color: #2F6F8F;
}
QPushButton {
    background-color: #FFB7C5;
    color: #6B3A47;
    border: 2px solid #FF9FB5;
    border-radius: 12px;
    padding: 6px 16px;
    min-height: 16px;
}
QPushButton:hover {
    background-color: #A8D8F0;
    border-color: #7FC4E8;
    color: #234E63;
}
QPushButton:pressed {
    background-color: #FF9FB5;
}
QPushButton:disabled {
    background-color: #F2E3E7;
    border-color: #EAD4DA;
    color: #B9A2A8;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #FFFDF9;
    color: #5B4A4F;
    border: 2px solid #FFD9E3;
    border-radius: 10px;
    padding: 4px 8px;
    selection-background-color: #A8D8F0;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border-color: #A8D8F0;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: #FFFDF9;
    color: #5B4A4F;
    border: 2px solid #FFD9E3;
    border-radius: 8px;
    selection-background-color: #FFE8EF;
    selection-color: #6B3A47;
}
QProgressBar {
    background-color: #FFE8EF;
    border: 2px solid #FFD9E3;
    border-radius: 10px;
    text-align: center;
    color: #6B3A47;
    min-height: 16px;
}
QProgressBar::chunk {
    background-color: #FFB7C5;
    border-radius: 8px;
}
QPlainTextEdit {
    background-color: #FFF9F2;
}
QLabel {
    background-color: transparent;
}
QMenuBar {
    background-color: #FFE8EF;
}
QMenuBar::item:selected {
    background-color: #A8D8F0;
    border-radius: 6px;
}
QMenu {
    background-color: #FFFDF9;
    border: 2px solid #FFD9E3;
}
QMenu::item:selected {
    background-color: #FFE8EF;
}
"""

LIGHT_QSS = """/* theme:light */
QWidget {
    background-color: #FFFFFF;
    color: #1A1A1A;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #D0D0D0;
    background-color: #FFFFFF;
}
QTabBar::tab {
    background-color: #F0F0F0;
    border: 1px solid #D0D0D0;
    border-bottom: none;
    padding: 6px 18px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #FFFFFF;
    color: #000000;
}
QPushButton {
    background-color: #F0F0F0;
    border: 1px solid #C0C0C0;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover {
    background-color: #E4E4E4;
}
QPushButton:disabled {
    color: #A0A0A0;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #C0C0C0;
    border-radius: 3px;
    padding: 3px 6px;
}
QProgressBar {
    background-color: #F0F0F0;
    border: 1px solid #C0C0C0;
    border-radius: 3px;
    text-align: center;
    min-height: 14px;
}
QProgressBar::chunk {
    background-color: #4A90D9;
}
QMenuBar {
    background-color: #F8F8F8;
}
QMenu::item:selected {
    background-color: #E4E4E4;
}
"""

DARK_QSS = """/* theme:dark */
QWidget {
    background-color: #000000;
    color: #F0F0F0;
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #000000;
}
QTabWidget::pane {
    border: 1px solid #2A2A2A;
    background-color: #000000;
}
QTabBar::tab {
    background-color: #111111;
    color: #B0B0B0;
    border: 1px solid #2A2A2A;
    border-bottom: none;
    padding: 6px 18px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #1F1F1F;
    color: #FFFFFF;
}
QPushButton {
    background-color: #1A1A1A;
    color: #F0F0F0;
    border: 1px solid #3A3A3A;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover {
    background-color: #2A2A2A;
}
QPushButton:disabled {
    color: #606060;
}
QLineEdit, QComboBox, QPlainTextEdit {
    background-color: #0A0A0A;
    color: #F0F0F0;
    border: 1px solid #3A3A3A;
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: #4A4A4A;
}
QComboBox QAbstractItemView {
    background-color: #0A0A0A;
    color: #F0F0F0;
    border: 1px solid #3A3A3A;
    selection-background-color: #3A3A3A;
}
QProgressBar {
    background-color: #0A0A0A;
    border: 1px solid #3A3A3A;
    border-radius: 3px;
    text-align: center;
    color: #F0F0F0;
    min-height: 14px;
}
QProgressBar::chunk {
    background-color: #E0E0E0;
}
QMenuBar {
    background-color: #0A0A0A;
}
QMenuBar::item:selected {
    background-color: #2A2A2A;
}
QMenu {
    background-color: #111111;
    border: 1px solid #3A3A3A;
}
QMenu::item:selected {
    background-color: #2A2A2A;
}
"""

THEMES = {
    "chiikawa": CHIIKAWA_QSS,
    "light": LIGHT_QSS,
    "dark": DARK_QSS,
}


def apply_theme(app, name):
    """把 name 对应 QSS 应用到 app；未知名称返回 False。"""
    qss = THEMES.get(name)
    if app is None or qss is None:
        return False
    app.setStyleSheet(qss)
    return True
