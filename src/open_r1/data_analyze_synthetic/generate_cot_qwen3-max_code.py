import os
import re
import json
import signal
import logging
import pandas as pd
from datasets import load_from_disk
from openai import OpenAI
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import sys
import io
import ast
import contextlib
from io import StringIO

# 导入 prompt 模板
from prompts import get_system_prompt, construct_user_prompt

# ================= 配置区域 =================
INPUT_PATH = "/ssd5/rxliu/datasets/KodCode-V1-SFT-R1/filtered_12k"
SUCCESS_OUTPUT_FILE = "kodcode_success_sft.jsonl" # 满足条件的数据
FALLBACK_OUTPUT_FILE = "kodcode_fallback_sft.jsonl" # 不满足条件的数据

# API 配置 (使用 OpenAI SDK 调用 Qwen)
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"  # 替换为你的 API Key
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3-max"

# 并发设置
MAX_WORKERS = 10  # 并发线程数，根据你的 API Rate Limit 调整

# ================= 工具函数 =================

# 1. API 调用函数
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def call_qwen(prompt, system_prompt):
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': prompt}
            ],
            temperature=0.7, # 稍微有点温度以便第二次生成可能不同
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"API Error: {e}")
        return None

# 2. 内容提取函数 (<think> 和 <answer>)
def parse_response(response_text):
    if not response_text:
        return None, None
    
    # 提取 think
    think_match = re.search(r'<think>(.*?)</think>', response_text, re.DOTALL)
    think_content = think_match.group(1).strip() if think_match else ""
    
    # 提取 answer
    answer_match = re.search(r'<answer>(.*?)</answer>', response_text, re.DOTALL)
    answer_content = answer_match.group(1).strip() if answer_match else ""
    
    # 如果没有标签，尝试清理 markdown 代码块作为 fallback
    if not answer_content:
        # 简单的提取 ```python ... ``` 中的内容
        code_match = re.search(r'```(?:python)?\s*(.*?)```', response_text, re.DOTALL)
        if code_match:
            answer_content = code_match.group(1).strip()
        else:
            # 如果实在没有格式，就把所有非 think 的内容当 answer
            answer_content = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
            
    return think_content, answer_content

# 3. 代码执行与测试函数
# 使用 signal 处理超时，防止死循环
class TimeoutException(Exception): pass

def timeout_handler(signum, frame):
    raise TimeoutException

def run_tests(solution_code, test_code, style, timeout=5):
    """
    根据 style 执行不同类型的测试。
    返回: (passed_count, total_count, all_passed)
    """
    
    # === 场景 A: Online Judge (IO流测试) ===
    if style == 'online_judge':
        return run_io_tests(solution_code, test_code, timeout)
    
    # === 场景 B: Unit Test (Complete / Instruct) ===
    else:
        return run_unit_tests(solution_code, test_code, timeout)

def run_io_tests(solution_code, test_data_str, timeout):
    """
    处理 {'stdin': [], 'stdout': []} 格式的 IO 测试
    """
    try:
        # 解析字典字符串
        test_cases = ast.literal_eval(test_data_str)
        inputs = test_cases['stdin']
        expected_outputs = test_cases['stdout']
        total = len(inputs)
    except Exception as e:
        print(f"IO Test Parse Error: {e}")
        return 0, 1, False # 解析失败算全挂

    passed = 0
    
    for inp, exp in zip(inputs, expected_outputs):
        # 捕获 stdout
        output_buffer = StringIO()
        input_buffer = StringIO(inp)
        
        try:
            # 设置超时
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # 重定向 stdin 和 stdout
            with contextlib.redirect_stdout(output_buffer):
                # 替换 sys.stdin，让 input() 从 input_buffer 读取
                sys.stdin = input_buffer
                # 在新的命名空间运行代码
                exec(solution_code, {'__name__': '__main__'}, {})
            
            signal.alarm(0) # 取消超时
            
            # 获取输出并清洗 (去掉首尾空白)
            user_out = output_buffer.getvalue().strip()
            exp_out = exp.strip()
            
            if user_out == exp_out:
                passed += 1
                
        except Exception:
            signal.alarm(0)
            continue
        finally:
            # 恢复 stdin (contextlib 自动恢复 stdout，但 stdin 需要手动重置)
            sys.stdin = sys.__stdin__

    return passed, total, (passed == total)

