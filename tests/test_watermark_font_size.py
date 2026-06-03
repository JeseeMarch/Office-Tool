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
    large = _text_watermark_xml("测试水印", 200)

    assert f"font-size:{_vml_text_font_size(96)}pt" in small
    assert f"font-size:{_vml_text_font_size(200)}pt" in large
    assert _vml_text_font_size(96) <= 24
    assert _vml_text_font_size(96) < 96
    assert _vml_text_font_size(200) > _vml_text_font_size(96)
    assert _style_measure(large, "width") > _style_measure(small, "width")

    # 每个 CJK 字接近方形：宽 ≈ 字数 × 框高（修复被压成瘦长的问题）。
    assert abs(_style_measure(small, "width") - 4 * _style_measure(small, "height")) <= 4


def test_word_multi_watermarks_create_distinct_vml_anchors() -> None:
    xml = _text_watermarks_xml("测试水印", 96, [(0, -70), (220, -70), (-110, 55)])

    # 所有水印放进同一个段落（避免多余空行/回车符），但各自是独立的 shape。
    assert xml.count("<w:p ") == 1
    assert xml.count("<w:pict>") == 3
    assert xml.count("<v:shape ") == 3
    # 绝对定位，不能带 center 关键字，否则水印会全部挤到正中重叠。
    assert "mso-position-horizontal:center" not in xml
    assert "mso-position-horizontal:absolute" in xml
    assert 'o:spid="_x0000_s2050"' in xml
    assert 'o:spid="_x0000_s2051"' in xml
    assert 'o:spid="_x0000_s2052"' in xml


def test_pdf_text_watermark_font_size_accounts_for_render_zoom() -> None:
    assert _rendered_text_font_size(96) == 192
    assert _rendered_text_font_size(144) == 288


def test_dialogs_default_font_size_is_72() -> None:
    QApplication.instance() or QApplication([])

    assert _WordWatermarkDialog().options().font_size == 72

    word_pdf_dialog = _WordToImagePdfDialog()
    word_pdf_dialog._single_text.setChecked(True)
    assert word_pdf_dialog.options().font_size == 72

    pdf_dialog = PdfToImagePdfDialog()
    pdf_dialog._single_line.setChecked(True)
    assert pdf_dialog.watermark_options().font_size == 72


def test_multi_text_watermark_field_is_rotated_as_a_whole() -> None:
    import math

    from tools.word_watermark import (
        WATERMARK_ANGLE_DEG,
        _multi_text_watermark_positions,
        _text_watermark_shape_size,
        _vml_text_font_size,
    )

    text = "环聚医药"
    font_size = 72
    page_w, page_h = 595.0, 842.0  # A4，单位 pt
    width, height = _text_watermark_shape_size(text, _vml_text_font_size(font_size))
    positions = _multi_text_watermark_positions(text, font_size, page_w, page_h)

    # 整页铺满多个水印。
    assert len(positions) >= 4

    # 还原每个水印的中心点。
    centers = [(left + width / 2, top + height / 2) for left, top in positions]
    cx, cy = page_w / 2, page_h / 2

    # 页心水印存在（整体旋转的中心）。
    assert any(abs(x - cx) < 1 and abs(y - cy) < 1 for x, y in centers)

    # 阵列整体绕页心旋转：相邻水印的偏移 = 旋转后的基向量。
    unit = max(80.0, (width + height) * 0.70710678 * 1.15)
    step_x = unit * 2
    step_y = unit * 2
    angle = math.radians(-WATERMARK_ANGLE_DEG)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    ex = (step_x * cos_a, step_x * sin_a)        # 沿文字斜向（密集方向）
    ey = (-step_y * sin_a, step_y * cos_a)       # 垂直文字方向（行间距 3 倍）
    assert any(abs(x - (cx + ex[0])) < 2 and abs(y - (cy + ex[1])) < 2 for x, y in centers)
    assert any(abs(x - (cx + ey[0])) < 2 and abs(y - (cy + ey[1])) < 2 for x, y in centers)

    # 旋转后基向量不再平行于坐标轴（确实“整体旋转”了，而非横平竖直网格）。
    assert abs(ex[1]) > 1 and abs(ey[0]) > 1


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
