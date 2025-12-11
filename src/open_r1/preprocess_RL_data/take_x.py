import pandas as pd
import os
import shutil

# 文件路径
file_path = "/ssd5/rxliu/datasets/DeepScaleR/0000.parquet"
output_put_path = "/ssd5/rxliu/datasets/DeepScaleR/0000.parquet"
x = 100

# 读取 Parquet 文件
df = pd.read_parquet(file_path)
print(f"原始数据行数: {len(df)}")

# 截取前 x 条
df_x = df.head(x)
print(f"截取后数据行数: {len(df_x)}")

# 保存
df_x.to_parquet(output_put_path)
print(f"🎉 修改完成！文件已保存至: {output_put_path}")