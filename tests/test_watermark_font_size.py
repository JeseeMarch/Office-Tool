from __future__ import annotations

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tools.pdf_to_images_pdf import PdfToImagePdfDialog
from tools.pdf_to_images_pdf import _rendered_text_font_size
from tools.word_watermark import _text_watermark_xml
from tools.word_watermark import _text_watermarks_xml
from tools.word_watermark import _WordWatermarkDialog
from tools.word_watermark import _vml_text_font_size
from tools.word_to_image_pdf_watermark import _WordToImagePdfDialog


def _style_measure(xml: str, name: str) -> int:
    match = re.search(rf"{name}:(\d+)pt", xml)
    assert match is not None
    return int(match.group(1))


def test_word_text_watermark_shape_scales_with_font_size() -> None:
    small = _text_watermark_xml("测试水印", 96)
    large = _text_watermark_xml("测试水印", 144)

    assert f"font-size:{_vml_text_font_size(96)}pt" in small
    assert f"font-size:{_vml_text_font_size(144)}pt" in large
    assert _vml_text_font_size(96) <= 24
    assert _vml_text_font_size(96) < 96
    assert _vml_text_font_size(144) > _vml_text_font_size(96)
    assert _style_measure(large, "width") > _style_measure(small, "width")


def test_word_multi_watermarks_create_distinct_vml_anchors() -> None:
    xml = _text_watermarks_xml("测试水印", 96, [(0, -70), (220, -70), (-110, 55)])

    assert xml.count("<w:p ") == 3
    assert xml.count("<w:pict>") == 3
    assert xml.count("<v:shape ") == 3
    assert 'o:spid="_x0000_s2050"' in xml
    assert 'o:spid="_x0000_s2051"' in xml
    assert 'o:spid="_x0000_s2052"' in xml


def test_pdf_text_watermark_font_size_accounts_for_render_zoom() -> None:
    assert _rendered_text_font_size(96) == 192
    assert _rendered_text_font_size(144) == 288


def test_dialogs_commit_typed_font_size_before_reading_options() -> None:
    QApplication.instance() or QApplication([])

    word_dialog = _WordWatermarkDialog()
    word_dialog._font_size.lineEdit().setText("144")
    assert word_dialog.options().font_size == 144

    word_pdf_dialog = _WordToImagePdfDialog()
    word_pdf_dialog._single_text.setChecked(True)
    word_pdf_dialog._font_size.lineEdit().setText("144")
    assert word_pdf_dialog.options().font_size == 144

    pdf_dialog = PdfToImagePdfDialog()
    pdf_dialog._single_line.setChecked(True)
    pdf_dialog._font_size.lineEdit().setText("144")
    assert pdf_dialog.watermark_options().font_size == 144
