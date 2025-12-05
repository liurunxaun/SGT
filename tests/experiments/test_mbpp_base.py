import os
import sys
import json
import re
import subprocess
import traceback
import pandas as pd

# ================= 0. 环境设置 =================
sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")
from inference_sglang import inference_sglang

# ================= 1. 参数配置 =================
MODEL_NAME = "Qwen3-8B-Base"
# 改个名字，避免和旧文件混淆
TIME_TAG = "20251204-MbppPlus-PromptTrigger" 

SERVER_PORT = 30000
DATASET_PATH = "/ssd5/rxliu/datasets/mbppplus/data/test-00000-of-00001-d5781c9c51e02795.parquet"
DATASET_NAME = "MbppPlus"

# 按你的要求保持 32768
MAX_TOKENS = 32768 
# Base 模型建议低温，0.0 或 0.2
TEMPERATURE = 0.0  

BASE_OUTPUT_DIR = "/ssd5/rxliu/projects/open-r1-main/results"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

INFERENCE_OUTPUT = f"{BASE_OUTPUT_DIR}/inference-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.xlsx"
SAMPLES_JSONL = f"{BASE_OUTPUT_DIR}/samples-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.jsonl"

# ================= 3. 代码清洗函数 =================
def sanitize_code(text: str) -> str:
    """
    针对 Base 模型 + 强制 Prompt 的清洗策略。
    因为 Prompt 结尾已经是 ```python，模型输出的通常直接是代码。
    我们主要负责清理结尾的 markdown 闭合符和可能的废话。
    """
    if not isinstance(text, str):
        return ""
    
    text = text.strip()
    
    # 1. 去掉结尾的 ``` (不管是不是 python)
    text = re.sub(r"```.*$", "", text, flags=re.DOTALL).strip()
    
    # 2. 如果模型还是输出了 <answer> 标签 (Qwen 系列特性)，提取内部
    pattern_answer = r"<answer>\s*(.*?)\s*</answer>"
    match = re.search(pattern_answer, text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1).strip()
        
    return text

# ================= 4. 主程序 =================
def main():
    print(f"=== 任务: {MODEL_NAME} (Base Mode with Prompt Trigger) ===")
    print(f"=== Port: {SERVER_PORT} | Max Tokens: {MAX_TOKENS} ===")
    
    # ---------------- Step 0: 预处理 Prompt (核心修复) ----------------
    print(f"\n>>> [0/3] 构建 Base 模型专用 Prompt...")
    try:
        df = pd.read_parquet(DATASET_PATH)
        
        # 【核心修改】
        # 给每个 prompt 后面强行拼接 "\n```python\n"
        # 这样模型会以为它正在补全一个 Markdown 代码块，从而直接输出代码
        df["engineered_prompt"] = df["prompt"].apply(
            lambda x: f'{x}\n\n```python\n'
        )
        
        # 保存一个临时文件供 Sglang 读取
        temp_parquet = f"{BASE_OUTPUT_DIR}/temp_input_mbpp_base.parquet"
        df.to_parquet(temp_parquet)
        print(f"✅ 临时 Prompt 文件已生成: {temp_parquet}")
        
    except Exception as e:
        print(f"❌ 数据预处理失败: {e}")
        return

    # ---------------- Step 1: 推理 ----------------
    print(f"\n>>> [1/3] Sglang 推理...")
    try:
        inference_sglang(
            temp_parquet,            # 使用处理过的数据
            "",                      # System Prompt 留空 (靠 engineered_prompt 引导)
            "engineered_prompt",     # 使用我们构造的带 trigger 的列
            "code",                  
            INFERENCE_OUTPUT,
            MODEL_NAME,
            TEMPERATURE,
            MAX_TOKENS,
        )
    except Exception as e:
        print(f"❌ 推理错误: {e}")
        return

    # ---------------- Step 2: 转换 JSONL ----------------
    print(f"\n>>> [2/3] 转换为 JSONL...")
    if not os.path.exists(INFERENCE_OUTPUT):
        print("❌ 推理文件未生成")
        return

    try:
        df_pred = pd.read_excel(INFERENCE_OUTPUT)
        
        # 恢复 task_id (从原始 df 拿，防止顺序错乱或丢失)
        if len(df_pred) == len(df):
            df_pred["task_id"] = df["task_id"].values
        else:
            print(f"❌ 行数不匹配 (Pred: {len(df_pred)} vs Src: {len(df)})，尝试通过 merge 恢复...")
            # 如果真的行数不对，这里需要更复杂的 merge，但通常 sglang 保持顺序
            # 简单处理：报错退出，避免错位
            return

        # 找预测列
        pred_col = None
        for col in df_pred.columns:
            if "pred" in str(col).lower() or "output" in str(col).lower():
                pred_col = col
                break
        
        if not pred_col:
            print("❌ 找不到预测列")
            return

        samples = []
        for _, row in df_pred.iterrows():
            raw_tid = str(row["task_id"])
            # 确保格式是 Mbpp/123
            tid = raw_tid if raw_tid.startswith("Mbpp/") else f"Mbpp/{raw_tid}"
            
            # 获取生成的代码
            generated = str(row.get(pred_col, ""))
            
            # 清洗
            clean_code = sanitize_code(generated)
            
            samples.append({"task_id": tid, "completion": clean_code})

        with open(SAMPLES_JSONL, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"✅ JSONL 生成完毕: {SAMPLES_JSONL}")
        
    except Exception as e:
        print(f"❌ 转换 JSONL 失败: {e}")
        traceback.print_exc()
        return

    # ---------------- Step 3: 评测 ----------------
    print(f"\n>>> [3/3] 运行 EvalPlus...")
    
    # 【强制删除缓存】防止读取旧的 0 分结果
    cache_file = SAMPLES_JSONL.replace(".jsonl", "_eval_results.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("🗑️  已删除旧的评测缓存文件，强制重测。")

    cmd = ["evalplus.evaluate", "--dataset", "mbpp", "--samples", SAMPLES_JSONL]
    
    print(f"执行命令: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print("\n✅ 评测流程结束！")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ EvalPlus 运行报错 (Code {e.returncode})")

if __name__ == "__main__":
    main()

