import pandas as pd
import os
from sklearn.model_selection import train_test_split

# 1. 配置路径
input_file = "/ssd5/rxliu/datasets/RL-Data/shuffled_10k/merged_olympiads_gsm8k_rl_shuffled_10k.parquet"
output_dir = "/ssd5/rxliu/datasets/RL-Data/shuffled_10k_train_test"

# 2. 确保输出目录存在
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    print(f"创建目录: {output_dir}")

# 3. 读取数据
print(f"正在读取文件: {input_file} ...")
df = pd.read_parquet(input_file)
total_rows = len(df)
print(f"原始数据行数: {total_rows}")

# 4. 切分数据 (9:1)
# random_state固定为42以保证复现性，如果你确信源文件已经shuffle得很好，shuffle=False也可以，但通常建议True
train_df, test_df = train_test_split(df, test_size=0.1, random_state=42, shuffle=True)

# 5. 保存文件
train_output_path = os.path.join(output_dir, "train.parquet")
test_output_path = os.path.join(output_dir, "test.parquet")

train_df.to_parquet(train_output_path, index=False)
test_df.to_parquet(test_output_path, index=False)

# 6. 输出结果统计
print("-" * 30)
print("✅ 处理完成！")
print(f"训练集保存至: {train_output_path} (行数: {len(train_df)})")
print(f"测试集保存至: {test_output_path} (行数: {len(test_df)})")
print("-" * 30)