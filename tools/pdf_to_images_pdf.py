import io
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import fitz
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
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


class WatermarkFonts(NamedTuple):
    cjk: ImageFont.FreeTypeFont | ImageFont.ImageFont
    latin: ImageFont.FreeTypeFont | ImageFont.ImageFont


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
    candidates = [
        str(fonts / "SourceHanSansSC-Regular.otf"),
        str(fonts / "SourceHanSansCN-Regular.otf"),
        str(fonts / "SourceHanSans-Regular.otf"),
        str(fonts / "NotoSansCJK-Regular.ttc"),
        str(fonts / "msyh.ttc"),
        "SourceHanSansSC-Regular.otf",
        "SourceHanSansCN-Regular.otf",
        "SourceHanSans-Regular.otf",
        "NotoSansCJK-Regular.ttc",
        "msyh.ttc",
    ]
    if fonts.is_dir():
        candidates.extend(str(path) for path in fonts.glob("SourceHanSans*"))
        candidates.extend(str(path) for path in fonts.glob("Source Han Sans*"))
    return candidates


def _times_new_roman_candidates() -> list[str]:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts = Path(windir) / "Fonts"
    return [
        str(fonts / "times.ttf"),
        str(fonts / "Times New Roman.ttf"),
        "times.ttf",
        "Times New Roman.ttf",
    ]


def _load_first_font(candidates: list[str], font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            continue
    return None


def _load_watermark_fonts(font_size: int) -> WatermarkFonts:
    fallback = ImageFont.load_default()
    cjk = _load_first_font(_font_candidates(), font_size) or fallback
    latin = _load_first_font(_times_new_roman_candidates(), font_size) or fallback
    return WatermarkFonts(cjk=cjk, latin=latin)


def _rendered_text_font_size(font_size: int) -> int:
    return max(1, int(round(font_size * RENDER_ZOOM)))


def _single_line_text(text: str) -> str:
    text = text.replace("\\n", "\n")
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _split_watermark_lines(text: str) -> list[str]:
    text = _single_line_text(text.replace("；", "\n").replace(";", "\n"))
    return [text] if text else []


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


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


def _font_for_char(char: str, fonts: WatermarkFonts):
    return fonts.cjk if _is_cjk(char) else fonts.latin


def _char_width(draw: ImageDraw.ImageDraw, char: str, font) -> int:
    if char == " ":
        return max(1, int(round(draw.textlength(char, font=font))))
    width, _ = _text_size(draw, char, font)
    return width


def _mixed_text_size(draw: ImageDraw.ImageDraw, text: str, fonts: WatermarkFonts, font_size: int) -> tuple[int, int]:
    width = sum(_char_width(draw, char, _font_for_char(char, fonts)) for char in text)
    return max(1, width), max(1, int(font_size * 1.25))


def _draw_mixed_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill, fonts: WatermarkFonts) -> None:
    x, y = xy
    for char in text:
        font = _font_for_char(char, fonts)
        draw.text((x, y), char, fill=fill, font=font)
        x += _char_width(draw, char, font)


