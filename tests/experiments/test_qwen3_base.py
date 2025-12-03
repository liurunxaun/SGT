import pandas as pd
import os
import sys
import json
import re
import subprocess
import traceback

# ================= 0. 环境设置 =================
# 添加工具路径 (根据你的环境)
sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")
from inference_sglang import inference_sglang

# ================= 1. 参数配置 =================
# 模型信息 (仅作文件名标识)
MODEL_NAME = "Qwen3-8B-Base"
TIME_TAG = "20251203-SimplePrompt"

# 服务器端口 (必须与 launch_server 的 --port 30000 一致)
SERVER_PORT = 30000

# 数据集路径
DATASET_PATH = "/ssd5/rxliu/datasets/humanevalplus/humaneval_test.parquet"
DATASET_NAME = "HumanEvalPlus"
EVALPLUS_TYPE = "humaneval"

# 推理参数
TEMPERATURE = 0.6
MAX_TOKENS = 32768
QUERY_FIELD = "prompt"

# 输出路径 (保存到 SSD5)
BASE_OUTPUT_DIR = "/ssd5/rxliu/projects/open-r1-main/results"
if not os.path.exists(BASE_OUTPUT_DIR):
    os.makedirs(BASE_OUTPUT_DIR)

INFERENCE_OUTPUT = f"{BASE_OUTPUT_DIR}/inference-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.xlsx"
SAMPLES_JSONL = f"{BASE_OUTPUT_DIR}/samples-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.jsonl"

# ================= 2. System Prompt (基础版) =================
# 针对 Base 模型，不需要复杂的 XML 思考标签，直接明确要求输出代码即可
SYSTEM_PROMPT = """You are a helpful AI Assistant.
Please solve the following coding problem in Python.
Wrap your code in a markdown block, like:
```python
def function_name(...):
    ...
```"""

# ================= 3. 代码清洗函数 =================
def sanitize_code(text):
    """清洗模型输出：提取 Markdown 代码块"""
    if not isinstance(text, str):
        return ""

    # 策略 1: 提取 ```python ... ```
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 策略 2: 提取通用 ``` ... ```
    match_gen = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if match_gen:
        return match_gen.group(1).strip()

    # 策略 3: 如果完全没有 Markdown，尝试返回原文本 (Base 模型有时会直接续写代码)
    return text.strip()


# ================= 4. 主程序 =================
def main():
    print(f"=== 任务: {MODEL_NAME} (Port={SERVER_PORT}) ===")
    print(f"=== 结果保存路径: {BASE_OUTPUT_DIR} ===")

    # ---------------- Step 1: 推理 ----------------
    print(f"\n>>> [1/3] Sglang 推理...")

    try:
        # 注意：这里调用 inference_sglang
        inference_sglang(
            DATASET_PATH,
            SYSTEM_PROMPT,
            QUERY_FIELD,
            "canonical_solution",  # 占位符
            INFERENCE_OUTPUT,
            MODEL_NAME,
            TEMPERATURE,
            MAX_TOKENS
            # , port=SERVER_PORT  # <-- 如需端口参数，确认 inference_sglang 是否支持
        )
    except Exception as e:
        print(f"❌ 推理阶段发生错误: {e}")
        print("提示: 请检查 Server 是否已在 30000 端口启动。")
        return

    # ---------------- Step 2: 格式转换 & 修复 ----------------
    print(f"\n>>> [2/3] 转换为 JSONL (含 task_id 修复)...")
    if not os.path.exists(INFERENCE_OUTPUT):
        print(f"❌ 找不到推理结果文件: {INFERENCE_OUTPUT}")
        return

    try:
        df = pd.read_excel(INFERENCE_OUTPUT)

        # === 核心修复: 找回丢失的 task_id ===
        if "task_id" not in df.columns:
            print("⚠️ 正在从原始数据恢复 task_id...")
            df_src = pd.read_parquet(DATASET_PATH)

            if len(df) == len(df_src):
                # 假设顺序未乱，直接按行索引对应
                df["task_id"] = df_src["task_id"].values
                print("✅ task_id 恢复成功。")
            else:
                print(f"❌ 行数不匹配 (结果 {len(df)} vs 原数据 {len(df_src)})，无法恢复。")
                return
        # ===================================

        # 确定预测结果所在的列
        pred_col = "predicted_answer"
        if pred_col not in df.columns:
            candidates = [c for c in df.columns if "pred" in c or "output" in c]
            if candidates:
                pred_col = candidates[0]

        samples = []
        for _, row in df.iterrows():
            clean_code = sanitize_code(row.get(pred_col, ""))
            samples.append(
                {
                    "task_id": row["task_id"],
                    "completion": clean_code,
                }
            )

        with open(SAMPLES_JSONL, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")
        print(f"✅ JSONL 已生成: {SAMPLES_JSONL}")

    except Exception as e:
        print(f"❌ 转换过程出错: {e}")
        traceback.print_exc()
        return

    # ---------------- Step 3: 评测 ----------------
    print(f"\n>>> [3/3] 运行 EvalPlus ({EVALPLUS_TYPE})...")

    cmd = [
        "evalplus.evaluate",
        "--dataset",
        EVALPLUS_TYPE,
        "--samples",
        SAMPLES_JSONL,
    ]

    print(f"执行命令: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print("\n✅ 评测完成！请查看生成在同目录下的 _eval_results.json 文件")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ EvalPlus 运行失败 (Code {e.returncode})")


if __name__ == "__main__":
    main()
