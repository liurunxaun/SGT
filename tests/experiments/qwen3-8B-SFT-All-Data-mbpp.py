import pandas as pd
import os
import sys
import json
import re
import subprocess
import traceback

# ================= 0. 环境设置 =================
# TODO: 请确认此路径是否存在
sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")

try:
    from inference_sglang import inference_sglang
except ImportError:
    # 占位防止IDE报错
    def inference_sglang(*args, **kwargs):
        raise ImportError("inference_sglang not found")

# ================= 1. Prompt 定义 (保持微调模型的 XML 格式) =================
# 你的微调模型专用的 System Prompt
BASE_SYSTEM_PROMPT = """You are a helpful AI Assistant that provides well-reasoned and detailed responses. You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <think>
...
</think>
<answer>
...
</answer>

Besides, you must comply with below requirements:
1.During the <think> phase you should organize the chain of thought using below tags:
- known: known conditions that can be found in the question. **For coding tasks, you MUST explicitly list Input/Output types, Constraints, and potential Edge Cases (e.g., empty inputs, negative numbers).**
- generate: from the current reasoning state, generate one or more new reasoning steps. It represents a step forward in the process of reasoning. **If writing code, first outline the logic (Plan), then write the code. If performing data transformation (e.g., removing spaces), you MUST output the transformed result explicitly to avoid repetitive calculation.**
- aggregate: merge multiple steps or jointly reason over them to produce a new reasoning step.
- feedback: go back to a previous reasoning step. Used to re-examine the correctness of a step or process. **For coding, perform a "Dry Run" by manually executing the code with a specific test case step-by-step.**
- refine: improve the current node. It is a refined modification of a certain node's statement, without producing a substantial step forward in the reasoning process.
- associative thinking: comparing the curent reasoning graph structure with other similar graph structures, in order to facilitate the current reasoning process. **For example, recalling specific algorithms (BFS, DP) or data structures suitable for the problem.**
- reverse thinking: starting from the goal of the problem, considering possible solution paths, and filtering them with the given conditions. This builds a abstruct reverse reasoning path from the goal to the conditions, from the unknown to the known. **For coding, consider what the Output implies about the necessary Logic (Test-Driven Thinking).**

2.At each reasoning step you must choose one of these tags. You cannot create other labels on your own. 
3.Wrap the reasoning step with the selected tag. For example:<generate>...</generate>.
4.The complete think phase must start with <known>...</konwn>, and the final inference tag must include the final result of the question and must belong to one of the seven tags mentioned above.
5.The tag content inside is a series of thinking steps, organized in a node based manner with node_id and parents. You need to ensure that the thinking process is coherent and effective, and ultimately these nodes can be organized into a directed graph. The format example for each node is as follows:
{
    node_id:The unique identifier of a node, usually an integer, increasing from 1.
    parents:A list of parent node IDs for this node, used to establish inference dependencies. If there is no parent node, you can fill in none.
    content:The content of this step. **WARNING: When writing code inside JSON, ensure all quotes (") and newlines (\\n) are properly escaped.**
}
6.For the content wrapped in different tags, there are the following formal requirements:
- konwn:It wraps one or more nodes, and the parents of these nodes should all be "none".
- generate:It wraps one or more nodels, (1) If it wraps one node, the parents of this nodes should be a single node. (2) If it wraps two or more nodes, the parents of these nodes should be a same single node.
- aggregate：It wraps one node, and the parent of this node should be multiple nodes.
- feedback：It wraps one node, and the parent of this node should be one or more nodes. Its parent_ids must include the last node of the current reasoning chain.
- refine: It wraps one node, and the parent of this node should be the last node in the current reasoning chain.
- associative thinking：It wraps one node, and the parent of this node should be one or more nodes.
- reverse thinking：It wraps one node, and the parent of this node should be one or more nodes.
7.If there are multiple nodes in a tag, each node cannot use other nodes in the same tag as parent node. If necessary, it needs to be placed in a new tag.
8.If a tag contains multiple nodes, the nodes should be separated by commas. Within a node, different tags do not require commas and should be separated by line breaks. 
9. Anti-Looping Rule: Do not perform mental simulations in a loop within a single node. If you calculate a value or transform a string, WRITE IT DOWN as a fact in the content and move on. Do not go back to question it unless a 'feedback' step proves it wrong.

**10. Coding Format Rules (CRITICAL):**
- The content inside `<answer>` must be PURE Python code. **Do NOT include any XML tags (like `</think>`) inside `<answer>`.**
- **NO INDENTATION for top-level definitions:** The `import` statements and the `def function_name(...)` line MUST start at the very beginning of the line (column 0). Do NOT add extra spaces before `def`.
- **Self-Contained:** Include all necessary imports (e.g., `from typing import List`).
- **Strict Signature:** Use the EXACT function name and argument names provided in the prompt, even if they contain typos. Do not change the API.

Please strictly follow the above format and requirements."""

