# import os
# import sys
# import pandas as pd
# import asyncio
# import httpx
# import time
# from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError
# from tqdm.asyncio import tqdm_asyncio
# from concurrent.futures import ThreadPoolExecutor

# # ================= 1. 导入本地评测模块 =================
# JUDGE_PATH = "/data/home/the/rxliu/projects/open-r1-main/tests/utils"
# if JUDGE_PATH not in sys.path:
#     sys.path.append(JUDGE_PATH)

# try:
#     from llm_judge import llm_judge_via_api
#     print("成功导入 llm_judge_via_api")
# except ImportError:
#     print(f"【错误】无法从 {JUDGE_PATH} 导入 llm_judge_via_api")
#     exit(1)

# # ================= 2. 配置区域 =================
# INPUT_FILE = "/ssd5/rxliu/datasets/rcmu/sampled_math_data.parquet"
# OUTPUT_BASE = INPUT_FILE.replace(".parquet", "_qwen3-max-preview_results")

# # 生成模型配置
# GEN_API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
# GEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# GEN_MODEL_NAME = "qwen3-max-preview"

# # 评测模型配置
# JUDGE_API_KEY = GEN_API_KEY 
# JUDGE_API_URL = GEN_BASE_URL 
# JUDGE_MODEL_NAME = "qwen3-next-80b-a3b-instruct"

# # --- 性能参数 ---
# MAX_ATTEMPTS = 1

# # 【并发 200】既然实测没问题，就保持高并发
# MAX_CONCURRENCY = 200

# # 【最大输出】
# MAX_TOKENS = 32768
# # MAX_TOKENS = 65536

# # 【超时 20分钟】防止长思考因为网络波动断连
# REQUEST_TIMEOUT = 1200.0
# # ===========================================

# judge_executor = ThreadPoolExecutor(max_workers=32) # 稍微调大一点判题线程池

# def extract_last_boxed_content(text):
#     """
#     提取 \boxed{...}。如果失败返回 None。
#     """
#     if not text: return None
#     idx = text.rfind("\\boxed{")
#     if idx == -1:
#         return None 

#     content_start = idx + 7 
#     balance = 0
#     content_end = -1
    
#     for i in range(content_start, len(text)):
#         char = text[i]
#         if char == '{':
#             balance += 1
#         elif char == '}':
#             if balance == 0:
#                 content_end = i
#                 break
#             balance -= 1
            
#     if content_end != -1:
#         return text[content_start:content_end]
#     return None

# def run_judge_sync(predicted, ground_truth):
#     """同步评测函数"""
#     try:
#         if not predicted: return False
#         is_correct = llm_judge_via_api(
#             predicted, 
#             ground_truth, 
#             JUDGE_API_URL, 
#             JUDGE_API_KEY, 
#             JUDGE_MODEL_NAME
#         )
#         return is_correct
#     except Exception as e:
#         # print(f"Judge Error: {e}") 
#         return False



# async def get_qwen_response_async(client, prompt):
#     messages = [{"role": "user", "content": prompt}]
    
#     try:
#         response = await client.chat.completions.create(
#             model=GEN_MODEL_NAME,
#             messages=messages,
#             extra_body={"enable_thinking": True},
#             stream=False, # 关流式，极速稳健
#             max_tokens=MAX_TOKENS 
#         )
#         print(response)

#         choice = response.choices[0]
        
#         # 即使设了63k，如果还不够，依然要报错重试
#         if choice.finish_reason == "length":
#             return "", "", "LENGTH_EXCEEDED"

#         message = choice.message
#         answer = message.content if message.content else ""

        
#         reasoning = ""
#         if hasattr(message, "reasoning_content") and message.reasoning_content:
#             reasoning = message.reasoning_content
#         elif hasattr(message, "model_extra") and message.model_extra:
#              reasoning = message.model_extra.get("reasoning_content", "")
                
#         return reasoning, answer, None

