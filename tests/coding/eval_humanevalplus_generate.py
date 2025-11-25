import json
import re
from pathlib import Path
from typing import Dict, Any

from datasets import load_from_disk
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ====== 配置区 ======

HUMANEVALPLUS_DISK_DIR = "evalplus_data/humanevalplus"
# 请修改为你的模型路径
MODEL_PATH = "/ssd5/rxliu/models/output/Qwen3-8B-Olympiads-2000+GSM8K-7200-sft-data-SFT" 
OUTPUT_JSONL = "samples_humanevalplus_structured_cot.jsonl"

# ⚠️ 关键设置：因为你的思考过程包含大量 JSON 节点，非常占 Token
# 建议至少设置 2048，如果显存允许，最好 4096，防止答案被截断
MAX_NEW_TOKENS = 16384  
TEMPERATURE = 0.0
TOP_P = 1.0

# ====== 核心修改 1: 填入你 SFT 时的完整 System Prompt ======
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
    content:The content of this step. **WARNING: When writing code inside JSON, ensure all quotes (\") and newlines (\\n) are properly escaped.**
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
ONE_SHOT_EXAMPLE_USER = """You are given an integer array `coins` representing coins of different denominations and an integer `amount` representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.
Example: `coins = [1, 2, 5]`, `amount = 11`. Output: `3` (5 + 5 + 1)."""

ONE_SHOT_EXAMPLE_ASSISTANT = '''<think>
  <known>
    {
      node_id:1
      parents:none
      content:Input: List of integers 'coins', Integer 'amount'. Goal: Find Minimum count of coins to sum to 'amount'.
    },
    {
      node_id:2
      parents:none
      content:Constraints: 'amount' can be 0 (return 0). If unsolvable, return -1. Coins are positive.
    }
  </known>

  <associative thinking>
    {
      node_id:3
      parents:1
      content:First thought: Greedy Strategy. Always take the largest coin possible to reduce the count rapidly.
    }
  </associative thinking>

  <feedback>
    {
      node_id:4
      parents:3
      content:Verify Greedy: Let's test Edge Case. Coins=[1, 3, 4], Amount=6. Greedy path: Take 4. Remaining=2. Take 1, 1. Total=3. Optimal: Take 3, 3. Total=2. Conclusion: Greedy fails. Must use Dynamic Programming.
    }
  </feedback>

  <generate>
    {
      node_id:5
      parents:4
      content:Plan (DP approach): Define dp[i] as min coins for amount 'i'. Base case dp[0]=0. Transition: dp[i] = min(dp[i], dp[i-coin]+1). Init array with amount+1 (infinity).
    }
  </generate>

  <known>
    {
      node_id:6
      parents:none
      content:Edge Case Check: If coins is empty? Return -1. If amount < 0? Return -1.
    }
  </known>

  <aggregate>
    {
      node_id:7
      parents:2,5,6
      content:Integrating DP logic with constraints: 1. Handle amount=0. 2. Init dp array. 3. Loop 1 to amount. 4. Inner loop coins. 5. Check if reachable.
    }
  </aggregate>

  <generate>
    {
      node_id:8
      parents:7
      content:Implementation Code:
def coin_change(coins, amount):
    if amount == 0:
        return 0
    max_val = amount + 1
    dp = [max_val] * (amount + 1)
    dp[0] = 0
    for i in range(1, amount + 1):
        for coin in coins:
            if i - coin >= 0:
                dp[i] = min(dp[i], dp[i - coin] + 1)
    return dp[amount] if dp[amount] != max_val else -1
}
</generate> <feedback> { node_id:9 parents:8 content:Dry Run Trace: Input coins=[1,2], amount=3. Init dp=[0, 4, 4, 4]. i=1: coin=1->dp[1]=1. coin=2->skip. dp=[0,1,4,4]. i=2: coin=1->dp[2]=2. coin=2->dp[2]=1. dp=[0,1,1,4]. i=3: coin=1->dp[3]=2. coin=2->dp[3]=2. dp=[0,1,1,2]. Result: 2. Correct. } </feedback> <refine> { node_id:10 parents:9 content:The trace confirms the logic handles optimal substructure correctly. Code is O(amount * len(coins)). } </refine> </think> <answer>

from typing import List

def coin_change(coins: List[int], amount: int) -> int:
"""
Computes the fewest number of coins needed to make up the amount.
Returns -1 if impossible.
"""
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
</answer> ''' 
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

# ====== 核心修改 2: 针对你的格式编写提取逻辑 ======

def extract_answer(text: str) -> str:
    """
    专门解析你的格式： <think>...</think><answer>...</answer>
    我们需要提取 <answer> 里面的内容，并清洗 Markdown。
    """
    
    # 1. 尝试提取 <answer> 标签内的内容
    #    re.DOTALL 让 . 能够匹配换行符
    match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL | re.IGNORECASE)
    
    if match:
        content = match.group(1).strip()
    else:
        # Fallback: 如果模型没写 </answer> (可能被截断)，或者是格式崩了
        # 我们尝试去掉 <think> 部分，保留剩下的
        content = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        # 如果模型连 <answer> 开头都没写，那可能内容就在最后，不做额外处理
        # 但通常建议去掉 <answer> 开头标签（如果存在）
        content = content.replace('<answer>', '').strip()

    # 2. 清洗 Markdown 代码块标记 (```python ... ```)
    #    很多模型在 <answer> 里还是会习惯性加 markdown
    content = re.sub(r'^```python', '', content, flags=re.MULTILINE)
    content = re.sub(r'^```', '', content, flags=re.MULTILINE)
    
    return content.strip()

