import os

def touch_file(file_path):
    """
    尝试读取文件第一个字节，触发 OneDrive 下载
    """
    try:
        with open(file_path, 'rb') as f:
            f.read(1)           # 只读一个字节就够了
        print(f"已触发下载: {file_path}")
    except FileNotFoundError:
        print(f"文件尚未下载（占位符）: {file_path}")
    except PermissionError:
        print(f"权限问题，跳过: {file_path}")
    except Exception as e:
        print(f"访问失败: {file_path} → {e}")

def download_onedrive_files(root_folder):
    if not os.path.isdir(root_folder):
        print("错误：这不是一个有效的文件夹")
        return

    print(f"\n开始扫描文件夹：{root_folder}")
    print("正在遍历文件...（可能需要几秒到几分钟，取决于文件数量）\n")

    count = 0
    triggered = 0

    for root, dirs, files in os.walk(root_folder):
        for file in files:
            file_path = os.path.join(root, file)
            count += 1
            # 可以在这里加过滤，例如跳过某些文件类型
            # if file.lower().endswith(('.url', '.lnk', 'thumbs.db')): continue

            touch_file(file_path)
            if "已触发下载" in "已触发下载":  # 简单计数，实际可优化
                triggered += 1

            # 每处理 200 个文件给一次反馈（避免太安静）
            if count % 200 == 0:
                print(f"已处理 {count} 个文件...")

    print(f"\n处理完成！")
    print(f"总文件数：{count}")
    print(f"成功触发下载的文件：{triggered}")
    print(f"其他文件可能是已下载、权限问题或占位符")

def main():
    print("=== OneDrive 文件按需下载触发工具 ===\n")
    print("操作步骤：")
    print("1. 在文件资源管理器中找到你的 OneDrive 文件夹")
    print("2. 右键地址栏 → 复制地址")
    print("   例如：D:\\Jesse's-OneDrive\\OneDrive")
    print("3. 把路径粘贴到下面，然后按 Enter\n")

    folder = input("请输入 OneDrive 文件夹完整路径：").strip()

    if not folder:
        print("未输入路径，程序退出。")
        return

    # 简单去掉可能的引号
    folder = folder.strip('"').strip("'")

    if not os.path.exists(folder):
        print("路径不存在，请检查后重试")
        return

    if not os.path.isdir(folder):
        print("你输入的不是文件夹路径，请重新运行并输入文件夹")
        return

    download_onedrive_files(folder)

    input("\n按 Enter 键退出...")

if __name__ == "__main__":
    main()