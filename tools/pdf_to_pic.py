import os
import sys
from pathlib import Path

import fitz
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)


TOOL_VERSION = "20260504-default-output-log"


def _suggest_output_dir(files: list[str]) -> str:
    if not files:
        return ""

    paths = [Path(file_path).resolve() for file_path in files]
    if len(paths) == 1:
        return str(paths[0].parent)

    try:
        common_dir = Path(os.path.commonpath([str(path.parent) for path in paths]))
    except ValueError:
        common_dir = paths[0].parent
    return str(common_dir)


def _pdf_output_dir(pdf_path: str, output_root: str) -> str:
    pdf = Path(pdf_path).resolve()
    root = Path(output_root).resolve()
    return str(root / f"{pdf.stem}_images")


def export_pdf_pages(pdf_path: str, output_root: str, image_format: str = "png", zoom: float = 2.0) -> int:
    output_dir = _pdf_output_dir(pdf_path, output_root)
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    matrix = fitz.Matrix(zoom, zoom)
    count = 0

    try:
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            output_path = os.path.join(output_dir, f"{base_name}_{index}.{image_format}")
            pix.save(output_path)
            count += 1
    finally:
        doc.close()

    return count


class _PdfToPicDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 导出为图片")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        # --- 文件选择 ---
        self._file_count_label = QLabel("PDF 文件（0 个已选）：")
        layout.addWidget(self._file_count_label)

        file_row = QHBoxLayout()
        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(100)
        file_row.addWidget(self._file_list)

        btn_col = QVBoxLayout()
        add_btn = QPushButton("添加文件")
        add_btn.clicked.connect(self._add_files)
        rm_btn = QPushButton("移除选中")
        rm_btn.clicked.connect(self._remove_selected)
        btn_col.addWidget(add_btn)
        btn_col.addWidget(rm_btn)
        btn_col.addStretch()
        file_row.addLayout(btn_col)
        layout.addLayout(file_row)

        # --- 输出目录 ---
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("输出目录："))
        self._output_dir = QLineEdit()
        self._output_dir.setPlaceholderText("选择输出目录…")
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(self._output_dir)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # --- 输出格式 ---
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("输出格式："))
        self._fmt_group = QButtonGroup(self)
        rb_png = QRadioButton("PNG")
        rb_jpg = QRadioButton("JPG")
        rb_png.setChecked(True)
        self._fmt_group.addButton(rb_png, 0)
        self._fmt_group.addButton(rb_jpg, 1)
        fmt_row.addWidget(rb_png)
        fmt_row.addWidget(rb_jpg)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # --- 确定 / 取消 ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        self._progress.hide()

        self._file_list.model().rowsInserted.connect(self._update_file_count)
        self._file_list.model().rowsRemoved.connect(self._update_file_count)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for f in files:
            if f not in existing:
                self._file_list.addItem(f)
        if files and not self._output_dir.text().strip():
            self._output_dir.setText(_suggest_output_dir(self.selected_files()))

    def _remove_selected(self):
        for item in reversed(self._file_list.selectedItems()):
            self._file_list.takeItem(self._file_list.row(item))

    def _update_file_count(self):
        n = self._file_list.count()
        self._file_count_label.setText(f"PDF 文件（{n} 个已选）：")

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._output_dir.setText(d)

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def output_dir(self) -> str:
        return self._output_dir.text().strip()

    def image_format(self) -> str:
        return "jpg" if self._fmt_group.checkedId() == 1 else "png"

    def start_progress(self, maximum: int) -> None:
        self._progress.setRange(0, max(1, maximum))
        self._progress.setValue(0)
        self.show()
        QApplication.processEvents()

    def set_progress(self, value: int) -> None:
        self._progress.setValue(value)
        QApplication.processEvents()


def run_pdf_to_images(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _PdfToPicDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：PDF 导出为图片。"

    files = dialog.selected_files()
    if not files:
        return "未选择任何文件，未导出。"

    output_dir = dialog.output_dir()
    if not output_dir:
        output_dir = _suggest_output_dir(files)
    output_dir = os.path.abspath(os.path.expanduser(output_dir))

    image_format = dialog.image_format()

    total = 0
    output_dirs = []
    if progress_callback:
        progress_callback(0, len(files))
    for index, pdf_path in enumerate(files, start=1):
        total += export_pdf_pages(pdf_path, output_dir, image_format=image_format)
        output_dirs.append(_pdf_output_dir(pdf_path, output_dir))
        if progress_callback:
            progress_callback(index, len(files))
    message = f"已导出 {total} 张图片。\n输出文件夹：\n" + "\n".join(output_dirs)
    return message.replace("\n", " ")


if __name__ == "__main__":
    run_pdf_to_images()
