# ------------------------------------------------------------
# 数据处理说明（Olympiads + GSM8K 合并）
#
# 本脚本将两个已处理的数据集合并成一个统一数据集：
#   1. /ssd5/rxliu/datasets/Olympiads_processed/train-00000-of-00001.parquet
#   2. /ssd5/rxliu/datasets/gsm8k_processed/train-00000-of-00001.parquet
#
# 要求：
#   - Olympiads 数据放在前
#   - GSM8K 数据放在后
#   - GSM8K 的 id 需要加上偏移量（Olympiads 数据集长度），避免 id 冲突
#
# 合并输出目录：
#   /ssd5/rxliu/datasets/RL-Data/merged_olympiads_gsm8k_rl.parquet
# ------------------------------------------------------------

import os
import pandas as pd

# 输入路径
olym_path = "/ssd5/rxliu/datasets/Olympiads_processed/train-00000-of-00001.parquet"
gsm_path  = "/ssd5/rxliu/datasets/gsm8k_processed/train-00000-of-00001.parquet"

# 输出目录
dst_dir = "/ssd5/rxliu/datasets/RL-Data"
os.makedirs(dst_dir, exist_ok=True)

# 设置合并后文件路径
dst_path = os.path.join(dst_dir, "merged_olympiads_gsm8k_rl.parquet")

# 读取两个数据集
df_olym = pd.read_parquet(olym_path)
df_gsm = pd.read_parquet(gsm_path)

print("Olympiads 样本数：", len(df_olym))
print("GSM8K 样本数：", len(df_gsm))

# -------------------------------
# 处理 GSM8K id：整体偏移
# -------------------------------
offset = len(df_olym)
df_gsm["id"] = df_gsm["id"] + offset

# 字段顺序检查（确保统一）
cols = ["id", "problem", "solving_process", "solution", "source"]
df_olym = df_olym[cols]
df_gsm = df_gsm[cols]

# -------------------------------
# 合并（Olympiads 在前）
# -------------------------------
df_merged = pd.concat([df_olym, df_gsm], ignore_index=True)

print("合并后总样本数：", len(df_merged))

# 保存合并文件
df_merged.to_parquet(dst_path, index=False)

print(f"合并完成，已保存到：{dst_path}")
