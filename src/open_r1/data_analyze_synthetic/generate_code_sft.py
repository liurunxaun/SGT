import json
import os
import random
import pandas as pd
from datasets import Dataset

# ================= 配置区域 =================
SUCCESS_FILE = "/ssd5/rxliu/datasets/KodCode-SFT/kodcode_success_sft.jsonl"
FALLBACK_FILE = "/ssd5/rxliu/datasets/KodCode-SFT/kodcode_fallback_sft.jsonl"
OUTPUT_DIR = "/ssd5/rxliu/datasets/KodCode-SFT/sft_final_v2_custom_prompt"
RANDOM_SEED = 42

# ================= 你的原始 Base Prompt (规则说明书) =================
# 这里只保留指令部分，去掉了 Few-Shot 示例，这是 SFT 的最佳实践
CUSTOM_SYSTEM_PROMPT = """You are a helpful AI Assistant specialized in solving programming problems.You will produce a correct and efficient Python solution.

  You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <tool_call>...<tool_call><answer>...</answer></answer>

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

  Please strictly follow the above format and requirements."""

# ================= 工具函数 (使用 Scheme B - 去格式化) =================

def construct_user_prompt_scheme_b(question, style, test_info=None):
    """
    Scheme B: 去掉 User Question 前缀，但保留 test_info 核心约束
    """
    content = str(question).strip()
    
    if test_info:
        if hasattr(test_info, 'tolist'): test_info = test_info.tolist()
        if isinstance(test_info, str):
            try: test_info = json.loads(test_info)
            except: pass 

        func_decl = None
        func_name = None
        if isinstance(test_info, list) and len(test_info) > 0:
            info_dict = test_info[0]
            if isinstance(info_dict, dict):
                func_decl = info_dict.get('function_declaration') 
                func_name = info_dict.get('function_name')
        
        if style in ['instruct', 'complete', 'default']:
            if func_decl:
                content += f"\n\nFunction Signature: {func_decl}"
            elif func_name:
                content += f"\n\nNote: You MUST name the function `{func_name}`."
    
    if style == 'online_judge':
        content += "\n\n### Format: Generate an executable Python function to solve the given problem. The function should read input from `stdin` and write the output to `stdout`."
        content += "\n\n### Input Constraints:\n1. Use `input()` to read line-by-line.\n2. Use `.split()` to handle whitespace."
    
    return content

def format_success_sample(row):
    question = row['question']
    style = row.get('style', 'default')
    test_info = row.get('test_info')
    
    user_content = construct_user_prompt_scheme_b(question, style, test_info)
    
    reasoning = row['reasoning']
    solution = row['solution']
    
    if "```" not in solution:
        solution = f"```python\n{solution}\n```"
        
    # 注意：你的 Prompt 要求 <think> 后面跟具体的 tag，这里直接拼接 reasoning 即可
    # 因为你的 raw data 里的 reasoning 应该是包含 <known> 等标签的
    assistant_content = f"<think>\n{reasoning}\n</think>\n\n<answer>\n{solution}\n</answer>"
    
    # ⚠️ 特别修正：你的 Prompt 里要求代码放在 <answer> 标签里
    # 之前的代码我用了 ```python，这里改为你的 Prompt 要求的 <answer> 格式以保持一致
    # 并且去掉 solution 里的 ```python (如果你的 solution 本身就带 ``` 的话要小心)
    # 这里我假设你的 solution 是纯代码。如果不是，需要做一些清洗。
    # 根据你的 generate 代码，solution 可能是带 ``` 的。
    # 让我们做一个健壮的处理：
    
    clean_sol = solution.replace("```python", "").replace("```", "").strip()
    assistant_content = f"<think>\n{reasoning}\n</think>\n\n<answer>\n{clean_sol}\n</answer>"

    return [
        {"role": "system", "content": CUSTOM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content}
    ]

def format_fallback_sample(row):
    question = row['question']
    style = row.get('style', 'default')
    test_info = row.get('test_info')
    solution = row['solution']
    
    if not solution: return None
        
    user_content = construct_user_prompt_scheme_b(question, style, test_info)
    
    # 清洗 solution 格式 (移除可能存在的 markdown 标记，因为我们下面会统一加)
    clean_sol = solution.replace("```python", "").replace("```", "").strip()
    
    # === 关键修改 ===
    # 构造一个符合 strict schema 的 "哑" 思考过程
    # 满足 System Prompt 要求: 必须以 <known> 开头，内容必须是 JSON 格式
    dummy_reasoning = """<known>
    {
        node_id: 1,
        parents: none,
        content: "Analysis skipped for fallback data. Direct solution provided based on ground truth."
    }
</known>"""

    # 组合最终输出
    assistant_content = f"<think>\n{dummy_reasoning}\n</think>\n\n<answer>\n{clean_sol}\n</answer>"
    
    return [
        {"role": "system", "content": CUSTOM_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content}
    ]

