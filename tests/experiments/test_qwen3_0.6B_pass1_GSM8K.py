print("========begin evaluate========")
print()

print("begin loading transformers")
print()
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import pandas as pd
import re
import datetime
import os
from extract_answer_from_output import extract_boxed_content
from llm_judge import llm_judge_via_api


# 定义超参数
# 模型路径
model_path = "/ssd5/rxliu/models/Qwen3-0.6B"
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
# system_prompt
self_prompt = ""
# 保存结果路径
save_dir = "/data/home/the/rxliu/projects/open-r1-main/tests/results"
# 动态生成文件名：模型名 + 数据集名 + 日期
model_name = os.path.basename(model_path)
dataset_name = os.path.basename(os.path.dirname(dataset_path))
date_str = datetime.datetime.now().strftime("%Y%m%d")
save_path = os.path.join(save_dir, f"{model_name}_{dataset_name}_{date_str}.csv")



# 加载 tokenizer 和模型
print("begin loading model")
print()
tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map="auto",   # 自动放到GPU上
    torch_dtype=torch.bfloat16  # 如果显卡支持BF16
)

results = []
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

    messages = [
        {"role": "system", "content": self_prompt},
        
        {"role": "user", "content": problem}
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True # Switches between thinking and non-thinking modes. Default is True.
    )
    model_inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=38912, # 32768或38912
            temperature=0.6,
            top_p=0.95,
            top_k=20,
            do_sample=True
        )
    output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist() 
    # parsing thinking content
    try:
        # rindex finding 151668 (</think>)
        index = len(output_ids) - output_ids[::-1].index(151668)
    except ValueError:
        index = 0

    thinking_content = tokenizer.decode(output_ids[:index], skip_special_tokens=True).strip("\n")
    answer_content = tokenizer.decode(output_ids[index:], skip_special_tokens=True).strip("\n")
    print(f"thinking_content:")
    print()
    print(thinking_content)
    print()
    print(f"answer_content:")
    print()
    print(answer_content)
    print()

    predict_answer = extract_boxed_content(answer_content)
    if not predict_answer:
        predict_answer = ""
        print("Cannot boxed answer found in the output.")
    
    # GSM8K给的answer包括解题过程和最终答案的数字，答案是在####之后，提取出来。如果提取失败的话，还是将原本的answer作为答案交给大模型评委
    match = re.search(r"####\s*([-\d\.]+)", ground_truth)
    if match:
        ground_truth_answer = match.group(1).strip()
    else:
        ground_truth_answer = ground_truth
        print("No final answer found in ground truth.")

    # 计算准确率
    total += 1
    try:
        is_correct = llm_judge_via_api(predict_answer, ground_truth_answer, api_url, api_key, judge_model_name)
        status = "✅" if is_correct else "❌"
    except Exception as e:
        print("Judge API error:", e)
        is_correct = (predict_answer.strip() == ground_truth_answer.strip())
        status = "⚠️ API_ERROR"

    if is_correct:
        correct += 1

    print(f"extracted answer: {predict_answer} | ground_truth: {ground_truth_answer} | {status}")
    print()
    print()

    # 保存结果
    results.append({
        "id": i,
        "question": problem,
        "predicted_answer": predict_answer,
        "ground_truth": ground_truth,
        "thinking_content": thinking_content,
        "is_correct": is_correct,
        "status": status
    })


# 保存结果为 CSV 文件
df_results = pd.DataFrame(results)
df_results["accuracy"] = correct / total if total > 0 else 0.0
df_results.to_csv(save_path, index=False, encoding="utf-8")

print("\n========evaluation finished========")
print(f"Total: {total}, Correct: {correct}, Accuracy: {correct/total:.4f}")
print(f"Results saved to: {save_path}")