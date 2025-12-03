import os
from datasets import load_from_disk

# 1. 你的原始数据目录
data_dir = "/ssd5/rxliu/datasets/humanevalplus"

# 2. 加载数据集
print(f"Loading from {data_dir}...")
dataset = load_from_disk(data_dir)

# 3. 提取 test集 并保存为 parquet 文件
# 通常这个格式下，数据都在 'test' 这个 key 里
output_file = os.path.join(data_dir, "humaneval_test.parquet")
dataset["test"].to_parquet(output_file)

print(f"Conversion complete! New file saved at: {output_file}")
