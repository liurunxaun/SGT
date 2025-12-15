import pandas as pd
import os
import sys
import asyncio
import httpx
import time
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tqdm.asyncio import tqdm_asyncio
from concurrent.futures import ThreadPoolExecutor
from llm_judge import llm_judge_via_api

# ================= 参数配置 =================
# 输入数据路径
dataset_path = "/ssd5/rxliu/datasets/rcmu/sampled_math_data.parquet"

# 输出文件路径
inference_output_path = "/data/home/the/rxliu/projects/open-r1-main/tests/results/inference-qwen3-8B-GSM8K-20251127-1730.xlsx"
result_output_path = "/data/home/the/rxliu/projects/open-r1-main/tests/results/sampled_math_data.xlsx"

# API配置
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 生成模型配置
GEN_MODEL = "qwen3-8B"  # 你可以根据需要更改模型

# 评测模型配置
JUDGE_MODEL = "qwen3-next-80b-a3b-instruct"

# 性能参数
MAX_CONCURRENCY = 200  # 并发数
MAX_TOKENS = 32768
REQUEST_TIMEOUT = 1200.0  # 20分钟超时
MAX_ATTEMPTS = 3  # 每个问题的最大尝试次数

# 字段配置
query_field = "problem"  # 问题字段
answer_field = "answer"  # 答案字段
system_prompt = ""  # 系统提示词
temperature = 0.6  # 温度参数

# 创建线程池用于评测
judge_executor = ThreadPoolExecutor(max_workers=32)

# ================= 辅助函数 =================

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

def extract_last_boxed_content(text):
    """
    提取 \boxed{...}。如果失败返回 None。
    """
    if not text: 
        return None
    
    idx = text.rfind("\\boxed{")
    if idx == -1:
        return None 

    content_start = idx + 7 
    balance = 0
    content_end = -1
    
    for i in range(content_start, len(text)):
        char = text[i]
        if char == '{':
            balance += 1
        elif char == '}':
            if balance == 0:
                content_end = i
                break
            balance -= 1
            
    if content_end != -1:
        return text[content_start:content_end]
    return None

def run_judge_sync(predicted, ground_truth):
    """同步评测函数"""
    try:
        if not predicted: 
            return False
        is_correct = llm_judge_via_api(
            predicted, 
            ground_truth, 
            API_URL, 
            API_KEY, 
            JUDGE_MODEL
        )
        return is_correct
    except Exception as e:
        print(f"Judge Error: {e}")
        return False

async def get_model_response_async(client, prompt):
    """异步获取模型响应"""
    messages = [{"role": "user", "content": prompt}]
    
    try:
        response = await client.chat.completions.create(
            model=GEN_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=MAX_TOKENS,
            stream=False
        )

        choice = response.choices[0]
        
        # 检查是否因为长度限制而截断
        if choice.finish_reason == "length":
            return "", "LENGTH_EXCEEDED"

        message = choice.message
        answer = message.content if message.content else ""
        
        return answer, None

    except RateLimitError:
        return "", "RATE_LIMIT"
    except APIConnectionError:
        return "", "CONNECTION_ERROR"
    except APITimeoutError:
        return "", "TIMEOUT"
    except Exception as e:
        return "", f"Error: {str(e)}"

async def process_single_problem(sem, client, idx, row):
    """处理单个问题"""
    async with sem:
        problem_text = row[query_field]
        ground_truth_raw = row[answer_field]
        
        # 处理ground truth
        clean_gt = process_ground_truth(ground_truth_raw)
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            retry_wait = 2
            
            # --- API 生成 ---
            while True:
                answer, error = await get_model_response_async(client, problem_text)
                
                if error == "RATE_LIMIT":
                    await asyncio.sleep(retry_wait)
                    retry_wait = min(retry_wait * 2, 60)
                    continue
                elif error in ["CONNECTION_ERROR", "TIMEOUT"]:
                    await asyncio.sleep(5)
                    continue
                elif error:
                    answer = f"[API Error] {error}"
                    break
                else:
                    break 

            # --- 判题准备 ---
            judge_input = None
            extracted_boxed = None
            judge_type = "fail"
            
            if not error or error == "LENGTH_EXCEEDED":
                extracted_boxed = extract_last_boxed_content(answer)
                
                # 优先使用Boxed内容，没有则使用全文
                if extracted_boxed:
                    judge_input = extracted_boxed
                    judge_type = "boxed"
                else:
                    judge_input = answer 
                    judge_type = "full_text"
            
            # --- 执行判题 ---
            if judge_input:
                loop = asyncio.get_running_loop()
                is_correct = await loop.run_in_executor(
                    judge_executor, 
                    run_judge_sync, 
                    judge_input,
                    clean_gt
                )
            else:
                is_correct = False

            # 创建结果记录
            record = {
                'id': idx,
                query_field: problem_text,
                'ground_truth_raw': ground_truth_raw,
                'processed_ground_truth': clean_gt,
                'predicted_answer': answer,
                'extracted_boxed': extracted_boxed,
                'judge_input_type': judge_type,
                'is_correct_judge': is_correct,
                'attempt': attempt,
                'error': error if error else None
            }
            
            # 如果正确，不再尝试
            if is_correct:
                return record
        
        # 如果所有尝试都失败，返回最后一次尝试的结果
        return record