def load_jsonl(file_path):
    data = []
    if not os.path.exists(file_path):
        print(f"⚠️ 文件不存在: {file_path}")
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try: data.append(json.loads(line))
            except: continue
    return data

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("="*60)
    print("开始处理 SFT 数据 (使用 Custom Base Prompt + Scheme B)")
    print("="*60)
    
    success_rows = load_jsonl(SUCCESS_FILE)
    fallback_rows = load_jsonl(FALLBACK_FILE)
    print(f" - Success Raw: {len(success_rows)}")
    print(f" - Fallback Raw: {len(fallback_rows)}")
    
    all_data = []
    
    print("\nProcessing Success Data...")
    for row in success_rows:
        try:
            msgs = format_success_sample(row)
            all_data.append({"messages": msgs}) # 注意：为了 Parquet 格式干净，建议只留 messages 字段，或者保留 source 用于 debug
        except Exception as e:
            print(f"Error in success row: {e}")
            
    print("Processing Fallback Data...")
    for row in fallback_rows:
        try:
            msgs = format_fallback_sample(row)
            if msgs:
                all_data.append({"messages": msgs})
        except Exception as e:
            print(f"Error in fallback row: {e}")

    total_len = len(all_data)
    print(f"\nTotal Valid Samples: {total_len}")
    
    print(f"Shuffling with seed {RANDOM_SEED}...")
    random.seed(RANDOM_SEED)
    random.shuffle(all_data)
    
    # ================= 核心修改区域 Start =================
    
    # 1. 设置切分比例 (例如: 5% 用于测试/验证)
    TEST_RATIO = 0.05 
    split_index = int(total_len * (1 - TEST_RATIO))
    
    train_data = all_data[:split_index]
    test_data = all_data[split_index:]
    
    print(f"\nData Split Result:")
    print(f" - Train set: {len(train_data)} samples")
    print(f" - Test set:  {len(test_data)} samples")
    
    # 2. 保存 train.parquet
    train_parquet_path = os.path.join(OUTPUT_DIR, "train.parquet")
    print(f"Saving Train Parquet to: {train_parquet_path}")
    pd.DataFrame(train_data).to_parquet(train_parquet_path, index=False)
    
    # 3. 保存 test.parquet
    test_parquet_path = os.path.join(OUTPUT_DIR, "test.parquet")
    print(f"Saving Test Parquet to: {test_parquet_path}")
    pd.DataFrame(test_data).to_parquet(test_parquet_path, index=False)

    # (可选) 仍然保存一份完整的 JSONL 用于人工检查，但训练不用它
    jsonl_path = os.path.join(OUTPUT_DIR, "all_data_debug.jsonl")
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    # (可选) 如果你还需要 HuggingFace Dataset 格式的对象 (Arrow 格式)
    # 你可以把它们存成 DatasetDict，这样加载时直接就是 split 好的
    from datasets import DatasetDict
    ds_dict = DatasetDict({
        "train": Dataset.from_list(train_data),
        "test": Dataset.from_list(test_data)
    })
    hf_path = os.path.join(OUTPUT_DIR, "kodcode_hf_dataset_dict")
    # ds_dict.save_to_disk(hf_path) 
    # print(f"Saved HF DatasetDict to {hf_path}")

    # ================= 核心修改区域 End =================
    
    print("\n" + "="*60)
    print("🔍 Final Data Preview (Train Sample 0)")
    print("="*60)
    if len(train_data) > 0:
        msgs = train_data[0]['messages']
        print(f"--- SYSTEM ---")
        print(msgs[0]['content'][:100] + "...")
        print(f"\n--- USER ---")
        print(msgs[1]['content'][:100] + "...")
        print(f"\n--- ASSISTANT ---")
        print(msgs[2]['content'][:200] + "...")

    print("\nDone! Ready for training.")

if __name__ == "__main__":
    main()