# One-Shot 示例 (通用编程示例，MBPP 也能用)
ONE_SHOT_USER_Q = """
Here is an example of how you should reason and answer:

User Question:
You are given an integer array coins representing coins of different denominations and an integer amount representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.
Function Signature: def coin_change(coins: List[int], amount: int) -> int:
"""

ONE_SHOT_ASSISTANT_A = """
Assistant Response:
<think>
  <known>
    {
      node_id:1,
      parents:none,
      content:Input: List of integers 'coins', Integer 'amount'. Goal: Find Minimum count of coins to sum to 'amount'.
    }
  </known>
  <generate>
    {
      node_id:2,
      parents:1,
      content:Plan: Use Dynamic Programming. dp[i] = min coins to make amount i.
    }
  </generate>
</think>
<answer>
from typing import List

def coin_change(coins: List[int], amount: int) -> int:
    \"\"\"
    Computes the fewest number of coins needed to make up the amount.
    Returns -1 if impossible.
    \"\"\"
    if amount == 0:
        return 0

    # Initialize DP array. amount + 1 acts as infinity.
    max_val = amount + 1
    dp = [max_val] * (amount + 1)
    dp[0] = 0

    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i:
                dp[i] = min(dp[i], dp[i - coin] + 1)

    return dp[amount] if dp[amount] <= amount else -1
</answer>
"""

# 将所有部分拼接成最终传给 sglang 的 System Prompt
FINAL_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + "\n\n" + ONE_SHOT_USER_Q + "\n" + ONE_SHOT_ASSISTANT_A


# ================= 2. 参数配置 (修改为 MBPP) =================

MODEL_NAME = "qwen3-8B-SFT-checkpoint105"
TIME_TAG = "20251205-Mbpp-Finetune" # 更新时间戳
TEMPERATURE = 0.6       
MAX_TOKENS = 32768      

# --- 修改点 1: 数据集信息 ---
DATASET_NAME = "MbppPlus"
# 你的 MBPP 数据路径
DATASET_PATH = "/ssd5/rxliu/datasets/mbppplus/data/test-00000-of-00001-d5781c9c51e02795.parquet"
EVALPLUS_TYPE = "mbpp"  # 这里的类型必须改，指明是 mbpp 评测

BASE_RESULT_DIR = "/data/home/the/rxliu/projects/open-r1-main/tests/results"
TEMP_PARQUET = f"{BASE_RESULT_DIR}/temp_mbpp_finetuned_input.parquet" # 临时文件路径

# ================= 3. 辅助函数 =================

def get_function_signature(code_snippet):
    """从参考代码中提取函数签名 (def xxx(...):)"""
    if not isinstance(code_snippet, str): return None
    match = re.search(r"^\s*(def\s+.*?:)", code_snippet, re.MULTILINE)
    if match: return match.group(1).strip()
    return None

