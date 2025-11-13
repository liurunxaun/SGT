import pandas as pd

path = "/data/home/the/rxliu/projects/open-r1-main/data/GSM8K-pre1000*3-sft-data-parquet/test.parquet"

df = pd.read_parquet(path)

print("样本条数：", len(df))
print("字段名：", df.columns.tolist())
