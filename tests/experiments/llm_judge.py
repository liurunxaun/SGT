import requests
import os
from openai import OpenAI
import json


def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
    prompt = (
        f'''
        You are an excellent answer evaluator.I will give you a predicted answer, and the ground truth. And you need to decide wether the predicted answer is right or wrong based on the ground truth.
        Input:
            Predicted Answer: {answer}
            Ground Truth: {ground_truth}
        Output:
            right or wrong

        There are some rules that you need to pay attention:
        1. Do not allow any rounding, approximation, or tolerance. For example, 233.5 is wrong if the ground truth is 233.
        2. Ignore formatting symbols like LaTeX syntax such as \( \), \\$, etc.
        3. The predicted answer may be a sentence rather than just a number. I need you to understand the semantics and determine whether the predicted answer is consistent with the ground truth. 
        4. If the predicted answer includes extra explanation or wording like but the numeric value matches, output 'right'.
        5. For situations where the predicted answer and the ground truth have the same meaning but different expressions, please mark them as 'right'
        6. Your output must be exactly either 'right' or 'wrong', nothing else.
        
        Below are some examples:
        1.
        Input:
            Predicted Answer: 20.00
            Ground Truth: 20
        Output:
            right
        
        2.
        Input:
            Predicted Answer: 1563
            Ground Truth: 1,563
        Output:
            right
        
        3.
        Input:
            Predicted Answer: 2h20min
            Ground Truth: 140min
        Output:
            right
        
        4.
        Input:
            Predicted Answer: 2$
            Ground Truth: 2.00
        Output:
            right
        
        5.
        Input:
            Predicted Answer: 150%
            Ground Truth: 150
        Output:
            right
        
        6.
        Input:
            Predicted Answer: Josh made a profit of $70,000.
            Ground Truth: 70000
        Output:
            right
      '''
    )

    if judge_model_name == "qwen3-next-80b-a3b-instruct":

        client = OpenAI(
            # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
            api_key = api_key,
            base_url = api_url
        )

        completion = client.chat.completions.create(
            # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
            model=judge_model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ]
        )
        response = completion.model_dump_json()
        verdict = json.loads(response)["choices"][0]["message"]["content"]
    
    else:
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
        verdict = resp_json["choices"][0]["message"]["content"].strip().lower()
    
    print()
    print(f"verdict: {verdict}")
    print()

    return verdict == "right"