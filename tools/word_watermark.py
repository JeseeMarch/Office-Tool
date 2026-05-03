import os
from tkinter import Tk, filedialog, messagebox, simpledialog
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import qn

WATERMARK_ID = "OfficeToolTextWatermark"
V_NS = "{urn:schemas-microsoft-com:vml}shape"


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
    for paragraph in list(header_element):
        if paragraph.tag != qn("w:p"):
            continue
        for shape in paragraph.iter(V_NS):
            if shape.get("id") == WATERMARK_ID:
                header_element.remove(paragraph)
                break


def _watermark_xml(text: str) -> str:
    escaped_text = escape(text, {'"': "&quot;"})
    return f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:v="urn:schemas-microsoft-com:vml"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:w10="urn:schemas-microsoft-com:office:word">
  <w:r>
    <w:pict>
      <v:shape id="{WATERMARK_ID}" o:spid="_x0000_s2050" type="#_x0000_t136"
        style="position:absolute;margin-left:0;margin-top:0;width:420pt;height:120pt;rotation:315;z-index:-251654144;mso-position-horizontal:center;mso-position-horizontal-relative:page;mso-position-vertical:center;mso-position-vertical-relative:page"
        fillcolor="#d8d8d8" stroked="f">
        <v:textpath on="t" string="{escaped_text}" style="font-family:SimSun;font-size:44pt"/>
        <w10:wrap anchorx="margin" anchory="margin"/>
      </v:shape>
    </w:pict>
  </w:r>
</w:p>"""


def add_text_watermark(doc: Document, text: str) -> None:
    for header in _iter_unique_headers(doc):
        _remove_existing_watermarks(header._element)
        header._element.insert(0, parse_xml(_watermark_xml(text)))


def run_word_watermark() -> None:
    root = Tk()
    root.withdraw()

    files = filedialog.askopenfilenames(
        title="选择要加水印的 Word 文件",
        filetypes=[("Word 文档", "*.docx")],
    )
    if not files:
        return

    text = simpledialog.askstring("水印文字", "请输入水印内容：", initialvalue="水印")
    if not text:
        return

    outputs = []
    failed = []
    for path in files:
        try:
            folder = os.path.dirname(path)
            base = os.path.splitext(os.path.basename(path))[0]
            output_path = os.path.join(folder, f"{base}_watermark.docx")
            doc = Document(path)
            add_text_watermark(doc, text)
            doc.save(output_path)
            outputs.append(output_path)
        except Exception as exc:
            failed.append(f"{path}: {exc}")

    if failed:
        messagebox.showwarning("部分失败", "\n".join(failed))
    if outputs:
        messagebox.showinfo("完成", "已生成：\n" + "\n".join(outputs))


if __name__ == "__main__":
    run_word_watermark()
