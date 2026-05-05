from __future__ import annotations

import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from PIL import Image, ImageEnhance
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)


TOOL_VERSION = "20260504-word-watermark-modes"
TEXT_WATERMARK_ID_PREFIX = "OfficeToolTextWatermark"
IMAGE_WATERMARK_ID = "OfficeToolImageWatermark"
LEGACY_IMAGE_WATERMARK_IDS = {"OfficeToolLogoVML"}
DOC_PR_NAME = "OfficeToolImageWatermark"
LEGACY_DOC_PR_NAMES = {"OfficeToolLogoWatermark"}
V_NS = "{urn:schemas-microsoft-com:vml}shape"
WP_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
EMU_PER_PT = 12700


@dataclass(frozen=True)
class WatermarkOptions:
    kind: str
    text: str = ""
    image_path: str = ""
    font_size: int = 96


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
    dead = set()
    for paragraph in list(header_element):
        if paragraph.tag != qn("w:p"):
            continue
        for shape in paragraph.iter(V_NS):
            shape_id = shape.get("id", "")
            if (
                shape_id.startswith(TEXT_WATERMARK_ID_PREFIX)
                or shape_id == IMAGE_WATERMARK_ID
                or shape_id in LEGACY_IMAGE_WATERMARK_IDS
            ):
                dead.add(id(paragraph))
                break
        for drawing in paragraph.findall(".//" + qn("w:drawing")):
            for doc_pr in drawing.iter(f"{{{WP_DRAWINGML_NS}}}docPr"):
                if doc_pr.get("name") == DOC_PR_NAME or doc_pr.get("name") in LEGACY_DOC_PR_NAMES:
                    dead.add(id(paragraph))
                    break
    for paragraph in list(header_element):
        if paragraph.tag == qn("w:p") and id(paragraph) in dead:
            header_element.remove(paragraph)


def _text_watermark_xml(
    text: str,
    row_index: int,
    row_count: int,
    font_size: int,
    column_index: int = 0,
    column_count: int = 1,
) -> str:
    escaped_text = escape(text, {'"': "&quot;"})
    line_step = max(60, int(font_size * 1.25))
    top = -70 + row_index * line_step - (row_count - 1) * line_step // 2
    left_offsets = {
        1: [0],
        2: [-145, 145],
        3: [-190, 0, 190],
    }
    left = left_offsets.get(column_count, [0])[column_index]
    watermark_id = f"{TEXT_WATERMARK_ID_PREFIX}{row_index}_{column_index}"
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  <w:r>
    <w:pict>
      <v:shape id="{watermark_id}" o:spid="_x0000_s2050" type="#_x0000_t136"
        style="position:absolute;margin-left:{left}pt;margin-top:{top}pt;width:360pt;height:120pt;rotation:315;z-index:-251654144;mso-position-horizontal:center;mso-position-horizontal-relative:page;mso-position-vertical:center;mso-position-vertical-relative:page"
        fillcolor="#d8d8d8" stroked="f">
        <v:textpath on="t" string="{escaped_text}" style="font-family:'Times New Roman','Source Han Sans SC','Source Han Sans','思源黑体';mso-fareast-font-family:'Source Han Sans SC';font-size:{font_size}pt"/>
        <w10:wrap anchorx="margin" anchory="margin"/>
      </v:shape>
    </w:pict>
  </w:r>
</w:p>"""


def _single_line_text(text: str) -> str:
    text = text.replace("\\n", "\n")
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _watermark_column_count(font_size: int) -> int:
    return 2 if font_size >= 88 else 3


def _prepare_image_watermark(src: Path) -> io.BytesIO:
    image = Image.open(src)
    if image.mode == "P":
        image = image.convert("RGBA")
    if image.mode == "RGBA":
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(image, mask=image.split()[3])
        image = bg
    else:
        image = image.convert("RGB")

    gray = image.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(1.15)
    gray = gray.point(lambda p: min(255, int(round(255 - (255 - p) * 0.3))))
    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _image_watermark_xml(r_id: str, width_pt: float, height_pt: float) -> str:
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  <w:r>
    <w:pict>
      <v:shape id="{IMAGE_WATERMARK_ID}" o:spid="_x0000_s2051" type="#_x0000_t75"
        style="position:absolute;margin-left:0;margin-top:0;width:{width_pt:.1f}pt;height:{height_pt:.1f}pt;z-index:-251658752;mso-position-horizontal:center;mso-position-horizontal-relative:page;mso-position-vertical:center;mso-position-vertical-relative:page"
        filled="f" stroked="f">
        <v:imagedata r:id="{r_id}" o:title="watermark"/>
      </v:shape>
      <w10:wrap anchorx="margin" anchory="margin"/>
    </w:pict>
  </w:r>
</w:p>"""


