import os
import re
from tkinter import Tk, filedialog, messagebox, simpledialog

from docx import Document

def replace_text_in_paragraph(paragraph, old_text, new_text):
    """替换段落中的文字，并保留格式"""
    runs = paragraph.runs
    full_text = "".join(run.text for run in runs)

    if old_text in full_text:
        # 备份第一个 Run 的格式
        if runs:
            font_name = runs[0].font.name
            font_size = runs[0].font.size
            bold = runs[0].bold
            italic = runs[0].italic
            underline = runs[0].underline

        # 替换文本
        full_text = full_text.replace(old_text, new_text)

        # 清空段落原内容
        paragraph.clear()
        new_run = paragraph.add_run(full_text)

        # 还原格式
        if runs:
            if font_name:
                new_run.font.name = font_name
            if font_size:
                new_run.font.size = font_size
            new_run.bold = bold
            new_run.italic = italic
            new_run.underline = underline


def replace_text_in_headers_footers(doc, old_text, new_text):
    """替换所有节的页眉和页脚文本，并确保标记文档已修改"""
    modified = False
    for section in doc.sections:
        # 处理页眉
        header = section.header
        if header.is_linked_to_previous:
            continue

        for paragraph in header.paragraphs:
            before = paragraph.text
            replace_text_in_paragraph(paragraph, old_text, new_text)
            if before != paragraph.text:
                print(f"页眉已修改: {before} → {paragraph.text}")
                modified = True

        # 处理页脚
        footer = section.footer
        if footer.is_linked_to_previous:
            continue

        for paragraph in footer.paragraphs:
            before = paragraph.text
            replace_text_in_paragraph(paragraph, old_text, new_text)
            if before != paragraph.text:
                print(f"页脚已修改: {before} → {paragraph.text}")
                modified = True
    return modified

def replace_text_in_docx(docx_file, old_text, new_text):
    """替换 Word 文档的正文、页眉、页脚"""
    doc = Document(docx_file)
    modified = False

    # 替换正文段落
    for para in doc.paragraphs:
        before = para.text
        replace_text_in_paragraph(para, old_text, new_text)
        if para.text != before:
            modified = True

    # 替换表格内容
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    before = para.text
                    replace_text_in_paragraph(para, old_text, new_text)
                    if para.text != before:
                        modified = True

    # 替换页眉和页脚
    modified |= replace_text_in_headers_footers(doc, old_text, new_text)

    # 保存文档
    if modified:
        print(f"已修改并保存文件: {docx_file}")
        os.chmod(docx_file, 0o666)  # 赋予写入权限
        doc.save(docx_file)
    else:
        print(f"未检测到变化: {docx_file}")

def search_and_replace(root_folder, old_text, new_text):
    """遍历所有 .docx 文件并执行替换"""
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.endswith('.docx'):
                docx_file = os.path.join(root, file)
                print(f"正在处理: {docx_file}")
                try:
                    replace_text_in_docx(docx_file, old_text, new_text)
                except Exception as e:
                    print(f"处理 {docx_file} 失败: {e}")

def run_batch_replace():
    root = Tk()
    root.withdraw()

    root_folder = filedialog.askdirectory(title="选择要批量替换的 Word 文件夹")
    if not root_folder:
        return

    old_text = simpledialog.askstring("查找文本", "请输入要替换的原文本：")
    if old_text is None:
        return

    new_text = simpledialog.askstring("替换为", "请输入新文本：")
    if new_text is None:
        return

    try:
        search_and_replace(root_folder, old_text, new_text)
        messagebox.showinfo("完成", "Word 内容批量替换完成。")
    except Exception as exc:
        messagebox.showerror("替换失败", str(exc))


if __name__ == "__main__":
    run_batch_replace()
