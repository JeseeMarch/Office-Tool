import io
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


RENDER_ZOOM = 2.0
TEXT_WATERMARK_ALPHA = 25
IMAGE_WATERMARK_ALPHA = 70
PDF_WATERMARK_ARTIFACT_RE = re.compile(
    rb"/Artifact\s*<<[^>]*?/Subtype\s*/Watermark[^>]*?>>\s*BDC\b.*?\bEMC\s*",
    re.S,
)
PDF_NUMBER_RE = rb"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"


@dataclass(frozen=True)
class WatermarkOptions:
    kind: str
    text: str = ""
    font_size: int = 72
    text_layout: str = "single"
    image_path: str = ""


@dataclass(frozen=True)
class ProcessOptions:
    watermark: WatermarkOptions | None = None


def _output_path(input_path: str) -> str:
    return str(Path(input_path).with_suffix("")) + "_.pdf"


def _fallback_output_path(input_path: str) -> str:
    base = str(Path(input_path).with_suffix(""))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base}_{stamp}.pdf"


def _looks_like_generated_output(input_path: str) -> bool:
    stem = Path(input_path).stem
    return stem.endswith("_") or re.search(r"_\(\d+\)$", stem) is not None


def _replace_output(tmp_path: str, desired_path: str, input_path: str) -> str:
    try:
        os.replace(tmp_path, desired_path)
        return desired_path
    except OSError:
        fallback = _fallback_output_path(input_path)
        os.replace(tmp_path, fallback)
        return fallback


def _watermark_summary(watermark: WatermarkOptions | None) -> str:
    if watermark is None:
        return "无水印"
    if watermark.kind == "text":
        layout = "多行" if watermark.text_layout == "multi" else "单行"
        return f"文字水印：{layout}，字号 {watermark.font_size}，内容：{watermark.text}"
    if watermark.kind == "image":
        return f"图片水印：{watermark.image_path}"
    return "未知设置"


def _process_summary(options: ProcessOptions) -> str:
    return _watermark_summary(options.watermark)


def _xref_object_is_watermark(doc: fitz.Document, xref: int) -> bool:
    try:
        obj = doc.xref_object(xref, compressed=False)
    except Exception:
        return False
    return "/Watermark" in obj or "/Private /Watermark" in obj


def _page_watermark_xobject_names(doc: fitz.Document, page: fitz.Page) -> list[str]:
    names: list[str] = []
    try:
        xobjects = page.get_xobjects()
    except Exception:
        return names

    for item in xobjects:
        if len(item) < 2:
            continue
        xref, name = item[0], item[1]
        if isinstance(xref, int) and isinstance(name, str) and _xref_object_is_watermark(doc, xref):
            names.append(name)
    return names


def _xobject_invocation_pattern(name: str) -> re.Pattern[bytes]:
    name_bytes = re.escape(f"/{name}".encode("latin-1", errors="ignore"))
    matrix = rb"(?:%s\s+){6}cm\s*" % PDF_NUMBER_RE
    return re.compile(
        rb"(?:/Artifact\s*<<[^>]*?/Subtype\s*/Watermark[^>]*?>>\s*BDC\s*)?"
        rb"q\s*(?:/[A-Za-z0-9_.#-]+\s+gs\s*)?"
        + matrix
        + name_bytes
        + rb"\s+Do\s*Q\s*(?:EMC\s*)?",
        re.S,
    )


def strip_pdf_watermark_artifacts_from_page(doc: fitz.Document, page: fitz.Page) -> int:
    """Remove PDF-native watermark artifacts before rasterizing the page."""
    watermark_xobjects = _page_watermark_xobject_names(doc, page)
    removed = 0

    for xref in page.get_contents():
        try:
            data = doc.xref_stream(xref)
        except Exception:
            continue
        if not data:
            continue

        new_data, count = PDF_WATERMARK_ARTIFACT_RE.subn(b"", data)
        removed += count

        for name in watermark_xobjects:
            new_data, count = _xobject_invocation_pattern(name).subn(b"", new_data)
            removed += count

        if new_data != data:
            doc.update_stream(xref, new_data)

    return removed


def _resampling(name: str):
    if hasattr(Image, "Resampling"):
        return getattr(Image.Resampling, name)
    return getattr(Image, name)


