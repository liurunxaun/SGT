import pandas as pd
import os

# 1. 设置文件路径
input_path = "/ssd5/rxliu/datasets/DeepScaleR/0000.parquet"
output_dir = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR"  # 保存到同一目录下，或者你可以修改这里

# 2. 读取 Parquet 文件
df = pd.read_parquet(input_path)
print(f"原始数据总行数: {len(df)}")

# 3. 切分数据 (前100条 vs 剩余部分)
# 注意：这里假设数据是有序的或者你不需要随机打乱。
# 如果需要随机抽取前100条作为测试集，请先 df.sample(frac=1) 打乱
df_test = df.iloc[:100]
df_train = df.iloc[100:]

# 4. 保存文件
test_path = os.path.join(output_dir, "test.parquet")
train_path = os.path.join(output_dir, "train.parquet")

df_test.to_parquet(test_path, index=False)
df_train.to_parquet(train_path, index=False)

print(f"处理完成！")
print(f"Test集 ({len(df_test)}条) 已保存至: {test_path}")
print(f"Train集 ({len(df_train)}条) 已保存至: {train_path}")