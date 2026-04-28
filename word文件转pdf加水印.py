import os
from tkinter import Tk, filedialog, simpledialog
from pdf2image import convert_from_path
from PIL import Image, ImageDraw, ImageFont
from docx2pdf import convert
from time import sleep

def select_files():
    """弹出文件选择对话框，让用户选择多个 Word 文件"""
    Tk().withdraw()  # 隐藏主窗口
    files = filedialog.askopenfilenames(
        title="选择 Word 文件",
        filetypes=[("Word 文件", "*.docx")],
    )
    return files

def get_watermark_settings():
    """弹出对话框，让用户输入水印文本"""
    Tk().withdraw()  # 隐藏主窗口
    text = simpledialog.askstring("水印文本", "请输入水印内容：", initialvalue="水印")
    if not text:
        raise ValueError("未输入水印内容，程序终止。")
    return text

def add_watermark_to_image(image, watermark_text, opacity=0.3, angle=-45):
    """
    在图片上添加水印。
    :param image: PIL 图像对象
    :param watermark_text: 水印文本
    :param opacity: 水印透明度
    :param angle: 水印旋转角度
    """
    width, height = image.size

    # 创建透明图层
    transparent_layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(transparent_layer)

    try:
        font = ImageFont.truetype("simsun.ttc", 144)  # 使用宋体字体
    except IOError:
        raise RuntimeError("未找到宋体字体，请确保系统安装了 simsun.ttc。")

    text_width = font.getbbox(watermark_text)[2]
    text_height = font.getbbox(watermark_text)[3]

    # 水平和垂直间距
    step_x = text_width * 2
    step_y = text_height * 3

    # 创建水印图层
    watermark_layer = Image.new("RGBA", (width * 2, height * 2), (255, 255, 255, 0))
    watermark_draw = ImageDraw.Draw(watermark_layer)

    for y in range(0, height * 2, step_y):
        for x in range(0, width * 2, step_x):
            watermark_draw.text(
                (x, y),
                watermark_text,
                fill=(0, 0, 0, int(255 * opacity)),
                font=font,
            )

    rotated_watermark = watermark_layer.rotate(angle, expand=True)

    # 合成水印
    x_offset = (width - rotated_watermark.width) // 2
    y_offset = (height - rotated_watermark.height) // 2
    transparent_layer.paste(rotated_watermark, (x_offset, y_offset), rotated_watermark)

    return Image.alpha_composite(image.convert("RGBA"), transparent_layer).convert("RGB")

def safe_convert(input_file, output_file, retry=3):
    """安全地将 Word 转为 PDF，支持重试"""
    for attempt in range(retry):
        try:
            convert(input_file, output_file)
            return True
        except Exception as e:
            print(f"尝试 {attempt + 1} 次失败：{e}")
            sleep(1)  # 等待后重试
    return False

def word_to_image_pdf(input_file, watermark_text):
    """
    将 Word 文件转换为图片型 PDF 文件并添加水印。
    :param input_file: 输入 Word 文件路径
    :param watermark_text: 水印文本
    """
    try:
        if not input_file:
            return False

        folder = os.path.dirname(input_file)
        base_name = os.path.basename(input_file)
        name, _ = os.path.splitext(base_name)

        # 临时文件名确保唯一
        intermediate_pdf = os.path.join(folder, f"{name}_temp_{os.getpid()}.pdf")
        output_pdf = os.path.join(folder, f"{name}.pdf")

        if not safe_convert(input_file, intermediate_pdf):
            raise RuntimeError(f"文件 {input_file} 转换失败。")

        images = convert_from_path(intermediate_pdf)

        watermarked_images = []
        for image in images:
            watermarked_image = add_watermark_to_image(
                image, watermark_text, opacity=0.4, angle=45
            )
            watermarked_images.append(watermarked_image)

        if watermarked_images:
            watermarked_images[0].save(
                output_pdf, save_all=True, append_images=watermarked_images[1:]
            )

        # 删除临时文件
        os.remove(intermediate_pdf)

        print(f"成功转换并添加水印：{output_pdf}")
        return True
    except Exception as e:
        print(f"处理文件 {input_file} 时发生错误：{e}")
        return False

def batch_convert_to_image_pdf():
    """批量处理多个 Word 文件"""
    try:
        files = select_files()
        if not files:
            print("未选择任何文件。")
            return

        watermark_text = get_watermark_settings()

        failed_files = []

        print(f"已选择 {len(files)} 个文件，开始转换...")
        for idx, file in enumerate(files):
            print(f"正在处理文件 {idx + 1}/{len(files)}: {file}")
            success = word_to_image_pdf(file, watermark_text)
            if not success:
                failed_files.append(file)

        if failed_files:
            print("以下文件转换失败：")
            for failed in failed_files:
                print(failed)
        else:
            print("所有文件处理完成。")
    except Exception as e:
        print(f"程序终止：{e}")

if __name__ == "__main__":
    batch_convert_to_image_pdf()
