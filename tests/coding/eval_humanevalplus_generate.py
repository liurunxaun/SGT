import json
import re
from pathlib import Path
from typing import Dict, Any, Tuple, List

from datasets import load_from_disk
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ====== 配置区 ======

HUMANEVALPLUS_DISK_DIR = "/ssd5/rxliu/datasets/humanevalplus"
# 模型路径
MODEL_PATH = "/ssd5/rxliu/models/output/Qwen3-8B-Olympiads-2000+GSM8K-7200-sft-data-SFT" 

# 1. 提交给评测工具的文件 (JSONL)
OUTPUT_JSONL = "/data/home/the/rxliu/projects/open-r1-main/tests/coding/samples_humanevalplus_structured_cot.jsonl"
# 2. 给你自己看的思考过程日志 (Markdown)
OUTPUT_THOUGHT_LOG = "/data/home/the/rxliu/projects/open-r1-main/tests/coding/thought_process_log.md"
# 3. 保存提取出的节点结构文件 (JSONL) <--- 新增
OUTPUT_NODES_JSONL = "/data/home/the/rxliu/projects/open-r1-main/tests/coding/nodes_humanevalplus.jsonl"

# 建议设置大一点，防止思考过程被截断
MAX_NEW_TOKENS = 16384 
TEMPERATURE = 0.0
TOP_P = 1.0

# ====== System Prompt & 1-Shot Example ======
SYSTEM_PROMPT = """You are a helpful AI Assistant that provides well-reasoned and detailed responses. You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <think>
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
**9. Anti-Looping Rule: Do not perform mental simulations in a loop within a single node. If you calculate a value or transform a string, WRITE IT DOWN as a fact in the content and move on. Do not go back to question it unless a 'feedback' step proves it wrong.**
Please strictly follow the above format and requirements.
Below I’ll give you some examples:"""

ONE_SHOT_EXAMPLE_USER = """
You are given an integer array `coins` representing coins of different denominations and an integer `amount` representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.
Example: `coins = [1, 2, 5]`, `amount = 11`. Output: `3` (5 + 5 + 1).
"""

ONE_SHOT_EXAMPLE_ASSISTANT = """
<think>
  <known>
    {
      node_id:1
      parents:none
      content:Input: List of integers 'coins', Integer 'amount'. Goal: Find Minimum count of coins to sum to 'amount'.
    },
    {
      node_id:2
      parents:none
      content:Constraints: 'amount' can be 0 (return 0). If unsolvable, return -1. Coins are positive integers.
    },
    {
      node_id:3
      parents:none
      content:Edge Cases: Coins list is empty; Amount is negative; Large amount vs small coins (performance).
    }
  </known>

  <reverse thinking>
    {
      node_id:4
      parents:1
      content:To reach the target 'amount' with minimum coins, the last coin added must be some coin 'c' from the list. This means the problem reduces to finding min coins for 'amount - c'. This recursive structure implies we solve from 0 up to 'amount'.
    }
  </reverse thinking>

  <associative thinking>
    {
      node_id:5
      parents:4
      content:This structure looks like the 'Unbounded Knapsack Problem'. A common approach is Greedy (always take largest) or Dynamic Programming. Let's try to verify if Greedy works because it is faster.
    }
  </associative thinking>

  <feedback>
    {
      node_id:6
      parents:5
      content:Verifying Greedy: Counter-example check. Coins=[1, 3, 4], Amount=6.
Greedy path: Take 4, remain 2. Take 1, remain 1. Take 1. Total 3 coins (4+1+1).
Optimal path: Take 3, remain 3. Take 3. Total 2 coins (3+3).
Conclusion: Greedy FAILS. Must use Dynamic Programming.
    }
  </feedback>

  <generate>
    {
      node_id:7
      parents:6
      content:Plan (DP approach):
1. Create array dp[amount + 1] initialized to 'infinity' (amount + 1).
2. Set dp[0] = 0.
3. Iterate i from 1 to amount.
4. For each coin, if i >= coin, dp[i] = min(dp[i], dp[i-coin] + 1).
    }
  </generate>

  <aggregate>
    {
      node_id:8
      parents:2,3,7
      content:Combine DP Plan with Edge Cases:
If amount is 0, return 0 immediately.
After DP loop, if dp[amount] > amount, implies no solution, return -1.
    }
  </aggregate>

  <generate>
    {
      node_id:9
      parents:8
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
    { node_id:10 
      parents:9 
      content:Dry Run Trace: Input: coins=[1, 2], amount=3. Init: dp=[0, 4, 4, 4]. i=1: coin=1 -> dp[1]=min(4, dp[0]+1)=1. dp=[0,1,4,4]. i=2: coin=1 -> dp[2]=min(4, dp[1]+1)=2. coin=2 -> dp[2]=min(2, dp[0]+1)=1. dp=[0,1,1,4]. i=3: coin=1 -> dp[3]=min(4, dp[2]+1)=2. coin=2 -> dp[3]=min(2, dp[1]+1)=2. dp=[0,1,1,2]. Result: 2. Logic holds. 
    } 
  </feedback> 
      
</think> 
      
<answer>
Python
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
            for coin in coins:
                if coin <= i:
                    dp[i] = min(dp[i], dp[i - coin] + 1)

    return dp[amount] if dp[amount] <= amount else -1
</answer>
"""

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

# ====== 提取与清洗逻辑 ======

