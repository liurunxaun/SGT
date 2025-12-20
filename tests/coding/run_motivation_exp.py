import os
import json
import time
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from openai import OpenAI  # 假设你使用 OpenAI 兼容协议调用 Qwen

# ================= 配置区域 =================
# 配置 API (这里以阿里云 DashScope 为例，或者你本地部署的 vLLM)
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"  # 替换你的 Key
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1" # 阿里云 Qwen endpoint
MODEL_NAME = "qwen3-max" # 或者 "qwen3-max"，根据你实际调用的模型名称填写

# 数据路径
DATA_DIR = "/ssd5/rxliu/datasets/livecodebench_lite"
OUTPUT_FILE = "/ssd5/rxliu/datasets/motivation_coding/qwen3_max_cot_experiment_results.jsonl"

# 并发数 (API调用建议 5-10，太高可能会触发 Rate Limit)
MAX_WORKERS = 5 
# ===========================================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def load_data(data_dir):
    """
    加载 LiveCodeBench 数据。
    假设 lite 版本可能是 jsonl 或者 json 文件。
    这里写了一个比较通用的加载逻辑。
    """
    tasks = []
    
    # 尝试查找目录下的 jsonl 文件
    files = glob.glob(os.path.join(data_dir, "*.jsonl"))
    if not files:
        files = glob.glob(os.path.join(data_dir, "*.json"))
        
    print(f"Found files: {files}")
    
    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.endswith('.jsonl'):
                for line in f:
                    if line.strip():
                        tasks.append(json.loads(line))
            else:
                # 如果是 json 列表
                data = json.load(f)
                if isinstance(data, list):
                    tasks.extend(data)
    
    # 如果数据量太大，截取前400个或者随机采样400个
    # tasks = tasks[:400] 
    print(f"Total tasks loaded: {len(tasks)}")
    return tasks

def build_prompt(problem):
    """
    构建 Prompt，强制模型输出思维链。
    LiveCodeBench 通常包含 'content' (题目描述) 等字段。
    """
    # 根据 LCB 数据格式调整字段名，通常是 'question_content' 或 'prompt'
    question = problem.get('question_content', problem.get('content', '')) 
    starter_code = problem.get('starter_code', '')
    
    system_prompt = (
        "You are an expert software engineer and algorithm specialist. "
        "You are tasked with solving complex coding problems.\n\n"
        "Instructions:\n\n"
        "Analyze First: Before writing any code, you must perform a deep, step-by-step analysis of the problem. "
        "Consider edge cases, time complexity, and potential pitfalls.\n\n"
        "Format: You MUST enclose your entire reasoning process within <think> and </think> tags.\n\n"
        "Implementation: After the <think> block, provide the final Python solution wrapped in a Markdown code block "
        "(python ... ).\n\n"
        "Goal: Your reasoning should be thorough. If you find a logical flaw in your initial thought, acknowledge it, correct it, and proceed. (Self-Correction is encouraged)."
    )
    
    user_prompt = f"""
## Problem Description
{question}

## Starter Code
{starter_code}

Please solve this problem. Remember to show your thinking process in <think> tags first.
"""
    return system_prompt, user_prompt

def solve_problem(problem):
    """
    调用模型解决单个问题
    """
    sys_p, user_p = build_prompt(problem)
    task_id = problem.get('task_id', problem.get('question_id', 'unknown'))
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_p}
            ],
            temperature=0.7, # 稍微给一点创造性，让它多想一点
            max_tokens=8192,
        )
        
        raw_content = response.choices[0].message.content
        
        return {
            "task_id": task_id,
            "original_problem": problem,
            "raw_response": raw_content,
            "status": "success"
        }
        
    except Exception as e:
        return {
            "task_id": task_id,
            "error": str(e),
            "status": "failed"
        }

def main():
    # 1. 加载数据
    all_problems = load_data(DATA_DIR)
    
    # 简单过滤：如果之前跑过，就跳过（简单的断点续传）
    existing_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    existing_ids.add(data.get('task_id'))
                except:
                    pass
    
    problems_to_run = [p for p in all_problems if p.get('task_id', p.get('question_id')) not in existing_ids]
    # 限制只跑400个（如果数据集很大的话）
    if len(problems_to_run) > 400:
        problems_to_run = problems_to_run[:400]
        
    print(f"Remaining problems to run: {len(problems_to_run)}")

    # 2. 并发执行
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f_out:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 提交任务
            future_to_prob = {executor.submit(solve_problem, p): p for p in problems_to_run}
            
            # 使用 tqdm 显示进度
            for future in tqdm(as_completed(future_to_prob), total=len(problems_to_run), desc="Running Qwen3-max"):
                result = future.result()
                
                # 3. 实时写入结果
                if result['status'] == 'success':
                    # 可以在这里做一个简单的解析，把 think 和 code 分开存，方便后续 judge
                    content = result['raw_response']
                    think_content = ""
                    code_content = ""
                    
                    # 简单提取逻辑
                    if "<think>" in content and "</think>" in content:
                        start = content.find("<think>") + 7
                        end = content.find("</think>")
                        think_content = content[start:end].strip()
                        code_part = content[end+8:].strip()
                    else:
                        # 如果模型没听话，把所有内容当做 think 或者 raw
                        think_content = content
                    
                    result['parsed_think'] = think_content
                    # 写入文件
                    f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                    f_out.flush() # 强制刷新缓冲区
                else:
                    print(f"\nTask {result['task_id']} failed: {result.get('error')}")

if __name__ == "__main__":
    main()