# prompts.py
import json

def get_system_prompt(style):
    """
    根据 style 返回对应的 system prompt。
    """
    shot_complete = r'''User Question:

def coin_change(coins: List[int], amount: int) -> int:
    """ You are given an integer array coins representing coins of different denominations and an integer amount representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.
    >>> coin_change([1, 2, 5], 11) == 3
    >>> coin_change([2], 3) == -1
    >>> coin_change([1], 0) == 0
    >>> coin_change([1], 1) == 1
    >>> coin_change([1], 2) == 2
    """

Assistant Response:
<think>
    <known>
        {
            node_id: 1,
            parents: none,
            content: "Input: 'coins' (List[int]), 'amount' (int). Goal: Find minimum number of coins to sum to 'amount'."
        },
        {
            node_id: 2,
            parents: none,
            content: "Constraints: Return -1 if impossible. 'amount' >= 0 (implied by context/doctests). Coins are positive integers."
        },
        {
            node_id: 3,
            parents: none,
            content: "Edge Cases: amount is 0 (expect 0). coins list is empty (expect -1 unless amount is 0). amount cannot be formed."
        }
    </known>

    <associative thinking>
        {
            node_id: 4,
            parents: 1,
            content: "Pattern Recognition: This is the classic 'Coin Change' problem, which is a variation of the Unbounded Knapsack Problem. Potential approaches: BFS (shortest path in a graph) or Dynamic Programming (optimal substructure)."
        }
    </associative thinking>

    <reflection>
        {
            node_id: 5,
            parents: 4,
            content: "Check Greedy Approach: If we always take the largest coin <= amount, does it work? \nCounter-example: coins=[1, 3, 4], amount=6. \nGreedy: 4 + 1 + 1 = 3 coins. \nOptimal: 3 + 3 = 2 coins. \nConclusion: Greedy is not optimal. Must use DP or BFS."
        }
    </reflection>

    <reverse thinking>
        {
            node_id: 6,
            parents: 5,
            content: "Logic Derivation: To find dp[x] (min coins for amount x), the last coin added must be some coin 'c'. Thus, dp[x] = min(dp[x-c]) + 1 for all c in coins. We solve from 0 up to amount."
        }
    </reverse thinking>

    <generate>
        {
            node_id: 7,
            parents: 6,
            content: "Plan (DP Bottom-Up):\n1. Initialize array 'dp' of size amount + 1.\n2. Fill 'dp' with a value > amount (representing infinity). dp[0] = 0.\n3. Iterate i from 1 to amount.\n4. For each coin, if i >= coin, dp[i] = min(dp[i], dp[i-coin] + 1).\n5. Final result is dp[amount] (or -1 if it's still infinity)."
        }
    </generate>

    <refine>
        {
            node_id: 8,
            parents: 7,
            content: "Optimization: We can check 'coin <= i' inside the inner loop to avoid negative index access. The 'infinity' value can be 'amount + 1' since the worst case is all 1s (count = amount)."
        }
    </refine>

    <generate>
        {
            node_id: 9,
            parents: 8,
            content: "Implementation Draft:\n\ndef coin_change(coins, amount):\n    dp = [amount + 1] * (amount + 1)\n    dp[0] = 0\n    for i in range(1, amount + 1):\n        for c in coins:\n            if i >= c:\n                dp[i] = min(dp[i], dp[i-c] + 1)\n    return dp[amount] if dp[amount] <= amount else -1"
        }
    </generate>

    <reflection>
        {
            node_id: 10,
            parents: 9,
            content: "Dry Run Trace:\nInput: coins=[1, 2], amount=3.\nInit: dp=[0, 4, 4, 4] (inf=4)\ni=1: c=1 -> dp[1]=min(4, dp[0]+1)=1. dp=[0, 1, 4, 4]\ni=2: c=1 -> dp[2]=min(4, dp[1]+1)=2. c=2 -> dp[2]=min(2, dp[0]+1)=1. dp=[0, 1, 1, 4]\ni=3: c=1 -> dp[3]=min(4, dp[2]+1)=2. c=2 -> dp[3]=min(2, dp[1]+1)=2. dp=[0, 1, 1, 2]\nResult: 2. Correct."
        }
    </reflection>

    <aggregate>
        {
            node_id: 11,
            parents: 2, 3, 10,
            content: "Final Verification: Handles edge case amount=0 correctly (dp[0]=0). Handles impossible case correctly (returns -1). Code structure is compliant with constraints."
        }
    </aggregate>
</think>

<answer>
from typing import List

def coin_change(coins: List[int], amount: int) -> int:
    """ You are given an integer array coins representing coins of different denominations and an integer amount representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.
    >>> coin_change([1, 2, 5], 11) == 3
    >>> coin_change([2], 3) == -1
    >>> coin_change([1], 0) == 0
    >>> coin_change([1], 1) == 1
    >>> coin_change([1], 2) == 2
    """
    if amount < 0:
        return -1
    if amount == 0:
        return 0

    max_val = amount + 1
    dp = [max_val] * (amount + 1)
    dp[0] = 0

    for i in range(1, amount + 1):
        for coin in coins:
            if i >= coin:
                dp[i] = min(dp[i], dp[i - coin] + 1)

    return dp[amount] if dp[amount] <= amount else -1
</answer>
'''
    shot_online_judge = '''User Question:

You are given an integer amount representing a total amount of money and a list of coins of different denominations.

Write a program to calculate the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, print -1.

Input Format:
- The first line contains an integer `amount`.
- The second line contains a sequence of integers `coins` separated by spaces.

Output Format:
- Print a single integer representing the minimum number of coins (or -1).

Example 1:
Input:
11
1 2 5
Output:
3

Example 2:
Input:
3
2
Output:
-1

### Format: Generate an executable Python function to solve the given problem. The function should read input from `stdin` and write the output to `stdout`. Do not directly test on the sample inputs. Ensure that when the Python program runs, it reads the inputs, executes the algorithm, and writes the output to `stdout`.

Assistant Response:
<think>
    <known>
        { 
            node_id: 1, 
            parents: none,
            content: "Task: Solve Coin Change problem (Min coins for 'amount').\\nInput Source: stdin (Standard Input).\\nOutput Target: stdout (Standard Output).\\nInput Format: Line 1 = amount (int), Line 2 = coins (space-separated ints)." 
        },
        { 
            node_id: 2,
            parents: none,
            content: "Constraints: Print -1 if impossible. Standard integer limits. Time complexity matters (Standard OJ limits usually ~1-2s)."
        }
    </known>

    <associative thinking>
        {
            node_id: 3,
            parents: 1,
            content: "Algorithm Selection: This is the 'Coin Change' problem (Unbounded Knapsack). DP (Dynamic Programming) is the standard optimal solution. BFS is also possible but DP is easier to implement for just counting."
        }
    </associative thinking>

    <reverse thinking>
        {
            node_id: 4,
            parents: 1,
            content: "IO Strategy: Unlike function completion, we must parse raw strings.\\nReading: `sys.stdin.read().split()` is robust for handling whitespace/newlines.\\nParsing sequence: First token is `amount`, subsequent tokens are `coins`."
        }
    </reverse thinking>

    <generate>
        {
            node_id: 5,
            parents: 3, 4,
            content: "Plan:\\n1. Import sys.\\n2. Read all stdin content.\\n3. Parse `amount` and `coins` list.\\n4. Initialize DP array `dp` size [amount + 1] with `amount + 1` (infinity).\\n5. Set dp[0] = 0.\\n6. Iterate i from 1 to amount: for each coin, update dp[i].\\n7. Print result."
        }
    </generate>

    <refine>
        {
            node_id: 6,
            parents: 5,
            content: "Robustness Check: What if the coins line is empty? (Though problem implies valid coins). What if amount is 0? The DP initialization covers amount=0 correctly. We should ensure we strip inputs properly."
        }
    </refine>

    <generate>
        {
            node_id: 7,
            parents: 6,
            content: "Implementation Logic:\\n\\nimport sys\\n\\ndef solve():\\n    input_data = sys.stdin.read().split()\\n    if not input_data: return\\n    amount = int(input_data[0])\\n    coins = [int(x) for x in input_data[1:]]\\n    \\n    # DP Logic\\n    dp = [amount + 1] * (amount + 1)\\n    dp[0] = 0\\n    for i in range(1, amount + 1):\\n        for c in coins:\\n             if i >= c:\\n                 dp[i] = min(dp[i], dp[i-c] + 1)\\n    \\n    result = dp[amount] if dp[amount] <= amount else -1\\n    print(result)\\n\\nif __name__ == '__main__':\\n    solve()"
        }
    </generate>

    <reflection>
        {
            node_id: 8,
            parents: 7,
            content: "Dry Run (Mental Sandbox):\\nInput:\\n11\\n1 2 5\\n\\nTokens: ['11', '1', '2', '5']\\namount = 11\\ncoins = [1, 2, 5]\\nDP Init: dp size 12.\\ni=1..11 loop runs.\\nFinal dp[11] will be 3 (5+5+1 or similar combo).\\nOutput: 3.\\n\\nInput:\\n3\\n2\\nTokens: ['3', '2']\\namount = 3, coins = [2]\\ndp[1] -> inf\\ndp[2] -> 1\\ndp[3] -> inf (since 3-2=1, dp[1] is inf)\\nOutput: -1.\\n\\nLogic holds."
        }
    </reflection>

    <aggregate>
        {
            node_id: 9,
            parents: 7, 8,
            content: "Final Polish: Combine logic into the required executable format. Ensure strict 'sys.stdin' usage and no extra prompt text (like 'Enter number:') as it breaks OJ graders."
        }
    </aggregate>
</think>

<answer>
import sys

def solve():
    input_data = sys.stdin.read().split()
    if not input_data:
        return

    amount = int(input_data[0])
    coins = [int(x) for x in input_data[1:]]

    # dp[i] = min coins to make i
    max_val = amount + 1
    dp = [max_val] * (amount + 1)
    dp[0] = 0

    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i:
                dp[i] = min(dp[i], dp[i - coin] + 1)

    print(dp[amount] if dp[amount] <= amount else -1)

if __name__ == "__main__":
    solve()
</answer>
'''
    shot_instruct = '''User Question:
  You are given an integer array coins representing coins of different denominations and an integer amount representing a total amount of money. Return the fewest number of coins that you need to make up that amount. If that amount of money cannot be made up by any combination of the coins, return -1.
  Function Signature: def coin_change(coins: List[int], amount: int) -> int:

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

    <reflection>
        {
            node_id:6,
            parents:5,
            content:Verifying Greedy: Counter-example check. Coins=[1, 3, 4], Amount=6.Greedy path: Take 4, remain 2. Take 1, remain 1. Take 1. Total 3 coins (4+1+1).Optimal path: Take 3, remain 3. Take 3. Total 2 coins (3+3). So Greedy FAILS. Must use Dynamic Programming.
        }
    </reflection>

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
    
    <reflection> 
        {   node_id:10,
            parents:9,
            content:Dry Run Trace: Input: coins=[1, 2], amount=3. Init: dp=[0, 4, 4, 4]. i=1: coin=1 -> dp[1]=min(4, dp[0]+1)=1. dp=[0,1,4,4]. i=2: coin=1 -> dp[2]=min(4, dp[1]+1)=2. coin=2 -> dp[2]=min(2, dp[0]+1)=1. dp=[0,1,1,4]. i=3: coin=1 -> dp[3]=min(4, dp[2]+1)=2. coin=2 -> dp[3]=min(2, dp[1]+1)=2. dp=[0,1,1,2]. Result: 2. Logic holds. 
        } 
    </reflection> 
        
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
'''


    base_prompt = """You are a helpful AI Assistant specialized in solving programming problems.
You will produce a correct and efficient Python solution.

You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <think>
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
  - reflection: go back to a previous reasoning step. Used to re-examine the correctness of a step or process. **For coding, perform a "Dry Run" by manually executing the code with a specific test case step-by-step.**
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
  - reflection：It wraps one node, and the parent of this node should be one or more nodes. Its parent_ids must include the last node of the current reasoning chain.
  - refine: It wraps one node, and the parent of this node should be the last node in the current reasoning chain.
  - associative thinking：It wraps one node, and the parent of this node should be one or more nodes.
  - reverse thinking：It wraps one node, and the parent of this node should be one or more nodes.
  7.If there are multiple nodes in a tag, each node cannot use other nodes in the same tag as parent node. If necessary, it needs to be placed in a new tag.
  8.If a tag contains multiple nodes, the nodes should be separated by commas. Within a node, different tags do not require commas and should be separated by line breaks. 
  9. Anti-Looping Rule: Do not perform mental simulations in a loop within a single node. If you calculate a value or transform a string, WRITE IT DOWN as a fact in the content and move on. Do not go back to question it unless a 'reflection' step proves it wrong.

  **10. Coding Format Rules (CRITICAL):**
  - The content inside `<answer>` must be PURE Python code. **Do NOT include any XML tags (like `</think>`) inside `<answer>`.**
  - **NO INDENTATION for top-level definitions:** The `import` statements and the `def function_name(...)` line MUST start at the very beginning of the line (column 0). Do NOT add extra spaces before `def`.
  - **Self-Contained:** Include all necessary imports (e.g., `from typing import List`). 

  **11. Engineering Safety Rules:**
  - **No Side Effects:** DO NOT modify the input arguments in-place (e.g., use `sorted(nums)` instead of `nums.sort()`).
  - **Strict Signature:** Use the EXACT function name and argument names provided in the prompt, even if they contain typos. Do not change the API.

  Please strictly follow the above format and requirements.
   Here is an example of how you should reason and answer:
"""

    
    if style == "complete":
        # 针对代码补全的 Prompt
        return base_prompt + shot_complete
    elif style == "instruct":
        # 针对指令生成的 Prompt
        return base_prompt + shot_instruct
    elif style == "online_judge":
        # 针对 OJ 题目的 Prompt
        return base_prompt + shot_online_judge
    else:
        return base_prompt

