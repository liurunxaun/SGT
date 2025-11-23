from datasets import load_dataset
import pandas as pd
import os
import json
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from llm_judge import llm_judge_via_api
import re
import time
from openai import APIError, RateLimitError
api_key_judge = "sk-8d445207b1ab47efb83069ccc1b845b6"
api_url_judge = "https://dashscope.aliyuncs.com/compatible-mode/v1"
API_KEY = "sk-LFNj6ND2W54z4lEGSMTwDnSL9oT3dMaWttX1SAgL8UkCB8Qf"
BASE_URL = "https://api.openai-proxy.org/v1"
model = "qwen3-max"
judge_model_name = "qwen3-next-80b-a3b-instruct"
def construct_prompt(sample):
    q, s,a = sample
    prompt = """
You are a helpful AI Assistant that provides well-reasoned and detailed responses. You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <think>\n...\n</think>\n<answer>\n...\n</answer>

Besides, you must comply with below conditions:
1.During the <think> phase you should organize the chain of thought using below tags:
- known: known conditions that can be found in the question.
- generate: from the current reasoning state, generate one or more new reasoning steps. It represents a step forward in the process of reasoning.
- aggregate: merge multiple steps or jointly reason over them to produce a new reasoning step.
- feedback: go back to a previous reasoning step. Used to re-examine the correctness of a step or process.
- refine: improve the current node. It is a refined modification of a certain node's statement, without producing a substantial step forward in the reasoning process.
- associative thinking: comparing the curent reasoning graph structure with other similar graph structures, in order to facilitate the current reasoning process. For example, when solving a math problem, recalling the solution methods used in previous similar problems.
- reverse thinking: starting from the goal of the problem, considering possible solution paths, and filtering them with the given conditions. This builds a abstruct reverse reasoning path from the goal to the conditions, from the unknown to the known. At this stage, you do not need to perform specific actions to get the answer. You just need to use reverse thinking to think about the reasoning method. The specific reasoning will be performed in the following tags.
2.At each further reasoning step you must choose one of these tags and wrap that step’s output with the chosen tag. For example: <generate>...</generate>
3.The complete think phase must start with <known>...</konwn>, and the final inference tag must include the final result of the question.
4.The tag content inside is a series of thinking steps, organized in a node based manner with node_id and parents. You need to ensure that the thinking process is coherent and effective, and ultimately these nodes can be organized into a directed graph. The format example for each node is as follows:
{
    node_id:The unique identifier of a node, usually an integer, increasing from 1.
    parents:A list of parent node IDs for this node, used to establish inference dependencies. If there is no parent node, you can fill in none.
    content:The content of this step
}
5.For the content wrapped in different tags, there are the following formal requirements:
- konwn:It wraps one or more nodes, and the parents of these nodes should all be "none".
- generate:It wraps one or more nodels, (1) If it wraps one node, the parents of this nodes should be a single node. (2) If it wraps two or more nodes, the parents of these nodes should be a same single node.
- aggregate：It wraps one node, and the parent of this node should be multiple nodes.
- feedback：It wraps one node, and the parent of this node should be one or more nodes. Its parent_ids must include the last node of the current reasoning chain.
- refine: It wraps one node, and the parent of this node should be the last node in the current reasoning chain.
- associative thinking：It wraps one node, and the parent of this node should be one or more nodes.
- reverse thinking：It wraps one node, and the parent of this node should be one or more nodes.
6.If a tag contains multiple nodes, the parents of these nodes cannot contain other nodes in the tag.
7.If a tag contains multiple nodes, the nodes should be separated by commas. Within a node, different tags do not require commas and should be separated by line breaks. 

Please strictly follow the above format and requirements.
Below I’ll give you some examples:
question 1:Find the smallest number \( n \) such that given any \( n \) distinct numbers from \(\{1, 2, 3, \ldots, 999\}\), one can choose four different numbers \( a, b, c, d \) such that \( a + 2b + 3c = d \).

<think>
  <known>
    {
      node_id:1
      parents:none
      content:The set is {1, 2, ..., 999}
    },
    {
      node_id:2
      parents:none
      content:We are to find the smallest n such that any subset of size n contains distinct a,b,c,d with a + 2b + 3c = d
    },
    {
      node_id:3
      parents:none
      content:a, b, c, d must be distinct elements from the chosen n numbers
    }
  </known>

  <reverse thinking>
    {
      node_id:4
      parents:2
      content:To find the minimal n that forces the equation a + 2b + 3c = d to hold among any n-element subset, we consider the maximal size of a subset that avoids this equation; then n is one more than that maximum.
    }
  </reverse thinking>

  <generate>
    {
      node_id:5
      parents:4
      content:Let S ⊆ {1,...,999} be a subset with no four distinct elements satisfying a + 2b + 3c = d. We want to maximize |S|.
    }
  </generate>

  <associative thinking>
    {
      node_id:6
      parents:5
      content:This resembles extremal combinatorics problems like Schur's theorem or sum-free sets. In such problems, choosing large numbers often avoids linear equations because the RHS (d) would exceed the universe bound.
    }
  </associative thinking>

  <generate>
    {
      node_id:7
      parents:6
      content:If we choose only large numbers, say all numbers > T, then a + 2b + 3c ≥ 1*T + 2*T + 3*T = 6T, so if 6T > 999, then d = a + 2b + 3c ∉ {1,...,999}, hence cannot be in S.
    }
  </generate>
  
  ......
I omitted the subsequent reasoning and answer generation process. In this example, you mainly learned how to use reverse thinking and associated thinking.


question 2：Find the sum of all integer bases b>9 for which 17_{b} is a divisor of 97_{b}

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

  <aggregate>

    {
      node_id:6
      parents:2,4,5
      content: 9*b+7=k(b+7)，k>0,k is an integer
    },

  </aggeregate>

  <generate>

    {
      node_id:7
      parents:6
      content:b=(7-7k)/(k-9),1<k<9,k is an integer
    }

  </generate>
  
  <associative thinking>
  
    {
      node_id:8
      parents:7
      content:When dealing with this type of problem before, I used the enumeration method, and I can apply the same method here as well.
    }
    
  </associative thinking>

  <aggregate>

    {
      node_id:9
      parents:1,3,7,8
      content:Next, I should enumerate k under the condition that 1<k<9, k is an integer, and calculate when b satisfies the condition that b>9 and b is an integer.
    },

  </aggeregate>

  <generate>

    {
      node_id:10
      parents:9
      content:1.if k=2,b=1,false.
    },

    {
      node_id:11
      parents:9
      content:2. if k=3,b=14/6,false.
    },

    {
      node_id:12
      parents:9
      content:3. if k=4,b=21/5,false.
    },

    {
      node_id:13
      parents:9
      content:4. if k=5,b=7,false.
    },

    {
      node_id:14
      parents:9
      content:5. if k=6,b=35/3,false.
    },

    {
      node_id:15
      parents:9
      content:6. if k=7,b=21,true. 
    },

    {
      node_id:16
      parents:9
      content:7.if k=8,b=49,true.
    }

  </generate>

  <feedback>

    {
      node_id:17
      parents:6,16
      content:But wait: Also b+7=? and 9*b+7=? Possibly b+7=56 and 9*b+7=448? 448/56=8 Yes.
    }

  </feedback>

  <aggeregate>

    {
      node_id:18
      parents:10,11,12,13,14,15,16
      content:Sum=21+49=70
    }

  </aggeregate>

</think>

<answer>

  70

</answer>
    """
    # prompt += "\n Now I have a math question.Please generate the thinking process and final answer for solving this math problem according to the above requirements and format.\n"
    # prompt += f"Question:{q}\n"
    prompt += "\n Now I have a math problem's query、solution and answer.Please rewrite the 'solution' into the thinking process for using a big language model to solve this math problem and the final result, in accordance with the aforementioned requirements and format.Sometimes feedback, associative thinking, reverse thinking etc. can also be added to demonstrate the thinking process of the model.Your reasoning process should not reflect that I provided the reference problem-solving process to you.\n"
    prompt += f"Query:{q}\n"
    prompt += f"Solution:{s}\n"
    prompt += f"Answer:{a}\n"
    return prompt

