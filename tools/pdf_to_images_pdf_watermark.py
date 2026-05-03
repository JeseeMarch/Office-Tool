import os
import traceback
from tkinter import Tk, filedialog, simpledialog
from PIL import Image, ImageDraw, ImageFont
import fitz  # PyMuPDF

def add_watermark_to_image(image, watermark_text="隐形水印", font_size=72, opacity=120, angle=45):
    """
    在图像上添加低透明度水印
    :param image: PIL 图像对象
    :param watermark_text: 水印文本
    :param font_size: 字体大小
    :param opacity: 水印透明度（0-255）
    :param angle: 水印旋转角度
    :return: 添加水印后的图像
    """
    watermark = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(watermark)

    try:
        font = ImageFont.truetype("simsun.ttc", font_size)
    except IOError:
        print("未找到宋体字体，使用默认字体代替。")
        font = ImageFont.load_default()

    # 获取水印文字尺寸
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), watermark_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        # 使用 font.getsize 作为备用
        text_width, text_height = font.getsize(watermark_text)

    # 创建单个水印的透明图层
    single_watermark = Image.new("RGBA", (text_width, text_height), (255, 255, 255, 0))
    single_draw = ImageDraw.Draw(single_watermark)
    single_draw.text((0, 0), watermark_text, fill=(0, 0, 0, opacity), font=font)

    # 旋转水印
    rotated_watermark = single_watermark.rotate(angle, expand=True)

    # 平铺水印
    for x in range(0, image.size[0], rotated_watermark.size[0] * 2):
        for y in range(0, image.size[1], rotated_watermark.size[1] * 2):
            watermark.paste(rotated_watermark, (x, y), rotated_watermark)

    return Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")


def convert_pdf_to_image_pdf(input_file, watermark_text):
    try:
        print(f"已选择文件：{input_file}")

        output_file = os.path.splitext(input_file)[0] + "_.pdf"
        print(f"输出文件将保存为：{output_file}")

        doc = fitz.open()
        input_pdf = fitz.open(input_file)
        zoom_x = 150 / 72
        zoom_y = 150 / 72
        matrix = fitz.Matrix(zoom_x, zoom_y)

        for page_num in range(len(input_pdf)):
            try:
                print(f"处理页面 {page_num + 1}...")
                page = input_pdf.load_page(page_num)
                pix = page.get_pixmap(matrix=matrix)

                img = Image.frombytes("RGB", [int(pix.width), int(pix.height)], pix.samples)
                img_with_watermark = add_watermark_to_image(img, watermark_text)

                temp_img_path = f"temp_page_{page_num + 1}.png"
                img_with_watermark.save(temp_img_path, "PNG")

                img_doc = fitz.open(temp_img_path)
                pdf_bytes = img_doc.convert_to_pdf()
                img_doc.close()

                img_pdf = fitz.open("pdf", pdf_bytes)
                doc.insert_pdf(img_pdf)

                os.remove(temp_img_path)
                print(f"页面 {page_num + 1} 已处理完成。")
            except Exception as e:
                print(f"处理页面 {page_num + 1} 时发生错误：{e}")
                traceback.print_exc()

        if len(doc) == 0:
            raise ValueError("未成功处理任何页面，输出文件为空。")

        doc.save(output_file)
        doc.close()
        input_pdf.close()

        print(f"转换完成！输出文件为：{output_file}")
    except Exception as e:
        print(f"程序运行时发生错误：{e}")
        traceback.print_exc()

def batch_convert_pdfs():
    try:
        print("初始化文件选择对话框...")
        Tk().withdraw()

        input_files = filedialog.askopenfilenames(
            title="选择PDF文件",
            filetypes=[("PDF文件", "*.pdf")]
        )

        if not input_files:
            print("未选择文件，程序退出。")
            return

        # 输入水印内容
        watermark_text = simpledialog.askstring("输入水印内容", "请输入水印文字：")
        if not watermark_text:
            print("水印内容不能为空，程序退出。")
            return

        print(f"选择了 {len(input_files)} 个文件进行处理。")

        for input_file in input_files:
            print(f"开始处理文件：{input_file}")
            convert_pdf_to_image_pdf(input_file, watermark_text)

        print("所有文件处理完成！")
    except Exception as e:
        print(f"批量处理时发生错误：{e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("程序启动...")
    batch_convert_pdfs()
    print("程序结束。")
