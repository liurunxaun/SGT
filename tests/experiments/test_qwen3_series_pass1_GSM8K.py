print("========begin evaluate========")
print()

print("begin loading transformers")
print()
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import pandas as pd
import re
import requests
import datetime
import os


def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
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
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    resp = requests.post(api_url, headers=headers, json=data)
    resp.raise_for_status()
    resp_json = resp.json()
    # 假设返回格式类似 OpenAI：resp_json["choices"][0]["message"]["content"]
    verdict = resp_json["choices"][0]["message"]["content"].strip().lower()
    return verdict == "correct"


# 定义超参数
# 模型路径
model_path = "/data/home/the/rxliu/projects/open-r1-main/output/Qwen3-0.6B-GRPO-Olympiads/checkpoint-500"
# 数据集路径
dataset_path = "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet"
# 问题字段名称
question_field = "question"
# 答案字段名称
answer_field = "answer"
# api_url
api_url = "https://ai-yyds.com/v1/chat/completions"
# api key
api_key = "sk-RyIv6tr8xb9AribIAfD9Ab640c2e4fCeBeAa98Cd892f894d"
# 选择LLM Judge的模型
judge_model_name = "gpt-4o-mini"
# system_prompt
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
# 保存结果路径
save_dir = "/data/home/the/rxliu/projects/open-r1-main/tests/results"
# 动态生成文件名：模型名 + 数据集名 + 日期
model_name = os.path.basename(model_path)
dataset_name = os.path.basename(os.path.dirname(dataset_path))
date_str = datetime.datetime.now().strftime("%Y%m%d")
save_path = os.path.join(save_dir, f"{model_name}_{dataset_name}_{date_str}.csv")



# 加载 tokenizer 和模型
print("begin loading model")
print()
tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map="auto",   # 自动放到GPU上
    torch_dtype=torch.bfloat16  # 如果显卡支持BF16
)

results = []
correct = 0
total = 0


# 读取数据集
df = pd.read_parquet(dataset_path)
# 遍历每一条样本
for i, row in df.iterrows():
    problem = row[question_field]
    ground_truth = row[answer_field]
    print(f"========question {i}========")
    print(f"question: {problem}")
    print()

    messages = [
        {"role": "system", "content": self_prompt},
        
        {"role": "user", "content": problem}
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True # Switches between thinking and non-thinking modes. Default is True.
    )
    model_inputs = tokenizer(text, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=38912, # 32768或38912
            temperature=0.6,
            top_p=0.95,
            top_k=20,
            do_sample=True
        )
    output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist() 
    # parsing thinking content
    try:
        # rindex finding 151668 (</think>)
        index = len(output_ids) - output_ids[::-1].index(151668)
    except ValueError:
        index = 0

    thinking_content = tokenizer.decode(output_ids[:index], skip_special_tokens=True).strip("\n")
    answer_content = tokenizer.decode(output_ids[index:], skip_special_tokens=True).strip("\n")
    print(f"thinking_content:")
    print()
    print(thinking_content)
    print()
    print(f"answer_content:")
    print()
    print(answer_content)
    print()

    # 用正则提取 <answer>...</answer> 中的内容（包括换行）
    match = re.search(r"<answer>([\s\S]*?)</answer>", answer_content)
    if match:
        predict_answer = match.group(1).strip()
    else:
        print("Cannot answer found in the output.")
    
    # GSM8K给的answer包括解题过程和最终答案的数字，答案是在####之后，提取出来。如果提取失败的话，还是将原本的answer作为答案交给大模型评委
    match = re.search(r"####\s*([-\d\.]+)", ground_truth)
    if match:
        ground_truth_answer = match.group(1).strip()
    else:
        ground_truth_answer = ground_truth
        print("No final answer found in ground truth.")

    # 计算准确率
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

    print(f"extracted answer: {predict_answer} | ground_truth: {ground_truth_answer} | {status}")
    print()
    print()

    # 保存结果
    results.append({
        "id": i,
        "question": problem,
        "predicted_answer": predict_answer,
        "ground_truth": ground_truth,
        "thinking_content": thinking_content,
        "is_correct": is_correct,
        "status": status
    })


# 保存结果为 CSV 文件
df_results = pd.DataFrame(results)
df_results["accuracy"] = correct / total if total > 0 else 0.0
df_results.to_csv(save_path, index=False, encoding="utf-8")

print("\n========evaluation finished========")
print(f"Total: {total}, Correct: {correct}, Accuracy: {correct/total:.4f}")
print(f"Results saved to: {save_path}")