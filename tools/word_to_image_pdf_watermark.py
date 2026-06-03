from __future__ import annotations

import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import NamedTuple

from pdf2image import convert_from_path
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


TOOL_VERSION = "20260603-word-image-pdf-aligned-grid-watermark"

# 页面渲染 DPI。水印字号会按 RENDER_DPI/72 放大，使 font_size 表示“页面磅值”，
# 与 PDF 工具（RENDER_ZOOM=2.0，即 144dpi）保持同字号同物理大小。
RENDER_DPI = 200


@dataclass(frozen=True)
class ImagePdfOptions:
    watermark_kind: str
    text: str = ""
    image_path: str = ""
    font_size: int = 72


class WatermarkFonts(NamedTuple):
    cjk: ImageFont.FreeTypeFont | ImageFont.ImageFont
    latin: ImageFont.FreeTypeFont | ImageFont.ImageFont


def _cjk_font_candidates() -> list[str]:
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


def _load_first_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    for font_name in candidates:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return None


def _load_watermark_fonts(size: int) -> WatermarkFonts:
    fallback = ImageFont.load_default()
    cjk = _load_first_font(_cjk_font_candidates(), size) or fallback
    latin = _load_first_font(_times_new_roman_candidates(), size) or fallback
    return WatermarkFonts(cjk=cjk, latin=latin)


def _line_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


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
    width, _ = _line_size(draw, char, font)
    return max(1, width)


def _mixed_line_size(draw: ImageDraw.ImageDraw, text: str, fonts: WatermarkFonts, font_size: int) -> tuple[int, int]:
    width = sum(_char_width(draw, char, _font_for_char(char, fonts)) for char in text)
    return max(1, width), max(1, int(font_size * 1.25))


def _draw_mixed_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill, fonts: WatermarkFonts) -> None:
    x, y = xy
    for char in text:
        font = _font_for_char(char, fonts)
        draw.text((x, y), char, fill=fill, font=font)
        x += _char_width(draw, char, font)


def _split_watermark_lines(text: str) -> list[str]:
    text = text.replace("\\n", "\n").replace("；", "\n").replace(";", "\n")
    text = " ".join(part.strip() for part in text.splitlines() if part.strip())
    return [text] if text else []