def add_watermark(doc: Document, options: WatermarkOptions) -> None:
    if options.kind in {"single_text", "multi_text"}:
        text = _single_line_text(options.text)
        if not text:
            raise ValueError("未输入水印文字。")
        if options.kind == "single_text":
            lines = [text]
            column_count = 1
        else:
            lines = [text, text, text]
            column_count = _watermark_column_count(options.font_size)
        for header in _iter_unique_headers(doc):
            _remove_existing_watermarks(header._element)
            insert_index = 0
            for row_index, line in enumerate(lines):
                for column_index in range(column_count):
                    header._element.insert(
                        insert_index,
                        parse_xml(
                            _text_watermark_xml(
                                line,
                                row_index,
                                len(lines),
                                options.font_size,
                                column_index,
                                column_count,
                            )
                        ),
                    )
                    insert_index += 1
        return

    if options.kind == "image":
        if not options.image_path:
            raise ValueError("未选择水印图片。")
        image_stream = _prepare_image_watermark(Path(options.image_path))
        first_sec = doc.sections[0]
        target_width = int(first_sec.page_width * 0.52 * 1.5)
        for header in _iter_unique_headers(doc):
            _remove_existing_watermarks(header._element)
            image_stream.seek(0)
            r_id, image = header.part.get_or_add_image(image_stream)
            cx, cy = image.scaled_dimensions(target_width, None)
            header._element.insert(0, parse_xml(_image_watermark_xml(r_id, int(cx) / EMU_PER_PT, int(cy) / EMU_PER_PT)))
        return

    raise ValueError(f"未知水印类型：{options.kind}")


class _WordWatermarkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Word 加水印")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)

        self._file_count_label = QLabel("Word 文件（0 个已选）：")
        layout.addWidget(self._file_count_label)

        file_row = QHBoxLayout()
        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(188)
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

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("输出模式："))
        self._mode_group = QButtonGroup(self)
        self._single_text = QRadioButton("单行水印")
        self._multi_text = QRadioButton("多行水印")
        self._image = QRadioButton("图片水印")
        self._single_text.setChecked(True)
        self._mode_group.addButton(self._single_text, 0)
        self._mode_group.addButton(self._multi_text, 1)
        self._mode_group.addButton(self._image, 2)
        for button in (self._single_text, self._multi_text, self._image):
            mode_row.addWidget(button)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("水印文字："))
        self._wm_text = QTextEdit("水印")
        self._wm_text.setMaximumHeight(86)
        text_row.addWidget(self._wm_text)
        layout.addLayout(text_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("字体大小："))
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 500)
        self._font_size.setSingleStep(4)
        self._font_size.setValue(96)
        font_row.addWidget(self._font_size)
        layout.addLayout(font_row)

        image_row = QHBoxLayout()
        image_row.addWidget(QLabel("水印图片："))
        self._image_path = QLineEdit()
        self._image_path.setPlaceholderText("选择图片水印文件...")
        image_btn = QPushButton("浏览")
        image_btn.clicked.connect(self._browse_image)
        image_row.addWidget(self._image_path)
        image_row.addWidget(image_btn)
        layout.addLayout(image_row)

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
        files, _ = QFileDialog.getOpenFileNames(self, "选择 Word 文件", "", "Word 文档 (*.docx)")
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for file_path in files:
            if file_path not in existing:
                self._file_list.addItem(file_path)

    def _remove_selected(self):
        for item in reversed(self._file_list.selectedItems()):
            self._file_list.takeItem(self._file_list.row(item))

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self._image_path.setText(path)
            self._image.setChecked(True)

    def _update_file_count(self):
        self._file_count_label.setText(f"Word 文件（{self._file_list.count()} 个已选）：")

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def options(self) -> WatermarkOptions:
        checked = self._mode_group.checkedId()
        if checked == 2:
            return WatermarkOptions(kind="image", image_path=self._image_path.text().strip())
        if checked == 1:
            return WatermarkOptions(
                kind="multi_text",
                text=self._wm_text.toPlainText().strip(),
                font_size=self._font_size.value(),
            )
        return WatermarkOptions(
            kind="single_text",
            text=self._wm_text.toPlainText().strip(),
            font_size=self._font_size.value(),
        )

    def start_progress(self, maximum: int) -> None:
        self._progress.setRange(0, max(1, maximum))
        self._progress.setValue(0)
        self.show()
        QApplication.processEvents()

    def set_progress(self, value: int) -> None:
        self._progress.setValue(value)
        QApplication.processEvents()


def run_word_watermark(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _WordWatermarkDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：Word 加水印。"

    files = dialog.selected_files()
    if not files:
        return "未选择任何 Word 文件，未处理。"

    options = dialog.options()
    outputs = []
    failed = []
    if progress_callback:
        progress_callback(0, len(files))
    for index, path in enumerate(files, start=1):
        try:
            folder = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            output_path = os.path.join(folder, f"{base}_.docx")
            doc = Document(path)
            add_watermark(doc, options)
            doc.save(output_path)
            outputs.append(output_path)
        except Exception as exc:
            failed.append(f"{path}: {exc}")
        if progress_callback:
            progress_callback(index, len(files))

    if failed:
        QMessageBox.warning(None, "部分失败", "\n".join(failed))
    if outputs:
        message = "已生成：\n" + "\n".join(outputs)
        return message.replace("\n", " ")
    return "Word 加水印未生成文件。"


if __name__ == "__main__":
    run_word_watermark()
