import pandas as pd
import re
from tqdm import tqdm
from llm_judge import llm_judge_via_api

# ===== 用户配置 =====
input_path = "/data/home/the/rxliu/projects/open-r1-main/tests/utils/_main_20251110_temp.csv"
output_path = "/data/home/the/rxliu/projects/open-r1-main/tests/utils/_main_20251110_judged.csv"

# LLM 评审接口配置（根据你的实际情况填写）
# api_url
api_url = "https://ai-yyds.com/v1/chat/completions"
# api key
api_key = "sk-noxrhBbTTb9qvHlGBb6d16D09a62480281C2E330E014Cf34"
# 选择LLM Judge的模型
judge_model_name = "gpt-5"


# ===== 读取 CSV =====
df = pd.read_csv(input_path)
df.columns = df.columns.str.strip()

# 确认列存在
assert "predicted_answer" in df.columns and "ground_truth" in df.columns, "缺少必要的列"

results = []
total = 0
right = 0
accuracy = 0

# ===== 遍历每一行 =====
for idx, row in tqdm(df.iterrows(), total=len(df)):
    predict_answer = str(row["predicted_answer"])
    ground_truth = str(row["ground_truth"])

    # 提取 ground_truth 中的最终答案
    match = re.search(r"####\s*([-\d\.]+)", ground_truth)
    if match:
        ground_truth_answer = match.group(1).strip()
    else:
        ground_truth_answer = ground_truth
        print(f"[Warning] No final answer found at row {idx}")

    # 通过 LLM 评审接口判断
    try:
        is_correct = llm_judge_via_api(
            predict_answer,
            ground_truth_answer,
            api_url,
            api_key,
            judge_model_name
        )
        print(is_correct)
    except Exception as e:
        print(f"[Error] row {idx}: {e}")
        is_correct = None
    
    if is_correct != None:
        total = total + 1
        if is_correct:
            right = right + 1

    if total != 0:
        accuracy = right / total
        print(accuracy)

    # 保存结果
    results.append({
        "index": idx,
        "predicted_answer": predict_answer,
        "ground_truth": ground_truth,
        "ground_truth_answer": ground_truth_answer,
        "is_correct": is_correct,
        "accuracy": accuracy
    })

# ===== 输出结果到新文件 =====
out_df = pd.DataFrame(results)
out_df.to_csv(output_path, index=False)
print(f"result saved at {output_path}")
print(f"accuracy: {accuracy}")
