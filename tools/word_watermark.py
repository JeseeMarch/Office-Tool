from __future__ import annotations

import io
import math
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


TOOL_VERSION = "20260505-word-watermark-multi-vml-anchors"
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
    font_size: int = 72


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
    font_size: int,
    left: int = 0,
    top: int = -70,
    watermark_index: int = 0,
) -> str:
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  {_text_watermark_run_xml(text, font_size, left, top, watermark_index)}
</w:p>"""


def _text_watermarks_xml(text: str, font_size: int, positions: list[tuple[float, float]]) -> str:
    # 所有水印 shape 放进同一个段落的多个 run，避免每个水印各占一段而产生多余空行（回车符）。
    runs = "\n".join(
        _text_watermark_run_xml(text, font_size, left, top, watermark_index)
        for watermark_index, (left, top) in enumerate(positions)
    )
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
{runs}
</w:p>"""


def _text_watermark_run_xml(text: str, font_size: int, left: int, top: int, watermark_index: int) -> str:
    return f"""<w:r>
    <w:pict>
      {_text_watermark_shape_xml(text, font_size, left, top, watermark_index)}
    </w:pict>
  </w:r>"""


def _text_watermark_shape_xml(text: str, font_size: int, left: int, top: int, watermark_index: int) -> str:
    escaped_text = escape(text, {'"': "&quot;"})
    watermark_id = f"{TEXT_WATERMARK_ID_PREFIX}{watermark_index}"
    vml_font_size = _vml_text_font_size(font_size)
    shape_width, shape_height = _text_watermark_shape_size(text, vml_font_size)
    spid = 2050 + watermark_index
    # 用绝对定位（相对页面）：margin-left/top 即水印左上角在页面上的坐标。
    # 注意不能再带 mso-position-horizontal/vertical:center，否则 margin 会被忽略、所有水印挤到正中重叠。
    return f"""<v:shape id="{watermark_id}" o:spid="_x0000_s{spid}" type="#_x0000_t136"
        style="position:absolute;margin-left:{left}pt;margin-top:{top}pt;width:{shape_width}pt;height:{shape_height}pt;rotation:315;z-index:-251654144;mso-position-horizontal:absolute;mso-position-horizontal-relative:page;mso-position-vertical:absolute;mso-position-vertical-relative:page"
        fillcolor="#d8d8d8" stroked="f">
        <v:textpath on="t" string="{escaped_text}" style="font-family:'Times New Roman','Source Han Sans SC','Source Han Sans','思源黑体';mso-fareast-font-family:'Source Han Sans SC';font-size:{vml_font_size}pt"/>
        <w10:wrap anchorx="page" anchory="page"/>
      </v:shape>"""


def _single_line_text(text: str) -> str:
    text = text.replace("\\n", "\n")
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _text_watermark_shape_size(text: str, font_size: int) -> tuple[int, int]:
    cjk_count = sum(1 for char in text if _is_cjk(char))
    other_count = len(text) - cjk_count
    height = max(45, int(round(font_size * 1.4)))
    # WordArt(textpath) 会把文字拉伸填满 shape 框，故框的宽高比必须等于文字自然比例，
    # 否则字会被压成瘦长。宽度 = 字数 × 框高（CJK 近似方形，西文按 0.58 折算）。
    width = max(height, int(round(cjk_count * height + other_count * height * 0.58)))
    return width, height


def _vml_text_font_size(font_size: int) -> int:
    return max(8, int(round(font_size * 0.22)))


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0xF900 <= code <= 0xFAFF
        or 0x2F800 <= code <= 0x2FA1F
    )


def _centered_text_watermark_position(text: str, font_size: int, page_w_pt: float, page_h_pt: float) -> tuple[float, float]:
    """单行水印：把 shape 居中放在页面正中（绝对坐标 = 页心 - 半个 shape）。"""
    shape_width, shape_height = _text_watermark_shape_size(text, _vml_text_font_size(font_size))
    return (round(page_w_pt / 2 - shape_width / 2, 1), round(page_h_pt / 2 - shape_height / 2, 1))