def _make_rotated_text_image(text: str, fonts: WatermarkFonts, font_size: int, opacity: float, angle: int) -> Image.Image:
    probe = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    probe_draw = ImageDraw.Draw(probe)
    text_width, text_height = _mixed_line_size(probe_draw, text, fonts, font_size)
    padding = max(50, int(text_width * 0.25))

    tile = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), (255, 255, 255, 0))
    draw = ImageDraw.Draw(tile)
    fill = (95, 95, 95, int(255 * opacity))
    _draw_mixed_text(draw, ((tile.width - text_width) // 2, (tile.height - text_height) // 2), text, fill, fonts)
    return tile.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def _make_rotated_multiline_image(
    lines: list[str],
    fonts: WatermarkFonts,
    font_size: int,
    opacity: float,
    angle: int,
) -> tuple[Image.Image, int, int]:
    probe = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    probe_draw = ImageDraw.Draw(probe)
    line_sizes = [_mixed_line_size(probe_draw, line, fonts, font_size) for line in lines]
    line_gap = max(16, int(font_size * 0.35))
    text_width = max(width for width, _ in line_sizes)
    text_height = sum(height for _, height in line_sizes) + line_gap * (len(lines) - 1)
    padding = max(50, int(text_width * 0.25))

    tile = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), (255, 255, 255, 0))
    draw = ImageDraw.Draw(tile)
    fill = (95, 95, 95, int(255 * opacity))
    y = padding
    for line, (line_width, line_height) in zip(lines, line_sizes):
        _draw_mixed_text(draw, ((tile.width - line_width) // 2, y), line, fill, fonts)
        y += line_height + line_gap
    rotated = tile.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    return rotated, text_width, text_height


def _paste_centered(overlay: Image.Image, tile: Image.Image, center_x: int, center_y: int) -> None:
    _paste_tile(overlay, tile, center_x - tile.width // 2, center_y - tile.height // 2)


def _paste_tile(overlay: Image.Image, tile: Image.Image, x: int, y: int) -> None:
    left = max(0, x)
    top = max(0, y)
    right = min(overlay.width, x + tile.width)
    bottom = min(overlay.height, y + tile.height)
    if left >= right or top >= bottom:
        return

    crop = tile.crop((left - x, top - y, right - x, bottom - y))
    overlay.alpha_composite(crop, (left, top))


def _paste_centered_grid(overlay: Image.Image, tile: Image.Image, step_x: int, step_y: int) -> None:
    # 以页面中心为基准，向四周铺满；所有行列严格对齐（不做半步错位），避免错行。
    step_x = max(1, step_x)
    step_y = max(1, step_y)
    center_x = (overlay.width - tile.width) // 2
    center_y = (overlay.height - tile.height) // 2

    start_x = center_x
    while start_x - step_x > -tile.width:
        start_x -= step_x
    start_y = center_y
    while start_y - step_y > -tile.height:
        start_y -= step_y

    y = start_y
    while y < overlay.height:
        x = start_x
        while x < overlay.width:
            _paste_tile(overlay, tile, x, y)
            x += step_x
        y += step_y


def _add_text_watermark(
    image: Image.Image,
    text: str,
    kind: str,
    font_size: int,
    opacity: float = 0.24,
    angle: int = 45,
) -> Image.Image:
    lines = _split_watermark_lines(text)
    if not lines:
        return image.convert("RGB")
    if kind == "single_text":
        lines = lines[:1]

    width, height = image.size
    fonts = _load_watermark_fonts(font_size)
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    if kind == "multi_text":
        tile, text_width, text_height = _make_rotated_multiline_image(lines, fonts, font_size, opacity, angle)
        # 旋转 angle 后，文字在水平/垂直方向的投影尺寸才是平铺间距的依据；
        # 若仍按未旋转的文字宽/高计算，字数变多时步长失衡，水印会沿斜向首尾相接而“串行”。
        cos_a, sin_a = abs(math.cos(math.radians(angle))), abs(math.sin(math.radians(angle)))
        horiz_extent = text_width * cos_a + text_height * sin_a
        vert_extent = text_width * sin_a + text_height * cos_a
        _paste_centered_grid(overlay, tile, max(120, int(horiz_extent * 1.15)), max(80, int(vert_extent * 1.15)))
    else:
        line = lines[0]
        tile = _make_rotated_text_image(line, fonts, font_size, opacity, angle)
        _paste_centered(overlay, tile, width // 2, height // 2)

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _prepare_watermark_image(path: str, page_size: tuple[int, int]) -> Image.Image:
    page_width, page_height = page_size
    mark = Image.open(path)
    if mark.mode == "P":
        mark = mark.convert("RGBA")
    if mark.mode != "RGBA":
        mark = mark.convert("RGBA")

    bg = Image.new("RGBA", mark.size, (255, 255, 255, 255))
    bg.alpha_composite(mark)
    gray = bg.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(1.15)
    gray = gray.point(lambda p: min(255, int(round(255 - (255 - p) * 0.35))))
    alpha = Image.new("L", gray.size, 95)
    mark = Image.merge("RGBA", (gray, gray, gray, alpha))

    max_width = int(page_width * 0.42)
    max_height = int(page_height * 0.28)
    ratio = min(max_width / mark.width, max_height / mark.height, 1.0)
    size = (max(1, int(mark.width * ratio)), max(1, int(mark.height * ratio)))
    return mark.resize(size, Image.LANCZOS)


def _add_image_watermark(image: Image.Image, image_path: str) -> Image.Image:
    page = image.convert("RGBA")
    mark = _prepare_watermark_image(image_path, page.size)
    x = (page.width - mark.width) // 2
    y = (page.height - mark.height) // 2
    page.alpha_composite(mark, (x, y))
    return page.convert("RGB")


def _export_word_to_pdf(input_file: str, output_file: str) -> None:
    import pythoncom
    import win32com.client

    input_path = str(Path(input_file).resolve())
    output_path = str(Path(output_file).resolve())
    word = None
    doc = None
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(
            input_path,
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        doc.ExportAsFixedFormat(
            OutputFileName=output_path,
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    finally:
        if doc is not None:
            doc.Close(False)
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


def _safe_convert(input_file: str, output_file: str, retry: int = 3) -> None:
    last_error = None
    for attempt in range(retry):
        try:
            _export_word_to_pdf(input_file, output_file)
            if Path(output_file).is_file() and Path(output_file).stat().st_size > 0:
                return
            last_error = RuntimeError("Word 未生成有效 PDF。")
        except Exception as exc:
            last_error = exc
            sleep(1)
    raise RuntimeError(f"Word 转 PDF 失败：{last_error}")


def word_to_image_pdf(input_file: str, options: ImagePdfOptions) -> str:
    folder = os.path.dirname(input_file)
    name = os.path.splitext(os.path.basename(input_file))[0]
    fd, intermediate_pdf = tempfile.mkstemp(prefix=f"{name}_", suffix=".pdf")
    os.close(fd)
    os.remove(intermediate_pdf)
    output_pdf = os.path.join(folder, f"{name}_.pdf")

    try:
        _safe_convert(input_file, intermediate_pdf)
        images = convert_from_path(intermediate_pdf, dpi=RENDER_DPI)
        if options.watermark_kind in {"single_text", "multi_text"}:
            # font_size 以页面磅值计；渲染图是 RENDER_DPI 像素密度，需同比放大字号。
            scaled_font = max(1, round(options.font_size * RENDER_DPI / 72))
            images = [
                _add_text_watermark(img, options.text, options.watermark_kind, scaled_font)
                for img in images
            ]
        elif options.watermark_kind == "image":
            images = [_add_image_watermark(img, options.image_path) for img in images]
        else:
            images = [img.convert("RGB") for img in images]

        if not images:
            raise RuntimeError("未生成任何页面图片。")
        images[0].save(output_pdf, save_all=True, append_images=images[1:])
        return output_pdf
    finally:
        if os.path.exists(intermediate_pdf):
            os.remove(intermediate_pdf)


class _WordToImagePdfDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Word → 图片型 PDF")
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
        self._none = QRadioButton("无水印")
        self._single_text = QRadioButton("单行水印")
        self._multi_text = QRadioButton("多行水印")
        self._image = QRadioButton("图片水印")
        self._none.setChecked(True)
        for index, button in enumerate((self._none, self._single_text, self._multi_text, self._image)):
            self._mode_group.addButton(button, index)
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
        files, _ = QFileDialog.getOpenFileNames(self, "选择 Word 文件", "", "Word 文件 (*.docx)")
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

    def options(self) -> ImagePdfOptions:
        checked = self._mode_group.checkedId()
        if checked == 3:
            return ImagePdfOptions("image", image_path=self._image_path.text().strip())
        if checked == 2:
            return ImagePdfOptions(
                "multi_text",
                text=self._wm_text.toPlainText().strip(),
                font_size=self._font_size_value(),
            )
        if checked == 1:
            first_line = next(iter(_split_watermark_lines(self._wm_text.toPlainText())), "")
            return ImagePdfOptions("single_text", text=first_line, font_size=self._font_size_value())
        return ImagePdfOptions("none")

    def start_progress(self, maximum: int) -> None:
        self._progress.setRange(0, max(1, maximum))
        self._progress.setValue(0)
        self.show()
        QApplication.processEvents()

    def set_progress(self, value: int) -> None:
        self._progress.setValue(value)
        QApplication.processEvents()


def _validate_options(options: ImagePdfOptions) -> None:
    if options.watermark_kind in {"single_text", "multi_text"} and not options.text.strip():
        raise ValueError("未输入水印文字。")
    if options.watermark_kind == "image" and not options.image_path:
        raise ValueError("未选择水印图片。")
    if options.watermark_kind == "image" and not Path(options.image_path).is_file():
        raise ValueError(f"找不到水印图片：{options.image_path}")


def batch_convert_to_image_pdf(progress_callback=None) -> str:
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _WordToImagePdfDialog()
    if dialog.exec() != QDialog.Accepted:
        return "已取消：Word 转图片型 PDF。"

    files = dialog.selected_files()
    if not files:
        return "未选择任何 Word 文件，未处理。"

    try:
        options = dialog.options()
        _validate_options(options)
    except Exception as exc:
        QMessageBox.warning(None, "提示", str(exc))
        return f"Word 转图片型 PDF 未执行：{exc}"

    failed_files = []
    success_files = []
    if progress_callback:
        progress_callback(0, len(files))
    for index, file_path in enumerate(files, start=1):
        try:
            success_files.append(word_to_image_pdf(file_path, options))
        except Exception as exc:
            failed_files.append(f"{file_path}：{exc}")
        if progress_callback:
            progress_callback(index, len(files))

    if failed_files:
        QMessageBox.warning(None, "部分失败", "\n".join(failed_files))
    if success_files:
        message = "已生成：\n" + "\n".join(success_files)
        return f"本次设置：{options.watermark_kind}，字号 {options.font_size}。 {message.replace(chr(10), ' ')}"
    return "Word 转图片型 PDF 未生成文件。"


if __name__ == "__main__":
    batch_convert_to_image_pdf()
