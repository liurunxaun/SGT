from datasets import load_dataset
import pandas as pd
import os
import json
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

API_KEY = "sk-UAQem3OyEglkpNxEG3uD0Eh0NCb2XQBJUZ277ccecP32dEDr"
BASE_URL = "https://api.openai-proxy.org/v1"
model = "gpt-4o"

def construct_prompt(sample):
    q, s, a = sample
    prompt = """
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
For the content wrapped in different tags, there are the following formal requirements:
- konwn:It wraps one or more nodes, and the parents of these nodes should all be "none".
- generate:(1) It wraps one node, and the parents of this nodes should be a single node. (2) It wraps two or more nodes, and the parents of these nodes should be a same single node. (3) It wraps two or more nodes, and the parents of these nodes should be mutiple nodes that are the same.
- aggregate：It wraps one node, and the parent of this node should be multiple nodes.
- feedback：It wraps one node, and the parent of this node should be one or more nodes.
- refine:It wraps one node, and the parent of this node should be a single node.
- associative thinking：It wraps one node, and the parent of this node should be one or more nodes.
- reverse thinking：It wraps one node, and the parent of this node should be one or more nodes.
If a tag contains multiple nodes, the parents of these nodes must be same.
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

  <generate>

    {
      node_id:9
      parents:1,3,7
      content:1.if k=2,b=1,false.
    },

    {
      node_id:10
      parents:1,3,7
      content:2. if k=3,b=14/6,false.
    },

    {
      node_id:11
      parents:1,3,7
      content:3. if k=4,b=21/5,false.
    },

    {
      node_id:12
      parents:1,3,7
      content:4. if k=5,b=7,false.
    },

    {
      node_id:13
      parents:1,3,7
      content:5. if k=6,b=35/3,false.
    },

    {
      node_id:14
      parents:1,3,7
      content:6. if k=7,b=21,true. 
    },

    {
      node_id:15
      parents:1,3,7
      content:7.if k=8,b=49,true.
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
    # prompt += "Now I have a math problem's query and answer.Please provide the thinking process and final result of solving the mathe problem according to the above requirements and format.\n"
    # prompt += f"Query:{q}\n"
    # prompt += f"Answer:{a}\n"
    # prompt += "Now I have a math problem's query.Please provide the thinking process and final result of solving the mathe problem according to the above requirements and format.\n"
    # prompt += f"Query:{q}\n"
    prompt += "\n Now I have a math problem's query、solution and answer.Please rewrite the 'solution' into the thinking process for using a big language model to solve this math problem and the final result, in accordance with the aforementioned requirements and format.Sometimes feedback, associative thinking, etc. can also be added to demonstrate the thinking process of the model.\n"
    prompt += f"Query:{q}\n"
    prompt += f"Solution:{s}\n"
    prompt += f"Answer:{a}\n"
    return prompt


def get_answer(sample, client):
    prompt = construct_prompt(sample)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    answer = response.choices[0].message.content
    print(answer)
    return answer


def load_or_cache_data():
    df = pd.read_parquet("/ssd5/rxliu/datasets/Olympiads/data/train-00000-of-00001.parquet")
    return df

def main():
    try:
        # 加载数据（使用缓存机制）
        df = load_or_cache_data()
        print("数据加载完成")

        client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
        outputs = []

        start = 1500
        end = 2000
        if start < 0 or end >= len(df) or start > end:
            print(f"索引无效！请确保 0≤start≤end<{len(df)}")
            return
        def process(i):
            sample = df.iloc[i]
            answer = get_answer((sample["problem"], sample["solution"],sample["answer"]), client)
            return {
                "problem": sample["problem"],
                "solution": sample["solution"],
                "answer": sample["answer"],
                "prompt": answer
            }
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 处理0到num_samples-1的所有样本
            outputs = list(executor.map(process, range(start,end)))

        output_file = "result_data.xlsx"
        result_df = pd.DataFrame(outputs)
        try:
            # 若文件存在，读取后拼接
            existing_df = pd.read_excel(output_file, engine='openpyxl')
            result_df = pd.concat([existing_df, result_df], ignore_index=True)
        except FileNotFoundError:
            # 若文件不存在，直接用新数据
            pass
        # 保存（覆盖式保存，因为已拼接了历史数据）
        result_df.to_excel(output_file, index=False, engine='openpyxl')
        
        print(f"结果已保存到 {output_file}")
        
    except Exception as e:
        print(f"程序运行出错: {str(e)}")

if __name__ == "__main__":
    main()