def extract_answer(text: str) -> str:
    """提取 <answer> 内容，并清洗 Markdown 格式，只保留代码"""
    match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL | re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
    else:
        # Fallback: 去掉 <think> 剩下的都算 answer
        content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        content = content.replace('<answer>', '').strip()

    # 清洗 ```python 和 ```
    content = re.sub(r'^```python', '', content, flags=re.MULTILINE)
    content = re.sub(r'^```', '', content, flags=re.MULTILINE)
    
    return content.strip()

def extract_raw_nodes(text: str) -> List[str]:
    """
    从 <think> 块中提取所有符合 { node_id: ... } 格式的原始文本块。
    返回由字符串组成的列表，每个字符串是一个节点的原始文本。
    """
    # 1. 先提取 <think> 内容
    think_match = re.search(r'<think>(.*?)</think>', text, re.DOTALL | re.IGNORECASE)
    if not think_match:
        return []
    think_content = think_match.group(1)

    # 2. 使用正则提取最外层的 {...} 结构
    # 说明：这里使用非贪婪匹配提取包含 node_id 和 parents 的花括号块
    node_pattern = re.compile(r'\{\s*node_id:.*?\s*parents:.*?\s*content:.*?\s*\}', re.DOTALL)
    nodes = node_pattern.findall(think_content)
    return nodes

def gen_solution(humaneval_prompt: str) -> Tuple[str, str]:
    """
    返回 (清洗后的代码, 原始的完整输出)
    """
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
            do_sample=(TEMPERATURE > 0),
            temperature=TEMPERATURE,
            top_p=TOP_P,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = outputs[0][input_len:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # 提取代码
    final_code_body = extract_answer(generated_text)
    
    # 拼接最终代码（兼容模型可能没写 def 头的情况）
    if "def " in final_code_body:
        solution = final_code_body
    else:
        solution = humaneval_prompt + "\n" + final_code_body

    return solution, generated_text

# ====== 主函数 ======

def main():
    print(f"Loading HumanEval+ from {HUMANEVALPLUS_DISK_DIR} ...")
    ds = load_from_disk(HUMANEVALPLUS_DISK_DIR)
    test_set = ds["test"]

    out_path = Path(OUTPUT_JSONL)
    log_path = Path(OUTPUT_THOUGHT_LOG)
    nodes_path = Path(OUTPUT_NODES_JSONL)

    # 创建父目录（如果不存在）
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ====== 1. 扫描已完成任务 (断点续跑) ======
    finished_task_ids = set()
    if out_path.exists():
        print("Checking existing output for resuming...")
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        finished_task_ids.add(data["task_id"])
                    except json.JSONDecodeError:
                        pass
        print(f"Found {len(finished_task_ids)} completed tasks. Resuming...")
    
    # 决定打开模式：'a' (追加) 或 'w' (新建)
    open_mode = "a" if len(finished_task_ids) > 0 else "w"

    print(f"Generating solutions for {len(test_set)} tasks ...")
    format_success_count = 0 

    # ====== 2. 打开所有文件 ======
    with out_path.open(open_mode, encoding="utf-8") as f_json, \
         log_path.open(open_mode, encoding="utf-8") as f_log, \
         nodes_path.open(open_mode, encoding="utf-8") as f_nodes:
        
        # 仅在全新开始时写入 Markdown Header
        if open_mode == "w":
            f_log.write("# HumanEval+ Graph CoT Thought Process Log\n\n")

        for i, problem in enumerate(test_set):
            task_id = problem["task_id"]
            
            # 跳过已完成
            if task_id in finished_task_ids:
                continue

            prompt = problem["prompt"]
            print(f"[{i+1}/{len(test_set)}] Generating for task {task_id} ...")
            try:
                # 获取 solution 和 raw_text
                solution, raw_text = gen_solution(prompt)
                
                if solution.strip():
                    format_success_count += 1
            except Exception as e:
                print(f"  !! Error when generating for {task_id}: {e}")
                solution = ""
                raw_text = f"Error: {e}"

            # 1. 写入 JSONL (EvalPlus 用)
            sample: Dict[str, Any] = {
                "task_id": task_id,
                "solution": solution,
            }
            f_json.write(json.dumps(sample, ensure_ascii=False) + "\n")
            f_json.flush() # 强制保存

            # 2. 写入 Markdown (日志)
            f_log.write(f"## Task: {task_id}\n")
            f_log.write(f"### Prompt\n```python\n{prompt}\n```\n\n")
            f_log.write(f"### Model Output (Think + Answer)\n")
            f_log.write(f"```text\n{raw_text}\n```\n")
            f_log.write(f"\n---\n\n")
            f_log.flush() # 强制保存

            # 3. 写入 Nodes (图结构数据)
            try:
                extracted_nodes_list = extract_raw_nodes(raw_text)
                node_sample = {
                    "task_id": task_id,
                    "node_count": len(extracted_nodes_list),
                    "nodes": extracted_nodes_list, 
                    "raw_think": re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL | re.IGNORECASE).group(1) if '<think>' in raw_text else ""
                }
                f_nodes.write(json.dumps(node_sample, ensure_ascii=False) + "\n")
                f_nodes.flush() # 强制保存
            except Exception as e:
                print(f"  !! Error saving nodes for {task_id}: {e}")

    print(f"Done! Samples saved to {out_path}")
    print(f"Thought process saved to {log_path}")
    print(f"Graph nodes saved to {nodes_path}")
    print(f"Approximate format adherence: {format_success_count}/{len(test_set)}")


if __name__ == "__main__":
    main()