def _font_candidates() -> list[str]:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts = Path(windir) / "Fonts"
    return [
        str(fonts / "msyh.ttc"),
        str(fonts / "simhei.ttf"),
        str(fonts / "simsun.ttc"),
        str(fonts / "arial.ttf"),
        "msyh.ttc",
        "simhei.ttf",
        "simsun.ttc",
        "arial.ttf",
    ]


def _load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_name in _font_candidates():
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            continue
    return ImageFont.load_default()


def _single_line_text(text: str) -> str:
    text = text.replace("\\n", "\n")
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


def _anchored_tile_positions(center: int, step: int, tile_size: int, canvas_size: int) -> list[int]:
    positions = [center]

    pos = center - step
    while pos > -tile_size:
        positions.insert(0, pos)
        pos -= step

    pos = center + step
    while pos < canvas_size + tile_size:
        positions.append(pos)
        pos += step

    return positions


def _three_row_tile_positions(tile_size: int, canvas_size: int) -> list[int]:
    if tile_size >= canvas_size:
        return [(canvas_size - tile_size) // 2]

    top = 0
    center = (canvas_size - tile_size) // 2
    bottom = canvas_size - tile_size
    return sorted({top, center, bottom})


def add_text_watermark(image: Image.Image, options: WatermarkOptions) -> Image.Image:
    text = _single_line_text(options.text)
    font = _load_font(options.font_size)

    probe = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    probe_draw = ImageDraw.Draw(probe)
    text_width, text_height = _text_size(probe_draw, text, font)

    pad = max(12, options.font_size // 2)
    tile = Image.new("RGBA", (text_width + pad * 2, text_height + pad * 2), (255, 255, 255, 0))
    tile_draw = ImageDraw.Draw(tile)
    fill = (0, 0, 0, TEXT_WATERMARK_ALPHA)
    tile_draw.text((pad, pad), text, fill=fill, font=font)

    tile = tile.rotate(45, expand=True, resample=_resampling("BICUBIC"))
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))

    if options.text_layout == "single":
        x = (image.width - tile.width) // 2
        y = (image.height - tile.height) // 2
        watermark.alpha_composite(tile, (x, y))
        return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")

    center_x = (image.width - tile.width) // 2
    step_x = max(tile.width + options.font_size, options.font_size * 4)
    for y in _three_row_tile_positions(tile.height, image.height):
        for x in _anchored_tile_positions(center_x, step_x, tile.width, image.width):
            watermark.alpha_composite(tile, (x, y))

    return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")


def _prepare_image_watermark(path: str, page_size: tuple[int, int]) -> Image.Image:
    page_width, page_height = page_size
    source = Image.open(path).convert("RGBA")
    source.thumbnail((int(page_width * 0.55), int(page_height * 0.55)), _resampling("LANCZOS"))

    alpha = source.getchannel("A")
    alpha = ImageEnhance.Brightness(alpha).enhance(IMAGE_WATERMARK_ALPHA / 255)
    source.putalpha(alpha)
    return source


def add_image_watermark(image: Image.Image, image_path: str) -> Image.Image:
    mark = _prepare_image_watermark(image_path, image.size)
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))
    x = (image.width - mark.width) // 2
    y = (image.height - mark.height) // 2
    watermark.alpha_composite(mark, (x, y))
    return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")


def render_page_to_image(page: fitz.Page, include_annotations: bool = False) -> Image.Image:
    pix = page.get_pixmap(
        matrix=fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM),
        alpha=False,
        annots=include_annotations,
    )
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def append_image_page(output_doc: fitz.Document, page_rect: fitz.Rect, image: Image.Image) -> None:
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    page = output_doc.new_page(width=page_rect.width, height=page_rect.height)
    page.insert_image(page.rect, stream=image_bytes.getvalue())


