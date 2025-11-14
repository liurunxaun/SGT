import pandas as pd
import re
from tqdm import tqdm
from math_verify import parse, verify


# ===== 用户配置 =====
input_path = "/data/home/the/rxliu/projects/open-r1-main/tests/results/olympiads+gsm8k_5000_qwen0.6B_sft_main_20251110_temp.csv"
output_path = "/data/home/the/rxliu/projects/open-r1-main/tests/results/olympiads+gsm8k_5000_qwen0.6B_sft_main_20251110_math_verify_judged.csv"


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

    # 通过 math-verify 判断
    try:
        # Parse the gold and predicted answers
        gold = parse(ground_truth_answer) # Gold standard answer
        answer = parse(predict_answer) # Predicted answer
        # Verify if the parsed answers are equivalent
        is_correct = verify(gold, answer)
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
