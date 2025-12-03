import pandas as pd
import os
import sys

sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")

from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from tqdm import tqdm  # 进度条库，没有请 pip install tqdm
from llm_judge import llm_judge_via_api
from inference_sglang import inference_sglang


# ================= 参数配置 =================

# sglang 推理参数
dataset_name = "GSM8K"
dataset_path = "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet"
query_field = "question"
model = "qwen3-8B-RL-20251202-2100-checkpoint-80"
time = "20251203-1200"
temperature = 0.6
max_tokens = 32768
system_prompt = ""

# sglang推理结果
inference_output_path = "/data/home/the/rxliu/projects/open-r1-main/tests/results/inference-" + model + "-" + dataset_name + "-" + time + ".xlsx"

# 测试参数
answer_field = "answer"

# 测试结果   
result_output_path = "/data/home/the/rxliu/projects/open-r1-main/tests/results/result-" + model + "-" + dataset_name + "-" + time + ".xlsx"

# llm judge 配置
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
JUDGE_MODEL = "qwen3-next-80b-a3b-instruct"
client = OpenAI(api_key=API_KEY, base_url=API_URL)
api_workers = 4


# ================= 数据处理函数 =================

def process_ground_truth(text):
    """
    处理 Ground Truth：提取 #### 之后的内容并去除空格
    """
    if not isinstance(text, str):
        return str(text)
    
    if "####" in text:
        # 分割并取最后一部分，去除前后空格
        return text.split("####")[-1].strip()
    else:
        # 如果没有 ####，则返回去除空格的原文本
        return text.strip()


def process_row(row):
    """
    处理单行数据的线程函数
    """
    # 1. 获取原始数据
    pred = row.get('predicted_answer', '')
    raw_gt = row.get('ground_truth', '')
    
    # 2. 处理 Ground Truth
    clean_gt = process_ground_truth(raw_gt)
    
    # 3. 调用 Judge
    is_correct = llm_judge_via_api(pred, clean_gt, API_URL, API_KEY, JUDGE_MODEL)
    
    # 4. 返回完整行数据（包含原有列和新结果）
    new_row = row.copy()
    new_row['processed_ground_truth'] = clean_gt # 方便你检查提取对不对
    new_row['is_correct_judge'] = is_correct     # 存入判断结果
    return new_row


# ================= 主程序 =================

def main():
 
    # sglang推理
    inference_sglang(dataset_path, system_prompt, query_field, answer_field, inference_output_path, model, temperature, max_tokens)

    # 读取推理结果
    if not os.path.exists(inference_output_path):
        print(f"错误：找不到文件 {inference_output_path}，请先运行推理部分。")
        return
    print(f"正在读取 {inference_output_path} ...")
    df = pd.read_excel(inference_output_path)
    
    # 转为字典列表以便并发处理
    data_list = df.to_dict('records')
    results = []
    
    # 开启线程池并发处理
    print(f"开始处理 {len(data_list)} 条数据，并发数: {api_workers}")
    with ThreadPoolExecutor(max_workers=api_workers) as executor:
        # map 会按顺序返回结果，tqdm 显示进度条
        results = list(tqdm(executor.map(process_row, data_list), total=len(data_list)))

    # 处理结果
    result_df = pd.DataFrame(results)

    # 计算准确率
    num_correct = result_df["is_correct_judge"].sum()
    total = len(result_df)
    accuracy = num_correct / total if total > 0 else 0
    print(f"\nJudge 正确数量：{num_correct}/{total}")
    print(f"Judge 准确率：{accuracy:.4f}")
    
    # 保存结果至文件
    result_df.to_excel(result_output_path, index=False)
    print(f"处理完成！结果已保存至 {result_output_path}")

if __name__ == "__main__":
    main()