def construct_user_prompt(question, style, test_info=None):
    """
    构造最终发送给模型的 User 内容。
    增加了 test_info 参数，用于提取函数名约束。
    """
    
    # 1. 基础包装：User Question
    content = f"User Question:\n{question}"
    
    # 2. 【核心修改】从 test_info 中提取函数约束
    if test_info:
        # --- 防御性处理开始 ---
        # 处理 numpy 数组 (如果它意外传进来的话)
        if hasattr(test_info, 'tolist'): 
            test_info = test_info.tolist()
            
        # 处理字符串形式的 json
        if isinstance(test_info, str):
            try:
                test_info = json.loads(test_info)
            except:
                pass 
        # --- 防御性处理结束 ---

        # 尝试提取 function_declaration
        func_decl = None
        func_name = None
        
        # 确保是列表且非空
        if isinstance(test_info, list) and len(test_info) > 0:
            info_dict = test_info[0]
            # 确保元素是字典 (有时候可能是 None)
            if isinstance(info_dict, dict):
                func_decl = info_dict.get('function_declaration') 
                func_name = info_dict.get('function_name')
        
        # 将约束拼接到 Prompt 中
        if style == 'instruct' or style == 'complete':
            if func_decl:
                # 强约束：给出完整函数头
                content += f"\n\nFunction Signature: {func_decl}"
            elif func_name:
                # 弱约束：至少名字要对
                content += f"\n\nNote: You MUST name the function `{func_name}`."
    
    # 3. 针对 Online Judge (OJ) 的特殊处理
    if style == 'online_judge':
        content += "\n\n### Format: Generate an executable Python function to solve the given problem. The function should read input from `stdin` and write the output to `stdout`. Do not directly test on the sample inputs. Ensure that when the Python program runs, it reads the inputs, executes the algorithm, and writes the output to `stdout`."
    
    # 4. 结尾引导
    content += "\n\nAssistant Response:"
    
    return content