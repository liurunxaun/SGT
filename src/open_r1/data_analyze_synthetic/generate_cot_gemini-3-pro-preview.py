import os
import sys
import pandas as pd
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from tqdm.asyncio import tqdm_asyncio

# ================= 0. 导入 Google GenAI SDK =================
try:
    from google import genai
    from google.genai import types
    print("成功导入 google.genai")
except ImportError:
    print("【错误】需要安装 google-genai 库 (pip install google-genai)")
    exit(1)

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
INPUT_FILE = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/test.parquet"
OUTPUT_BASE = INPUT_FILE.replace(".parquet", "_gemini-3-pro-preview_results")

# --- 生成模型配置 (Google Gemini) ---
# 请填入你的 Google/Vertex API Key
GEN_API_KEY = "sk-wz6J5hsrKSCAuvE5eRJ2Q70OQHMNJxl3KMLC2ANSVdJIbv13" 
GEN_BASE_URL_PROXY = "https://api.openai-proxy.org/google"
GEN_MODEL_NAME = "gemini-3-pro-preview" # 或 gemini-2.0-flash-thinking-exp

# --- 评测模型配置 (Qwen/DashScope) ---
# 【注意】这里必须填入 DashScope 的 API Key，因为评测用的是 Qwen
JUDGE_API_KEY = "sk-YOUR_DASHSCOPE_KEY_HERE" 
JUDGE_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
JUDGE_MODEL_NAME = "qwen3-next-80b-a3b-instruct"

# --- 性能参数 ---
MAX_ATTEMPTS = 2 
MAX_CONCURRENCY = 100  # Gemini 的并发限制通常比 Qwen 严，建议先设 100，如稳定可调高
REQUEST_TIMEOUT = 1200.0

judge_executor = ThreadPoolExecutor(max_workers=32)

def extract_last_boxed_content(text):
    """提取 \\boxed{...}"""
    if not text: return None
    idx = text.rfind("\\boxed{")
    if idx == -1: return None 

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
        return False

async def get_gemini_response_async(client, prompt):
    """
    使用 Google GenAI SDK 获取回复，解析思考过程和答案
    """
    try:
        # 配置 Thinking
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_level="High",
                include_thoughts=True
            ),
            response_mime_type="text/plain"
        )

        # 异步调用 (.aio)
        response = await client.aio.models.generate_content(
            model=GEN_MODEL_NAME,
            contents=prompt,
            config=config
        )

        reasoning_parts = []
        answer_parts = []
        
        # 解析 Parts (分离 thought 和 text)
        if response.parts:
            for part in response.parts:
                if part.thought:
                    # 某些 SDK 版本 text 字段在 thought 为 True 时存放思考内容
                    reasoning_parts.append(part.text or "")
                else:
                    answer_parts.append(part.text or "")
        
        full_reasoning = "\n".join(reasoning_parts).strip()
        full_answer = "\n".join(answer_parts).strip()
        
        # 如果没有明确的 thought part (有时候模型可能不触发 thinking)，做个兜底
        if not full_answer and response.text:
            full_answer = response.text

        # 提取 Token 使用量
        thoughts_tokens = 0
        prompt_tokens = 0
        
        if response.usage_metadata:
            thoughts_tokens = response.usage_metadata.thoughts_token_count or 0
            prompt_tokens = response.usage_metadata.prompt_token_count or 0

        return full_reasoning, full_answer, thoughts_tokens, prompt_tokens, None

    except Exception as e:
        err_str = str(e)
        # 简单判断 Rate Limit (Google 的错误码通常在 message 里)
        if "429" in err_str or "ResourceExhausted" in err_str:
            return "", "", 0, 0, "RATE_LIMIT"
        return "", "", 0, 0, f"Error: {err_str}"

async def process_single_problem(sem, client, idx, row):
    async with sem:
        problem_text = row['problem']
        ground_truth = row['answer']
        problem_results = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            retry_wait = 2
            
            # --- API 生成 ---
            while True:
                reasoning, answer, t_tokens, p_tokens, error = await get_gemini_response_async(client, problem_text)
                
                if error == "RATE_LIMIT":
                    await asyncio.sleep(retry_wait)
                    retry_wait = min(retry_wait * 2, 60)
                    continue
                elif error:
                    reasoning = f"[API Error] {error}"
                    break # 其他错误跳出重试
                else:
                    break 

            # --- 判题准备 ---
            judge_input = None
            extracted_boxed = None
            judge_type = "fail"
            
            if not error:
                extracted_boxed = extract_last_boxed_content(answer)
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
                "gen_reasoning": reasoning, # Gemini 思考过程
                "gen_answer": answer,       # Gemini 最终回答
                "tokens_thinking": t_tokens, # 思考 Token 数
                "tokens_prompt": p_tokens,   # 提示词 Token 数
                "extracted_boxed": extracted_boxed, 
                "judge_input_type": judge_type,
                "is_correct": is_correct
            }
            problem_results.append(record)

            if is_correct:
                break
        
        return problem_results

async def main():
    # 初始化 Google GenAI Client
    # 注意：genai.Client 自己管理连接池，通常不需要传入 httpx client
    client = genai.Client(
        api_key=GEN_API_KEY,
        vertexai=True,
        http_options={
            "base_url": GEN_BASE_URL_PROXY,
            "api_version": "v1alpha" # 预览版功能通常需要 alpha 版本
        },
    )

    print(f"读取文件: {INPUT_FILE}...")
    try:
        df = pd.read_parquet(INPUT_FILE)
        print(f"成功加载，共 {len(df)} 条数据。")
    except Exception as e:
        print(f"读取失败: {e}")
        return

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    
    print("="*60)
    print(f"🚀 全速启动 | 并发: {MAX_CONCURRENCY} | Model: {GEN_MODEL_NAME}")
    print(f"模式: Gemini Thinking Mode (High) + 本地 Judge")
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
    total_thinking_tokens = df_res['tokens_thinking'].sum()
    
    print("-" * 30)
    print(f"耗时: {elapsed:.1f}s | 吞吐: {len(df)/elapsed:.2f} TPS")
    print(f"准确率: {uniq_correct}/{len(df)} ({uniq_correct/len(df):.2%})")
    print(f"总思考 Tokens: {total_thinking_tokens} | 平均: {total_thinking_tokens/len(df_res):.1f}")

    judge_executor.shutdown()

if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except: pass
    asyncio.run(main())