import requests

def llm_judge_via_api(answer, ground_truth, api_url, api_key, judge_model_name):
    prompt = (
        f"I will give you predict_answer and ground_truth. I need you to compare them and tell me wether the predict_answer is right or wrong"
        f"predict_answer: {answer}"
        f"ground_truth: {ground_truth}"
        f"""
        You need to pay attention that: 
        1. Your output must exactly only can be "right" or "wrong".
        2. The two answer that I give you may be differet type. I need you to judge based on semantics instead of simply seeing if it's the same
        """
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
    return verdict == "right"