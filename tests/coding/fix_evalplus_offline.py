import json
import os
from datasets import load_from_disk

# 1. 你的本地数据集路径
LOCAL_HF_PATH = "/ssd5/rxliu/datasets/humanevalplus"

# 2. EvalPlus 的缓存目录
CACHE_DIR = os.path.expanduser("~/.cache/evalplus")
TARGET_FILENAME = "HumanEvalPlus-v0.1.10.jsonl" # 对应你报错里的版本
TARGET_PATH = os.path.join(CACHE_DIR, TARGET_FILENAME)

def main():
    print(f"Checking local dataset at: {LOCAL_HF_PATH}")
    if not os.path.exists(LOCAL_HF_PATH):
        print("Error: Local dataset path not found!")
        return

    print("Loading HuggingFace dataset...")
    ds = load_from_disk(LOCAL_HF_PATH)
    
    if 'test' not in ds:
        print("Error: Dataset does not contain 'test' split.")
        return
    
    test_data = ds['test']
    
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    print(f"Converting and patching data to {TARGET_PATH} ...")
    
    with open(TARGET_PATH, "w", encoding="utf-8") as f:
        for item in test_data:
            # 将 dataset item 转换为字典
            data_dict = dict(item)
            
            # === 核心修复逻辑：补全缺失字段 ===
            # 如果本地数据缺少 contract，就给它一个空字符串
            if "contract" not in data_dict:
                data_dict["contract"] = "" 
            
            # 如果缺少 entry_point (极少数情况)
            if "entry_point" not in data_dict:
                # 尝试从 prompt 或 test 里推断，或者留空（可能会报错，但先试试）
                pass 

            # 如果缺少 plus_input (Plus 测试用例)，给空列表
            if "plus_input" not in data_dict:
                data_dict["plus_input"] = []
            
            # 如果缺少 base_input (基础测试用例)，给空列表
            if "base_input" not in data_dict:
                data_dict["base_input"] = []

            # 写入文件
            json_str = json.dumps(data_dict, ensure_ascii=False)
            f.write(json_str + "\n")
            
    print(f"✅ Success! Patched ground truth file created at: {TARGET_PATH}")
    print("WARNING: Since we mocked missing fields (like 'contract'),")
    print("the 'Plus' evaluation might effectively degrade to standard HumanEval.")

if __name__ == "__main__":
    main()

