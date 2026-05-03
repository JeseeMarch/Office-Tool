import io
import os
import sys

import fitz  # PyMuPDF
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


def add_watermark(image, text, font_size=50, opacity=0.1):
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark)

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (image.width - text_width) // 2
    y = (image.height - text_height) // 2

    draw.text((x, y), text, font=font, fill=(255, 255, 255, int(255 * opacity)))
    return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")


def pdf_to_image_pdf(input_pdf_path, output_pdf_path, watermark_text):
    pdf_document = fitz.open(input_pdf_path)
    image_pdf_document = fitz.open()

    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        img = Image.open(io.BytesIO(pix.tobytes("png")))
        watermarked_img = add_watermark(img, watermark_text)

        img_bytes = io.BytesIO()
        watermarked_img.save(img_bytes, format="PDF")
        img_pdf = fitz.open("pdf", img_bytes.getvalue())
        image_pdf_document.insert_pdf(img_pdf)

    image_pdf_document.save(output_pdf_path)
    image_pdf_document.close()
    pdf_document.close()


class _HiddenWatermarkDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF 居中浅水印")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        # --- 文件选择 ---
        self._file_count_label = QLabel("PDF 文件（0 个已选）：")
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
        files, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)")
        existing = {self._file_list.item(i).text() for i in range(self._file_list.count())}
        for f in files:
            if f not in existing:
                self._file_list.addItem(f)

    def _remove_selected(self):
        for item in reversed(self._file_list.selectedItems()):
            self._file_list.takeItem(self._file_list.row(item))

    def _update_file_count(self):
        n = self._file_list.count()
        self._file_count_label.setText(f"PDF 文件（{n} 个已选）：")

    def selected_files(self) -> list[str]:
        return [self._file_list.item(i).text() for i in range(self._file_list.count())]

    def watermark_text(self) -> str:
        return self._wm_text.text().strip()


def run_pdf_hidden_watermark():
    app = QApplication.instance() or QApplication(sys.argv)

    dialog = _HiddenWatermarkDialog()
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

    success = 0
    for file_path in files:
        file_dir = os.path.dirname(file_path)
        file_base_name, file_ext = os.path.splitext(os.path.basename(file_path))
        output_pdf_path = os.path.join(file_dir, f"{file_base_name}_{file_ext}")
        try:
            pdf_to_image_pdf(file_path, output_pdf_path, watermark_text)
            success += 1
        except Exception as e:
            print(f"处理失败：{file_path}，错误：{e}")

    QMessageBox.information(None, "完成", f"所有文件处理完成，成功 {success} 个。")


if __name__ == "__main__":
    run_pdf_hidden_watermark()
