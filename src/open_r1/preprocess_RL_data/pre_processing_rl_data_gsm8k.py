# ------------------------------------------------------------
# 数据处理说明（GSM8K 数据集）
# 本脚本用于对原始 GSM8K 数据集进行以下处理：
# 1. 将 question 字段重命名为 problem
# 2. answer 字段按 "…… #### 答案" 拆分为：
#       - solving_process
#       - solution
# 3. 添加 id 字段（从 0 开始）和 source 字段（值为 'gsm8k'）
# 4. 按统一顺序排列字段：
#       ['id', 'problem', 'solving_process', 'solution', 'source']
# 5. question 字段名称改为 problem
# ------------------------------------------------------------

import os
import re
import pandas as pd

# 输入路径
src_path = "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet"

# 输出目录
dst_dir = "/ssd5/rxliu/datasets/gsm8k_processed"
os.makedirs(dst_dir, exist_ok=True)

# 输出路径
dst_path = os.path.join(dst_dir, "test-00000-of-00001.parquet")

# 读取 parquet
df = pd.read_parquet(src_path)

# 字段重命名
df = df.rename(columns={"question": "problem"})

# 拆分 answer 字段
def split_answer(text):
    match = re.search(r"^(.*)####\s*(.*)$", text, flags=re.DOTALL)
    if match:
        solving_process = match.group(1).strip()
        solution = match.group(2).strip()
    else:
        solving_process = None
        solution = text.strip()
    return solving_process, solution

df["solving_process"], df["solution"] = zip(*df["answer"].map(split_answer))

# 删除原 answer
df = df.drop(columns=["answer"])

# 添加 id、source
df["id"] = range(len(df))
df["source"] = "gsm8k"

# ⚠️ 设置字段顺序
df = df[["id", "problem", "solving_process", "solution", "source"]]

# 保存
df.to_parquet(dst_path, index=False)

print("处理完成，已保存到：", dst_path)
print("字段顺序：", df.columns.tolist())