import os
import sys
from time import sleep

from docx2pdf import convert
from pdf2image import convert_from_path
from PIL import Image, ImageDraw, ImageFont
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


def add_watermark_to_image(image, watermark_text, opacity=0.3, angle=-45):
    width, height = image.size
    transparent_layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(transparent_layer)

    try:
        font = ImageFont.truetype("simsun.ttc", 144)
    except IOError:
        raise RuntimeError("未找到宋体字体，请确保系统安装了 simsun.ttc。")

    text_width = font.getbbox(watermark_text)[2]
    text_height = font.getbbox(watermark_text)[3]

    step_x = text_width * 2
    step_y = text_height * 3

    watermark_layer = Image.new("RGBA", (width * 2, height * 2), (255, 255, 255, 0))
    watermark_draw = ImageDraw.Draw(watermark_layer)

    for y in range(0, height * 2, step_y):
        for x in range(0, width * 2, step_x):
            watermark_draw.text(
                (x, y),
                watermark_text,
                fill=(0, 0, 0, int(255 * opacity)),
                font=font,
            )

    rotated_watermark = watermark_layer.rotate(angle, expand=True)
    x_offset = (width - rotated_watermark.width) // 2
    y_offset = (height - rotated_watermark.height) // 2
    transparent_layer.paste(rotated_watermark, (x_offset, y_offset), rotated_watermark)

    return Image.alpha_composite(image.convert("RGBA"), transparent_layer).convert("RGB")


def _safe_convert(input_file, output_file, retry=3):
    for attempt in range(retry):
        try:
            convert(input_file, output_file)
            return True
        except Exception as e:
            print(f"尝试 {attempt + 1} 次失败：{e}")
            sleep(1)
    return False


def word_to_image_pdf(input_file, watermark_text):
    folder = os.path.dirname(input_file)
    name = os.path.splitext(os.path.basename(input_file))[0]

    intermediate_pdf = os.path.join(folder, f"{name}_temp_{os.getpid()}.pdf")
    output_pdf = os.path.join(folder, f"{name}_.pdf")

    if not _safe_convert(input_file, intermediate_pdf):
        raise RuntimeError(f"文件 {input_file} 转换失败。")

    images = convert_from_path(intermediate_pdf)

    watermarked = [add_watermark_to_image(img, watermark_text, opacity=0.4, angle=45) for img in images]

    if watermarked:
        watermarked[0].save(output_pdf, save_all=True, append_images=watermarked[1:])

    os.remove(intermediate_pdf)
    return output_pdf


class _WordToImagePdfDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Word → 图片型 PDF + 水印")
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
        files, _ = QFileDialog.getOpenFileNames(self, "选择 Word 文件", "", "Word 文件 (*.docx)")
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


def batch_convert_to_image_pdf():
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _WordToImagePdfDialog()
    if dialog.exec() != QDialog.Accepted:
        return

    files = dialog.selected_files()
    if not files:
        QMessageBox.information(None, "提示", "未选择任何文件。")
        return

    watermark_text = dialog.watermark_text()
    if not watermark_text:
        QMessageBox.warning(None, "提示", "未输入水印内容。")
        return

    failed_files = []
    success_files = []
    for file in files:
        try:
            out = word_to_image_pdf(file, watermark_text)
            success_files.append(out)
        except Exception as e:
            failed_files.append(f"{file}：{e}")

    if failed_files:
        QMessageBox.warning(None, "部分失败", "\n".join(failed_files))
    else:
        QMessageBox.information(None, "完成", f"已成功处理 {len(success_files)} 个文件。")


if __name__ == "__main__":
    batch_convert_to_image_pdf()
