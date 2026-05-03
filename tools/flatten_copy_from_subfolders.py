import os
import shutil
import sys

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


def copy_specific_files(source_dir, target_dir, file_extension):
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(file_extension):
                source_file_path = os.path.join(root, file)
                target_file_path = os.path.join(target_dir, file)

                if os.path.exists(target_file_path):
                    base, extension = os.path.splitext(file)
                    counter = 1
                    new_target = os.path.join(target_dir, f"{base}_{counter}{extension}")
                    while os.path.exists(new_target):
                        counter += 1
                        new_target = os.path.join(target_dir, f"{base}_{counter}{extension}")
                    target_file_path = new_target

                shutil.copy2(source_file_path, target_file_path)


class _FlattenCopyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("子文件夹文件扁平复制")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # 源目录
        src_row = QHBoxLayout()
        self._src_dir = QLineEdit()
        self._src_dir.setPlaceholderText("选择源目录…")
        src_btn = QPushButton("浏览")
        src_btn.clicked.connect(lambda: self._browse(self._src_dir, "选择源目录"))
        src_row.addWidget(self._src_dir)
        src_row.addWidget(src_btn)
        form.addRow("源目录：", src_row)

        # 目标目录
        dst_row = QHBoxLayout()
        self._dst_dir = QLineEdit()
        self._dst_dir.setPlaceholderText("选择目标目录…")
        dst_btn = QPushButton("浏览")
        dst_btn.clicked.connect(lambda: self._browse(self._dst_dir, "选择目标目录"))
        dst_row.addWidget(self._dst_dir)
        dst_row.addWidget(dst_btn)
        form.addRow("目标目录：", dst_row)

        # 扩展名
        self._ext_input = QLineEdit(".pdf")
        form.addRow("文件扩展名：", self._ext_input)

        layout.addLayout(form)

        # --- 确定 / 取消 ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self, line_edit: QLineEdit, title: str):
        d = QFileDialog.getExistingDirectory(self, title)
        if d:
            line_edit.setText(d)

    def source_dir(self) -> str:
        return self._src_dir.text().strip()

    def target_dir(self) -> str:
        return self._dst_dir.text().strip()

    def file_extension(self) -> str:
        ext = self._ext_input.text().strip()
        if ext and not ext.startswith("."):
            ext = "." + ext
        return ext


def run_flatten_copy():
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _FlattenCopyDialog()
    if dialog.exec() != QDialog.Accepted:
        return

    source_directory = dialog.source_dir()
    target_directory = dialog.target_dir()
    file_ext = dialog.file_extension()

    if not source_directory:
        QMessageBox.warning(None, "提示", "未选择源目录。")
        return
    if not target_directory:
        QMessageBox.warning(None, "提示", "未选择目标目录。")
        return
    if not file_ext:
        QMessageBox.warning(None, "提示", "未输入文件扩展名。")
        return

    try:
        copy_specific_files(source_directory, target_directory, file_ext)
        QMessageBox.information(None, "完成", "文件扁平复制完成。")
    except Exception as exc:
        QMessageBox.critical(None, "复制失败", str(exc))


if __name__ == "__main__":
    run_flatten_copy()
