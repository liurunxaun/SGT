import os
from datasets import load_dataset, Dataset

# 1. 定义文件路径和常量
FILE_PATH = "/ssd5/rxliu/datasets/RL-Data/merged_olympiads_gsm8k_rl.parquet"
OUTPUT_DIR = os.path.dirname(FILE_PATH)
MAX_RECORDS = 10000  # 前 10000 条
SHUFFLED_FULL_NAME = "merged_olympiads_gsm8k_rl_shuffled_full.parquet"
SHUFFLED_10K_NAME = "merged_olympiads_gsm8k_rl_shuffled_10k.parquet"
SHUFFLED_REST_NAME = "merged_olympiads_gsm8k_rl_shuffled_rest.parquet"

# 确保目标路径存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# 2. 加载数据集
print("--- 1. 正在加载数据集... ---")
try:
    # load_dataset('parquet', data_files=FILE_PATH, split='train')
    # 使用 split='train' 是为了获取一个可操作的 Dataset 对象
    dataset = load_dataset('parquet', data_files=FILE_PATH, split='train')
except Exception as e:
    print(f"加载数据集失败，请检查文件路径和格式: {e}")
    exit()

TOTAL_SIZE = len(dataset)
print(f"原始数据集大小: {TOTAL_SIZE} 条记录")

# 3. 打乱数据顺序
# seed 参数确保每次打乱的结果是确定的
print("--- 2. 正在打乱数据顺序 (使用种子 42)... ---")
shuffled_dataset = dataset.shuffle(seed=42)

# 4. 保存完整的打乱后的数据集
full_output_path = os.path.join(OUTPUT_DIR, SHUFFLED_FULL_NAME)
print(f"--- 3. 正在保存完整打乱后的文件到: {full_output_path} ---")
shuffled_dataset.to_parquet(full_output_path)
print(f"文件 '{SHUFFLED_FULL_NAME}' 保存完毕。")

# 5. 截取前 10000 条记录
print(f"--- 4. 正在截取前 {MAX_RECORDS} 条记录... ---")
if TOTAL_SIZE > MAX_RECORDS:
    # 截取前 10,000 条
    subset_10k_dataset = shuffled_dataset.select(range(MAX_RECORDS))
    
    # 截取剩余的数据 (从第 10,000 条记录开始，即索引 10000)
    subset_rest_dataset = shuffled_dataset.select(range(MAX_RECORDS, TOTAL_SIZE))
    
    print(f"10k 文件大小: {len(subset_10k_dataset)} 条记录")
    print(f"剩余文件大小: {len(subset_rest_dataset)} 条记录")
    
    # 6. 保存截取后的 10k 数据集
    subset_10k_output_path = os.path.join(OUTPUT_DIR, SHUFFLED_10K_NAME)
    print(f"--- 5. 正在保存 10k 文件到: {subset_10k_output_path} ---")
    subset_10k_dataset.to_parquet(subset_10k_output_path)
    print(f"文件 '{SHUFFLED_10K_NAME}' 保存完毕。")

    # 7. 保存剩余的数据集
    subset_rest_output_path = os.path.join(OUTPUT_DIR, SHUFFLED_REST_NAME)
    print(f"--- 6. 正在保存剩余文件到: {subset_rest_output_path} ---")
    subset_rest_dataset.to_parquet(subset_rest_output_path)
    print(f"文件 '{SHUFFLED_REST_NAME}' 保存完毕。")

else:
    print(f"警告: 数据集总数 ({TOTAL_SIZE}) 小于 {MAX_RECORDS}，无法分割。只保存了完整打乱文件。")

print("\n--- 所有操作完成！---")