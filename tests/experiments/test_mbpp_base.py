import os
import sys
import json
import re
import subprocess
import traceback

import pandas as pd

# ================= 0. 环境设置 =================
# 添加工具路径 (根据你的项目结构)
sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")
from inference_sglang import inference_sglang


# ================= 1. 参数配置 =================

MODEL_NAME = "Qwen3-8B-Base"
TIME_TAG = "20251203-MbppPlus-Fixed-V2"

# 端口 (和你启动 sglang server 时一致)
SERVER_PORT = 30000

# MBPP+ Parquet 数据路径（HF 的 evalplus/mbppplus）
DATASET_PATH = "/ssd5/rxliu/datasets/mbppplus/data/test-00000-of-00001-d5781c9c51e02795.parquet"
DATASET_NAME = "MbppPlus"
EVALPLUS_TYPE = "mbpp"  # 目前只用于标识

# 推理参数
TEMPERATURE = 0.2          # 建议 Base 模型用低温，减少瞎改函数名
MAX_TOKENS =  32768        # MBPP 题目代码量不大，不用 3w 这么夸张

# 输入列：在 parquet 里用作 prompt 的列
# 对 HF 的 mbppplus 来说，prompt 是自然语言描述，不带 def 行，没关系
QUERY_FIELD = "prompt"

# 输出路径
BASE_OUTPUT_DIR = "/ssd5/rxliu/projects/open-r1-main/results"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

INFERENCE_OUTPUT = f"{BASE_OUTPUT_DIR}/inference-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.xlsx"
SAMPLES_JSONL = f"{BASE_OUTPUT_DIR}/samples-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.jsonl"

# ================= 2. System Prompt =================
# 对 Base 模型做 code completion，尽量不用 chat 风格 prompt
SYSTEM_PROMPT = ""


# ================= 3. 代码清洗函数 =================

def sanitize_code(text: str) -> str:
    """
    对模型生成的代码做轻量清洗：
    - 去掉 markdown ``` 包裹
    - 去掉可能的前后多余空行
    不做过度处理，避免误删合法代码。
    """
    if not isinstance(text, str):
        return ""

    # 去掉 ```python 或 ``` 包裹
    text = re.sub(r"^```python\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text.strip())

    return text.strip()


# ================= 4. 主程序 =================

def main():
    print(f"=== 任务: {MODEL_NAME} on {DATASET_NAME} (Base Model for MBPP+) ===")
    print(f"=== 数据路径: {DATASET_PATH} ===")

    # ---------------- Step 1: 推理 ----------------
    print(f"\n>>> [1/3] Sglang 推理 (Port {SERVER_PORT})...")
    try:
        inference_sglang(
            DATASET_PATH,    # 包含 task_id / prompt / code 等
            SYSTEM_PROMPT,   # 这里传空字符串
            QUERY_FIELD,     # 用 parquet 里的 prompt 列作为输入
            "code",          # 让 inference_sglang 把输出写到一个列，名字不重要
            INFERENCE_OUTPUT,
            MODEL_NAME,
            TEMPERATURE,
            MAX_TOKENS,
        )
    except Exception as e:
        print(f"❌ 推理错误: {e}")
        traceback.print_exc()
        return

    # ---------------- Step 2: 转换 JSONL ----------------
    print(f"\n>>> [2/3] 转换为 JSONL（只保留模型生成的 completion）...")

    if not os.path.exists(INFERENCE_OUTPUT):
        print(f"❌ 找不到推理文件: {INFERENCE_OUTPUT}")
        return

    try:
        # 读取推理结果
        df_pred = pd.read_excel(INFERENCE_OUTPUT)

        # 读取原始数据（至少要拿到 task_id）
        df_src = pd.read_parquet(DATASET_PATH)

        if "task_id" not in df_src.columns:
            print("❌ 原始 parquet 缺少 'task_id' 列，无法对齐 MBPP+。")
            return

        # 确保 df_pred 也有 task_id 列
        if "task_id" not in df_pred.columns:
            # 如果长度一致，按顺序对齐
            if len(df_pred) != len(df_src):
                print(f"❌ df_pred 和 df_src 长度不一致，且 df_pred 没有 task_id，无法安全对齐！")
                print(f"    df_pred: {len(df_pred)}, df_src: {len(df_src)}")
                return
            df_pred["task_id"] = df_src["task_id"].values

        # 为了稳妥，可以做一个 inner merge 检查对齐情况（可选）
        # 这里只用 df_pred 本身，也没问题，因为 task_id 已对齐
        merged_df = df_pred.copy()

        # 找到预测结果所在列
        pred_col = None
        if "predicted_answer" in merged_df.columns:
            pred_col = "predicted_answer"
        else:
            # 尝试模糊匹配列名里带 'pred' 或 'output' 的列
            candidates = [
                c for c in merged_df.columns
                if isinstance(c, str) and ("pred" in c.lower() or "output" in c.lower())
            ]
            if candidates:
                pred_col = candidates[0]

        if pred_col is None:
            print("❌ 找不到预测结果列（例如 'predicted_answer'、'*pred*' 或 '*output*'）")
            print("当前列名:", list(merged_df.columns))
            return

        print(f"使用预测列: {pred_col}")

        # 构造 samples.jsonl
        samples = []
        for _, row in merged_df.iterrows():
            raw_tid = row["task_id"]
            tid = str(raw_tid)

            # 统一成 EvalPlus 的 Mbpp/xxx 格式
            if not tid.startswith("Mbpp/"):
                tid = f"Mbpp/{tid}"

            generated = str(row.get(pred_col, ""))
            generated = sanitize_code(generated)

            samples.append({
                "task_id": tid,
                # 注意：completion 只放「模型生成的部分」
                # EvalPlus 会自己用 problem["prompt"] + completion 来构造完整程序
                "completion": generated,
            })

        with open(SAMPLES_JSONL, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

        print(f"✅ JSONL 已生成: {SAMPLES_JSONL}")

    except Exception as e:
        print(f"❌ 转换出错: {e}")
        traceback.print_exc()
        return

    # ---------------- Step 3: 评测 ----------------
    print(f"\n>>> [3/3] 运行 EvalPlus (mbpp)...")

    cmd = [
        "evalplus.evaluate",
        "--dataset", "mbpp",  # EvalPlus 里 mbpp / mbpp+ 都用这一个名字
        "--samples", SAMPLES_JSONL,
    ]

    print("执行命令:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
        print("\n✅ 评测完成！")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ EvalPlus 运行失败 (Code {e.returncode})")


if __name__ == "__main__":
    main()

