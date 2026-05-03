import os
import sys
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

WATERMARK_ID = "OfficeToolTextWatermark"
V_NS = "{urn:schemas-microsoft-com:vml}shape"


def _iter_unique_headers(doc: Document):
    seen = set()
    odd_even = doc.settings.odd_and_even_pages_header_footer
    for section in doc.sections:
        headers = [section.header]
        if section.different_first_page_header_footer:
            headers.append(section.first_page_header)
        if odd_even:
            headers.append(section.even_page_header)
        for header in headers:
            key = str(header.part.partname)
            if key in seen:
                continue
            seen.add(key)
            yield header


def _remove_existing_watermarks(header_element) -> None:
    for paragraph in list(header_element):
        if paragraph.tag != qn("w:p"):
            continue
        for shape in paragraph.iter(V_NS):
            if shape.get("id") == WATERMARK_ID:
                header_element.remove(paragraph)
                break


def _watermark_xml(text: str) -> str:
    escaped_text = escape(text, {'"': "&quot;"})
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  <w:r>
    <w:pict>
      <v:shape id="{WATERMARK_ID}" o:spid="_x0000_s2050" type="#_x0000_t136"
        style="position:absolute;margin-left:0;margin-top:0;width:420pt;height:120pt;rotation:315;z-index:-251654144;mso-position-horizontal:center;mso-position-horizontal-relative:page;mso-position-vertical:center;mso-position-vertical-relative:page"
        fillcolor="#d8d8d8" stroked="f">
        <v:textpath on="t" string="{escaped_text}" style="font-family:SimSun;font-size:44pt"/>
        <w10:wrap anchorx="margin" anchory="margin"/>
      </v:shape>
    </w:pict>
  </w:r>
</w:p>"""


def add_text_watermark(doc: Document, text: str) -> None:
    for header in _iter_unique_headers(doc):
        _remove_existing_watermarks(header._element)
        header._element.insert(0, parse_xml(_watermark_xml(text)))


class _WordWatermarkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Word 加水印")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        # --- 文件选择 ---
        self._file_count_label = QLabel("Word 文件（0 个已选）：")
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

        # --- 水印文字 ---
        form = QFormLayout()
        self._wm_text = QLineEdit("水印")
        form.addRow("水印内容：", self._wm_text)
        layout.addLayout(form)

        # --- 确定 / 取消 ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._file_list.model().rowsInserted.connect(self._update_file_count)
        self._file_list.model().rowsRemoved.connect(self._update_file_count)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择 Word 文件", "", "Word 文档 (*.docx)")
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for f in files:
            if f not in existing:
                self._file_list.addItem(f)

    def _remove_selected(self):
        for item in reversed(self._file_list.selectedItems()):
            self._file_list.takeItem(self._file_list.row(item))

    def _update_file_count(self):
        n = self._file_list.count()
        self._file_count_label.setText(f"Word 文件（{n} 个已选）：")

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def watermark_text(self) -> str:
        return self._wm_text.text().strip()


def run_word_watermark() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _WordWatermarkDialog()
    if dialog.exec() != QDialog.Accepted:
        return

    files = dialog.selected_files()
    if not files:
        QMessageBox.information(None, "提示", "未选择任何文件。")
        return

    text = dialog.watermark_text()
    if not text:
        QMessageBox.warning(None, "提示", "未输入水印内容。")
        return

    outputs = []
    failed = []
    for path in files:
        try:
            folder = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            output_path = os.path.join(folder, f"{base}_.docx")
            doc = Document(path)
            add_text_watermark(doc, text)
            doc.save(output_path)
            outputs.append(output_path)
        except Exception as exc:
            failed.append(f"{path}: {exc}")

    if failed:
        QMessageBox.warning(None, "部分失败", "\n".join(failed))
    if outputs:
        QMessageBox.information(None, "完成", "已生成：\n" + "\n".join(outputs))


if __name__ == "__main__":
    run_word_watermark()
