import sys
import os
import asyncio
import pandas as pd
from typing import Dict, Any, List
from tqdm import tqdm
from openai import AsyncOpenAI


# 基础路径与环境设置
current_file_path = os.path.abspath(__file__)
folder1_path = os.path.dirname(current_file_path)
project_path = os.path.dirname(folder1_path)
sys.path.append(project_path)


async def generate_sglang(client: AsyncOpenAI, messages: List[Dict], temperature: float = 0.6, max_tokens: int = 32768) -> str:
    """调用 SGLang API 生成回复"""
    try:
        response = await client.chat.completions.create(
            model = "default",  # SGLang Server 只有一个模型时，通常用 "default" 或模型原名
            messages = messages,
            temperature = temperature,
            top_p = 0.95,
            max_tokens = max_tokens,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True}, # 默认启用思考模式，对应 tokenizer.apply_chat_template(enable_thinking=True)
                "top_k": 20,
            },
        )
        content = response.choices[0].message.content
        return content if content else ""
    except Exception as e:
        print(f"[Inference Error]: {e}")
        return ""


async def process_single_row(
    index: int,
    row: pd.Series,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    loop: asyncio.AbstractEventLoop, 
    system_prompt, 
    query_field,
    answer_field,
    temperature, 
    max_tokens
) -> Dict[str, Any]:
    """处理单行数据：生成 -> 解析 -> 评测"""
    
    query = row[query_field]
    ground_truth = row[answer_field]

    # 1. 构建 Prompt
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]

    # 2. 调用 SGLang 推理 (受信号量限制并发)
    async with semaphore:
        raw_output_text = await generate_sglang(client, messages, temperature, max_tokens)

    # 3. 解析结果
        # SGLang 返回的是 text，直接用字符串分割，逻辑等同于原代码找 token id
        # 查找 </think>
    split_token = "</think>"
    if split_token in raw_output_text:
        parts = raw_output_text.rsplit(split_token, 1)
        thinking_content = parts[0].strip()
        predict_answer = parts[1].strip()
    else:
        thinking_content = ""
        predict_answer = raw_output_text.strip()

    # 4. 返回结果
    return {
        "id": index,
        "query": query,
        "response": raw_output_text,
        "predicted_answer": predict_answer,
        "ground_truth": ground_truth,
        "thinking_content": thinking_content,
    }


async def run_inference(dataset_path, system_prompt, query_field, answer_field, output_path, model, temperature, max_tokens,):
    print("========begin inference========")
    print()

    # 处理SGLang 配置
    if model == "qwen3-8B":
        SGLANG_BASE_URL = "http://localhost:30000/v1"
    elif model == "qwen3-8B-SFT":
        SGLANG_BASE_URL = "http://localhost:30001/v1"
    elif model == "qwen3-8B-RL":
        SGLANG_BASE_URL = "http://localhost:30002/v1"
    elif model == "qwen3-4B":
        SGLANG_BASE_URL = "http://localhost:30003/v1"
    elif model == "qwen3-4B-SFT":
        SGLANG_BASE_URL = "http://localhost:30004/v1"
    elif model == "qwen3-4B-RL":
        SGLANG_BASE_URL = "http://localhost:30005/v1"
    else:
        SGLANG_BASE_URL = "http://localhost:30000/v1"

    SGLANG_API_KEY = "sglang"  # 本地服务通常只需占位符
    CONCURRENCY = 64 # 并发控制：控制发送给SGLang的请求数量

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
        task = process_single_row(i, row, client, semaphore, loop, system_prompt, query_field, answer_field, temperature, max_tokens)
        tasks.append(task)

    results = []

    # 使用 as_completed 并发执行并显示进度条
    print(f"Starting concurrent evaluation (Concurrency: {CONCURRENCY})...")
    for future in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
        res = await future
        results.append(res)

    # 排序（因为异步完成顺序不确定）
    results.sort(key=lambda x: x['id'])

    # 保存结果 (保留原逻辑)
    df_results = pd.DataFrame(results)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_results.to_excel(output_path, index=False)

    print("\n========inference finished========")


# 程序主入口
def inference_sglang(dataset_path, system_prompt, query_field, answer_field, output_path, model, temperature, max_tokens):

    asyncio.run(run_inference(dataset_path, system_prompt, query_field, answer_field, output_path, model, temperature, max_tokens))