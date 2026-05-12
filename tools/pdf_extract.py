from __future__ import annotations

import os
import re
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
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


TOOL_VERSION = "20260512"


def parse_page_spec(spec: str, total: int) -> list[int]:
    """Parse spec like '1,3,5-7,10-' into sorted 0-indexed page list."""
    pages: list[int] = []
    seen: set[int] = set()
    for part in re.split(r"[,，；;]", spec):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)?\s*-\s*(\d+)?", part)
        if m:
            start = int(m.group(1)) if m.group(1) else 1
            end = int(m.group(2)) if m.group(2) else total
            for p in range(max(1, start), min(total, end) + 1):
                if p not in seen:
                    pages.append(p - 1)
                    seen.add(p)
        elif re.fullmatch(r"\d+", part):
            p = int(part)
            if 1 <= p <= total and p not in seen:
                pages.append(p - 1)
                seen.add(p)
    return pages


def extract_pages(input_path: str, pages: list[int], output_path: str) -> None:
    src = fitz.open(input_path)
    out = fitz.open()
    try:
        for page_index in pages:
            out.insert_pdf(src, from_page=page_index, to_page=page_index)
        out.save(output_path, garbage=4, deflate=True)
    finally:
        out.close()
        src.close()


class _ExtractDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 页面提取")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("源 PDF："))
        self._src_path = QLineEdit()
        self._src_path.setPlaceholderText("选择源 PDF…")
        browse_src = QPushButton("浏览")
        browse_src.clicked.connect(self._browse_src)
        src_row.addWidget(self._src_path)
        src_row.addWidget(browse_src)
        layout.addLayout(src_row)

        self._page_count_label = QLabel("（未选择文件）")
        layout.addWidget(self._page_count_label)

        layout.addWidget(QLabel("提取页码（例：1,3,5-7,10-，页码从 1 开始）："))
        self._page_spec = QLineEdit()
        self._page_spec.setPlaceholderText("1,3,5-7,10-")
        layout.addWidget(self._page_spec)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出文件："))
        self._out_path = QLineEdit()
        self._out_path.setPlaceholderText("选择输出 PDF 路径…")
        browse_out = QPushButton("浏览")
        browse_out.clicked.connect(self._browse_out)
        out_row.addWidget(self._out_path)
        out_row.addWidget(browse_out)
        layout.addLayout(out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("提取")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_src(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        if path:
            self._src_path.setText(path)
            try:
                doc = fitz.open(path)
                count = len(doc)
                doc.close()
                self._page_count_label.setText(f"共 {count} 页")
            except Exception:
                self._page_count_label.setText("无法读取页数")
            if not self._out_path.text().strip():
                stem = Path(path).stem
                self._out_path.setText(str(Path(path).parent / f"{stem}_extracted.pdf"))

    def _browse_out(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存提取 PDF", "", "PDF 文件 (*.pdf)")
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self._out_path.setText(path)

    def src_path(self) -> str:
        return self._src_path.text().strip()

    def page_spec(self) -> str:
        return self._page_spec.text().strip()

    def out_path(self) -> str:
        return self._out_path.text().strip()


def run_pdf_extract(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = _ExtractDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：PDF 页面提取。"

    src = dialog.src_path()
    if not src or not os.path.exists(src):
        QMessageBox.warning(None, "提示", "请选择有效的源 PDF 文件。")
        return "未选择源文件，未提取。"

    spec = dialog.page_spec()
    if not spec:
        QMessageBox.warning(None, "提示", "请输入提取页码范围。")
        return "未输入页码范围，未提取。"

    out = dialog.out_path()
    if not out:
        QMessageBox.warning(None, "提示", "请指定输出文件路径。")
        return "未指定输出路径，未提取。"
    if not out.lower().endswith(".pdf"):
        out += ".pdf"

    try:
        doc = fitz.open(src)
        total = len(doc)
        doc.close()
    except Exception as exc:
        return f"无法读取 PDF：{exc}"

    pages = parse_page_spec(spec, total)
    if not pages:
        QMessageBox.warning(None, "提示", f"页码范围无效或超出范围（共 {total} 页）。")
        return "页码范围无效，未提取。"

    if progress_callback:
        progress_callback(0, 1)

    try:
        extract_pages(src, pages, out)
    except Exception as exc:
        return f"提取失败：{exc}"

    if progress_callback:
        progress_callback(1, 1)

    try:
        os.startfile(out)
    except OSError:
        pass

    return f"已提取 {len(pages)} 页（共 {total} 页）→ {out}"


if __name__ == "__main__":
    run_pdf_extract()