def convert_pdf_to_image_pdf(input_path: str, options: ProcessOptions | WatermarkOptions | None = None) -> str:
    if isinstance(options, WatermarkOptions) or options is None:
        options = ProcessOptions(watermark=options)

    desired_path = _output_path(input_path)
    out_dir = os.path.dirname(os.path.abspath(input_path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix="office_tool_", suffix=".pdf", dir=out_dir)
    os.close(fd)

    input_doc = fitz.open(input_path)
    output_doc = fitz.open()
    try:
        for page_index in range(len(input_doc)):
            page = input_doc.load_page(page_index)
            if strip_pdf_watermark_artifacts_from_page(input_doc, page):
                page = input_doc.reload_page(page)
            image = render_page_to_image(page, include_annotations=False)
            if options.watermark and options.watermark.kind == "text":
                image = add_text_watermark(image, options.watermark)
            elif options.watermark and options.watermark.kind == "image":
                image = add_image_watermark(image, options.watermark.image_path)
            append_image_page(output_doc, page.rect, image)

        output_doc.save(tmp_path, garbage=4, deflate=True)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    finally:
        output_doc.close()
        input_doc.close()

    output_path = _replace_output(tmp_path, desired_path, input_path)
    return output_path


class PdfToImagePdfDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 转图片型 PDF")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)

        self._file_count = QLabel("PDF 文件（0 个已选）：")
        root.addWidget(self._file_count)

        file_row = QHBoxLayout()
        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(120)
        file_row.addWidget(self._file_list)

        file_buttons = QVBoxLayout()
        add_file = QPushButton("添加文件")
        add_file.clicked.connect(self._add_files)
        remove_file = QPushButton("移除选中")
        remove_file.clicked.connect(self._remove_selected)
        file_buttons.addWidget(add_file)
        file_buttons.addWidget(remove_file)
        file_buttons.addStretch()
        file_row.addLayout(file_buttons)
        root.addLayout(file_row)

        mode_box = QGroupBox("处理方式")
        mode_layout = QVBoxLayout(mode_box)
        self._mode_group = QButtonGroup(self)
        self._no_watermark = QRadioButton("转为图片型 PDF（无水印）")
        self._with_watermark = QRadioButton("添加水印")
        self._no_watermark.setChecked(True)
        self._mode_group.addButton(self._no_watermark, 0)
        self._mode_group.addButton(self._with_watermark, 1)
        mode_layout.addWidget(self._no_watermark)
        mode_layout.addWidget(self._with_watermark)
        root.addWidget(mode_box)

        self._watermark_box = QGroupBox("水印选项")
        wm_root = QVBoxLayout(self._watermark_box)

        wm_type_row = QHBoxLayout()
        self._wm_type_group = QButtonGroup(self)
        self._text_watermark = QRadioButton("文字水印")
        self._image_watermark = QRadioButton("图片水印")
        self._text_watermark.setChecked(True)
        self._wm_type_group.addButton(self._text_watermark, 0)
        self._wm_type_group.addButton(self._image_watermark, 1)
        wm_type_row.addWidget(self._text_watermark)
        wm_type_row.addWidget(self._image_watermark)
        wm_type_row.addStretch()
        wm_root.addLayout(wm_type_row)

        self._text_panel = QWidget()
        text_form = QFormLayout(self._text_panel)
        text_form.setContentsMargins(0, 0, 0, 0)
        self._watermark_text = QLineEdit("水印")
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 500)
        self._font_size.setValue(72)

        self._layout_group = QButtonGroup(self)
        self._single_line = QRadioButton("单行")
        self._multi_line = QRadioButton("多行")
        self._single_line.setChecked(True)
        self._layout_group.addButton(self._single_line, 0)
        self._layout_group.addButton(self._multi_line, 1)
        layout_row = QHBoxLayout()
        layout_row.addWidget(self._single_line)
        layout_row.addWidget(self._multi_line)
        layout_row.addStretch()
        layout_widget = QWidget()
        layout_widget.setLayout(layout_row)

        text_form.addRow("水印文字：", self._watermark_text)
        text_form.addRow("字号：", self._font_size)
        text_form.addRow("排列：", layout_widget)
        wm_root.addWidget(self._text_panel)

        self._image_panel = QWidget()
        image_row = QHBoxLayout(self._image_panel)
        image_row.setContentsMargins(0, 0, 0, 0)
        self._image_path = QLineEdit()
        self._image_path.setPlaceholderText("选择水印图片...")
        browse_image = QPushButton("浏览")
        browse_image.clicked.connect(self._browse_image)
        image_row.addWidget(QLabel("水印图片："))
        image_row.addWidget(self._image_path)
        image_row.addWidget(browse_image)
        wm_root.addWidget(self._image_panel)

        self._watermark_box.hide()
        self._image_panel.hide()
        root.addWidget(self._watermark_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._with_watermark.toggled.connect(self._watermark_box.setVisible)
        self._text_watermark.toggled.connect(self._sync_watermark_panels)
        self._image_watermark.toggled.connect(self._sync_watermark_panels)
        self._file_list.model().rowsInserted.connect(self._update_file_count)
        self._file_list.model().rowsRemoved.connect(self._update_file_count)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for file_path in files:
            if file_path not in existing:
                self._file_list.addItem(file_path)

    def _remove_selected(self) -> None:
        for item in reversed(self._file_list.selectedItems()):
            self._file_list.takeItem(self._file_list.row(item))

    def _update_file_count(self) -> None:
        self._file_count.setText(f"PDF 文件（{self._file_list.count()} 个已选）：")

    def _sync_watermark_panels(self) -> None:
        image_mode = self._image_watermark.isChecked()
        self._text_panel.setVisible(not image_mode)
        self._image_panel.setVisible(image_mode)
        self.adjustSize()

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择水印图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)",
        )
        if path:
            self._image_path.setText(path)

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def watermark_options(self) -> WatermarkOptions | None:
        if self._no_watermark.isChecked():
            return None

        if self._image_watermark.isChecked():
            return WatermarkOptions(kind="image", image_path=self._image_path.text().strip())

        return WatermarkOptions(
            kind="text",
            text=self._watermark_text.text().strip(),
            font_size=self._font_size.value(),
            text_layout="multi" if self._multi_line.isChecked() else "single",
        )

    def process_options(self) -> ProcessOptions:
        return ProcessOptions(watermark=self.watermark_options())