def run_unit_tests(solution_code, test_code, timeout):
    """
    处理 def test_xxx(): assert ... 格式的单元测试
    """
    # 1. 清理 Import 语句
    # 因为 solution 就在当前内存里，不需要 import
    # 移除 'from solution import ...' 或 'import solution'
    lines = test_code.split('\n')
    cleaned_lines = [line for line in lines if 'solution' not in line and 'import' not in line]
    cleaned_test_code = '\n'.join(cleaned_lines)

    # 2. 准备执行环境
    global_scope = {}
    
    try:
        # A. 先执行 Solution 代码，把函数定义加载到 global_scope
        exec(solution_code, global_scope)
        
        # B. 再执行 Test 代码（定义测试函数）
        exec(cleaned_test_code, global_scope)
    except Exception as e:
        # 如果定义阶段就错了（语法错误等），直接返回
        return 0, 1, False

    # 3. 寻找所有 test_ 开头的函数
    test_funcs = [name for name in global_scope if name.startswith('test_') and callable(global_scope[name])]
    total = len(test_funcs)
    
    if total == 0:
        # 如果没找到 test 函数，可能是直接写在顶层的 assert
        # 退回到之前的逻辑：尝试直接运行清理后的 test_code
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            exec(cleaned_test_code, global_scope)
            signal.alarm(0)
            return 1, 1, True
        except:
            signal.alarm(0)
            return 0, 1, False

    # 4. 逐个运行测试函数
    passed = 0
    for func_name in test_funcs:
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            # 调用函数，例如 test_max_product_positive_numbers()
            global_scope[func_name]()
            
            signal.alarm(0)
            passed += 1
        except Exception:
            signal.alarm(0)
            continue
            
    return passed, total, (passed == total)

# ================= 主逻辑 =================

# 线程锁，防止写入文件冲突
file_lock = threading.Lock()

def save_record(filename, data):
    with file_lock:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')

def process_single_row(row):
    question = row['question']
    style = row['style']
    test_code = row['test']
    r1_solution = row['r1_solution'] # 用于 fallback
    
    sys_prompt = get_system_prompt(style)
    user_prompt = construct_user_prompt(question, style)
    
    # --- 第一次尝试 ---
    response1 = call_qwen(user_prompt, sys_prompt)
    cot1, ans1 = parse_response(response1)
    
    if ans1:
        passed, total, all_passed = run_tests(ans1, test_code, style=style)
        
        # 条件1: 第一次就全过
        if all_passed:
            save_record(SUCCESS_OUTPUT_FILE, {
                "question": question,
                "reasoning": cot1,
                "solution": ans1,
                "pass_rate": 1.0,
                "attempt": 1
            })
            return "Success (1st try)"
            
    # --- 如果第一次没过，进行第二次尝试 ---
    # 可以在 prompt 中加入“重试”提示，或者仅仅是再次采样
    response2 = call_qwen(user_prompt, sys_prompt) # 这里依赖 temperature=0.7 产生不同结果
    cot2, ans2 = parse_response(response2)
    
    if ans2:
        passed, total, all_passed = run_tests(ans2, test_code, style=style)
        pass_rate = passed / total if total > 0 else 0
        
        # 条件2: 第二次 全过
        if all_passed:
             save_record(SUCCESS_OUTPUT_FILE, {
                "question": question,
                "reasoning": cot2,
                "solution": ans2,
                "pass_rate": 1.0,
                "attempt": 2
            })
             return "Success (2nd try)"
        
        # 条件3: 第二次 没全过但 > 50%
        elif pass_rate > 0.5:
             save_record(SUCCESS_OUTPUT_FILE, {
                "question": question,
                "reasoning": cot2,
                "solution": ans2,
                "pass_rate": pass_rate,
                "attempt": 2
            })
             return f"Success (2nd try partial {pass_rate:.2f})"
    
    # --- 条件4: 两次都失败，保存原始数据 ---
    save_record(FALLBACK_OUTPUT_FILE, {
        "question": question,
        "solution": r1_solution,
        "note": "Failed generation"
    })
    return "Fallback"

def main():
    # 1. 加载数据
    print(f"Loading data from {INPUT_PATH}...")
    ds = load_from_disk(INPUT_PATH)
    
    # 清空/初始化输出文件
    open(SUCCESS_OUTPUT_FILE, 'w').close()
    open(FALLBACK_OUTPUT_FILE, 'w').close()
    
    print(f"Starting processing with {MAX_WORKERS} workers...")
    
    # 2. 并行处理
    # 将 dataset 转为 list of dicts 以便处理
    data_list = ds.to_pandas().to_dict('records')
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 使用 tqdm 显示进度
        futures = {executor.submit(process_single_row, row): row for row in data_list}
        
        for future in tqdm(as_completed(futures), total=len(data_list), desc="Processing"):
            try:
                result = future.result()
                # 可以选择打印 debug 信息，但大量数据时建议注释掉
                # print(result) 
            except Exception as e:
                print(f"Error processing row: {e}")

    print("\nProcessing complete!")
    print(f"Success data saved to: {SUCCESS_OUTPUT_FILE}")
    print(f"Fallback data saved to: {FALLBACK_OUTPUT_FILE}")

if __name__ == "__main__":
    main()
