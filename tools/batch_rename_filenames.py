import os
import sys

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


def batch_rename_files(directory, old_str, new_str) -> int:
    renamed_count = 0
    for root, _, files in os.walk(directory):
        for filename in files:
            if old_str in filename:
                new_filename = filename.replace(old_str, new_str)
                os.rename(os.path.join(root, filename), os.path.join(root, new_filename))
                renamed_count += 1
    return renamed_count


class _BatchRenameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量替换文件名")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        form = QFormLayout()

        dir_row = QHBoxLayout()
        self._dir_input = QLineEdit()
        self._dir_input.setPlaceholderText("选择文件夹…")
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_folder)
        dir_row.addWidget(self._dir_input)
        dir_row.addWidget(browse_btn)
        form.addRow("选择文件夹：", dir_row)

        self._old_str = QLineEdit()
        self._new_str = QLineEdit()
        form.addRow("原文件名包含：", self._old_str)
        form.addRow("新文件名替换为：", self._new_str)
        layout.addLayout(form)

        # --- 确定 / 取消 ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("执行重命名")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if d:
            self._dir_input.setText(d)

    def directory(self) -> str:
        return self._dir_input.text().strip()

    def old_str(self) -> str:
        return self._old_str.text()

    def new_str(self) -> str:
        return self._new_str.text()


def run_batch_rename_filenames():
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _BatchRenameDialog()
    if dialog.exec() != QDialog.Accepted:
        return

    directory = dialog.directory()
    old_str = dialog.old_str()
    new_str = dialog.new_str()

    if not directory or not old_str:
        QMessageBox.warning(None, "输入错误", "请填写文件夹路径和要查找的文件名内容。")
        return

    count = batch_rename_files(directory, old_str, new_str)
    QMessageBox.information(None, "完成", f"重命名完成，共修改 {count} 个文件。")


if __name__ == "__main__":
    run_batch_rename_filenames()