def gen_solution(humaneval_prompt: str) -> str:
    # 构造更强的 User Instruction，明确告知这是编程任务
    user_target_content = f"""Please complete the following Python function. 
Apply the graph-structured reasoning format (nodes, edges, tags) learned from math problems to this coding problem.
Analyze the logic first in <think>, then output code in <answer>.

Problem:
{humaneval_prompt}"""
    
    # 构造 Messages，插入 1-Shot 样例
    messages = [
        # 1. System Prompt (保持不变，是你那一长串规则)
        {"role": "system", "content": SYSTEM_PROMPT},
        
        # 2. 插入 1-Shot Example (教它迁移)
        {"role": "user", "content": ONE_SHOT_EXAMPLE_USER},
        {"role": "assistant", "content": ONE_SHOT_EXAMPLE_ASSISTANT},
        
        # 3. 真正的测试题
        {"role": "user", "content": user_target_content}
    ]
    
    # 应用 Chat 模板
    text_input = tokenizer.apply_chat_template(
        messages, 
        tokenize=False, 
        add_generation_prompt=True
    )
    
    inputs = tokenizer(text_input, return_tensors="pt").to(model.device)

    # 记录 prompt 长度，方便后面截取
    input_len = inputs.input_ids.shape[1]

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=(TEMPERATURE > 0),
            temperature=TEMPERATURE,
            top_p=TOP_P,
            eos_token_id=tokenizer.eos_token_id,
            # 你的 SFT 数据里可能有特定的停止符，如果没有就默认 EOS
        )

    # 只解码生成的新内容
    generated_ids = outputs[0][input_len:]
    generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

    # --- 后处理 ---
    # 此时 generated_text 应该是： "<think>...JSON...</think><answer>def ...</answer>"
    
    final_code_body = extract_answer(generated_text)
    
    # 拼接 HumanEval 的 prompt (如果模型输出里不包含 def 头的话)
    if "def " in final_code_body:
        solution = final_code_body
    else:
        solution = humaneval_prompt + "\n" + final_code_body

    return solution

# ====== 主函数 ======

def main():
    print(f"Loading HumanEval+ from {HUMANEVALPLUS_DISK_DIR} ...")
    ds = load_from_disk(HUMANEVALPLUS_DISK_DIR)
    test_set = ds["test"]

    out_path = Path(OUTPUT_JSONL)
    if out_path.exists():
        print(f"[Warn] Output {out_path} already exists, it will be overwritten.")
        out_path.unlink()

    print(f"Generating solutions for {len(test_set)} tasks ...")
    
    # 计数器：记录有多少个题目成功生成了 <answer> 标签
    format_success_count = 0 

    with out_path.open("w", encoding="utf-8") as f:
        for i, problem in enumerate(test_set):
            task_id = problem["task_id"]
            prompt = problem["prompt"]

            print(f"[{i+1}/{len(test_set)}] Generating for task {task_id} ...")
            try:
                solution = gen_solution(prompt)
                # 简单的检查：如果 solution 不为空，说明至少提取到了东西
                if solution.strip():
                    format_success_count += 1
            except Exception as e:
                print(f"  !! Error when generating for {task_id}: {e}")
                solution = ""

            sample: Dict[str, Any] = {
                "task_id": task_id,
                "solution": solution,
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"Done! Samples saved to {out_path}")
    print(f"Approximate format adherence: {format_success_count}/{len(test_set)}")


if __name__ == "__main__":
    main()