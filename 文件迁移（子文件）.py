import os
import shutil
def copy_specific_files(source_dir, target_dir, file_extension):
    print(f"正在检查源目录: {source_dir}") # 调试信息
    if not os.path.exists(source_dir):
        print("错误：源目录不存在！")
        return

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"创建了目标目录: {target_dir}")

    count = 0
    for root, dirs, files in os.walk(source_dir):
        # 打印当前正在扫描的文件夹，看看程序动没动
        print(f"正在扫描: {root}") 
        for file in files:
            if file.endswith(file_extension):
                # ... 原有的复制逻辑 ...
                count += 1
    
    print(f"任务完成，共复制了 {count} 个文件。")
def copy_specific_files(source_dir, target_dir, file_extension):
    # 创建目标文件夹
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    # 遍历源文件夹及其子文件夹
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(file_extension):
                # 构建源文件的完整路径
                source_file_path = os.path.join(root, file)
                
                # 构建目标文件的完整路径，不保留目录结构
                target_file_path = os.path.join(target_dir, file)
                
                # 如果目标文件夹中已经存在同名文件，可以选择重命名或覆盖
                if os.path.exists(target_file_path):
                    base, extension = os.path.splitext(file)
                    counter = 1
                    new_file_name = f"{base}_{counter}{extension}"
                    new_target_file_path = os.path.join(target_dir, new_file_name)
                    while os.path.exists(new_target_file_path):
                        counter += 1
                        new_file_name = f"{base}_{counter}{extension}"
                        new_target_file_path = os.path.join(target_dir, new_file_name)
                    target_file_path = new_target_file_path
                
                # 复制文件到目标路径
                shutil.copy2(source_file_path, target_file_path)
                print(f"复制文件: {source_file_path} 到 {target_file_path}")

# 示例用法



source_directory = r'D:\Pharmacy'
target_directory = r'D:\a'
file_ext = '.pdf'  # 指定文件类型，例如 '.txt'

copy_specific_files(source_directory, target_directory, file_ext)