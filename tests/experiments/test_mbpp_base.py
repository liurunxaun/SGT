import os
import sys
import json
import re
import subprocess
import traceback
import pandas as pd

# ================= 0. 环境设置 =================
# TODO: 请确认此路径是否存在
UTILS_PATH = "/data/home/the/rxliu/projects/open-r1-main/tests/utils"

if os.path.exists(UTILS_PATH):
    sys.path.append(UTILS_PATH)
else:
    print(f"⚠️ 警告: 找不到工具路径 {UTILS_PATH}")

try:
    from inference_sglang import inference_sglang
except ImportError:
    # 占位防止IDE报错
    def inference_sglang(*args, **kwargs):
        raise ImportError("inference_sglang not found")

# ================= 1. 参数配置 =================
MODEL_NAME = "Qwen3-8B-Base"
# 标记为 CoT 版本
TIME_TAG = "20251204-MbppPlus-CoT-V1" 

SERVER_PORT = 30000
DATASET_PATH = "/ssd5/rxliu/datasets/mbppplus/data/test-00000-of-00001-d5781c9c51e02795.parquet"

# CoT 需要更长的输出长度
MAX_TOKENS = 32768 
# 允许一点温度以激发推理
TEMPERATURE = 0.6  

BASE_OUTPUT_DIR = "/ssd5/rxliu/projects/open-r1-main/results"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

INFERENCE_OUTPUT = f"{BASE_OUTPUT_DIR}/inference-{MODEL_NAME}-{TIME_TAG}.jsonl"
SAMPLES_JSONL = f"{BASE_OUTPUT_DIR}/samples-{MODEL_NAME}-{TIME_TAG}.jsonl"
TEMP_PARQUET = f"{BASE_OUTPUT_DIR}/temp_input_cot.parquet"

# ================= 3. 辅助函数 =================

