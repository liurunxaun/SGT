import pandas as pd

# 读取处理后的parquet文件
df = pd.read_parquet('/ssd5/rxliu/datasets/rcmu/new_math_data_processed.parquet')

print(f"总数据: {len(df)} 条记录")

# 随机抽取100条作为test
test_df = df.sample(n=100, random_state=42)

# 剩余的作为train
train_df = df.drop(test_df.index)

# 重置索引
train_df = train_df.reset_index(drop=True)
test_df = test_df.reset_index(drop=True)

# 保存
train_path = '/ssd5/rxliu/datasets/rcmu/train.parquet'
test_path = '/ssd5/rxliu/datasets/rcmu/test.parquet'

train_df.to_parquet(train_path, index=False)
test_df.to_parquet(test_path, index=False)

print(f"\nTrain集: {len(train_df)} 条记录")
print(f"Test集: {len(test_df)} 条记录")
print(f"\nTrain文件: {train_path}")
print(f"Test文件: {test_path}")