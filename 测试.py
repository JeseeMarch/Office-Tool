import os

folder_path = r"D:/excel"  # 修改为实际路径
file2 = os.path.join(folder_path, "excel2.xlsx")

if not os.path.exists(file2):
    print(f"❌ 错误：文件 {file2} 不存在，请检查路径是否正确！")
else:
    print(f"✅ 找到文件：{file2}")

