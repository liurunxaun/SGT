print("========begin evaluate========")
print()

import os
import re
import torch
import datetime
import pandas as pd
import requests
from vllm import LLM, SamplingParams
from transformers import AutoTokenizer


# ======================= 评测函数 =======================
def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
    """调用 LLM 评委 API，判断答案是否正确"""
    prompt = (
        f"You are a math evaluator. Compare the two answers and respond with exactly "
        f"'correct' or 'incorrect'.\n\n"
        f"Ground truth: {ground_truth}\n"
        f"Model answer: {answer}\n"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": judge_model_name,
        "messages": [{"role": "user", "content": prompt}]
    }
    resp = requests.post(api_url, headers=headers, json=data)
    resp.raise_for_status()
    resp_json = resp.json()
    verdict = resp_json["choices"][0]["message"]["content"].strip().lower()
    return verdict == "correct"


# ======================= 参数定义 =======================
model_path = "/data/home/the/rxliu/projects/open-r1-main/output/Qwen3-0.6B-GRPO-Olympiads/checkpoint-500"
dataset_path = "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet"
save_dir = "/data/home/the/rxliu/projects/open-r1-main/tests/results"

api_url = "https://ai-yyds.com/v1/chat/completions"
api_key = "sk-RyIv6tr8xb9AribIAfD9Ab640c2e4fCeBeAa98Cd892f894d"
judge_model_name = "gpt-4o-mini"

batch_size = 8   # 每次并行生成 8 条（可改大）
question_field = "question"
answer_field = "answer"

model_name = os.path.basename(model_path)
dataset_name = os.path.basename(os.path.dirname(dataset_path))
date_str = datetime.datetime.now().strftime("%Y%m%d")
save_path = os.path.join(save_dir, f"{model_name}_{dataset_name}_{date_str}.csv")

# system prompt（保持原样）
self_prompt = """
    You are a helpful AI Assistant that provides well-reasoned and detailed responses. You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <think>\n...\n</think>\n<answer>\n...\n</answer>

  Besides, you must comply with below conditions:
  1.During the <think> phase you should organize the chain of thought using below tags:
  - known: known conditions that can be found in the query
  - generate: from the current node, generate one or more new node(s).
  - aggregate: merge multiple nodes or jointly reason over them to produce a new node.
  - feedback: go back to a previous node.
  - refine: improve the current node.
  - associative thinking: comparing the curent reasoning graph structure with other similar graph structures, in order to facilitate the current reasoning process. For example, when solving a math problem, recalling the solution methods used in previous similar problems.
  - reverse thinking: starting from the goal of the problem, considering possible solution paths, and filtering them with the given conditions. This builds a reverse reasoning path from the goal to the conditions, from the unknown to the known, leading to the final answer.
  At each further reasoning step you must choose one of these seven tags and wrap that step’s output with the chosen tag. For example: <Generate>...</Generate>
  2.The tag content inside is a series of thinking steps, organized in a node based manner with node_id and parents. You need to ensure that the thinking process is coherent and effective, and ultimately these nodes can be organized into a directed graph. The format example for each node is as follows:
  {
      node_id:The unique identifier of a node, usually an integer, increasing from 1.
      parents:A list of parent node IDs for this node, used to establish inference dependencies. If there is no parent node, you can fill in none.
      content:The content of this step
  }
  If a tag contains multiple nodes, the parents of these nodes must be same.
  For the content wrapped in different tags, there are the following formal requirements:
  - konwn:It wraps one or more nodes, and the parents of these nodes should all be "none".
  - generate:(1) It wraps one node, and the parents of this nodes should be a single node. (2) It wraps two or more nodes, and the parents of these nodes should be a same single node. (3) It wraps two or more nodes, and the parents of these nodes should be mutiple nodes that are the same.
  - aggregate：It wraps one node, and the parent of this node should be multiple nodes.
  - feedback：It wraps one node, and the parent of this node should be one or more nodes.
  - refine:It wraps one node, and the parent of this node should be a single node.
  - associative thinking：It wraps one node, and the parent of this node should be one or more nodes.
  - reverse thinking：It wraps one node, and the parent of this node should be one or more nodes.
  If a tag contains multiple nodes, the nodes should be separated by commas. Within a node, different fields do not require commas and should be separated by line breaks. 

  Below I’ll give you an example:
  query：Find the sum of all integer bases b>9 for which 17_{b} is a divisor of 97_{b}
  <think>

    <known>

      {
        node_id:1
        parents:none
        content:b>9 
      },

      {
        node_id:2
        parents:none
        content:17_{b} is a divisor of 97_{b} 
      },

      {
        node_id:3
        parents:none
        content:b is an integer
      }

    </known>

    <generate>

      {
        node_id:4
        parents:2
        content:17_{b}=b+7
      },

      {
        node_id:5
        parents:2
        content:97_{b}=9*b+7
      },

    </generate>

    <aggeregate>

      {
        node_id:6
        parents:2,4,5
        content: 9*b+7=k(b+7)，k>0,k is an integer
      },

    </aggeregate>

    <refine>

      {
        node_id:7
        parents:6
        content:b=(7-7k)/(k-9),1<k<9,k is an integer
      }

    </refine>
    
    <associative thinking>
    
      {
        node_id:8
        parents:7
        content:When dealing with this type of problem before, I used the enumeration method, and I can apply the same method here as well.
      }
      
    </associative thinking>

    <generate>

      {
        node_id:9
        parents:1,7
        content:if k=2,b=1,false.
      },

      {
        node_id:10
        parents:1,3,7
        content:2. if k=3,b=14/6,false.
      },

      {
        node_id:11
        parents:1,3,7
        content:if k=4,b=21/5,false.
      },

      {
        node_id:12
        parents:1,7
        content:if k=5,b=7,false.
      },

      {
        node_id:13
        parents:3,7
        content:if k=6,b=35/3,false.
      },

      {
        node_id:14
        parents:7
        content:if k=7,b=21,true. 
      },

      {
        node_id:15
        parents:7
        content:if k=8,b=49,true.
      }

    </generate>

    <feedback>

      {
        node_id:16
        parents:6,14
        content:But wait: Also b+7=? and 9*b+7=? Possibly b+7=56 and 9*b+7=448? 448/56=8 Yes.
      }

    </feedback>

    <aggeregate>

      {
        node_id:17
        parents:9,10,11,12,13,14,15
        content:Sum=21+49=70
      }

    </aggeregate>

  </think>

  <answer>

    70

  </answer>
  """


