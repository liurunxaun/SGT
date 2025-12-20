import os
import re
import json
import signal
import logging
import pandas as pd
from datasets import load_from_disk
from openai import OpenAI
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys
import io
import ast
import contextlib
from io import StringIO
import numpy as np

# 导入 prompt 模板
from prompts import get_system_prompt, construct_user_prompt

# ================= 配置区域 =================
INPUT_PATH = "/ssd5/rxliu/datasets/KodCode-V1-SFT-R1/filtered_12k"
SUCCESS_OUTPUT_FILE = "/ssd5/rxliu/datasets/KodCode-SFT/kodcode_success_sft.jsonl" 
FALLBACK_OUTPUT_FILE = "/ssd5/rxliu/datasets/KodCode-SFT/kodcode_fallback_sft.jsonl" 

# API 配置 
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"  
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3-max"

# 进程数配置
MAX_WORKERS = 10 

# 【修改点】批处理大小改成 50，防止数据丢失
BATCH_SIZE = 50

# ================= 屏蔽日志 =================
# 加上这个，你的控制台就会清爽很多，能看到进度条
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# ================= 工具函数 (保持不变) =================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def to_python_type(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: to_python_type(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_python_type(i) for i in obj]
    return obj

def call_qwen(prompt, system_prompt, temperature=0.5, max_tokens=32768):
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens, 
            top_p=0.95,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"API Error: {e}")
        return None

def parse_response(response_text):
    if not response_text:
        return None, None
    think_match = re.search(r'<think>(.*?)</think>', response_text, re.DOTALL)
    think_content = think_match.group(1).strip() if think_match else ""
    answer_match = re.search(r'<answer>(.*?)</answer>', response_text, re.DOTALL)
    answer_content = answer_match.group(1).strip() if answer_match else ""
    if not answer_content:
        code_match = re.search(r'```(?:python)?\s*(.*?)```', response_text, re.DOTALL)
        if code_match:
            answer_content = code_match.group(1).strip()
        else:
            answer_content = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
    return think_content, answer_content

class TimeoutException(Exception): pass
def timeout_handler(signum, frame): raise TimeoutException
signal.signal(signal.SIGALRM, timeout_handler)

def run_tests(solution_code, test_code, style, timeout=5):
    if style == 'online_judge':
        return run_io_tests(solution_code, test_code, timeout)
    else:
        return run_unit_tests(solution_code, test_code, timeout)

def run_io_tests(solution_code, test_data_str, timeout):
    try:
        test_cases = ast.literal_eval(test_data_str)
        inputs = test_cases['stdin']
        expected_outputs = test_cases['stdout']
        total = len(inputs)
    except Exception as e:
        return 0, 1, False
    passed = 0
    for inp, exp in zip(inputs, expected_outputs):
        output_buffer = StringIO()
        input_buffer = StringIO(inp)
        try:
            signal.alarm(timeout)
            with contextlib.redirect_stdout(output_buffer):
                sys.stdin = input_buffer 
                exec(solution_code, {'__name__': '__main__'}, {})
            signal.alarm(0)
            user_out = output_buffer.getvalue().strip()
            if user_out == exp.strip(): passed += 1
        except Exception:
            signal.alarm(0)
            continue
        finally:
            sys.stdin = sys.__stdin__
    return passed, total, (passed == total)

def run_unit_tests(solution_code, test_code, timeout):
    lines = test_code.split('\n')
    cleaned_lines = [line for line in lines if 'solution' not in line and 'import' not in line]
    cleaned_test_code = '\n'.join(cleaned_lines)
    global_scope = {}
    try:
        exec(solution_code, global_scope)
        exec(cleaned_test_code, global_scope)
    except Exception:
        return 0, 1, False
    test_funcs = [name for name in global_scope if name.startswith('test_') and callable(global_scope[name])]
    total = len(test_funcs)
    if total == 0:
        try:
            signal.alarm(timeout)
            exec(cleaned_test_code, global_scope)
            signal.alarm(0)
            return 1, 1, True
        except:
            signal.alarm(0)
            return 0, 1, False
    passed = 0
    for func_name in test_funcs:
        try:
            signal.alarm(timeout)
            global_scope[func_name]()
            signal.alarm(0)
            passed += 1
        except Exception:
            signal.alarm(0)
            continue
    return passed, total, (passed == total)