def process_pdf() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = PdfToImagePdfDialog()
    if dialog.exec() != QDialog.Accepted:
        return

    files = dialog.selected_files()
    if not files:
        QMessageBox.information(None, "提示", "未选择任何文件。")
        return

    generated_inputs = [path for path in files if _looks_like_generated_output(path)]
    if generated_inputs:
        names = "\n".join(os.path.basename(path) for path in generated_inputs[:8])
        if len(generated_inputs) > 8:
            names += f"\n...还有 {len(generated_inputs) - 8} 个"
        choice = QMessageBox.question(
            None,
            "确认输入文件",
            "以下文件名看起来像本工具生成过的输出 PDF：\n\n"
            f"{names}\n\n"
            "如果这些文件里已经有旧水印，“无水印”转换也会保留旧水印。\n"
            "建议选择最原始、未加水印的 PDF。\n\n仍要继续处理这些文件吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice != QMessageBox.Yes:
            return

    options = dialog.process_options()
    watermark = options.watermark
    if watermark and watermark.kind == "text" and not watermark.text:
        QMessageBox.warning(None, "提示", "未输入水印内容。")
        return
    if watermark and watermark.kind == "image":
        if not watermark.image_path:
            QMessageBox.warning(None, "提示", "未选择水印图片。")
            return
        if not os.path.exists(watermark.image_path):
            QMessageBox.warning(None, "提示", "水印图片不存在。")
            return

    outputs: list[str] = []
    failures: list[str] = []
    for file_path in files:
        try:
            outputs.append(convert_pdf_to_image_pdf(file_path, options))
        except Exception as exc:
            failures.append(f"{os.path.basename(file_path)}\n错误信息：{exc}")

    for output in outputs:
        print(f"[输出文件] {output}")
        try:
            os.startfile(output)
        except OSError:
            pass

    output_text = "\n".join(outputs) if outputs else "（无）"
    if not failures:
        QMessageBox.information(
            None,
            "完成",
            f"处理完成。\n本次设置：{_process_summary(options)}\n\n已生成：\n{output_text}",
        )
        return

    failure_text = "\n\n".join(failures[:5])
    if len(failures) > 5:
        failure_text += f"\n\n还有 {len(failures) - 5} 个文件出错未显示。"
    QMessageBox.warning(
        None,
        "处理完成",
        f"本次设置：{_process_summary(options)}\n\n成功：{len(outputs)} 个\n已生成：\n{output_text}"
        f"\n\n失败：{len(failures)} 个\n失败详情：\n{failure_text}",
    )


if __name__ == "__main__":
    process_pdf()