def sanitize_code(text):
    """
    清洗模型输出：
    1. 优先提取 <answer>...</answer> 中的纯代码
    2. 如果没找到 tag，则回退到寻找 markdown 代码块
    """
    if not isinstance(text, str):
        return ""
    
    # 策略 1: 严格匹配 <answer> 标签 (根据你的 Prompt 要求)
    # re.DOTALL 确保 . 能匹配换行符
    answer_pattern = r"<answer>(.*?)</answer>"
    match = re.search(answer_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 策略 2: 兜底匹配 Markdown (防止模型没听话，还是输出了 ```python)
    markdown_pattern = r"```python\n(.*?)```"
    match_md = re.search(markdown_pattern, text, re.DOTALL)
    if match_md:
        return match_md.group(1).strip()
    
    # 策略 3: 通用 Markdown
    generic_md = r"```\n(.*?)```"
    match_gen = re.search(generic_md, text, re.DOTALL)
    if match_gen:
        return match_gen.group(1).strip()
        
    # 如果什么都没匹配到，返回原文本（极其危险，但总比空着好）
    return text.strip()


# ================= 4. 主程序 =================

def main():
    print(f"=== 任务: {DATASET_NAME} (MBPP Finetune Eval) ===")
    
    inference_output = f"{BASE_RESULT_DIR}/inference-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.xlsx"
    samples_jsonl = f"{BASE_RESULT_DIR}/samples-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.jsonl"

    # --- 修改点 2: 预处理 (注入函数签名) ---
    print(f"\n>>> [0/3] 构建 MBPP Prompt (注入函数签名)...")
    try:
        if not os.path.exists(DATASET_PATH):
            print(f"❌ 错误: 数据集路径不存在: {DATASET_PATH}")
            return

        df = pd.read_parquet(DATASET_PATH)
        
        # 确定参考代码列 (mbpp 可能是 'code'，humaneval 是 'canonical_solution')
        ref_col = "code" if "code" in df.columns else "canonical_solution"
        if ref_col not in df.columns:
            print(f"❌ 找不到代码列，列名: {df.columns}")
            return

        def construct_prompt(row):
            prompt_text = row["prompt"]
            ref_code = row[ref_col]
            
            # 提取签名
            sig = get_function_signature(ref_code)
            
            # 构造符合 One-Shot 风格的输入
            # One-Shot 格式: "User Question: ... \n Function Signature: ..."
            if sig:
                return f"{prompt_text}\nFunction Signature: {sig}"
            else:
                return prompt_text

        df["engineered_prompt"] = df.apply(construct_prompt, axis=1)
        
        # 保存临时 Parquet 供 Sglang 使用
        df.to_parquet(TEMP_PARQUET)
        print(f"✅ 临时输入文件已生成: {TEMP_PARQUET}")
        
    except Exception as e:
        print(f"❌ 预处理失败: {e}")
        traceback.print_exc()
        return

    # --- Step 1: 推理 ---
    print(f"\n>>> [1/3] Sglang 推理...")
    
    if not os.path.exists(inference_output):
        inference_sglang(
            TEMP_PARQUET,         # 使用处理过的临时文件
            FINAL_SYSTEM_PROMPT,  # 包含 One-Shot 的大 Prompt
            "engineered_prompt",  # 使用注入了签名的新列
            "code",               # 占位符
            inference_output, 
            MODEL_NAME, 
            TEMPERATURE, 
            MAX_TOKENS
        )
    else:
        print("⚠️ 结果文件已存在，跳过推理。")

    # --- Step 2: 格式转换 ---
    print(f"\n>>> [2/3] 提取 <answer> 并转换 JSONL...")
    if not os.path.exists(inference_output):
        print("❌ 找不到结果文件")
        return

    try:
        df = pd.read_excel(inference_output)
        # 读取源数据用于对齐
        df_src = pd.read_parquet(TEMP_PARQUET)

        # 修复 task_id
        if "task_id" not in df.columns:
            print("⚠️ 正在恢复 task_id...")
            if len(df) == len(df_src):
                df["task_id"] = df_src["task_id"].values
            else:
                print(f"❌ 行数不匹配 (Output:{len(df)} vs Source:{len(df_src)})，无法自动恢复 ID")
                return

        # 自动找输出列
        pred_col = "predicted_answer"
        if pred_col not in df.columns:
            candidates = [c for c in df.columns if "pred" in c or "output" in c]
            if candidates: pred_col = candidates[0]

        if not pred_col:
             print(f"❌ 找不到预测列: {df.columns}")
             return

        samples = []
        for _, row in df.iterrows():
            raw_output = str(row.get(pred_col, ""))
            clean_code = sanitize_code(raw_output)
            
            # MBPP 的 ID 格式处理 (例如 "1" -> "Mbpp/1")
            raw_tid = str(row["task_id"])
            final_tid = raw_tid if str(raw_tid).startswith("Mbpp/") else f"Mbpp/{raw_tid}"

            samples.append({
                "task_id": final_tid,
                "completion": clean_code
            })
            
        with open(samples_jsonl, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"✅ JSONL 已生成: {samples_jsonl}")
                
    except Exception as e:
        print(f"❌ 转换出错: {e}")
        traceback.print_exc()
        return

    # --- Step 3: 评测 ---
    print(f"\n>>> [3/3] 运行 EvalPlus ({EVALPLUS_TYPE})...")
    
    # 清理旧缓存
    cache_file = samples_jsonl.replace(".jsonl", "_eval_results.json")
    if os.path.exists(cache_file): os.remove(cache_file)

    cmd = [
        sys.executable, "-m", 
        "evalplus.evaluate",
        "--dataset", EVALPLUS_TYPE, # 确保是 "mbpp"
        "--samples", samples_jsonl
    ]
    
    print(f"执行: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ 评测完成！请查看 {samples_jsonl} 同目录下的 _eval_results.json")
    except subprocess.CalledProcessError as e:
        print(f"❌ EvalPlus 运行失败: {e}")

if __name__ == "__main__":
    main()