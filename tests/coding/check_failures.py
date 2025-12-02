import json
import os
from pathlib import Path

# ====== 修改这里：你的结果文件路径 ======
# 注意：EvalPlus 会在原文件名后加上 _eval_results.json
RESULT_FILE = "/data/home/the/rxliu/projects/open-r1-main/tests/results_coding/samples_humanevalplus_CLEANED_eval_results.json"

def main():
    path = Path(RESULT_FILE)
    if not path.exists():
        print(f"❌ 找不到文件: {path}")
        print("请确认 evalplus.evaluate 是否运行完成？")
        return

    print(f"📖 Reading results from: {path} ...\n")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # EvalPlus 的结果结构通常是 data['eval'] -> { "HumanEval/0": [result_dict, ...], ... }
    # 因为你测的是 pass@1，列表里通常只有 1 个结果，或者我们取第一个。
    
    eval_data = data.get("eval", {})
    
    failed_base = []      # HumanEval 基础版就挂了
    failed_plus_only = [] # 基础版过了，但 HumanEval+ 挂了 (这是 EvalPlus 的核心价值)
    passed_all = []

    for task_id, results in eval_data.items():
        # 结果是一个列表 (取决于你的 samples 数量)，pass@1 通常只看第一个生成的解
        if not results:
            continue
            
        # 取第一个生成结果的评测状态
        # 结果对象里通常有 'base_status' 和 'plus_status'
        res = results[0] 
        
        base_status = res.get("base_status", "fail") # pass / fail
        plus_status = res.get("plus_status", "fail") # pass / fail

        if base_status != "pass":
            failed_base.append(task_id)
        elif plus_status != "pass":
            failed_plus_only.append(task_id)
        else:
            passed_all.append(task_id)

    # ====== 输出统计 ======
    total = len(eval_data)
    print(f"📊 总题数: {total}")
    print(f"✅ 全通过 (Base + Plus): {len(passed_all)}")
    print(f"❌ Base 就错了 (基本逻辑错误): {len(failed_base)}")
    print(f"⚠️ Base 通过但 Plus 错了 (Corner Case 没过): {len(failed_plus_only)}")
    print("-" * 50)

    if failed_base:
        print("\n[🔴 严重错误] Base HumanEval 失败的题目 (建议优先检查):")
        # 排序并打印，每行打印 5 个
        failed_base.sort(key=lambda x: int(x.split('/')[-1]))
        print(", ".join(failed_base))

    if failed_plus_only:
        print("\n[🟠 细节错误] Base 通过但 Plus 失败的题目 (鲁棒性差):")
        failed_plus_only.sort(key=lambda x: int(x.split('/')[-1]))
        print(", ".join(failed_plus_only))

if __name__ == "__main__":
    main()
