import pandas as pd

df = pd.read_parquet("/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files/train_part_1_of_4.parquet")

print(f"原始数据行数: {len(df)}")
print(f"Index 范围: {df.index.min()} 到 {df.index.max()}")
print(f"Index 是否连续: {df.index.is_monotonic_increasing and (df.index.max() - df.index.min() + 1 == len(df))}")
print(f"\n前20个 index:")
print(df.index[:20].tolist())