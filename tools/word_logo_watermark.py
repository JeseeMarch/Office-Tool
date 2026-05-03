"""
在 Word (.docx) 页眉中插入公司 Logo 水印：与 Word 内置文字水印相同的 VML 机制，
相对页面居中、负 z-index 衬于正文下方；正文区一般不可选中。
输出「原名_.docx」。默认 assets/company_logo.png。
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from PIL import Image, ImageEnhance
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
)

VML_SHAPE_ID = "OfficeToolLogoVML"
DOC_PR_NAME = "OfficeToolLogoWatermark"
WP_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V_NS = "{urn:schemas-microsoft-com:vml}shape"

EMU_PER_PT = 12700


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_logo_path() -> Path:
    return _project_root() / "assets" / "company_logo.png"


def prepare_bw_logo_png(src: Path) -> io.BytesIO:
    """白底合成 → 灰度；对比微调后与白色的距离减半（颜色深度减半，更浅的水印）。"""
    im = Image.open(src)
    if im.mode == "P":
        im = im.convert("RGBA")
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    else:
        im = im.convert("RGB")
    gray = im.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(1.15)
    gray = ImageEnhance.Brightness(gray).enhance(0.95)
    gray = gray.point(lambda p: min(255, int(round(255 - (255 - p) * 0.3))))
    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _iter_unique_headers(doc: Document):
    seen: set[str] = set()
    odd_even = doc.settings.odd_and_even_pages_header_footer
    for sec in doc.sections:
        candidates = [sec.header]
        if sec.different_first_page_header_footer:
            candidates.append(sec.first_page_header)
        if odd_even:
            candidates.append(sec.even_page_header)
        for h in candidates:
            try:
                key = str(h.part.partname)
            except AttributeError:
                continue
            if key in seen:
                continue
            seen.add(key)
            yield h


def _strip_logo_watermark(hdr_element) -> None:
    dead_ids: set[int] = set()
    for p in list(hdr_element):
        if p.tag != qn("w:p"):
            continue
        for shape in p.iter(V_NS):
            if shape.get("id") == VML_SHAPE_ID:
                dead_ids.add(id(p))
                break
        for dr in p.findall(".//" + qn("w:drawing")):
            for doc_pr in dr.iter(f"{{{WP_DRAWINGML_NS}}}docPr"):
                if doc_pr.get("name") == DOC_PR_NAME:
                    dead_ids.add(id(p))
                    break
    for p in list(hdr_element):
        if p.tag == qn("w:p") and id(p) in dead_ids:
            hdr_element.remove(p)


def _vml_logo_paragraph_xml(r_id: str, width_pt: float, height_pt: float) -> str:
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  <w:r>
    <w:pict>
      <v:shape id="{VML_SHAPE_ID}" o:spid="_x0000_s2051" type="#_x0000_t75"
        style="position:absolute;margin-left:0;margin-top:0;width:{width_pt:.1f}pt;height:{height_pt:.1f}pt;z-index:-251658752;mso-position-horizontal:center;mso-position-horizontal-relative:page;mso-position-vertical:center;mso-position-vertical-relative:page"
        filled="f" stroked="f">
        <v:imagedata r:id="{r_id}" o:title="logo"/>
      </v:shape>
      <w10:wrap anchorx="margin" anchory="margin"/>
    </w:pict>
  </w:r>
</w:p>"""


def add_logo_watermark_to_document(doc: Document, logo_stream: io.BytesIO) -> None:
    logo_stream.seek(0)
    first_sec = doc.sections[0]
    target_w = int(first_sec.page_width * 0.52 * 1.5)

    for header in _iter_unique_headers(doc):
        _strip_logo_watermark(header._element)
        r_id, image = header.part.get_or_add_image(logo_stream)
        logo_stream.seek(0)
        cx, cy = image.scaled_dimensions(target_w, None)
        width_pt = float(int(cx)) / EMU_PER_PT
        height_pt = float(int(cy)) / EMU_PER_PT
        fragment = _vml_logo_paragraph_xml(r_id, width_pt, height_pt)
        wp = parse_xml(fragment)
        header._element.insert(0, wp)


def run_word_logo_watermark():
    app = QApplication.instance() or QApplication(sys.argv)

    logo_path = default_logo_path()
    if not logo_path.is_file():
        QMessageBox.critical(
            None, "缺少 Logo",
            f"未找到默认 Logo 文件：\n{logo_path}\n请将公司 Logo 保存为该路径。",
        )
        return

    files, _ = QFileDialog.getOpenFileNames(
        None, "选择要加 Logo 水印的 Word 文件", "", "Word (*.docx)"
    )
    if not files:
        return

    try:
        logo_png = prepare_bw_logo_png(logo_path)
    except Exception as e:
        QMessageBox.critical(None, "错误", f"处理 Logo 图片失败：{e}")
        return

    failed = []
    outputs = []
    for path in files:
        try:
            folder = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            out_path = os.path.join(folder, f"{base}_.docx")

            doc = Document(path)
            add_logo_watermark_to_document(doc, logo_png)
            doc.save(out_path)
            outputs.append(out_path)
        except Exception as exc:
            failed.append(f"{path}: {exc}")

    if failed:
        QMessageBox.warning(None, "完成（部分失败）", "\n".join(failed))
    if outputs:
        QMessageBox.information(
            None, "完成",
            "已生成（原文件未修改）：\n"
            + "\n".join(outputs)
            + "\n\n水印使用 Word 兼容的页眉 VML 图片，居中衬于文字下方。"
            + "\n若仍看不见，请在 Word 中双击页眉进入页眉编辑查看。",
        )


if __name__ == "__main__":
    run_word_logo_watermark()