# ================= 主程序 =================

async def main_async():
    """异步主程序"""
    print(f"读取数据文件: {dataset_path}...")
    try:
        df = pd.read_parquet(dataset_path)
        print(f"成功加载，共 {len(df)} 条数据。")
    except Exception as e:
        print(f"读取失败: {e}")
        return

    # 调整连接池以支持高并发
    limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENCY + 50, 
                         max_connections=MAX_CONCURRENCY + 100)
    http_client = httpx.AsyncClient(limits=limits, timeout=REQUEST_TIMEOUT)
    
    client = AsyncOpenAI(api_key=API_KEY, base_url=API_URL, http_client=http_client)

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    
    print("="*60)
    print(f"开始推理 | 模型: {GEN_MODEL} | 并发: {MAX_CONCURRENCY}")
    print(f"温度: {temperature} | 最大tokens: {MAX_TOKENS}")
    print("="*60)

    # 创建任务
    tasks = [process_single_problem(sem, client, idx, row) 
             for idx, row in df.iterrows()]
    
    # 执行所有任务并显示进度条
    start_time = time.time()
    all_results = await tqdm_asyncio.gather(*tasks)
    elapsed = time.time() - start_time

    # 转换为DataFrame
    result_df = pd.DataFrame(all_results)
    
    # 计算准确率（只考虑第一次尝试的结果）
    first_attempt_df = result_df[result_df['attempt'] == 1]
    num_correct = first_attempt_df["is_correct_judge"].sum()
    total = len(first_attempt_df)
    accuracy = num_correct / total if total > 0 else 0
    
    print(f"\n推理完成！")
    print(f"总耗时: {elapsed:.1f}s | 平均每条: {elapsed/total:.2f}s")
    print(f"Judge 正确数量：{num_correct}/{total}")
    print(f"Judge 准确率：{accuracy:.4f} ({accuracy:.2%})")
    
    # 保存推理结果
    print(f"\n保存推理结果到: {inference_output_path}")
    result_df.to_excel(inference_output_path, index=False)
    
    # 保存评测结果（只保留需要的列）
    final_df = result_df[['id', query_field, 'ground_truth_raw', 'processed_ground_truth', 
                         'predicted_answer', 'is_correct_judge']].copy()
    print(f"保存评测结果到: {result_output_path}")
    final_df.to_excel(result_output_path, index=False)
    
    # 关闭客户端
    await http_client.aclose()
    judge_executor.shutdown()
    
    return result_df

def main():
    """主函数入口"""
    try:
        import uvloop
        uvloop.install()
        print("使用uvloop优化异步性能")
    except ImportError:
        print("未找到uvloop，使用标准asyncio")
        pass
    
    # 运行异步主程序
    result_df = asyncio.run(main_async())
    
    # 显示统计信息
    if result_df is not None:
        print("\n" + "="*60)
        print("详细统计:")
        print("="*60)
        
        # 按尝试次数统计
        attempt_stats = result_df.groupby('attempt').agg({
            'is_correct_judge': ['count', 'sum', 'mean']
        }).round(4)
        print("\n按尝试次数统计:")
        print(attempt_stats)
        
        # 按judge类型统计
        if 'judge_input_type' in result_df.columns:
            type_stats = result_df.groupby('judge_input_type').agg({
                'is_correct_judge': ['count', 'sum', 'mean']
            }).round(4)
            print("\n按judge输入类型统计:")
            print(type_stats)
        
        # 错误统计
        if 'error' in result_df.columns:
            error_stats = result_df['error'].value_counts()
            print("\n错误类型统计:")
            print(error_stats)

if __name__ == "__main__":
    main()