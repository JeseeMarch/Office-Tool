import os
import traceback
from tkinter import Tk, filedialog
from PyPDF2 import PdfWriter
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF

def add_watermark_to_image(image, watermark_text="隐形水印", opacity=5):
    """
    在图像上添加低透明度水印
    :param image: PIL 图像对象
    :param watermark_text: 水印文本
    :param opacity: 水印透明度，0-255
    :return: 添加水印后的图像
    """
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark)

    font_size = max(10, int(image.size[0] // 20))
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    text_width = int(draw.textlength(watermark_text, font=font)) if hasattr(draw, "textlength") else int(draw.textsize(watermark_text, font=font)[0])
    text_height = int(font_size)

    for x in range(0, int(image.size[0]), text_width + 50):
        for y in range(0, int(image.size[1]), text_height + 50):
            draw.text((x, y), watermark_text, fill=(0, 0, 0, opacity), font=font)

    return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")

def convert_pdf_to_image_pdf(input_file):
    try:
        print(f"已选择文件：{input_file}")

        # 设置输出文件路径
        output_file = os.path.splitext(input_file)[0] + "_.pdf"
        print(f"输出文件将保存为：{output_file}")

        # 创建 PyPDF2 Writer 对象
        pdf_writer = PdfWriter()

        # 使用 PyMuPDF 处理 PDF 文件
        doc = fitz.open(input_file)
        print("开始处理 PDF 文件...")
        try:
            zoom_x = 150 / 72
            zoom_y = 150 / 72
            matrix = fitz.Matrix(zoom_x, zoom_y)

            for page_num in range(len(doc)):
                try:
                    print(f"处理页面 {page_num + 1}...")
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(matrix=matrix)

                    img = Image.frombytes("RGB", [int(pix.width), int(pix.height)], pix.samples)
                    img_with_watermark = add_watermark_to_image(img)

                    temp_img_path = f"temp_page_{page_num + 1}.pdf"
                    img_with_watermark.save(temp_img_path, "PDF")

                    with open(temp_img_path, "rb") as temp_pdf:
                        pdf_writer.append(temp_pdf)

                    os.remove(temp_img_path)
                    print(f"页面 {page_num + 1} 已处理完成。")
                except Exception as page_error:
                    print(f"处理页面 {page_num + 1} 时发生错误：{page_error}")
                    traceback.print_exc()

            # 将图像型 PDF 写入输出文件
            with open(output_file, "wb") as output_pdf:
                pdf_writer.write(output_pdf)

            print(f"转换完成！输出文件为：{output_file}")

        except Exception as e:
            print(f"处理 PDF 时发生错误：{e}")
            traceback.print_exc()

        finally:
            doc.close()

        print("PDF 处理已完成。")

    except Exception as e:
        print(f"程序运行时发生错误：{e}")
        traceback.print_exc()

def batch_convert_pdfs():
    try:
        # 初始化 Tkinter
        print("初始化文件选择对话框...")
        Tk().withdraw()

        # 弹出文件选择对话框，支持多选
        input_files = filedialog.askopenfilenames(
            title="选择PDF文件",
            filetypes=[("PDF文件", "*.pdf")]
        )

        if not input_files:
            print("未选择文件，程序退出。")
            return

        print(f"选择了 {len(input_files)} 个文件进行处理。")

        for input_file in input_files:
            print(f"开始处理文件：{input_file}")
            convert_pdf_to_image_pdf(input_file)

        print("所有文件处理完成！")

    except Exception as e:
        print(f"批量处理时发生错误：{e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("程序启动...")
    batch_convert_pdfs()
    print("程序结束。")