def get_function_signature(code_snippet):
    """从参考代码中提取函数签名 (def xxx(...):)"""
    if not isinstance(code_snippet, str):
        return None
    match = re.search(r"^\s*(def\s+.*?:)", code_snippet, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None

def sanitize_code_cot(text):
    """
    参考 HumanEval 的方式：使用正则提取 Markdown 代码块。
    这允许模型先输出思考过程，再输出代码。
    """
    if not isinstance(text, str):
        return ""

    # 策略 1: 提取标准 ```python ... ```
    # re.DOTALL 让 . 匹配换行符，re.IGNORECASE 忽略大小写
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 策略 2: 提取通用 ``` ... ``` (有些模型可能忘写 python 标签)
    match_gen = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match_gen:
        return match_gen.group(1).strip()

    # 策略 3: 如果提取不到 Block，但内容里有 def，可能模型没写 markdown
    # 对于 CoT 来说这比较危险，因为可能包含解释性文字，但作为兜底：
    if "def " in text:
        return text.strip()
        
    return ""

# ================= 4. 主程序 =================
def main():
    print(f"=== 任务: {MODEL_NAME} (Chain of Thought Mode) ===")
    
    # ---------------- Step 0: 预处理 Prompt (CoT) ----------------
    print(f"\n>>> [0/3] 构建 CoT Prompt...")
    
    # 强制重新生成 Prompt
    try:
        if not os.path.exists(DATASET_PATH):
            print(f"❌ 错误: 数据集路径不存在: {DATASET_PATH}")
            return

        df = pd.read_parquet(DATASET_PATH)
        ref_col = "code" if "code" in df.columns else "canonical_solution"
        
        def construct_cot_prompt(row):
            prompt_text = row["prompt"]
            ref_code = row[ref_col]
            
            # 我们仍然需要提取签名，告诉模型我们要什么函数名
            # 否则 EvalPlus 评测时找不到对应的函数入口会报错
            signature = get_function_signature(ref_code)
            if not signature:
                signature = "a function" # 兜底

            # === CoT Prompt 模板 ===
            # 这里不再强行接续，而是给出指令
            return (
                f"You are an expert Python programmer.\n"
                f"Please solve the following problem.\n"
                f"Problem: {prompt_text}\n\n"
                f"Requirements:\n"
                f"1. You must use this function signature: `{signature}`\n"
                f"2. Think step by step about the logic before coding.\n"
                f"3. Wrap your final code in a ```python markdown block.\n"
            )

        df["engineered_prompt"] = df.apply(construct_cot_prompt, axis=1)
        
        # 保存带有 CoT Prompt 的临时文件
        df.to_parquet(TEMP_PARQUET)
        print(f"✅ CoT Prompt 构建完成: {TEMP_PARQUET}")
        
    except Exception as e:
        print(f"❌ 预处理失败: {e}")
        traceback.print_exc()
        return

    # ---------------- Step 1: 推理 ----------------
    print(f"\n>>> [1/3] Sglang 推理...")
    if not os.path.exists(INFERENCE_OUTPUT):
        try:
            inference_sglang(
                TEMP_PARQUET,
                "",                    # System Prompt
                "engineered_prompt",   # 使用新的 CoT Prompt 列
                "code",
                INFERENCE_OUTPUT,
                MODEL_NAME,
                TEMPERATURE,
                MAX_TOKENS,
            )
        except Exception as e:
            print(f"❌ 推理错误: {e}")
            return
    else:
        print(f"⚠️ 检测到结果文件已存在，跳过推理: {INFERENCE_OUTPUT}")

    # ---------------- Step 2: 提取代码 (Regex Extraction) ----------------
    print(f"\n>>> [2/3] 从思维链中提取代码...")
    if not os.path.exists(INFERENCE_OUTPUT):
        print("❌ 推理文件未生成")
        return

    try:
        df_pred = pd.read_json(INFERENCE_OUTPUT, lines=True)
        df_src = pd.read_parquet(TEMP_PARQUET)

        # === 强制对齐 Task ID (防止 Sglang 丢列) ===
        if "task_id" not in df_pred.columns:
            print("⚠️ 警告: 推理结果缺少 task_id，正在执行行对齐...")
            if len(df_pred) == len(df_src):
                df_pred["task_id"] = df_src["task_id"].values
            else:
                print(f"❌ 行数不匹配 ({len(df_pred)} vs {len(df_src)})，无法对齐！")
                return

        samples = []
        
        # 查找输出列
        pred_col = None
        candidates = ["text", "output", "pred", "completion", "generated_text"]
        for col in df_pred.columns:
            if any(c in str(col).lower() for c in candidates):
                pred_col = col
                break
        
        if not pred_col:
            print(f"❌ 找不到预测列: {df_pred.columns}")
            return
        
        print(f"✅ 使用列 '{pred_col}' 进行提取")

        for _, row in df_pred.iterrows():
            raw_tid = str(row["task_id"])
            tid = raw_tid if raw_tid.startswith("Mbpp/") else f"Mbpp/{raw_tid}"
            
            # 获取包含 CoT 的完整输出
            raw_output = str(row.get(pred_col, ""))
            
            # === 关键修改：使用正则提取 ===
            final_code = sanitize_code_cot(raw_output)
            
            # 如果提取失败（比如空字符串），可能模型没写代码，或者格式极度错误
            # 这种情况下 EvalPlus 会判错，符合预期
            samples.append({"task_id": tid, "completion": final_code})

        with open(SAMPLES_JSONL, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"✅ JSONL 生成完毕: {SAMPLES_JSONL}")
        
    except Exception as e:
        print(f"❌ 提取阶段出错: {e}")
        traceback.print_exc()
        return

    # ---------------- Step 3: 评测 ----------------
    print(f"\n>>> [3/3] 运行 EvalPlus...")
    
    cache_file = SAMPLES_JSONL.replace(".jsonl", "_eval_results.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)

    # 使用 sys.executable 确保环境正确
    cmd = [sys.executable, "-m", "evalplus.evaluate", "--dataset", "mbpp", "--samples", SAMPLES_JSONL]
    
    print(f"执行命令: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ EvalPlus 运行报错: {e}")

if __name__ == "__main__":
    main()