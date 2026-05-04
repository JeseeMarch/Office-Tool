from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import sleep

from docx2pdf import convert
from pdf2image import convert_from_path
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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


TOOL_VERSION = "20260504-word-image-pdf-3x3-grid-watermark"


@dataclass(frozen=True)
class ImagePdfOptions:
    watermark_kind: str
    text: str = ""
    image_path: str = ""
    font_size: int = 96


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_name in ("simsun.ttc", "simhei.ttf", "msyh.ttc"):
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _line_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _split_watermark_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.replace("；", "\n").replace(";", "\n").splitlines():
        line = raw_line.strip()
        if line:
            lines.append(line)
    return lines


def _make_rotated_text_image(text: str, font, opacity: float, angle: int) -> Image.Image:
    probe = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    probe_draw = ImageDraw.Draw(probe)
    text_width, text_height = _line_size(probe_draw, text, font)
    padding = max(50, int(text_width * 0.25))

    tile = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), (255, 255, 255, 0))
    draw = ImageDraw.Draw(tile)
    fill = (95, 95, 95, int(255 * opacity))
    draw.text(((tile.width - text_width) // 2, (tile.height - text_height) // 2), text, fill=fill, font=font)
    return tile.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def _make_rotated_multiline_image(lines: list[str], font, opacity: float, angle: int) -> Image.Image:
    probe = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    probe_draw = ImageDraw.Draw(probe)
    line_sizes = [_line_size(probe_draw, line, font) for line in lines]
    line_gap = max(4, int(font.size * 0.08)) if hasattr(font, "size") else 8
    text_width = max(width for width, _ in line_sizes)
    text_height = sum(height for _, height in line_sizes) + line_gap * (len(lines) - 1)
    padding = max(50, int(text_width * 0.25))

    tile = Image.new("RGBA", (text_width + padding * 2, text_height + padding * 2), (255, 255, 255, 0))
    draw = ImageDraw.Draw(tile)
    fill = (95, 95, 95, int(255 * opacity))
    y = padding
    for line, (line_width, line_height) in zip(lines, line_sizes):
        draw.text(((tile.width - line_width) // 2, y), line, fill=fill, font=font)
        y += line_height + line_gap
    return tile.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)


def _paste_centered(overlay: Image.Image, tile: Image.Image, center_x: int, center_y: int) -> None:
    overlay.alpha_composite(tile, (center_x - tile.width // 2, center_y - tile.height // 2))


def _paste_centered_grid(overlay: Image.Image, tile: Image.Image) -> None:
    center_x = overlay.width // 2
    center_y = overlay.height // 2
    step_x = max(int(tile.width * 1.55), overlay.width // 3)
    step_y = max(int(tile.height * 1.55), overlay.height // 3)
    x_offsets = [-step_x, 0, step_x]
    y_offsets = [-step_y, 0, step_y]

    for y_offset in y_offsets:
        for x_offset in x_offsets:
            _paste_centered(overlay, tile, center_x + x_offset, center_y + y_offset)


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
    font = _load_font(font_size)
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    if kind == "multi_text":
        tile = _make_rotated_multiline_image(lines, font, opacity, angle)
        _paste_centered_grid(overlay, tile)
    else:
        line = lines[0]
        tile = _make_rotated_text_image(line, font, opacity, angle)
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


def _safe_convert(input_file: str, output_file: str, retry: int = 3) -> bool:
    for attempt in range(retry):
        try:
            convert(input_file, output_file)
            return True
        except Exception as exc:
            print(f"尝试 {attempt + 1} 次失败：{exc}")
            sleep(1)
    return False


def word_to_image_pdf(input_file: str, options: ImagePdfOptions) -> str:
    folder = os.path.dirname(input_file)
    name = os.path.splitext(os.path.basename(input_file))[0]
    intermediate_pdf = os.path.join(folder, f"{name}_temp_{os.getpid()}.pdf")
    output_pdf = os.path.join(folder, f"{name}_.pdf")

    if not _safe_convert(input_file, intermediate_pdf):
        raise RuntimeError(f"文件 {input_file} 转换失败。")

    try:
        images = convert_from_path(intermediate_pdf)
        if options.watermark_kind in {"single_text", "multi_text"}:
            images = [
                _add_text_watermark(img, options.text, options.watermark_kind, options.font_size)
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

        form = QFormLayout()
        self._wm_text = QTextEdit("水印")
        self._wm_text.setMaximumHeight(90)
        form.addRow("水印文字：", self._wm_text)
        self._font_size = QSpinBox()
        self._font_size.setRange(48, 220)
        self._font_size.setSingleStep(4)
        self._font_size.setValue(96)
        form.addRow("字体大小：", self._font_size)

        image_row = QHBoxLayout()
        self._image_path = QLineEdit()
        self._image_path.setPlaceholderText("选择图片水印文件…")
        image_btn = QPushButton("浏览")
        image_btn.clicked.connect(self._browse_image)
        image_row.addWidget(self._image_path)
        image_row.addWidget(image_btn)
        form.addRow("水印图片：", image_row)
        layout.addLayout(form)

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

    def options(self) -> ImagePdfOptions:
        checked = self._mode_group.checkedId()
        if checked == 3:
            return ImagePdfOptions("image", image_path=self._image_path.text().strip())
        if checked == 2:
            return ImagePdfOptions(
                "multi_text",
                text=self._wm_text.toPlainText().strip(),
                font_size=self._font_size.value(),
            )
        if checked == 1:
            first_line = next(iter(_split_watermark_lines(self._wm_text.toPlainText())), "")
            return ImagePdfOptions("single_text", text=first_line, font_size=self._font_size.value())
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
        return message.replace("\n", " ")
    return "Word 转图片型 PDF 未生成文件。"


if __name__ == "__main__":
    batch_convert_to_image_pdf()