def get_answer(sample, client):
    """
    一个带有自动重试逻辑的、更健壮的API请求函数。
    """
    prompt = construct_prompt(sample)
    q, s,a = sample
    
    max_retries = 5  # 设置一个请求最多重试5次
    retry_delay = 5  # 每次重试前，等待5秒

    for attempt in range(max_retries):
        try:
            # --- 这是您原来的主要逻辑 ---
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                n=1,
                temperature=1.0,
                top_p=0.8
            )
            result = response.choices[0].message.content
            
            # --- 拆分和判断的逻辑也放在这里 ---
            parts = result.split('</think>')
            if len(parts) == 2:
                # ... (您原来的拆分和提取答案的逻辑) ...
                match = re.search(r"<answer>([\s\S]*?)</answer>", parts[1].strip())
                if match:
                    predict_answer = match.group(1).strip()
                else:
                    predict_answer = ""
                
                # 调用 judge API (这里也可能触发429，所以整个逻辑都在try块中)
                is_correct = llm_judge_via_api(predict_answer, a, api_url_judge, api_key_judge, judge_model_name)
                
                answer_info = { "all": result, "judge": is_correct }
            else:
                answer_info = { "all": result, "judge": "split_failed" }
            
            # 如果代码能成功运行到这里，说明没有出错，直接返回结果并跳出循环
            return answer_info

        # --- 错误处理逻辑 ---
        except (APIError, RateLimitError) as e:
            # 判断捕获到的错误是不是 429
            if hasattr(e, 'status_code') and e.status_code == 429:
                print(f"触发API速率限制。将在 {retry_delay} 秒后进行第 {attempt + 2} 次尝试...")
                time.sleep(retry_delay)
                # 可选：让下一次等待的时间更长一些，避免连续冲击服务器
                # retry_delay *= 1.5 
            else:
                # 如果是其他类型的API错误（如认证失败、参数错误等），则直接抛出，不再重试
                print(f"发生了一个非429的API错误: {e}")
                # 将错误信息返回，方便记录
                return {"all": str(e), "judge": "api_error"}
        
        except Exception as e:
            # 捕获其他所有意想不到的错误（如网络中断等）
            print(f"发生未知错误: {e}。将在 {retry_delay} 秒后重试...")
            time.sleep(retry_delay)

    # 如果 for 循环执行完了（即所有重试都失败了），则返回一个失败标记
    print("已达到最大重试次数，该样本处理失败。")
    return {"all": "Max retries exceeded", "judge": "retry_failed"}
