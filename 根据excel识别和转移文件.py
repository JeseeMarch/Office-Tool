import os
import shutil
import pandas as pd

# === 配置区 ===
excel_path = r"D:\OneDrive\a\bbb.xlsx"
word_root_dir = r"D:\OneDrive\a"
output_dir = r"D:\OneDrive\c"

# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

# 读取 Excel，提取第77到152号的姓名和编号
data = pd.read_excel(excel_path, header=None).iloc[3:, [0, 2]]
data.columns = ["序号", "姓名"]
data = data[pd.to_numeric(data["序号"], errors="coerce").notnull()]
data["序号"] = data["序号"].astype(int)
selected = data[(data["序号"] >= 0) & (data["序号"] <= 600)].copy()

# 遍历文件夹，查找并复制匹配的文件（不限类型）
match_count = 0
for root, dirs, files in os.walk(word_root_dir):
    for file in files:
        file_path = os.path.join(root, file)
        if os.path.isfile(file_path):
            for _, row in selected.iterrows():
                name = str(row["姓名"])
                number = f"{row['序号']:03d}"
                if name in file:
                    new_filename = f"{number}_{name}_{file}"
                    new_path = os.path.join(output_dir, new_filename)
                    shutil.copy2(file_path, new_path)
                    print(f"已复制：{new_filename}")
                    match_count += 1
                    break  # 一旦匹配到就不再继续

print(f"\n✅ 共复制匹配文件 {match_count} 个到：{output_dir}")
