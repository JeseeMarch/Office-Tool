import os
import tkinter as tk
from tkinter import filedialog, messagebox

entry_directory = None
entry_old = None
entry_new = None

def select_directory():
    """弹出文件夹选择对话框"""
    directory = filedialog.askdirectory()
    if directory:
        entry_directory.delete(0, tk.END)
        entry_directory.insert(0, directory)

def batch_rename_files():
    """执行批量重命名"""
    directory = entry_directory.get()
    old_str = entry_old.get()
    new_str = entry_new.get()

    if not directory or not old_str or not new_str:
        messagebox.showwarning("输入错误", "请填写完整信息！")
        return

    renamed_count = 0
    for root, _, files in os.walk(directory):
        for filename in files:
            if old_str in filename:
                new_filename = filename.replace(old_str, new_str)
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, new_filename)
                os.rename(old_path, new_path)
                renamed_count += 1

    messagebox.showinfo("完成", f"重命名完成，共修改 {renamed_count} 个文件")

def run_batch_rename_filenames():
    global entry_directory, entry_old, entry_new

    root = tk.Tk()
    root.title("批量文件名替换")

    tk.Label(root, text="选择文件夹:").grid(row=0, column=0, padx=10, pady=5)
    entry_directory = tk.Entry(root, width=40)
    entry_directory.grid(row=0, column=1, padx=10, pady=5)
    btn_select = tk.Button(root, text="浏览", command=select_directory)
    btn_select.grid(row=0, column=2, padx=10, pady=5)

    tk.Label(root, text="原文件名包含:").grid(row=1, column=0, padx=10, pady=5)
    entry_old = tk.Entry(root, width=30)
    entry_old.grid(row=1, column=1, padx=10, pady=5)

    tk.Label(root, text="新文件名替换为:").grid(row=2, column=0, padx=10, pady=5)
    entry_new = tk.Entry(root, width=30)
    entry_new.grid(row=2, column=1, padx=10, pady=5)

    btn_rename = tk.Button(root, text="执行重命名", command=batch_rename_files)
    btn_rename.grid(row=3, column=0, columnspan=3, pady=10)

    root.mainloop()


if __name__ == "__main__":
    run_batch_rename_filenames()
