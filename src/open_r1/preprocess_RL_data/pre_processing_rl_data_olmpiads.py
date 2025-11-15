# ------------------------------------------------------------
# 数据处理说明（Metaskepsis/Olympiads数据集）
# 本脚本用于对原始 Olympiads 数据集的字段进行规范化处理：
# 1. 将原字段 "solution" 重命名为 "solving_process"，用于表示完整推理过程；
# 2. 将原字段 "answer" 重命名为 "solution"，用于表示最终答案；因为open-r1框架强行读取solution字段，他自己提取答案还不准
# 3. 处理后的文件统一保存到：/ssd5/rxliu/datasets/Olympiads_processed/
# 该操作仅修改字段名，不改变数据内容及样本数量。
# ------------------------------------------------------------

import os
import pandas as pd

# 输入文件
src_path = "/ssd5/rxliu/datasets/Olympiads/data/train-00000-of-00001.parquet"

# 输出目录
dst_dir = "/ssd5/rxliu/datasets/Olympiads_processed"
os.makedirs(dst_dir, exist_ok=True)

# 输出文件路径
dst_path = os.path.join(dst_dir, "train-00000-of-00001.parquet")

# 读取 parquet
df = pd.read_parquet(src_path)

print("样本数：", len(df))
print("原字段名：", df.columns.tolist())

# 字段重命名
df = df.rename(columns={
    "solution": "solving_process",
    "answer": "solution"
})

print("修改后字段名：", df.columns.tolist())

# 保存
df.to_parquet(dst_path, index=False)

print(f"处理完成，已保存到：{dst_path}")
