import pandas as pd

# 读取 parquet 文件
path = "/ssd5/rxliu/datasets/gsm8k/main/train-00000-of-00001.parquet"
df = pd.read_parquet(path)

# 查看行数
print("样本数：", len(df))

# 查看字段名
print("字段名：", df.columns.tolist())

# 可选：查看前几行数据
print(df.head())
