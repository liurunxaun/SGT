import json
import re
from pathlib import Path
from typing import Dict, Any, Tuple

from datasets import load_from_disk
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ====== 配置区 ======

HUMANEVALPLUS_DISK_DIR = "evalplus_data/humanevalplus"
# 你的模型路径
MODEL_PATH = "/ssd5/rxliu/models/Qwen3-8B" 

# 1. 给评测工具用的文件
OUTPUT_JSONL = "samples_humaneval_structured_cot.jsonl"
# 2. 给你肉眼看思维过程的文件 (Markdown格式)
OUTPUT_READABLE_FILE = "read_thoughts.md"

# 调试模式：只跑前 10 个来看看，看完觉得没问题再跑全量
DEBUG_LIMIT = 5

MAX_NEW_TOKENS = 4096 
TEMPERATURE = 0.0
TOP_P = 1.0

# ====== System Prompt (保持不变) ======
SYSTEM_PROMPT = """You are a helpful AI Assistant... (这里太长了，请保留你之前完整的System Prompt内容，不要删减) ..."""
# 为了代码简洁，这里我省略了那一大段，实际运行请务必填入你完整的 Prompt
# ... (省略) ...

ONE_SHOT_EXAMPLE_USER = """Implement a function `is_even(n)` that returns True if n is even."""
ONE_SHOT_EXAMPLE_ASSISTANT = """<think>
{
    "node_id": 1,
    "parents": ["none"],
    "content": "known: The goal is to check if an integer n is divisible by 2.",
    "tag": "known"
}
{
    "node_id": 2,
    "parents": [1],
    "content": "generate: To check divisibility by 2, I can use the modulo operator %. If n % 2 == 0, it is even.",
    "tag": "generate"
}
{
    "node_id": 3,
    "parents": [2],
    "content": "refine: The function should return a boolean value. The expression n % 2 == 0 evaluates to a boolean.",
    "tag": "refine"
}
</think>
<answer>
def is_even(n):
    return n % 2 == 0
</answer>"""


# ====== 加载模型 ======
print(f"Loading model from {MODEL_PATH} ...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto",
    trust_remote_code=True,
)
model.eval()

# ====== 提取逻辑 ======

def extract_answer(text: str) -> str:
    match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
    else:
        content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        content = content.replace('<answer>', '').strip()
    
    content = re.sub(r'^```python', '', content, flags=re.MULTILINE)
    content = re.sub(r'^```', '', content, flags=re.MULTILINE)
    return content.strip()

# !!! 修改点 1: 返回值改为元组 (Clean Solution, Raw Full Text)
def gen_solution(humaneval_prompt: str) -> Tuple[str, str]:
    user_target_content = f"""Please complete the following Python function. 
Apply the graph-structured reasoning format (nodes, edges, tags) learned from math problems to this coding problem.
Analyze the logic first in <think>, then output code in <answer>.

Problem:
{humaneval_prompt}"""
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": ONE_SHOT_EXAMPLE_USER},
        {"role": "assistant", "content": ONE_SHOT_EXAMPLE_ASSISTANT},
        {"role": "user", "content": user_target_content}
    ]
    
    text_input = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text_input, return_tensors="pt").to(model.device)
    input_len = inputs.input_ids.shape[1]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=(TEMPERATURE > 0),
            temperature=TEMPERATURE,
            top_p=TOP_P,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][input_len:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # 提取代码
    final_code_body = extract_answer(generated_text)
    
    if "def " in final_code_body:
        solution = final_code_body
    else:
        solution = humaneval_prompt + "\n" + final_code_body

    # 返回 (清洗后的代码, 原始的包含思考过程的文本)
    return solution, generated_text

# ====== 主函数 ======

def main():
    print(f"Loading HumanEval+ from {HUMANEVALPLUS_DISK_DIR} ...")
    ds = load_from_disk(HUMANEVALPLUS_DISK_DIR)
    test_set = ds["test"]

    out_path = Path(OUTPUT_JSONL)
    readable_path = Path(OUTPUT_READABLE_FILE) # 这是一个 Markdown 文件

    print(f"Running... Limit: {DEBUG_LIMIT}")

    # 同时打开两个文件
    with out_path.open("w", encoding="utf-8") as f_json, \
         readable_path.open("w", encoding="utf-8") as f_md:
        
        # 写 Markdown 文件的头
        f_md.write(f"# HumanEval Graph CoT Inspection Log\n\n")

        for i, problem in enumerate(test_set):
            if DEBUG_LIMIT and i >= DEBUG_LIMIT:
                break

            task_id = problem["task_id"]
            prompt = problem["prompt"]

            print(f"[{i+1}] Generating for {task_id} ...")
            try:
                # !!! 修改点 2: 接收两个返回值
                solution, raw_text = gen_solution(prompt)
            except Exception as e:
                print(f"Error: {e}")
                solution = ""
                raw_text = "ERROR GENERATING"

            # 1. 存 JSONL (为了 EvalPlus 评测)
            # 技巧：我在里面加了一个 extra 字段存 raw_text，EvalPlus 会忽略它，但你可以用来查
            sample = {
                "task_id": task_id,
                "solution": solution,
                "raw_output": raw_text 
            }
            f_json.write(json.dumps(sample, ensure_ascii=False) + "\n")

            # !!! 修改点 3: 存 Markdown (为了人类阅读)
            f_md.write(f"## Task: {task_id}\n")
            f_md.write(f"### Problem Prompt\n```python\n{prompt}\n```\n\n")
            
            # 这里我们尝试稍微美化一下 JSON 节点的显示 (可选)
            f_md.write(f"### Model Graph CoT & Answer\n")
            # 把 raw_text 直接写进去，因为里面包含了 <think> 和 <answer>
            # 使用 blockquote (引用) 格式或者 code block 格式
            f_md.write(f"```text\n{raw_text}\n```\n") 
            
            f_md.write(f"\n---\n\n") # 分割线

    print(f"Done! \n1. Eval file: {OUTPUT_JSONL} \n2. Readable file: {OUTPUT_READABLE_FILE}")

if __name__ == "__main__":
    main()