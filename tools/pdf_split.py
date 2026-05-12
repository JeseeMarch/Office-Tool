from __future__ import annotations

import os
import re
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
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


TOOL_VERSION = "20260512"


def _parse_split_ranges(text: str, total: int) -> list[list[int]]:
    groups: list[list[int]] = []
    for part in re.split(r"[,，；;]", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)?\s*-\s*(\d+)?", part)
        if m:
            start = int(m.group(1)) if m.group(1) else 1
            end = int(m.group(2)) if m.group(2) else total
            pages = list(range(max(0, start - 1), min(total, end)))
            if pages:
                groups.append(pages)
        elif re.fullmatch(r"\d+", part):
            p = int(part)
            if 1 <= p <= total:
                groups.append([p - 1])
    return groups


def build_page_groups(mode: str, n: int, custom_text: str, total: int) -> list[list[int]]:
    if mode == "every_page":
        return [[i] for i in range(total)]
    if mode == "every_n":
        groups = []
        for start in range(0, total, n):
            groups.append(list(range(start, min(total, start + n))))
        return groups
    return _parse_split_ranges(custom_text, total)


def split_pdf(input_path: str, page_groups: list[list[int]], output_dir: str) -> list[str]:
    stem = Path(input_path).stem
    os.makedirs(output_dir, exist_ok=True)
    src = fitz.open(input_path)
    outputs: list[str] = []
    digits = len(str(len(page_groups)))
    try:
        for idx, pages in enumerate(page_groups, start=1):
            out = fitz.open()
            try:
                for p in pages:
                    out.insert_pdf(src, from_page=p, to_page=p)
                out_name = f"{stem}_{str(idx).zfill(digits)}.pdf"
                out_path = str(Path(output_dir) / out_name)
                out.save(out_path, garbage=4, deflate=True)
                outputs.append(out_path)
            finally:
                out.close()
    finally:
        src.close()
    return outputs


class _SplitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 分割")
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

        self._mode_group = QButtonGroup(self)
        self._rb_every = QRadioButton("每页一个文件")
        self._rb_n = QRadioButton("每 N 页一个文件：")
        self._rb_custom = QRadioButton("自定义范围（如 1-3, 4-6, 7-）：")
        self._rb_every.setChecked(True)
        self._mode_group.addButton(self._rb_every, 0)
        self._mode_group.addButton(self._rb_n, 1)
        self._mode_group.addButton(self._rb_custom, 2)

        layout.addWidget(self._rb_every)

        n_row = QHBoxLayout()
        n_row.addWidget(self._rb_n)
        self._n_spin = QSpinBox()
        self._n_spin.setRange(1, 9999)
        self._n_spin.setValue(2)
        n_row.addWidget(self._n_spin)
        n_row.addStretch()
        layout.addLayout(n_row)

        layout.addWidget(self._rb_custom)
        self._custom_spec = QLineEdit()
        self._custom_spec.setPlaceholderText("例：1-3, 4-6, 7-")
        layout.addWidget(self._custom_spec)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出目录："))
        self._out_dir = QLineEdit()
        self._out_dir.setPlaceholderText("选择输出目录…")
        browse_out = QPushButton("浏览")
        browse_out.clicked.connect(self._browse_out)
        out_row.addWidget(self._out_dir)
        out_row.addWidget(browse_out)
        layout.addLayout(out_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("分割")
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
            if not self._out_dir.text().strip():
                stem = Path(path).stem
                self._out_dir.setText(str(Path(path).parent / f"{stem}_split"))

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._out_dir.setText(d)

    def src_path(self) -> str:
        return self._src_path.text().strip()

    def split_mode(self) -> str:
        return {0: "every_page", 1: "every_n", 2: "custom"}.get(self._mode_group.checkedId(), "every_page")

    def n_value(self) -> int:
        return self._n_spin.value()

    def custom_spec(self) -> str:
        return self._custom_spec.text().strip()

    def out_dir(self) -> str:
        return self._out_dir.text().strip()


def run_pdf_split(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = _SplitDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：PDF 分割。"

    src = dialog.src_path()
    if not src or not os.path.exists(src):
        QMessageBox.warning(None, "提示", "请选择有效的源 PDF 文件。")
        return "未选择源文件，未分割。"

    out_dir = dialog.out_dir()
    if not out_dir:
        QMessageBox.warning(None, "提示", "请指定输出目录。")
        return "未指定输出目录，未分割。"

    mode = dialog.split_mode()
    n = dialog.n_value()
    custom = dialog.custom_spec()

    try:
        doc = fitz.open(src)
        total = len(doc)
        doc.close()
    except Exception as exc:
        return f"无法读取 PDF：{exc}"

    if total == 0:
        return "PDF 页数为 0，未分割。"

    groups = build_page_groups(mode, n, custom, total)
    if not groups:
        QMessageBox.warning(None, "提示", "分割范围无效，请检查输入。")
        return "分割范围无效，未分割。"

    if progress_callback:
        progress_callback(0, len(groups))

    try:
        outputs = split_pdf(src, groups, out_dir)
    except Exception as exc:
        return f"分割失败：{exc}"

    if progress_callback:
        progress_callback(len(groups), len(groups))

    try:
        os.startfile(out_dir)
    except OSError:
        pass

    return f"分割完成，共生成 {len(outputs)} 个文件 → {out_dir}"


if __name__ == "__main__":
    run_pdf_split()