#     except RateLimitError:
#         print("Rate limit error encountered.")
#         return "", "", "RATE_LIMIT"
#     except APIConnectionError:
#         print("API connection error encountered.")
#         return "", "", "CONNECTION_ERROR"
#     except APITimeoutError:
#         print("API timeout error encountered.")
#         return "", "", "TIMEOUT"
#     except Exception as e:
#         print(f"Unexpected error: {e}")
#         return "", "", f"Error: {str(e)}"

# async def process_single_problem(sem, client, idx, row):
#     async with sem:
#         problem_text = row['problem']
#         ground_truth = row['answer']
#         problem_results = []

#         for attempt in range(1, MAX_ATTEMPTS + 1):
#             retry_wait = 2
            
#             # --- API 生成 ---
#             while True:
#                 reasoning, answer, error = await get_qwen_response_async(client, problem_text)
                
#                 if error == "RATE_LIMIT":
#                     await asyncio.sleep(retry_wait)
#                     retry_wait = min(retry_wait * 2, 60)
#                     continue
#                 elif error in ["CONNECTION_ERROR", "TIMEOUT"]:
#                     await asyncio.sleep(5)
#                     continue
#                 elif error:
#                     reasoning = f"[API Error] {error}"
#                     break
#                 else:
#                     break 

#             # --- 判题准备 ---
#             judge_input = None
#             extracted_boxed = None
#             judge_type = "fail"
            
#             if not error:
#                 extracted_boxed = extract_last_boxed_content(answer)
                
#                 # 【策略】优先 Boxed，没有则全文
#                 if extracted_boxed:
#                     judge_input = extracted_boxed
#                     judge_type = "boxed"
#                 else:
#                     judge_input = answer 
#                     judge_type = "full_text"
            
#             # --- 执行判题 ---
#             if judge_input:
#                 loop = asyncio.get_running_loop()
#                 is_correct = await loop.run_in_executor(
#                     judge_executor, 
#                     run_judge_sync, 
#                     judge_input,
#                     ground_truth
#                 )
#             else:
#                 is_correct = False

#             record = {
#                 "id": idx,
#                 "problem": problem_text,
#                 "ground_truth": ground_truth,
#                 "attempt": attempt,
#                 "qwen_reasoning": reasoning,
#                 "qwen_answer": answer,
#                 "extracted_boxed": extracted_boxed, 
#                 "judge_input_type": judge_type,
#                 "is_correct": is_correct
#             }
#             problem_results.append(record)

#             if is_correct:
#                 break
        
#         return problem_results

# async def main():
#     # 调整连接池以支持 200+ 并发
#     limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENCY + 50, max_connections=MAX_CONCURRENCY + 100)
#     http_client = httpx.AsyncClient(limits=limits, timeout=REQUEST_TIMEOUT)
    
#     client = AsyncOpenAI(api_key=GEN_API_KEY, base_url=GEN_BASE_URL, http_client=http_client)


#     print(f"读取文件: {INPUT_FILE}...")
#     try:
#         df = pd.read_parquet(INPUT_FILE)
#         print(f"成功加载，共 {len(df)} 条数据。")
#     except Exception as e:
#         print(f"读取失败: {e}")
#         return

#     sem = asyncio.Semaphore(MAX_CONCURRENCY)
    
#     print("="*60)
#     print(f"🚀 全速启动 | 并发: {MAX_CONCURRENCY} | MaxTokens: {MAX_TOKENS}")
#     print(f"模式: 非流式 + 本地LLM Judge (优先Boxed -> 降级FullText)")
#     print("="*60)

#     tasks = [process_single_problem(sem, client, idx, row) for idx, row in df.iterrows()]
    
#     start_time = time.time()
#     results_nested = await tqdm_asyncio.gather(*tasks)
#     all_results = [item for sublist in results_nested for item in sublist]
#     elapsed = time.time() - start_time

#     if not all_results: return
    
#     # 保存结果
#     df_res = pd.DataFrame(all_results).sort_values(by=['id', 'attempt'])
    
#     print(f"正在保存 ({len(df_res)}条记录)...")
#     df_res.to_excel(OUTPUT_BASE + "_all.xlsx", index=False)
    
