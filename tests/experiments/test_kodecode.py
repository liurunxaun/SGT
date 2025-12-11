from datasets import load_dataset
import json

# 1. 加载轻量版 KodCode 数据集（只取前几条，不用全下）
# 如果网络不好，可以尝试加参数 trust_remote_code=True
print("正在加载 KodCode 数据集...")
dataset = load_dataset("KodCode/KodCode-Light-RL-10K", split="train", streaming=True)

# 2. 取出第一条数据来看看
iterator = iter(dataset)
sample = next(iterator)

print("="*50)
print("🔍 字段列表:", sample.keys())
print("="*50)

# 3. 打印核心字段：Prompt (题目)
print("\n[Input / Prompt 题目描述]:")
print(sample.get('prompt', sample.get('question', '字段没找到'))) 

# 4. 打印核心字段：Test Cases (测试用例/验证代码)
# 这是决定我们 reward 函数怎么写的关键！
print("\n[Test / Verification 验证代码]:")
print(sample.get('test', sample.get('verification_info', '字段没找到')))

print("="*50)