import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import io
import os
from tkinter import Tk, filedialog, simpledialog, messagebox

def add_watermark(image, text, font_size=50, opacity=0.1):
    """
    在图片上添加隐形水印
    """
    # 创建一个透明的水印层
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark)
    
    # 设置字体和水印文本
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
    
    # 计算水印位置（居中）
    # 使用 textbbox 获取文本的边界框
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (image.width - text_width) // 2
    y = (image.height - text_height) // 2
    
    # 添加水印文本
    draw.text((x, y), text, font=font, fill=(255, 255, 255, int(255 * opacity)))
    
    # 将水印层叠加到原图上
    watermarked_image = Image.alpha_composite(image.convert("RGBA"), watermark)
    return watermarked_image.convert("RGB")

def pdf_to_image_pdf(input_pdf_path, output_pdf_path, watermark_text):
    """
    将PDF转换为图片型PDF，并添加隐形水印
    """
    # 打开PDF文件
    pdf_document = fitz.open(input_pdf_path)
    image_pdf_document = fitz.open()  # 创建一个新的PDF文档
    
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 提高分辨率
        
        # 将页面转换为PIL图像
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        
        # 添加水印
        watermarked_img = add_watermark(img, watermark_text)
        
        # 将水印图像转换为PDF页面
        img_bytes = io.BytesIO()
        watermarked_img.save(img_bytes, format="PDF")
        img_pdf = fitz.open("pdf", img_bytes.getvalue())
        
        # 将页面插入到新的PDF文档中
        image_pdf_document.insert_pdf(img_pdf)
    
    # 保存新的PDF文件
    image_pdf_document.save(output_pdf_path)
    image_pdf_document.close()
    pdf_document.close()

def select_files_and_watermark():
    """
    通过GUI选择文件并输入水印内容
    """
    # 初始化Tkinter
    root = Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 选择多个PDF文件
    file_paths = filedialog.askopenfilenames(
        title="选择PDF文件",
        filetypes=[("PDF文件", "*.pdf")]
    )
    if not file_paths:
        messagebox.showinfo("提示", "未选择文件！")
        return
    
    # 输入水印内容
    watermark_text = simpledialog.askstring("输入水印内容", "请输入水印文本：")
    if not watermark_text:
        messagebox.showinfo("提示", "未输入水印内容！")
        return
    
    # 处理每个文件
    for file_path in file_paths:
        # 获取原文件目录和文件名
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_base_name, file_ext = os.path.splitext(file_name)
        
        # 生成新文件名（原文件名 + "_"）
        new_file_name = f"{file_base_name}_{file_ext}"
        output_pdf_path = os.path.join(file_dir, new_file_name)
        
        try:
            pdf_to_image_pdf(file_path, output_pdf_path, watermark_text)
            print(f"处理完成：{file_name} -> {new_file_name}")
        except Exception as e:
            print(f"处理失败：{file_name}，错误：{e}")
    
    messagebox.showinfo("完成", "所有文件处理完成！")

# 运行程序
if __name__ == "__main__":
    select_files_and_watermark()