def process_single_row(row):
    row = to_python_type(row)
    question = row['question']
    style = row['style']
    test_code = row['test']
    r1_solution = row['r1_solution']
    test_info = row.get('test_info')
    gpt_difficulty = row.get('gpt_difficulty')
    
    sys_prompt = get_system_prompt(style)
    user_prompt = construct_user_prompt(question, style, test_info=test_info)
    
    last_generated_cot = ""
    last_generated_sol = ""
    last_pass_rate = 0.0
    
    # Attempt 1
    response1 = call_qwen(user_prompt, sys_prompt, temperature=0.5)
    cot1, ans1 = parse_response(response1)
    if ans1:
        passed, total, all_passed = run_tests(ans1, test_code, style=style)
        current_pass_rate = passed / total if total > 0 else 0.0
        last_generated_cot, last_generated_sol, last_pass_rate = cot1, ans1, current_pass_rate
        if all_passed:
            return ("success", {"question": question, "reasoning": cot1, "solution": ans1, "pass_rate": 1.0, "attempt": 1, "config": "temp_0.5", "test": test_code, "difficulty": gpt_difficulty, "test_info": test_info, "style": style}, "Success (1st)")
            
    # Attempt 2
    response2 = call_qwen(user_prompt, sys_prompt, temperature=0.8)
    cot2, ans2 = parse_response(response2)
    if ans2:
        passed, total, all_passed = run_tests(ans2, test_code, style=style)
        current_pass_rate = passed / total if total > 0 else 0.0
        last_generated_cot, last_generated_sol, last_pass_rate = cot2, ans2, current_pass_rate
        if all_passed:
            return ("success", {"question": question, "reasoning": cot2, "solution": ans2, "pass_rate": 1.0, "attempt": 2, "config": "temp_0.8", "test": test_code, "difficulty": gpt_difficulty, "test_info": test_info, "style": style}, "Success (2nd)")
        elif current_pass_rate > 0.5:
            return ("success", {"question": question, "reasoning": cot2, "solution": ans2, "pass_rate": current_pass_rate, "attempt": 2, "config": "temp_0.8_partial", "test": test_code, "difficulty": gpt_difficulty, "test_info": test_info, "style": style}, "Success (Partial)")
    
    return ("fallback", {"question": question, "solution": r1_solution, "note": "Failed generation", "solution_incorrect": last_generated_sol, "reasoning_incorrect": last_generated_cot, "pass_rate": last_pass_rate, "test": test_code, "difficulty": gpt_difficulty, "test_info": test_info, "style": style}, "Fallback")

def save_batch(file_handle, data_list):
    if not data_list: return
    for item in data_list:
        file_handle.write(json.dumps(item, ensure_ascii=False) + '\n')
    file_handle.flush()

# ================= 核心修复逻辑 =================

def get_existing_questions():
    """读取已存在的题目，避免重复跑"""
    existing = set()
    # 读取成功文件
    if os.path.exists(SUCCESS_OUTPUT_FILE):
        with open(SUCCESS_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip(): existing.add(json.loads(line)['question'])
    # 读取失败文件
    if os.path.exists(FALLBACK_OUTPUT_FILE):
        with open(FALLBACK_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip(): existing.add(json.loads(line)['question'])
    return existing

def main_resume():
    print(f"Loading original data from {INPUT_PATH}...")
    ds = load_from_disk(INPUT_PATH)
    full_data = ds.to_pandas().to_dict('records')
    print(f"Total original records: {len(full_data)}")
    
    print("Checking existing progress (Scanning files)...")
    existing_questions = get_existing_questions()
    print(f"Found {len(existing_questions)} already processed.")
    
    # 筛选出剩下的数据
    data_to_process = [row for row in full_data if row['question'] not in existing_questions]
    print(f"Remaining to process: {len(data_to_process)}")
    
    if not data_to_process:
        print("All done! No missing data.")
        return

    # 初始化缓冲区
    success_buffer = []
    fallback_buffer = []
    
    print(f"Starting resume process with BATCH_SIZE={BATCH_SIZE}...")
    
    # 【重点】使用 'a' (append) 模式，绝不覆盖
    with open(SUCCESS_OUTPUT_FILE, 'a', encoding='utf-8') as f_success, \
         open(FALLBACK_OUTPUT_FILE, 'a', encoding='utf-8') as f_fallback:
        
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_single_row, row): row for row in data_to_process}
            
            for future in tqdm(as_completed(futures), total=len(data_to_process), desc="Resuming"):
                try:
                    result_type, data, status_msg = future.result()
                    
                    if result_type == "success":
                        success_buffer.append(data)
                    else:
                        fallback_buffer.append(data)
                    
                    # 检查缓冲区
                    if len(success_buffer) >= BATCH_SIZE:
                        save_batch(f_success, success_buffer)
                        success_buffer = []
                    
                    if len(fallback_buffer) >= BATCH_SIZE:
                        save_batch(f_fallback, fallback_buffer)
                        fallback_buffer = []
                        
                except Exception as e:
                    print(f"Error: {e}")
        
        # 最后的扫尾
        if success_buffer: save_batch(f_success, success_buffer)
        if fallback_buffer: save_batch(f_fallback, fallback_buffer)

    print("\nProcessing complete! All missing data repaired.")

if __name__ == "__main__":
    main_resume()