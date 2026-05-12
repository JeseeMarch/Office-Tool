from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


TOOL_VERSION = "20260512"


def merge_pdfs(input_paths: list[str], output_path: str) -> None:
    out = fitz.open()
    try:
        for path in input_paths:
            src = fitz.open(path)
            try:
                out.insert_pdf(src)
            finally:
                src.close()
        out.save(output_path, garbage=4, deflate=True)
    finally:
        out.close()


class _MergeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 合并")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        self._file_count_label = QLabel("PDF 文件（0 个，将按列表顺序合并）：")
        layout.addWidget(self._file_count_label)

        file_row = QHBoxLayout()
        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(180)
        file_row.addWidget(self._file_list)

        btn_col = QVBoxLayout()
        add_btn = QPushButton("添加文件")
        add_btn.clicked.connect(self._add_files)
        rm_btn = QPushButton("移除选中")
        rm_btn.clicked.connect(self._remove_selected)
        up_btn = QPushButton("上移")
        up_btn.clicked.connect(self._move_up)
        dn_btn = QPushButton("下移")
        dn_btn.clicked.connect(self._move_down)
        for b in (add_btn, rm_btn, up_btn, dn_btn):
            btn_col.addWidget(b)
        btn_col.addStretch()
        file_row.addLayout(btn_col)
        layout.addLayout(file_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出文件："))
        self._out_path = QLineEdit()
        self._out_path.setPlaceholderText("选择或输入输出 PDF 路径…")
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self._out_path)
        out_row.addWidget(browse_btn)
        layout.addLayout(out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("合并")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._file_list.model().rowsInserted.connect(self._update_count)
        self._file_list.model().rowsRemoved.connect(self._update_count)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for f in files:
            if f not in existing:
                self._file_list.addItem(f)
        if files and not self._out_path.text().strip():
            first = Path(files[0])
            self._out_path.setText(str(first.parent / "merged.pdf"))

    def _remove_selected(self):
        for item in reversed(self._file_list.selectedItems()):
            self._file_list.takeItem(self._file_list.row(item))

    def _move_up(self):
        row = self._file_list.currentRow()
        if row > 0:
            item = self._file_list.takeItem(row)
            self._file_list.insertItem(row - 1, item)
            self._file_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self._file_list.currentRow()
        if row >= 0 and row < self._file_list.count() - 1:
            item = self._file_list.takeItem(row)
            self._file_list.insertItem(row + 1, item)
            self._file_list.setCurrentRow(row + 1)

    def _update_count(self):
        self._file_count_label.setText(f"PDF 文件（{self._file_list.count()} 个，将按列表顺序合并）：")

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存合并 PDF", "", "PDF 文件 (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self._out_path.setText(path)

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def output_path(self) -> str:
        return self._out_path.text().strip()


def run_pdf_merge(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = _MergeDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：PDF 合并。"

    files = dialog.selected_files()
    if not files:
        return "未选择任何文件，未合并。"

    out = dialog.output_path()
    if not out:
        QMessageBox.warning(None, "提示", "请指定输出文件路径。")
        return "未指定输出路径，未合并。"
    if not out.lower().endswith(".pdf"):
        out += ".pdf"

    if progress_callback:
        progress_callback(0, len(files))

    try:
        merge_pdfs(files, out)
    except Exception as exc:
        return f"合并失败：{exc}"

    if progress_callback:
        progress_callback(len(files), len(files))

    try:
        os.startfile(out)
    except OSError:
        pass

    return f"合并完成，共 {len(files)} 个文件 → {out}"


if __name__ == "__main__":
    run_pdf_merge()
