"""GUI 弹窗薄封装，测试中可 monkeypatch。"""

import os

from PySide6.QtWidgets import QMessageBox


def show_error(parent, message):
    """以错误弹窗展示可直接展示的中文 message。"""
    QMessageBox.critical(parent, "错误", message)


def show_cancelled(parent, message="已取消下载"):
    """取消提示。"""
    QMessageBox.information(parent, "提示", message)


def show_success(parent, title, message, folder=None):
    """成功弹窗；传入 folder 时提供"打开所在文件夹"按钮（os.startfile）。

    返回 True 表示用户点击了"打开所在文件夹"。
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Information)
    box.setWindowTitle(title)
    box.setText(message)
    open_button = None
    if folder is not None:
        open_button = box.addButton("打开所在文件夹", QMessageBox.ActionRole)
    box.addButton("关闭", QMessageBox.RejectRole)
    box.exec()
    if folder is not None and box.clickedButton() is open_button:
        try:
            os.startfile(str(folder))
        except OSError as exc:
            show_error(parent, f"无法打开文件夹：{exc}")
        return True
    return False
