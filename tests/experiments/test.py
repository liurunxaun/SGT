print("========begin evaluate========")

print("begin loading transformers")
print()
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import pandas as pd
import re
import requests


def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
    prompt = (
        f"You are a math evaluator. Compare the two answers and respond with exactly "
        f"'correct' or 'incorrect'.\n\n"
        f"Ground truth: {ground_truth}\n"
        f"Model answer: {answer}\n"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": judge_model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    resp = requests.post(api_url, headers=headers, json=data)
    resp.raise_for_status()
    resp_json = resp.json()
    # 假设返回格式类似 OpenAI：resp_json["choices"][0]["message"]["content"]
    verdict = resp_json["choices"][0]["message"]["content"].strip().lower()
    return verdict == "correct"


# 定义超参数
# 模型路径
model_path = "/data/home/the/rxliu/projects/open-r1-main/output/Qwen3-0.6B-GRPO-Olympiads/checkpoint-500"
# 数据集路径
dataset_path = "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet"
# 问题字段名称
question_field = "question"
# 答案字段名称
answer_field = "answer"
# api_url
api_url = "https://ai-yyds.com/v1/chat/completions"
# api key
api_key = "sk-RyIv6tr8xb9AribIAfD9Ab640c2e4fCeBeAa98Cd892f894d"
# 选择LLM Judge的模型
judge_model_name = "gpt-4o-mini"
# 当前测试指标默认为accuracy


# 加载 tokenizer 和模型
print("begin loading model")
print()
tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map="auto",   # 自动放到GPU上
    torch_dtype=torch.bfloat16  # 如果显卡支持BF16
)


correct = 0
total = 0


# 读取数据集
df = pd.read_parquet(dataset_path)
# 遍历每一条样本
for i, row in df.iterrows():
    problem = row[question_field]
    ground_truth = row[answer_field]
    print(f"========question {i}========")
    print(f"question: {problem}")
    print()
    
    # Qwen 是 chat 模型，建议用 chat 模式
    messages = [
        {"role": "system", "content":"solve the math problem"},
        
        {"role": "user", "content": problem}
    ]

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    # 转tensor
    # print("begin loading inputs")
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    # 生成
    # print("begin generate outputs")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=8196,
            do_sample=True,
            temperature=0.7
        )
    # 解码输出
    output = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"output:")
    print(output)
    print()

    # 用正则提取 <answer>...</answer> 中的内容（包括换行）
    match = re.search(r"<answer>([\s\S]*?)</answer>", output)
    if match:
        answer = match.group(1).strip()
    else:
        print("Cannot answer found in the output.")

    # 计算准确率
    total += 1
    try:
        if llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
            correct += 1
            status = "✅"
        else:
            status = "❌"
    except Exception as e:
        print("Judge API error:", e)
        print()
        status = "ERROR"

    print(f"extracted answer: {answer} | ground_truth: {ground_truth} | {status}")
    print()
    print()


accuracy = correct / total if total > 0 else 0
print(f"Accuracy: {accuracy:.4f}")