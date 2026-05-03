import os
import io
import tkinter as tk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfWriter
from PIL import Image
import fitz  # PyMuPDF


def process_pdf():
    # 初始化主窗口并隐藏
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    # 选择 PDF 文件
    files = filedialog.askopenfilenames(
        title="选择PDF文件",
        filetypes=[("PDF 文件", "*.pdf")]
    )

    if not files:
        messagebox.showinfo("提示", "未选择任何文件。")
        return

    success_count = 0
    fail_count = 0
    fail_list = []

    for file_path in files:
        try:
            # 输出文件名：原文件名后加 _img.pdf
            base_name = os.path.splitext(file_path)[0]
            output_path = base_name + "_img.pdf"

            writer = PdfWriter()
            doc = fitz.open(file_path)

            for page in doc:
                # 2倍分辨率渲染页面
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)

                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                img_io = io.BytesIO()
                img.save(img_io, format="PDF")
                img_io.seek(0)

                writer.append(img_io)

            with open(output_path, "wb") as f:
                writer.write(f)

            doc.close()
            success_count += 1

        except Exception as e:
            fail_count += 1
            fail_list.append(f"{os.path.basename(file_path)}\n错误信息：{str(e)}")

    # 处理完成提示
    if fail_count == 0:
        messagebox.showinfo(
            "完成",
            f"处理完成！\n成功转换 {success_count} 个 PDF 文件。"
        )
    else:
        error_text = "\n\n".join(fail_list[:5])
        if fail_count > 5:
            error_text += f"\n\n还有 {fail_count - 5} 个文件出错未显示。"

        messagebox.showwarning(
            "处理完成",
            f"成功转换：{success_count} 个\n失败：{fail_count} 个\n\n失败详情：\n{error_text}"
        )


if __name__ == "__main__":
    process_pdf()
    