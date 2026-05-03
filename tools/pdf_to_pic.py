import os
from tkinter import Tk, filedialog, messagebox, simpledialog

import fitz


def export_pdf_pages(pdf_path: str, output_dir: str, image_format: str = "png", zoom: float = 2.0) -> int:
    doc = fitz.open(pdf_path)
    matrix = fitz.Matrix(zoom, zoom)
    count = 0

    try:
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            output_path = os.path.join(output_dir, f"{base_name}_page_{index:03d}.{image_format}")
            pix.save(output_path)
            count += 1
    finally:
        doc.close()

    return count


def run_pdf_to_images() -> None:
    root = Tk()
    root.withdraw()

    files = filedialog.askopenfilenames(
        title="选择 PDF 文件",
        filetypes=[("PDF 文件", "*.pdf")],
    )
    if not files:
        return

    output_dir = filedialog.askdirectory(title="选择图片输出目录")
    if not output_dir:
        return

    image_format = simpledialog.askstring("图片格式", "请输入输出格式：png 或 jpg", initialvalue="png")
    if not image_format:
        return
    image_format = image_format.lower().strip(".")
    if image_format == "jpeg":
        image_format = "jpg"
    if image_format not in {"png", "jpg"}:
        messagebox.showwarning("格式不支持", "只支持 png 或 jpg。")
        return

    try:
        total = 0
        for pdf_path in files:
            total += export_pdf_pages(pdf_path, output_dir, image_format=image_format)
        messagebox.showinfo("完成", f"已导出 {total} 张图片。")
    except Exception as exc:
        messagebox.showerror("导出失败", str(exc))


if __name__ == "__main__":
    run_pdf_to_images()
