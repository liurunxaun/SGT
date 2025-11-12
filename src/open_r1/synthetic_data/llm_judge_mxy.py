# import requests

# def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
#     prompt = (
#         f"I will give you predict_answer and ground_truth. I need you to compare them and tell me wether the predict_answer is right or wrong"
#         f"predict_answer: {answer}"
#         f"ground_truth: {ground_truth}"
#         f"""
#         You need to pay attention that: 
#         1. Your output must exactly only can be "right" or "wrong".
#         2. The two answer that I give you may be differet type. I need you to judge based on semantics instead of simply seeing if it's the same
#         """
#     )
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {api_key}"
#     }
#     data = {
#         "model": judge_model_name,
#         "messages": [
#             {"role": "user", "content": prompt}
#         ]
#     }
#     resp = requests.post(api_url, headers=headers, json=data)
#     resp.raise_for_status()
#     resp_json = resp.json()
#     # 假设返回格式类似 OpenAI：resp_json["choices"][0]["message"]["content"]
#     verdict = resp_json["choices"][0]["message"]["content"].strip().lower()
#     return verdict == "right"


import requests

def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name, problem):
    prompt = (
        f'''
        You are an answer evaluator.

I will give you a problem, a predicted answer, and the ground truth answer.
Your job is to decide if the predicted answer is correct based on the problem and the ground truth answer.

Problem: {problem}
Predicted Answer: {answer}
Ground Truth Answer: {ground_truth}

Rules:
1. Compare the numeric values of the predicted answer and the ground truth.
   - As the answer to this problem, the meaning of the predicted answer must match the ground truth in order to be marked as 'right'.
   - Do NOT allow any rounding, approximation, or tolerance. For example, 233.5 is wrong if the ground truth is 233.
2. Ignore formatting symbols like LaTeX syntax such as \( \), \\$, etc.
3. If the predicted answer includes extra explanation or wording but the numeric value exactly matches, mark as 'right'.
4. Your output must be exactly either 'right' or 'wrong', nothing else.
5. For situations where the predicted answer and the ground truth have the same meaning but different expressions, please mark them as 'right', such as '20.00' and '20' being the same, '1563' and '1,563' being the same, '2h20min' and '140min' being the same, etc
'''
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
    verdict = resp_json["choices"][0]["message"]["content"].strip().lower()
    return verdict == "right"