# def get_answer(sample, client):
#     prompt = construct_prompt(sample)
#     q,a = sample
#     response = client.chat.completions.create(
#         model=model,
#         messages=[{"role": "user", "content": prompt}],
#         n=1,
#         temperature=1.0,
#         top_p=0.8
#     )
#     result = response.choices[0].message.content
#     parts = result.split('</think>')
#     if len(parts) == 2:
#         part1 = parts[0]+'</think>'
#         part1 = part1.strip()
#         part2 = parts[1].strip()
#         # print("拆分后第一部分：")
#         # print(part1)
#         # print("\n拆分后第二部分：")
#         # print(part2)
#         match = re.search(r"<answer>([\s\S]*?)</answer>", part2)
#         if match:
#           predict_answer = match.group(1).strip()
#         else:
#           print("Cannot answer found in the output.")
#           predict_answer = ""
#         is_correct = llm_judge_via_api(predict_answer, a, api_url_judge, api_key_judge, judge_model_name)
#         #print(is_correct)
#         answer_info = {
#             "all":result,
#             "judge":is_correct 
#         }
#     else:
#         answer_info = {
#             "all": result,
#             "judge": "split_failed"
#         }
#     return answer_info


def load_or_cache_data():
    df = pd.read_parquet("/ssd5/rxliu/datasets/Olympiads_hard/data/train-00000-of-00001.parquet")
    return df

def main():
    try:
        # 加载数据（使用缓存机制）
        df = load_or_cache_data()
        print("数据加载完成")

        client = OpenAI(base_url=api_url_judge, api_key=api_key_judge)
        start = 2700
        end = len(df)-1
        chunk_size = 50  # 设置块大小，每50条保存一次
        output_file = "/ssd5/rxliu/data/result_data_Olympids_qwen3-max_sloution.xlsx"
        if start < 0 or end >= len(df) or start > end:
            print(f"索引无效！请确保 0≤start≤end<{len(df)}")
            return
        def process(i):
            sample = df.iloc[i]
            answer = get_answer((sample["problem"],sample["solution"],sample["answer"]), client)
            if answer["judge"] != True:
                print(sample["problem"],"第二次尝试")
                answer = get_answer((sample["problem"],sample["solution"],sample["answer"]), client)
                print(answer["judge"])
            return {
                "question": sample["problem"],
                "answer": sample["answer"],
                "solution": sample["solution"],
                "prompt": answer["all"],
                "judge": answer["judge"],
            }
        for i in range(start, end, chunk_size):
            chunk_start = i
            # 确保最后一个块不会超出总数据范围
            chunk_end = min(i + chunk_size, end) 
            
            print(f"正在处理索引从 {chunk_start} 到 {chunk_end - 1} 的数据...")

            with ThreadPoolExecutor(max_workers=5) as executor:
                # 处理当前块的所有样本
                chunk_outputs = list(executor.map(process, range(chunk_start, chunk_end)))

            # 将当前块的结果转换为 DataFrame
            new_data_df = pd.DataFrame(chunk_outputs)

            # 保存逻辑：读取现有文件，拼接新数据，然后保存
            try:
                # 若文件存在，读取后拼接
                existing_df = pd.read_excel(output_file, engine='openpyxl')
                result_df = pd.concat([existing_df, new_data_df], ignore_index=True)
            except FileNotFoundError:
                # 若文件不存在，直接用新数据
                result_df = new_data_df
            
            # 保存（覆盖式保存，因为已拼接了历史数据）
            result_df.to_excel(output_file, index=False, engine='openpyxl')
            
            print(f"索引从 {chunk_start} 到 {chunk_end - 1} 的数据已成功保存到 {output_file}")
        
        print(f"所有数据处理完成！最终结果已保存到 {output_file}")
        
    except Exception as e:
        print(f"程序运行出错: {str(e)}")

if __name__ == "__main__":
    main()
