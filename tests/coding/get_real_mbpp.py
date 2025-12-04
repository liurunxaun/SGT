import json
import os
import pandas as pd
from datasets import load_dataset

# 输出路径
output_file = "/ssd5/rxliu/datasets/mbppplus/mbpp_sanitized_correct.jsonl"
os.makedirs(os.path.dirname(output_file), exist_ok=True)

print("🚀 正在从 Hugging Face 加载标准的 MBPP (Sanitized) 数据集...")

try:
    # 1. 加载官方 mbpp 数据集 (sanitized 分支对应 EvalPlus 评测的标准版)
    # trust_remote_code=True 是必须的，因为 mbpp 加载脚本需要执行代码
    dataset = load_dataset("mbpp", "sanitized", split="test", trust_remote_code=True)
    
    print(f"✅ 数据集加载成功，共 {len(dataset)} 条题目 (标准应为 397-399 条)")

    # 2. 转换为 EvalPlus 需要的 JSONL 格式
    # EvalPlus 需要: {"task_id": 11, "prompt": "..."}
    count = 0
    with open(output_file, "w", encoding="utf-8") as f:
        for item in dataset:
            # 提取 task_id (MBPP 是整数)
            task_id = item["task_id"]
            
            # 提取 prompt (MBPP 数据集里的 prompt 字段通常只是一句话描述)
            # 为了更好的生成效果，通常会加上函数签名，或者只用 description
            # 这里我们使用 raw prompt，模型比较强的话可以自己补全
            prompt = item["prompt"]
            
            # 有些模型需要 text 字段，有些需要 prompt
            # 我们保留 prompt，同时在 prompt 里带上部分 code（如果有）
            # 标准做法：直接用 prompt 字段
            
            sample = {
                "task_id": str(task_id), # 转为字符串以防万一
                "prompt": prompt,
                "code": item["code"] # 保留参考代码以备不时之需
            }
            
            f.write(json.dumps(sample) + "\n")
            count += 1

    print(f"✅ 文件转换完成！已保存 {count} 条数据。")
    print(f"📂 文件路径: {output_file}")
    print("\n👉 下一步：请使用这个文件作为 DATASET_PATH 运行你的 test_mbpp_base.py")

except Exception as e:
    print(f"\n❌ 加载失败: {e}")
    print("请确保网络通畅（可以访问 HuggingFace），或者尝试手动下载。")