# ======================= 初始化模型 =======================
print("begin loading vLLM model")
tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False)

llm = LLM(
    model=model_path,
    tensor_parallel_size=4,  # 使用 4 张 GPU
    dtype="bfloat16",
)

sampling_params = SamplingParams(
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    max_tokens=38912,
)


# ======================= 数据加载 =======================
df = pd.read_parquet(dataset_path)
results = []
correct = 0
total = 0


# ======================= 批量生成 =======================
print("========begin batch generation========")

for start in range(0, len(df), batch_size):
    batch = df.iloc[start:start + batch_size]
    print(f"\n--- Processing batch {start} ~ {start + len(batch) - 1} ---")

    # 构造输入 prompts
    prompts = []
    for _, row in batch.iterrows():
        problem = row[question_field]
        messages = [
            {"role": "system", "content": self_prompt},
            {"role": "user", "content": problem}
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True
        )
        prompts.append(text)

    # vLLM 并行推理
    outputs = llm.generate(prompts, sampling_params)

    # 遍历每个样本结果
    for i, row in enumerate(batch.itertuples()):
        idx = start + i
        problem = getattr(row, question_field)
        ground_truth = getattr(row, answer_field)
        output_text = outputs[i].outputs[0].text.strip()

        # 提取 <think> 和 <answer>
        match_think = re.search(r"<think>([\s\S]*?)</think>", output_text)
        match_ans = re.search(r"<answer>([\s\S]*?)</answer>", output_text)
        thinking_content = match_think.group(1).strip() if match_think else ""
        predict_answer = match_ans.group(1).strip() if match_ans else output_text

        # Ground truth 提取 #### 后数字
        match_gt = re.search(r"####\s*([-\d\.]+)", ground_truth)
        ground_truth_answer = match_gt.group(1).strip() if match_gt else ground_truth

        # 调用评审 API
        total += 1
        try:
            is_correct = llm_judge_via_api(predict_answer, ground_truth_answer, api_url, api_key, judge_model_name)
            status = "✅" if is_correct else "❌"
        except Exception as e:
            print("Judge API error:", e)
            is_correct = (predict_answer.strip() == ground_truth_answer.strip())
            status = "⚠️ API_ERROR"

        if is_correct:
            correct += 1

        acc = correct / total
        print(f"[{idx}] extracted: {predict_answer} | gt: {ground_truth_answer} | {status}")

        results.append({
            "id": idx,
            "question": problem,
            "predicted_answer": predict_answer,
            "ground_truth": ground_truth,
            "thinking_content": thinking_content,
            "is_correct": is_correct,
            "status": status
        })

    # ✅ 每个 batch 打印一次实时准确率
    print(f"Batch {start // batch_size + 1} done. Current accuracy: {correct}/{total} = {correct/total:.4f}")


# ======================= 保存结果 =======================
df_results = pd.DataFrame(results)
df_results["accuracy"] = correct / total if total > 0 else 0.0
df_results.to_csv(save_path, index=False, encoding="utf-8")

print("\n========evaluation finished========")
print(f"Total: {total}, Correct: {correct}, Accuracy: {correct/total:.4f}")
print(f"Results saved to: {save_path}")
