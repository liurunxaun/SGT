from datasets import load_dataset
import pandas as pd
import os
import csv
from openai import OpenAI

API_KEY = "sk-zW6D55kW8GpDnUFSz5wJ5oxC72kZnM9mRPwhwZd2VNTQIpgX"
BASE_URL = "https://api.openai-proxy.org/v1"
model = "gpt-4o"
DATA_CACHE_FILE = "MATH-500/cached_data.pkl"  # 数据缓存文件路径


def construct_prompt(sample):
    q, s, a = sample
    prompt = "You are a helpful AI Assistant that provides well-reasoned and detailed responses. You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: \n...\n<|FunctionCallEnd|>\n\n...\n<|FunctionCallEnd|>\n"
    prompt += "During the  phase you should organize the chain of thought using five tags:\n"
    prompt += "Known：The known conditions explicitly provided from the problem statement or the facts recognized as axioms.\n"
    prompt += "Generate: from the current node, generate one or more new node(s).\n"
    prompt += "Aggregate: merge multiple nodes or jointly reason over them to produce a new node.\n"
    prompt += "Feedback: go back to a previous node.\n"
    prompt += "Refine: improve the current node.\n"
    prompt += "During the  phase,you must start with the Known tag and wrap the output of that step with that tag. For example: <Known>[content]</Known>\n"
    prompt += "At each further reasoning step you must choose one of these four tags and wrap that step’s output with the chosen tag. For example: <Generate>[content]</Generate>\n"
    prompt += "Below I’ll give you an example:\n"
    prompt += "Query:Find the sum of all integer bases $$b>9$$ for which $$17_{b}$$ is a divisor of $$97_{b}$$\n"
    prompt += "<Known> $$b>9$$ ,$$17_{b}$$ is a divisor of $$97_{b}$$,$$b$$is an integer</Known>\n"
    prompt += "<Refine>$$17_{b}=b+7$$,$$97_{b}=9*b+7$$,$$9*b+7=k(b+7)$$，$$k>0$$,$$k$$is an integaer</Refine>\n"
    prompt += "<Aggregate>$$b=(7-7k)/(k-9)$$,$$1<k<9$$,$$k$$is an integaer</Aggregate>\n"
    prompt += "<Generate>1.if $$k=2,b=1$$,false.2. if $$k=3,b=14/6$$,false.3. if $$k=4,b=21/5$$,false.4. if $$k=5,b=7$$,false.5. if $$k=6,b=35/3$$,false.6. if $$k=7,b=21$$,true. 7.if $$k=8,b=49$$,true.</Generate>\n"
    prompt += "<Aggregate> $$Sum=21+49=70$$</Aggregate>\n"
    prompt += "<Answer>$$70$$</Answer>\n"
    prompt += "Now I have a math problem's query, solution, and answer. Please modify the solution to the content of thestage according to the above requirements and format, and output the results of theandstages to me.Do not output any other content.\n"
    prompt += f"Query:{q}\n"
    prompt += f"Solution:{s}\n"
    prompt += f"Answer:{a}\n"
    return prompt


def get_answer(sample, client):
    prompt = construct_prompt(sample)
    print(prompt)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    # 修复了原代码中的content()调用错误
    answer = response.choices[0].message.content
    print(answer)
    return answer


def load_or_cache_data():
    """加载数据，如果本地有缓存则使用缓存，否则从HuggingFace加载并缓存"""
    # 创建数据目录（如果不存在）
    os.makedirs(os.path.dirname(DATA_CACHE_FILE), exist_ok=True)

    if os.path.exists(DATA_CACHE_FILE):
        print("从本地缓存加载数据...")
        return pd.read_pickle(DATA_CACHE_FILE)
    else:
        print("从HuggingFace加载数据...")
        dataset = load_dataset("HuggingFaceH4/MATH-500")
        df = dataset["test"].to_pandas()
        # 保存数据到本地缓存
        df.to_pickle(DATA_CACHE_FILE)
        print(f"数据已缓存到 {DATA_CACHE_FILE}")
        return df


def main():
    # 加载数据（使用缓存机制）
    df = load_or_cache_data()
    print("数据加载完成")

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    outputs = []

    # 创建输出目录（如果不存在）
    output_dir = os.path.dirname("MATH-500/result_prompt.csv")
    os.makedirs(output_dir, exist_ok=True)

    for i in range(5):
        # 取第i条数据
        sample = df.iloc[i]
        print(f"\n【题目 {i + 1}】:", sample["problem"])
        print("【解题步骤】:", sample["solution"])
        print("【答案】:", sample["answer"])

        data = (sample["problem"], sample["solution"], sample["answer"])
        answer = get_answer(data, client)
        outputs.append((sample["problem"], sample["solution"], sample["answer"], answer))

    # 保存结果
    output_file = "MATH-500/result_prompt_4o.csv"
    with open(output_file, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        header = ["problem", "solution", "answer", "prompt"]
        writer.writerow(header)
        for i, (q, s, a, p) in enumerate(outputs):
            row = [q, s, a, p]
            writer.writerow(row)
    print(f"结果已保存到 {output_file}")


if __name__ == "__main__":
    main()