#     df_correct = df_res[df_res['is_correct'] == True]
#     df_correct.to_excel(OUTPUT_BASE + "_correct.xlsx", index=False)
    
#     # 最终统计
#     uniq_correct = len(df_correct['id'].unique())
#     print("-" * 30)
#     print(f"耗时: {elapsed:.1f}s | 吞吐: {len(df)/elapsed:.2f} TPS")
#     print(f"准确率: {uniq_correct}/{len(df)} ({uniq_correct/len(df):.2%})")

#     await http_client.aclose()
#     judge_executor.shutdown()

# if __name__ == "__main__":
#     try:
#         import uvloop
#         uvloop.install()
#     except: pass
#     asyncio.run(main())


import os
import sys
import pandas as pd
import asyncio
import httpx
import time
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tqdm.asyncio import tqdm_asyncio
from concurrent.futures import ThreadPoolExecutor

# ================= 1. 导入本地评测模块 =================
JUDGE_PATH = "/data/home/the/rxliu/projects/open-r1-main/tests/utils"
if JUDGE_PATH not in sys.path:
    sys.path.append(JUDGE_PATH)

try:
    from llm_judge import llm_judge_via_api
    print("成功导入 llm_judge_via_api")
except ImportError:
    print(f"【错误】无法从 {JUDGE_PATH} 导入 llm_judge_via_api")
    exit(1)

# ================= 2. 配置区域 =================
INPUT_FILE = "/ssd5/rxliu/datasets/rcmu/sampled_math_data.parquet"
OUTPUT_BASE = INPUT_FILE.replace(".parquet", "_qwen3-max-preview_results")

# 生成模型配置
GEN_API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
GEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
GEN_MODEL_NAME = "qwen3-max-preview"

# 评测模型配置
JUDGE_API_KEY = GEN_API_KEY 
JUDGE_API_URL = GEN_BASE_URL 
JUDGE_MODEL_NAME = "qwen3-next-80b-a3b-instruct"

# --- 性能参数 ---
MAX_ATTEMPTS = 1
MAX_CONCURRENCY = 200
MAX_TOKENS = 32768
THINKING_BUDGET = 81920  # 思考预算
REQUEST_TIMEOUT = 1200.0
# ===========================================

judge_executor = ThreadPoolExecutor(max_workers=32) # 稍微调大一点判题线程池

def extract_last_boxed_content(text):
    """
    提取 \boxed{...}。如果失败返回 None。
    """
    if not text: return None
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
        if not predicted: return False
        is_correct = llm_judge_via_api(
            predicted, 
            ground_truth, 
            JUDGE_API_URL, 
            JUDGE_API_KEY, 
            JUDGE_MODEL_NAME
        )
        return is_correct
    except Exception as e:
        # print(f"Judge Error: {e}") 
        return False

async def get_qwen_response_async(client, prompt):
    """流式获取Qwen响应，支持思考过程"""
    messages = [{"role": "user", "content": prompt}]
    
    try:
        # 启用流式调用
        response = await client.chat.completions.create(
            model=GEN_MODEL_NAME,
            messages=messages,
            extra_body={
                "enable_thinking": True,
                "thinking_budget": THINKING_BUDGET
            },
            stream=True,  # 启用流式
            stream_options={
                "include_usage": True
            },
            max_tokens=MAX_TOKENS
        )
        
        reasoning_content = ""  # 完整思考过程
        answer_content = ""     # 完整回复
        is_answering = False   # 是否进入回复阶段
        
        async for chunk in response:
            if not chunk.choices:
                # 这里是usage信息，可以记录但不需要处理内容
                # print(f"Usage: {chunk.usage}")
                continue
                
            delta = chunk.choices[0].delta
            
            # 收集思考内容
            if hasattr(delta, "reasoning_content") and delta.reasoning_content is not None:
                reasoning_content += delta.reasoning_content
            
            # 收集回复内容
            if hasattr(delta, "content") and delta.content:
                answer_content += delta.content
        
        # 检查是否因长度限制而截断
        finish_reason = chunk.choices[0].finish_reason if chunk.choices else None
        if finish_reason == "length":
            return reasoning_content, answer_content, "LENGTH_EXCEEDED"
            
        return reasoning_content, answer_content, None

    except RateLimitError:
        print("Rate limit error encountered.")
        return "", "", "RATE_LIMIT"
    except APIConnectionError:
        print("API connection error encountered.")
        return "", "", "CONNECTION_ERROR"
    except APITimeoutError:
        print("API timeout error encountered.")
        return "", "", "TIMEOUT"
    except Exception as e:
        print(f"Unexpected error: {e}")
        return "", "", f"Error: {str(e)}"

