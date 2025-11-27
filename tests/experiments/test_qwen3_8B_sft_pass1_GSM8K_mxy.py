import sys
import os
import re
import datetime
import asyncio
import pandas as pd
from typing import Dict, Any, List
from tqdm import tqdm
from openai import AsyncOpenAI
from concurrent.futures import ThreadPoolExecutor

# ======== 1. 基础路径与环境设置 (保留原逻辑) ========
current_file_path = os.path.abspath(__file__)
folder1_path = os.path.dirname(current_file_path)
project_path = os.path.dirname(folder1_path)
sys.path.append(project_path)

from utils.llm_judge import llm_judge_via_api

print("========begin evaluate========")
print()

# ======== 2. 超参数定义 (保留原逻辑) ========
# 模型路径 (仅用于生成文件名，实际调用走API)
model_path = "/ssd5/rxliu/models/Qwen3-8B"
# 数据集路径
dataset_path = "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet"
# 问题字段名称
question_field = "question"
# 答案字段名称
answer_field = "answer"

# api_url & key
judge_api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
judge_api_key = "sk-8d445207b1ab47efb83069ccc1b845b6"
judge_model_name = "qwen3-next-80b-a3b-instruct"

# system_prompt
self_prompt = "Your answer only needs to include one number"

# 保存结果路径
save_dir = "/data/home/the/rxliu/projects/open-r1-main/tests/results"
model_name = os.path.basename(model_path)
dataset_name = os.path.basename(os.path.dirname(dataset_path))
date_str = datetime.datetime.now().strftime("%Y%m%d")
save_path = os.path.join(save_dir, f"{model_name}_{dataset_name}_{date_str}.csv")

# ======== 3. SGLang 配置 ========
SGLANG_BASE_URL = "http://localhost:30000/v1"
SGLANG_API_KEY = "sglang"  # 本地服务通常只需占位符
# 并发控制：控制同时发送给SGLang和Judge API的请求数量
CONCURRENCY = 64 

# ======== 4. 异步处理函数 ========

async def generate_sglang(client: AsyncOpenAI, messages: List[Dict], temperature: float = 0.6) -> str:
    """调用 SGLang API 生成回复"""
    try:
        response = await client.chat.completions.create(
            model="default",  # SGLang Server 只有一个模型时，通常用 "default" 或模型原名
            messages=messages,
            temperature=temperature,
            top_p=0.95,
            max_tokens=32768, # 对应原代码 max_new_tokens
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True}, # 启用思考模式，对应 tokenizer.apply_chat_template(enable_thinking=True)
                "top_k": 20,
            },
        )
        content = response.choices[0].message.content
        return content if content else ""
    except Exception as e:
        print(f"[Inference Error]: {e}")
        return ""

def run_judge_sync(predict_answer, ground_truth_answer, problem):
    """
    同步的 Judge 函数，将被放入线程池运行
    保留原代码的 Judge 逻辑
    """
    try:
        is_correct = llm_judge_via_api(predict_answer, ground_truth_answer, judge_api_url, judge_api_key, judge_model_name, problem)
        status = "✅" if is_correct else "❌"
        return is_correct, status
    except Exception as e:
        # print("Judge API error:", e)
        is_correct = (predict_answer.strip() == ground_truth_answer.strip())
        status = "⚠️ API_ERROR"
        return is_correct, status

async def process_single_row(
    index: int,
    row: pd.Series,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    loop: asyncio.AbstractEventLoop
) -> Dict[str, Any]:
    """处理单行数据：生成 -> 解析 -> 评测"""
    
    problem = row[question_field]
    ground_truth = row[answer_field]

    # 1. 构建 Prompt (保留原逻辑)
    messages = [
        {"role": "system", "content": self_prompt},
        {"role": "user", "content": problem}
    ]

    # 2. 调用 SGLang 推理 (受信号量限制并发)
    async with semaphore:
        raw_output_text = await generate_sglang(client, messages)

    # 3. 解析结果 (保留原逻辑)
    # SGLang 返回的是 text，直接用字符串分割，逻辑等同于原代码找 token id
    # 查找 </think>
    split_token = "</think>"
    if split_token in raw_output_text:
        parts = raw_output_text.split(split_token, 1)
        thinking_content = parts[0].strip()
        answer_content = parts[1].strip()
    else:
        thinking_content = ""
        answer_content = raw_output_text.strip()
    
    # 用正则提取 <answer>...</answer>
    match = re.search(r"<answer>([\s\S]*?)</answer>", answer_content)
    if match:
        predict_answer = match.group(1).strip()
    else:
        # print(f"Cannot answer found in the output for id {index}")
        predict_answer = "Cannot answer found"

    # 提取 Ground Truth (保留原逻辑)
    match = re.search(r"####\s*([-\d\.]+)", ground_truth)
    if match:
        ground_truth_answer = match.group(1).strip()
    else:
        ground_truth_answer = ground_truth
        # print(f"No final answer found in ground truth for id {index}")

    # 4. 调用 Judge (并发运行)
    # llm_judge_via_api 是同步阻塞 IO，必须放入 run_in_executor 避免阻塞 asyncio 循环
    is_correct, status = await loop.run_in_executor(
        None, # 使用默认的 ThreadPoolExecutor
        run_judge_sync,
        predict_answer,
        ground_truth_answer,
        problem
    )

    # 打印简略日志 (可选)
    # print(f"ID: {index} | {status}")

    return {
        "id": index,
        "question": problem,
        "predicted_answer": predict_answer,
        "ground_truth": ground_truth,
        "thinking_content": thinking_content,
        "is_correct": is_correct,
        "status": status
    }

async def run_evaluation():
    # 读取数据集
    print("begin loading data")
    df = pd.read_parquet(dataset_path)
    print(f"Total samples: {len(df)}")
    print()

    # 初始化 OpenAI Client 和 信号量
    client = AsyncOpenAI(base_url=SGLANG_BASE_URL, api_key=SGLANG_API_KEY)
    semaphore = asyncio.Semaphore(CONCURRENCY)
    loop = asyncio.get_running_loop()

    tasks = []
    # 创建所有任务
    for i, row in df.iterrows():
        task = process_single_row(i, row, client, semaphore, loop)
        tasks.append(task)

    results = []
    correct = 0
    total = 0

    # 使用 as_completed 并发执行并显示进度条
    print(f"Starting concurrent evaluation (Concurrency: {CONCURRENCY})...")
    for future in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
        res = await future
        results.append(res)
        
        total += 1
        if res['is_correct']:
            correct += 1

    # 排序（因为异步完成顺序不确定）
    results.sort(key=lambda x: x['id'])

    # 保存结果 (保留原逻辑)
    df_results = pd.DataFrame(results)
    df_results["accuracy"] = correct / total if total > 0 else 0.0
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    df_results.to_csv(save_path, index=False, encoding="utf-8")

    print("\n========evaluation finished========")
    print(f"Total: {total}, Correct: {correct}, Accuracy: {correct/total:.4f}")
    print(f"Results saved to: {save_path}")

# ======== 5. 主程序入口 ========
if __name__ == "__main__":
    asyncio.run(run_evaluation())