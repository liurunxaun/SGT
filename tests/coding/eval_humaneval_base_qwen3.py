import json
from pathlib import Path
from typing import Dict, Any

from datasets import load_from_disk
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ====== 配置区 ======

# 数据集路径
HUMANEVALPLUS_DISK_DIR = "/ssd5/rxliu/datasets/humanevalplus"

# ⚠️ Base 模型路径
MODEL_PATH = "/ssd5/rxliu/models/Qwen3-8B" 

# 输出文件路径
OUTPUT_JSONL = "/data/home/the/rxliu/projects/open-r1-main/tests/coding/samples_humanevalplus_base_qwen3.jsonl"

# Base 模型配置
MAX_NEW_TOKENS = 2048 
DO_SAMPLE = False # 贪心解码

# ====== 加载模型 ======
print(f"Loading BASE model from {MODEL_PATH} ...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    device_map="auto",
    trust_remote_code=True,
)
model.eval()

def gen_base_solution(humaneval_prompt: str) -> str:
    """
    Base 模型的生成逻辑：零样本补全 (Zero-shot Completion)
    不使用 Chat Template，直接喂入代码前缀。
    """
    
    # 直接把函数签名作为输入
    inputs = tokenizer(humaneval_prompt, return_tensors="pt").to(model.device)
    input_len = inputs.input_ids.shape[1]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=DO_SAMPLE,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id, # 防止警告
        )

    # 只解码新生成的内容
    generated_ids = outputs[0][input_len:]
    generated_code = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # 拼接 Prompt + 生成内容作为最终 Solution
    solution = humaneval_prompt + generated_code

    return solution

# ====== 主函数 ======

def main():
    print(f"Loading HumanEval+ from {HUMANEVALPLUS_DISK_DIR} ...")
    ds = load_from_disk(HUMANEVALPLUS_DISK_DIR)
    test_set = ds["test"]

    out_path = Path(OUTPUT_JSONL)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ====== 1. 扫描已完成任务 (基于 task_id 的断点续跑) ======
    finished_task_ids = set()
    if out_path.exists():
        print(f"Checking existing progress in {out_path}...")
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if "task_id" in data:
                            finished_task_ids.add(data["task_id"])
                    except json.JSONDecodeError:
                        pass
        print(f"Found {len(finished_task_ids)} completed samples. Resuming...")

    # 决定打开模式：'a' (追加) 或 'w' (新建)
    open_mode = "a" if len(finished_task_ids) > 0 else "w"
    
    # 进度提示
    remaining_count = len(test_set) - len(finished_task_ids)
    if remaining_count <= 0:
        print("All tasks finished.")
        return
    print(f"Generating for remaining {remaining_count} tasks ...")

    # ====== 2. 打开文件并循环 ======
    # Base 模型不需要 Log 和 Node 文件，只需要一个 JSONL
    with out_path.open(open_mode, encoding="utf-8") as f:
        for i, problem in enumerate(test_set):
            task_id = problem["task_id"]
            
            # 跳过已完成
            if task_id in finished_task_ids:
                continue

            prompt = problem["prompt"]
            print(f"[{i+1}/{len(test_set)}] Generating for {task_id} ...")
            
            try:
                solution = gen_base_solution(prompt)
            except Exception as e:
                print(f"  !! Error when generating for {task_id}: {e}")
                solution = "" # 出错时留空，避免程序中断，后续可手动补测

            sample = {
                "task_id": task_id,
                "solution": solution,
            }
            
            # 写入并强制保存
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            f.flush()

    print(f"Done! Base model results saved to {out_path}")

if __name__ == "__main__":
    main()