import json
import re
import sys
from pathlib import Path
from typing import Tuple
import packaging.version

from datasets import load_from_disk
import torch
import transformers
from transformers import AutoTokenizer, AutoModelForCausalLM

# ====== 0. 环境版本检查 ======
required_version = "4.37.0" # 放宽一点限制，但建议越新越好
if packaging.version.parse(transformers.__version__) < packaging.version.parse(required_version):
    print(f"⚠️  Warning: transformers version {transformers.__version__} is low.")

# ====== 配置区 ======

# 数据集路径
HUMANEVALPLUS_DISK_DIR = "/ssd5/rxliu/datasets/humanevalplus"

# 模型路径
MODEL_PATH = "/ssd5/rxliu/models/Qwen3-8B" 

# 输出文件 1: 评测用 (纯净代码)
OUTPUT_JSONL = "/data/home/the/rxliu/projects/open-r1-main/tests/coding/samples_humanevalplus_qwen3_instruct_11.27_2.jsonl"

# 输出文件 2: 调试日志 (Markdown, 包含 Prompt 和 思考过程)
OUTPUT_LOG_MD = "/data/home/the/rxliu/projects/open-r1-main/tests/coding/samples_humanevalplus_qwen3_instruct_11.27_2.md"

# 参数配置
MAX_NEW_TOKENS = 32768 
TEMPERATURE = 0.6 
TOP_P = 0.95 

# ====== 加载模型 ======
print(f"Loading Qwen3 model from {MODEL_PATH} ...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto",
    trust_remote_code=True,
)
model.eval()

def extract_final_code(text: str) -> str:
    """清洗代码用于评测"""
    # 1. 移除 <think> 标签内容
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    
    # 2. 提取 Python 代码块
    pattern = re.compile(r'```python\n(.*?)```', re.DOTALL)
    matches = pattern.findall(clean_text)
    
    if matches:
        return matches[-1].strip()
    
    pattern_generic = re.compile(r'```\n(.*?)```', re.DOTALL)
    matches_generic = pattern_generic.findall(clean_text)
    if matches_generic:
        return matches_generic[-1].strip()
        
    return clean_text

def gen_qwen3_solution(humaneval_prompt: str) -> Tuple[str, str, str]:
    """
    返回三个值: 
    1. solution (用于评测的纯代码)
    2. full_response (模型生成的原始文本，含 think)
    3. actual_input (喂给模型的实际 Prompt 字符串)
    """
    
    content = f"""Please complete the following Python function.
Note: You must wrap the code in ```python ... ``` blocks.

{humaneval_prompt}"""

    messages = [
        {"role": "user", "content": content}
    ]
    
    # 尝试应用模板
    try:
        text_input = tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True,
            # enable_thinking=True # 如果报错不支持，请注释掉这行
        )
    except TypeError:
        text_input = tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True
        )
    
    inputs = tokenizer(text_input, return_tensors="pt").to(model.device)
    input_len = inputs.input_ids.shape[1]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][input_len:]
    full_response = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # 提取纯代码
    clean_code = extract_final_code(full_response)
    
    if "def " in clean_code:
        solution = clean_code
    else:
        solution = humaneval_prompt + "\n" + clean_code

    return solution, full_response, text_input

# ====== 主函数 ======

def main():
    print(f"Loading HumanEval+ from {HUMANEVALPLUS_DISK_DIR} ...")
    ds = load_from_disk(HUMANEVALPLUS_DISK_DIR)
    test_set = ds["test"]

    out_path = Path(OUTPUT_JSONL)
    log_path = Path(OUTPUT_LOG_MD)
    
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 断点续跑
    finished_task_ids = set()
    if out_path.exists():
        print(f"Checking progress in {out_path}...")
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        finished_task_ids.add(data["task_id"])
                    except: pass
        print(f"Found {len(finished_task_ids)} completed samples.")

    open_mode = "a" if len(finished_task_ids) > 0 else "w"
    
    # 同时打开 JSONL 和 Markdown 文件
    with out_path.open(open_mode, encoding="utf-8") as f_json, \
         log_path.open(open_mode, encoding="utf-8") as f_md:
        
        # 如果是新文件，写个 Markdown 标题
        if open_mode == "w":
            f_md.write("# Qwen3 Testing Log\n\nGenerated outputs with prompts and thinking process.\n\n")

        for i, problem in enumerate(test_set):
            task_id = problem["task_id"]
            if task_id in finished_task_ids:
                continue

            print(f"[{i+1}/{len(test_set)}] Generating for {task_id} ...")
            
            try:
                # 获取 solution (评测用), raw_resp (日志用), prompt_str (日志用)
                solution, raw_resp, prompt_str = gen_qwen3_solution(problem["prompt"])
                
                # 1. 写入 JSONL
                sample = {"task_id": task_id, "solution": solution}
                f_json.write(json.dumps(sample, ensure_ascii=False) + "\n")
                f_json.flush()
                
                # 2. 写入 Markdown 日志
                # 使用 Markdown 的代码块和引用格式，阅读体验很好
                f_md.write(f"## Task: {task_id}\n\n")
                
                f_md.write(f"### 📥 Input Prompt\n")
                f_md.write(f"```text\n{prompt_str}\n```\n\n")
                
                f_md.write(f"### 📤 Model Output\n")
                # 如果有 think 标签，Markdown 渲染通常能直接显示，或者用引用块包裹
                f_md.write(f"> **Raw Response:**\n\n")
                f_md.write(f"{raw_resp}\n\n")
                
                f_md.write(f"### 🐍 Extracted Solution\n")
                f_md.write(f"```python\n{solution}\n```\n")
                
                f_md.write(f"\n---\n\n") # 分隔线
                f_md.flush()

            except Exception as e:
                print(f"  !! Error: {e}")
                f_md.write(f"## Task: {task_id} - ERROR\n`{str(e)}`\n\n---\n\n")

    print(f"Done! \nJSONL saved to: {out_path}\nMarkdown Log saved to: {log_path}")

if __name__ == "__main__":
    main()