def _make_text_tile(lines: list[str], fonts: WatermarkFonts, font_size: int) -> Image.Image:
    probe = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    probe_draw = ImageDraw.Draw(probe)
    line_sizes = [_mixed_text_size(probe_draw, line, fonts, font_size) for line in lines]
    line_gap = max(16, int(font_size * 0.35)) if len(lines) > 1 else 0
    text_width = max(width for width, _ in line_sizes)
    text_height = sum(height for _, height in line_sizes) + line_gap * (len(lines) - 1)

    pad = max(12, font_size // 2)
    tile = Image.new("RGBA", (text_width + pad * 2, text_height + pad * 2), (255, 255, 255, 0))
    tile_draw = ImageDraw.Draw(tile)
    fill = (0, 0, 0, TEXT_WATERMARK_ALPHA)
    y = pad
    for line, (line_width, line_height) in zip(lines, line_sizes):
        _draw_mixed_text(tile_draw, ((tile.width - line_width) // 2, y), line, fill, fonts)
        y += line_height + line_gap
    return tile


def _paste_tile(watermark: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    left = max(0, x)
    top = max(0, y)
    right = min(watermark.width, x + tile.width)
    bottom = min(watermark.height, y + tile.height)
    if left >= right or top >= bottom:
        return

    crop = tile.crop((left - x, top - y, right - x, bottom - y))
    watermark.alpha_composite(crop, (left, top))


def _staggered_tile_positions(tile_size: tuple[int, int], canvas_size: tuple[int, int]) -> list[tuple[int, int]]:
    tile_width, tile_height = tile_size
    canvas_width, canvas_height = canvas_size
    step_x = max(int(tile_width * 1.35), int(canvas_width * 0.36))
    step_y = max(int(tile_height * 1.12), int(canvas_height * 0.2))
    center_x = (canvas_width - tile_width) // 2
    center_y = (canvas_height - tile_height) // 2
    positions = [(center_x, center_y)]

    x = center_x - step_x
    while x > -tile_width:
        positions.append((x, center_y))
        x -= step_x
    x = center_x + step_x
    while x < canvas_width:
        positions.append((x, center_y))
        x += step_x

    row_offset = -1
    while center_y + row_offset * step_y > -tile_height:
        y = center_y + row_offset * step_y
        x = center_x + (step_x // 2 if abs(row_offset) % 2 else 0)
        while x > -tile_width:
            positions.append((x, y))
            x -= step_x
        x = center_x + (step_x // 2 if abs(row_offset) % 2 else 0) + step_x
        while x < canvas_width:
            positions.append((x, y))
            x += step_x
        row_offset -= 1

    row_offset = 1
    while center_y + row_offset * step_y < canvas_height:
        y = center_y + row_offset * step_y
        x = center_x - (step_x // 2 if abs(row_offset) % 2 else 0)
        while x > -tile_width:
            positions.append((x, y))
            x -= step_x
        x = center_x - (step_x // 2 if abs(row_offset) % 2 else 0) + step_x
        while x < canvas_width:
            positions.append((x, y))
            x += step_x
        row_offset += 1

    return positions


def add_text_watermark(image: Image.Image, options: WatermarkOptions) -> Image.Image:
    if options.text_layout == "single":
        lines = [_single_line_text(options.text)]
    else:
        lines = _split_watermark_lines(options.text)
    if not lines or not lines[0]:
        return image.convert("RGB")

    rendered_font_size = _rendered_text_font_size(options.font_size)
    fonts = _load_watermark_fonts(rendered_font_size)
    tile = _make_text_tile(lines, fonts, rendered_font_size)

    tile = tile.rotate(45, expand=True, resample=_resampling("BICUBIC"))
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))

    if options.text_layout == "single":
        x = (image.width - tile.width) // 2
        y = (image.height - tile.height) // 2
        watermark.alpha_composite(tile, (x, y))
        return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")

    for x, y in _staggered_tile_positions(tile.size, image.size):
        _paste_tile(watermark, tile, x, y)

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
        self.setWindowTitle("PDF → 图片型 PDF")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)

        self._file_count = QLabel("PDF 文件（0 个已选）：")
        root.addWidget(self._file_count)

        file_row = QHBoxLayout()
        self._file_list = QListWidget()
        self._file_list.setMinimumHeight(188)
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

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("输出模式："))
        self._mode_group = QButtonGroup(self)
        self._no_watermark = QRadioButton("无水印")
        self._single_line = QRadioButton("单行水印")
        self._multi_line = QRadioButton("多行水印")
        self._image_watermark = QRadioButton("图片水印")
        self._no_watermark.setChecked(True)
        self._mode_group.addButton(self._no_watermark, 0)
        self._mode_group.addButton(self._single_line, 1)
        self._mode_group.addButton(self._multi_line, 2)
        self._mode_group.addButton(self._image_watermark, 3)
        for button in (self._no_watermark, self._single_line, self._multi_line, self._image_watermark):
            mode_row.addWidget(button)
        mode_row.addStretch()
        root.addLayout(mode_row)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel("水印文字："))
        self._watermark_text = QTextEdit("水印")
        self._watermark_text.setMaximumHeight(86)
        text_row.addWidget(self._watermark_text)
        root.addLayout(text_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("字体大小："))
        self._font_size = QSpinBox()
        self._font_size.setRange(8, 500)
        self._font_size.setSingleStep(4)
        self._font_size.setValue(96)
        font_row.addWidget(self._font_size)
        root.addLayout(font_row)

        image_row = QHBoxLayout()
        image_row.addWidget(QLabel("水印图片："))
        self._image_path = QLineEdit()
        self._image_path.setPlaceholderText("选择图片水印文件...")
        browse_image = QPushButton("浏览")
        browse_image.clicked.connect(self._browse_image)
        image_row.addWidget(self._image_path)
        image_row.addWidget(browse_image)
        root.addLayout(image_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        root.addWidget(self._progress)
        self._progress.hide()

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

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择水印图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)",
        )
        if path:
            self._image_path.setText(path)
            self._image_watermark.setChecked(True)

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def _font_size_value(self) -> int:
        self._font_size.interpretText()
        return self._font_size.value()

    def watermark_options(self) -> WatermarkOptions | None:
        if self._no_watermark.isChecked():
            return None

        if self._image_watermark.isChecked():
            return WatermarkOptions(kind="image", image_path=self._image_path.text().strip())

        return WatermarkOptions(
            kind="text",
            text=self._watermark_text.toPlainText().strip(),
            font_size=self._font_size_value(),
            text_layout="multi" if self._multi_line.isChecked() else "single",
        )

    def process_options(self) -> ProcessOptions:
        return ProcessOptions(watermark=self.watermark_options())

    def start_progress(self, maximum: int) -> None:
        self._progress.setRange(0, max(1, maximum))
        self._progress.setValue(0)
        self.show()
        QApplication.processEvents()

    def set_progress(self, value: int) -> None:
        self._progress.setValue(value)
        QApplication.processEvents()


def process_pdf(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = PdfToImagePdfDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：PDF 转图片型 PDF。"

    files = dialog.selected_files()
    if not files:
        return "未选择任何 PDF 文件，未处理。"

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
    if progress_callback:
        progress_callback(0, len(files))
    for index, file_path in enumerate(files, start=1):
        try:
            outputs.append(convert_pdf_to_image_pdf(file_path, options))
        except Exception as exc:
            failures.append(f"{os.path.basename(file_path)}\n错误信息：{exc}")
        if progress_callback:
            progress_callback(index, len(files))

    for output in outputs:
        print(f"[输出文件] {output}")
        try:
            os.startfile(output)
        except OSError:
            pass

    output_text = "\n".join(outputs) if outputs else "（无）"
    if not failures:
        return f"处理完成。本次设置：{_process_summary(options)} 成功：{len(outputs)} 个 已生成：{output_text}"

    failure_text = "\n\n".join(failures[:5])
    if len(failures) > 5:
        failure_text += f"\n\n还有 {len(failures) - 5} 个文件出错未显示。"
    return (
        f"处理完成。本次设置：{_process_summary(options)} 成功：{len(outputs)} 个 "
        f"失败：{len(failures)} 个 已生成：{output_text} 失败详情：{failure_text}"
    )


if __name__ == "__main__":
    process_pdf()
