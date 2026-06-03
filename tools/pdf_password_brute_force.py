import itertools
from tkinter import Tk, filedialog, messagebox, simpledialog

import PyPDF2

def brute_force_pdf_password(pdf_path, max_length=4):
    """
    Tries to brute-force the password of a PDF by generating all possible combinations
    of lowercase letters and numbers up to a given length.

    :param pdf_path: Path to the password-protected PDF file.
    :param max_length: Maximum length of password to try.
    """
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    try:
        with open(pdf_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)

            if not reader.is_encrypted:
                print("The PDF is not encrypted.")
                return

            print(f"Starting brute force attack (max length: {max_length})...")

            for length in range(1, max_length + 1):
                for password_tuple in itertools.product(chars, repeat=length):
                    password = ''.join(password_tuple)
                    try:
                        if reader.decrypt(password):
                            print(f"Password found: {password}")
                            return password
                    except Exception:
                        pass
            print("Password not found with brute force attack.")
    except FileNotFoundError:
        print(f"Error: The file {pdf_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

def run_pdf_password_brute_force() -> str:
    root = Tk()
    root.withdraw()

    pdf_path = filedialog.askopenfilename(
        title="选择要尝试密码的 PDF",
        filetypes=[("PDF 文件", "*.pdf")],
    )
    if not pdf_path:
        return "已取消：PDF 密码尝试。"

    max_length = simpledialog.askinteger(
        "最大密码长度",
        "请输入最大尝试长度：",
        initialvalue=4,
        minvalue=1,
        maxvalue=8,
    )
    if not max_length:
        return "已取消：PDF 密码尝试。"

    password = brute_force_pdf_password(pdf_path, max_length=max_length)
    if password:
        return f"已找到 PDF 密码：{password}"
    return "未在指定长度内找到密码。"


if __name__ == "__main__":
    run_pdf_password_brute_force()
