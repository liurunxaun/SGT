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

# 导入 prompt 模板 (请确保 prompts.py 已更新支持 test_info 参数)
from prompts import get_system_prompt, construct_user_prompt

# ================= 配置区域 =================
INPUT_PATH = "/ssd5/rxliu/datasets/KodCode-V1-SFT-R1/filtered_12k_test"
SUCCESS_OUTPUT_FILE = "/ssd5/rxliu/datasets/KodCode-SFT/kodcode_success_sft_test.jsonl" 
FALLBACK_OUTPUT_FILE = "/ssd5/rxliu/datasets/KodCode-SFT/kodcode_fallback_sft_test.jsonl" 

# API 配置 
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"  
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3-max"

# 进程数配置
MAX_WORKERS = 10 

# ================= 工具函数 =================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def to_python_type(obj):
    """
    递归地将 numpy 类型转换为原生 python 类型，防止 JSON 序列化报错
    """
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

# --- 测试函数区域 ---

class TimeoutException(Exception): pass

def timeout_handler(signum, frame):
    raise TimeoutException

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
            exp_out = exp.strip()
            if user_out == exp_out:
                passed += 1
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

# ================= 主逻辑 =================

def process_single_row(row):
    """
    修改点：
    1. 在返回的 result_data 和 fallback_data 中增加了 'test', 'difficulty' 和 'test_info' 字段。
    """
    row = to_python_type(row)
    question = row['question']
    style = row['style']
    test_code = row['test']  # 获取测试代码
    r1_solution = row['r1_solution']
    
    # 提取 metadata
    test_info = row.get('test_info')
    gpt_difficulty = row.get('gpt_difficulty') 
    
    sys_prompt = get_system_prompt(style)
    # 将 test_info 传入用于构造 Prompt
    user_prompt = construct_user_prompt(question, style, test_info=test_info)
    
    # --- 第一次尝试 ---
    response1 = call_qwen(user_prompt, sys_prompt, temperature=0.5, max_tokens=32768)
    cot1, ans1 = parse_response(response1)
    
    if ans1:
        passed, total, all_passed = run_tests(ans1, test_code, style=style)
        
        if all_passed:
            result_data = {
                "question": question,
                "reasoning": cot1,
                "solution": ans1,
                "pass_rate": 1.0,
                "attempt": 1,
                "config": "temp_0.5",
                # 【保存所有关键元数据】
                "test": test_code,       # 保留测试代码
                "difficulty": gpt_difficulty,
                "test_info": test_info
            }
            return ("success", result_data, "Success (1st try)")
            
    # --- 第二次尝试 ---
    response2 = call_qwen(user_prompt, sys_prompt, temperature=0.8, max_tokens=32768)
    cot2, ans2 = parse_response(response2)
    
    if ans2:
        passed, total, all_passed = run_tests(ans2, test_code, style=style)
        pass_rate = passed / total if total > 0 else 0
        
        if all_passed:
            result_data = {
                "question": question,
                "reasoning": cot2,
                "solution": ans2,
                "pass_rate": 1.0,
                "attempt": 2,
                "config": "temp_0.8",
                # 【保存所有关键元数据】
                "test": test_code,
                "difficulty": gpt_difficulty,
                "test_info": test_info
            }
            return ("success", result_data, "Success (2nd try)")
        
        elif pass_rate > 0.5:
            result_data = {
                "question": question,
                "reasoning": cot2,
                "solution": ans2,
                "pass_rate": pass_rate,
                "attempt": 2,
                "config": "temp_0.8_partial",
                # 【保存所有关键元数据】
                "test": test_code,
                "difficulty": gpt_difficulty,
                "test_info": test_info
            }
            return ("success", result_data, f"Success (2nd try partial {pass_rate:.2f})")
    
    # --- 失败 (Fallback) ---
    fallback_data = {
        "question": question,
        "solution": r1_solution,
        "note": "Failed generation",
        # 【保存所有关键元数据】
        "test": test_code,
        "difficulty": gpt_difficulty,
        "test_info": test_info
    }
    return ("fallback", fallback_data, "Fallback")

def main():
    print(f"Loading data from {INPUT_PATH}...")
    ds = load_from_disk(INPUT_PATH)
    
    # 初始化文件
    open(SUCCESS_OUTPUT_FILE, 'w').close()
    open(FALLBACK_OUTPUT_FILE, 'w').close()
    
    print(f"Starting processing with {MAX_WORKERS} processes...")
    
    data_list = ds.to_pandas().to_dict('records')
    
    # 打开文件句柄，准备写入
    with open(SUCCESS_OUTPUT_FILE, 'a', encoding='utf-8') as f_success, \
         open(FALLBACK_OUTPUT_FILE, 'a', encoding='utf-8') as f_fallback:
        
        # 使用 ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_single_row, row): row for row in data_list}
            
            for future in tqdm(as_completed(futures), total=len(data_list), desc="Processing"):
                try:
                    # 获取子进程返回的结果
                    result_type, data, status_msg = future.result()
                    
                    # 主进程负责写入
                    if result_type == "success":
                        f_success.write(json.dumps(data, ensure_ascii=False) + '\n')
                        f_success.flush() 
                    else:
                        f_fallback.write(json.dumps(data, ensure_ascii=False) + '\n')
                        f_fallback.flush()
                        
                except Exception as e:
                    print(f"Error processing row: {e}")

    print("\nProcessing complete!")
    print(f"Success data saved to: {SUCCESS_OUTPUT_FILE}")
    print(f"Fallback data saved to: {FALLBACK_OUTPUT_FILE}")

if __name__ == "__main__":
    main()