WATERMARK_ANGLE_DEG = 45  # 文字斜向角度；shape 用 rotation:315(=-45°) 渲染，整个阵列绕页心同角度旋转。


def _multi_text_watermark_positions(
    text: str, font_size: int, page_w_pt: float, page_h_pt: float
) -> list[tuple[float, float]]:
    """多行水印：以页心水印为中心、把整个网格阵列绕页心旋转 45°（整体旋转），返回各 shape 左上角的页面绝对坐标。

    密集方向 step_x 平行于文字斜向（沿对角线连成行），稀疏方向 step_y 垂直于文字、取 3 倍行间距。
    """
    shape_width, shape_height = _text_watermark_shape_size(text, _vml_text_font_size(font_size))
    rotated_extent = (shape_width + shape_height) * 0.70710678
    unit = max(80.0, rotated_extent * 1.15)  # 一个水印的基本步长
    step_x = unit * 2  # 列方向：两个水印之间留出一个水印的间距（中心距 = 2×基本步长）
    step_y = unit * 2  # 行间距：由 3 倍基本步长改为 2 倍
    center_x, center_y = page_w_pt / 2, page_h_pt / 2

    # 与文字旋转同角度（rotation:315 → -45°），让网格随文字整体旋转。
    angle = math.radians(-WATERMARK_ANGLE_DEG)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    # 旋转后仍要盖满整页，用页面对角线半径决定网格范围。
    reach = math.hypot(page_w_pt, page_h_pt) / 2
    cols = int(reach // step_x) + 2
    rows = int(reach // step_y) + 2
    # 允许中心略微出界、但水印仍覆盖到页面的也保留（留半个 footprint 余量），保证边缘也铺满。
    margin = rotated_extent / 2

    positions: list[tuple[float, float]] = []
    for row in range(-rows, rows + 1):
        for col in range(-cols, cols + 1):
            offset_x = col * step_x
            offset_y = row * step_y
            # 把网格点绕页心整体旋转
            px = center_x + offset_x * cos_a - offset_y * sin_a
            py = center_y + offset_x * sin_a + offset_y * cos_a
            if -margin <= px <= page_w_pt + margin and -margin <= py <= page_h_pt + margin:
                positions.append((round(px - shape_width / 2, 1), round(py - shape_height / 2, 1)))
    return positions


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
        section = doc.sections[0]
        page_w_pt = float(section.page_width or 0) / EMU_PER_PT or 595.0
        page_h_pt = float(section.page_height or 0) / EMU_PER_PT or 842.0
        if options.kind == "single_text":
            positions = [_centered_text_watermark_position(text, options.font_size, page_w_pt, page_h_pt)]
        else:
            positions = _multi_text_watermark_positions(text, options.font_size, page_w_pt, page_h_pt)
        for header in _iter_unique_headers(doc):
            _remove_existing_watermarks(header._element)
            header._element.insert(0, parse_xml(_text_watermarks_xml(text, options.font_size, positions)))
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
        self._font_size.setValue(72)
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

    def _font_size_value(self) -> int:
        self._font_size.interpretText()
        return self._font_size.value()

    def options(self) -> WatermarkOptions:
        checked = self._mode_group.checkedId()
        if checked == 2:
            return WatermarkOptions(kind="image", image_path=self._image_path.text().strip())
        if checked == 1:
            return WatermarkOptions(
                kind="multi_text",
                text=self._wm_text.toPlainText().strip(),
                font_size=self._font_size_value(),
            )
        return WatermarkOptions(
            kind="single_text",
            text=self._wm_text.toPlainText().strip(),
            font_size=self._font_size_value(),
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
        summary = f"本次设置：{options.kind}，字号 {options.font_size}。"
        return f"{summary} {message.replace(chr(10), ' ')}"
    return "Word 加水印未生成文件。"


if __name__ == "__main__":
    run_word_watermark()
