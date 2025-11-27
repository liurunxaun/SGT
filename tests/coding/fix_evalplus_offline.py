import json
import os
from datasets import load_from_disk

# 1. 你的本地数据集路径
LOCAL_HF_PATH = "/ssd5/rxliu/datasets/humanevalplus"

# 2. EvalPlus 的缓存目录 (通常在 ~/.cache/evalplus)
CACHE_DIR = os.path.expanduser("~/.cache/evalplus")

# 3. 目标文件名
# 根据你的报错 URL: .../v0.1.10/HumanEvalPlus.jsonl.gz
# EvalPlus 代码通常会把解压后的文件命名为 HumanEvalPlus-v0.1.10.jsonl
TARGET_FILENAME = "HumanEvalPlus-v0.1.10.jsonl"
TARGET_PATH = os.path.join(CACHE_DIR, TARGET_FILENAME)

def main():
    print(f"Checking local dataset at: {LOCAL_HF_PATH}")
    if not os.path.exists(LOCAL_HF_PATH):
        print("Error: Local dataset path not found!")
        return

    # 加载本地数据集
    print("Loading HuggingFace dataset...")
    ds = load_from_disk(LOCAL_HF_PATH)
    
    # HumanEvalPlus 只有 'test' split
    if 'test' not in ds:
        print("Error: Dataset does not contain 'test' split.")
        return
    
    test_data = ds['test']
    
    # 创建缓存目录
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    print(f"Converting and writing to {TARGET_PATH} ...")
    
    with open(TARGET_PATH, "w", encoding="utf-8") as f:
        for item in test_data:
            # 将 dataset item 转换为字典并写入 jsonl
            # item 包含 task_id, prompt, canonical_solution, test, entry_point 等字段
            # 这些正是 EvalPlus 需要的
            json_str = json.dumps(item, ensure_ascii=False)
            f.write(json_str + "\n")
            
    print("✅ Success! Ground truth file created manually.")
    print("You can now run the evaluate command again.")

if __name__ == "__main__":
    main()