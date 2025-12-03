import pandas as pd
import os
import sys
import json
import re
import subprocess

sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")
from inference_sglang import inference_sglang

# ================= 1. Prompt 定义区域 (核心修改) =================

# 基础指令
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

**11. Engineering Safety Rules:**
- **No Side Effects:** DO NOT modify the input arguments in-place (e.g., use `sorted(nums)` instead of `nums.sort()`).
- **Strict Signature:** Use the EXACT function name and argument names provided in the prompt, even if they contain typos. Do not change the API.

Please strictly follow the above format and requirements."""

# One-Shot 示例构造
# 为了让模型理解，我们需要模拟一个 "Example User Input" 和 "Example Assistant Output"
# 我们将其作为 System Prompt 的一部分传入，让模型进行 In-Context Learning

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
    },
    {
      node_id:2,
      parents:none,
      content:Constraints: 'amount' can be 0 (return 0). If unsolvable, return -1. Coins are positive integers.
    },
    {
      node_id:3,
      parents:none,
      content:Edge Cases: Coins list is empty; Amount is negative; Large amount vs small coins (performance).
    }
  </known>

  <reverse thinking>
    {
      node_id:4,
      parents:1,
      content:To reach the target 'amount' with minimum coins, the last coin added must be some coin 'c' from the list. This means the problem reduces to finding min coins for 'amount - c'. This recursive structure implies we solve from 0 up to 'amount'.
    }
  </reverse thinking>

  <associative thinking>
    {
      node_id:5,
      parents:4,
      content:This structure looks like the 'Unbounded Knapsack Problem'. A common approach is Greedy (always take largest) or Dynamic Programming. Let's try to verify if Greedy works because it is faster.
    }
  </associative thinking>

  <feedback>
    {
      node_id:6,
      parents:5,
      content:Verifying Greedy: Counter-example check. Coins=[1, 3, 4], Amount=6.
Greedy path: Take 4, remain 2. Take 1, remain 1. Take 1. Total 3 coins (4+1+1).
Optimal path: Take 3, remain 3. Take 3. Total 2 coins (3+3).
Conclusion: Greedy FAILS. Must use Dynamic Programming.
    }
  </feedback>

  <generate>
    {
      node_id:7,
      parents:6,
      content:Plan (DP approach):
1. Create array dp[amount + 1] initialized to 'infinity' (amount + 1).
2. Set dp[0] = 0.
3. Iterate i from 1 to amount.
4. For each coin, if i >= coin, dp[i] = min(dp[i], dp[i-coin] + 1).
    }
  </generate>

  <aggregate>
    {
      node_id:8,
      parents:2,3,7,
      content:Combine DP Plan with Edge Cases:
If amount is 0, return 0 immediately.
After DP loop, if dp[amount] > amount, implies no solution, return -1.
    }
  </aggregate>

  <generate>
    {
      node_id:9,
      parents:8,
      content:Implementation Code:
def coin_change(coins, amount):
    if amount == 0: return 0
    max_val = amount + 1
    dp = [max_val] * (max_val)
    dp[0] = 0
    for i in range(1, amount + 1):
        for coin in coins:
            if i - coin >= 0:
                dp[i] = min(dp[i], dp[i - coin] + 1)
    return dp[amount] if dp[amount] != max_val else -1
}
  </generate> 
  
  <feedback> 
    { node_id:10,
      parents:9,
      content:Dry Run Trace: Input: coins=[1, 2], amount=3. Init: dp=[0, 4, 4, 4]. i=1: coin=1 -> dp[1]=min(4, dp[0]+1)=1. dp=[0,1,4,4]. i=2: coin=1 -> dp[2]=min(4, dp[1]+1)=2. coin=2 -> dp[2]=min(2, dp[0]+1)=1. dp=[0,1,1,4]. i=3: coin=1 -> dp[3]=min(4, dp[2]+1)=2. coin=2 -> dp[3]=min(2, dp[1]+1)=2. dp=[0,1,1,2]. Result: 2. Logic holds. 
    } 
  </feedback> 
      
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


# ================= 2. 参数配置 =================

MODEL_NAME = "qwen3-8B-SFT-checkpoint105"
TIME_TAG = "20251203-1500"
TEMPERATURE = 0.6       # 保持 0.6
MAX_TOKENS = 32768      # 保持 32768

# 只测试 HumanEvalPlus
DATASET_NAME = "HumanEvalPlus"
DATASET_PATH = "/ssd5/rxliu/datasets/humanevalplus/humaneval_test.parquet" # 请确保路径正确
QUERY_FIELD = "prompt"
EVALPLUS_TYPE = "humaneval"

BASE_RESULT_DIR = "/data/home/the/rxliu/projects/open-r1-main/tests/results"


# ================= 3. 新的清洗函数 (适配 XML 标签) =================

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
    print(f"=== 任务: {DATASET_NAME} (Temp={TEMPERATURE}) ===")
    
    # 文件路径定义
    inference_output = f"{BASE_RESULT_DIR}/inference-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.xlsx"
    samples_jsonl = f"{BASE_RESULT_DIR}/samples-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}.jsonl"
    eval_result_dir = f"{BASE_RESULT_DIR}/eval_results-{MODEL_NAME}-{DATASET_NAME}-{TIME_TAG}"

    # 1. 推理
    print(f">>> [1/3] Sglang 推理...")
    print(f"    System Prompt 长度: {len(FINAL_SYSTEM_PROMPT)} 字符 (包含 One-Shot)")
    
    inference_sglang(
        DATASET_PATH, 
        FINAL_SYSTEM_PROMPT,  # 传入包含 One-Shot 的大 Prompt
        QUERY_FIELD, 
        "canonical_solution", # 占位符
        inference_output, 
        MODEL_NAME, 
        TEMPERATURE, 
        MAX_TOKENS
    )

    # 2. 格式转换
   # 2. 格式转换 (新增了“找回 task_id”的逻辑)
    print(f">>> [2/3] 提取 <answer> 代码并转换为 JSONL...")
    if not os.path.exists(inference_output):
        print("❌ 推理失败，未找到结果文件。")
        return

    try:
        # 读取推理结果
        df = pd.read_excel(inference_output)
        
        # =========== 【修复补丁开始】 ===========
        # 如果推理结果里没有 task_id，我们就去原始数据里拿！
        if "task_id" not in df.columns:
            print("⚠️ 发现结果缺少 'task_id'，正在从原始 Parquet 文件中恢复...")
            # 读取原始数据
            df_src = pd.read_parquet(DATASET_PATH)
            
            # 建立映射：假设 inference_sglang 保存的 'id' 列对应原始数据的索引
            # 如果 inference_sglang 没保存 'id'，则假设顺序是一致的
            if "id" in df.columns:
                # 这里的 'id' 是 sglang 脚本里生成的行号
                id_map = df_src["task_id"].to_dict() # index -> task_id
                df["task_id"] = df["id"].map(id_map)
            else:
                # 兜底方案：直接按行号赋值 (前提是行数一致且顺序未乱)
                if len(df) == len(df_src):
                    df["task_id"] = df_src["task_id"].values
                else:
                    raise ValueError(f"行数不匹配！结果 {len(df)} 行，原数据 {len(df_src)} 行，无法自动恢复 task_id。")
            print("✅ task_id 恢复成功！")
        # =========== 【修复补丁结束】 ===========
        
        # 自动寻找输出列
        pred_col = "predicted_answer"
        if pred_col not in df.columns:
            candidates = [c for c in df.columns if "pred" in c or "output" in c]
            if candidates: pred_col = candidates[0]
        
        samples = []
        for _, row in df.iterrows():
            # 使用新的 sanitize_code 提取 <answer> 里的内容
            raw_output = row.get(pred_col, "")
            clean_code = sanitize_code(raw_output)
            
            samples.append({
                "task_id": row["task_id"],
                "completion": clean_code
            })
            
        with open(samples_jsonl, "w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s) + "\n")
        print(f"    已生成 JSONL: {samples_jsonl}")
                
    except Exception as e:
        print(f"❌ 转换出错: {e}")
        import traceback
        traceback.print_exc() # 打印详细报错方便排查
        return

    # 3. 评测
    print(f">>> [3/3] 运行 EvalPlus ({EVALPLUS_TYPE})...")
    
    # 【修改这里】去掉 --output-dir 参数
    cmd = [
        "evalplus.evaluate",
        "--dataset", EVALPLUS_TYPE,
        "--samples", samples_jsonl
        # "--output-dir", eval_result_dir  <-- 删除这一行
    ]
    
    print(f"    执行: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        # 结果通常会生成在 samples_jsonl 同目录下，文件名加个后缀
        print(f"✅ 评测完成！请在 {samples_jsonl} 同目录下查找 _eval_results.json 文件")
    except subprocess.CalledProcessError as e:
        print(f"❌ EvalPlus 运行失败，错误码: {e.returncode}")

if __name__ == "__main__":
    main()