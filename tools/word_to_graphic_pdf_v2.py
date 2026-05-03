import os
from tkinter import Tk, filedialog
from pdf2image import convert_from_path
from PIL import Image
from docx2pdf import convert

def select_files():
    """弹出文件选择对话框，让用户选择多个文件"""
    Tk().withdraw()  # 隐藏主窗口
    files = filedialog.askopenfilenames(
        title="选择 Word 文件",
        filetypes=[("Word 文件", "*.docx")],
    )
    return files

def word_to_image_pdf(input_file):
    """
    将单个 Word 文件转换为图片型 PDF 文件
    :param input_file: 输入的 Word 文件路径
    """
    try:
        if not input_file:
            return False
        
        # 获取文件夹路径和文件名
        folder = os.path.dirname(input_file)
        base_name = os.path.basename(input_file)
        name, _ = os.path.splitext(base_name)
        
        # 中间 PDF 和输出 PDF 文件路径
        intermediate_pdf = os.path.join(folder, f"{name}_temp.pdf")
        output_pdf = os.path.join(folder, f"{name}_.pdf")
        
        # 将 Word 转换为 PDF
        print(f"正在将 {input_file} 转换为 PDF...")
        convert(input_file, intermediate_pdf)
        
        # 检查中间 PDF 文件是否存在
        if not os.path.exists(intermediate_pdf):
            print(f"中间 PDF 文件 {intermediate_pdf} 未生成。")
            return False
        
        # 将 PDF 每一页转换为图像
        print(f"正在将 PDF 转换为图像...")
        images = convert_from_path(intermediate_pdf)
        
        # 将图像保存为图片型 PDF
        print(f"正在将图像保存为 PDF...")
        images[0].save(output_pdf, save_all=True, append_images=images[1:])
        
        # 删除中间 PDF
        os.remove(intermediate_pdf)
        
        print(f"成功转换：{output_pdf}")
        return True
    except Exception as e:
        print(f"处理文件 {input_file} 时发生错误：{e}")
        return False

def batch_convert_to_image_pdf():
    """批量处理多个 Word 文件"""
    files = select_files()
    if not files:
        print("未选择任何文件。")
        return
    
    print(f"已选择 {len(files)} 个文件，开始转换...")
    for file in files:
        success = word_to_image_pdf(file)
        if not success:
            print(f"文件 {file} 转换失败。")

if __name__ == "__main__":
    batch_convert_to_image_pdf()