async def process_single_problem(sem, client, idx, row):
    async with sem:
        problem_text = row['problem']
        ground_truth = row['answer']
        problem_results = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            retry_wait = 2
            
            # --- API 生成 ---
            while True:
                reasoning, answer, error = await get_qwen_response_async(client, problem_text)
                
                if error == "RATE_LIMIT":
                    await asyncio.sleep(retry_wait)
                    retry_wait = min(retry_wait * 2, 60)
                    continue
                elif error in ["CONNECTION_ERROR", "TIMEOUT"]:
                    await asyncio.sleep(5)
                    continue
                elif error:
                    reasoning = f"[API Error] {error}"
                    break
                else:
                    break 

            # --- 判题准备 ---
            judge_input = None
            extracted_boxed = None
            judge_type = "fail"
            
            if not error:
                extracted_boxed = extract_last_boxed_content(answer)
                
                # 【策略】优先 Boxed，没有则全文
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
                    ground_truth
                )
            else:
                is_correct = False

            record = {
                "id": idx,
                "problem": problem_text,
                "ground_truth": ground_truth,
                "attempt": attempt,
                "qwen_reasoning": reasoning,
                "qwen_answer": answer,
                "extracted_boxed": extracted_boxed, 
                "judge_input_type": judge_type,
                "is_correct": is_correct
            }
            problem_results.append(record)

            if is_correct:
                break
        
        return problem_results

async def main():
    # 调整连接池以支持 200+ 并发
    limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENCY + 50, max_connections=MAX_CONCURRENCY + 100)
    http_client = httpx.AsyncClient(limits=limits, timeout=REQUEST_TIMEOUT)
    
    client = AsyncOpenAI(api_key=GEN_API_KEY, base_url=GEN_BASE_URL, http_client=http_client)

    print(f"读取文件: {INPUT_FILE}...")
    try:
        df = pd.read_parquet(INPUT_FILE)
        print(f"成功加载，共 {len(df)} 条数据。")
    except Exception as e:
        print(f"读取失败: {e}")
        return

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    
    print("="*60)
    print(f"🚀 全速启动 | 并发: {MAX_CONCURRENCY} | MaxTokens: {MAX_TOKENS}")
    print(f"模式: 流式 + 本地LLM Judge (优先Boxed -> 降级FullText)")
    print(f"思考预算: {THINKING_BUDGET}")
    print("="*60)

    tasks = [process_single_problem(sem, client, idx, row) for idx, row in df.iterrows()]
    
    start_time = time.time()
    results_nested = await tqdm_asyncio.gather(*tasks)
    all_results = [item for sublist in results_nested for item in sublist]
    elapsed = time.time() - start_time

    if not all_results: return
    
    # 保存结果
    df_res = pd.DataFrame(all_results).sort_values(by=['id', 'attempt'])
    
    print(f"正在保存 ({len(df_res)}条记录)...")
    df_res.to_excel(OUTPUT_BASE + "_all.xlsx", index=False)
    
    df_correct = df_res[df_res['is_correct'] == True]
    df_correct.to_excel(OUTPUT_BASE + "_correct.xlsx", index=False)
    
    # 最终统计
    uniq_correct = len(df_correct['id'].unique())
    print("-" * 30)
    print(f"耗时: {elapsed:.1f}s | 吞吐: {len(df)/elapsed:.2f} TPS")
    print(f"准确率: {uniq_correct}/{len(df)} ({uniq_correct/len(df):.2%})")

    await http_client.aclose()
    judge_executor.shutdown()

if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except: 
        pass
    asyncio.run(main())