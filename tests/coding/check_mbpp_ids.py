import json
from evalplus.data import get_mbpp_plus

# ① EvalPlus 内置的官方 MBPP+ 任务
problems = get_mbpp_plus()
problem_ids = set(problems.keys())
print("EvalPlus 官方 MBPP+ 任务数:", len(problem_ids))

# ② 你的 samples 路径：改成你真实的那个
SAMPLES_PATH = "/ssd5/rxliu/projects/open-r1-main/results/samples-Qwen3-8B-Base-MbppPlus-20251203-MbppPlus.jsonl"

sample_ids = []
with open(SAMPLES_PATH, "r") as f:
    for line in f:
        if not line.strip():
            continue
        obj = json.loads(line)
        # 按照 EvalPlus README，必须有 "task_id" 字段
        tid = obj.get("task_id")
        if tid is None:
            continue
        sample_ids.append(tid)

sample_ids_set = set(sample_ids)
print("samples 行数:", len(sample_ids))
print("samples 里去重后的 task_id 数:", len(sample_ids_set))

missing = sorted(problem_ids - sample_ids_set)
extra   = sorted(sample_ids_set - problem_ids)

print("\n在官方 problems 里但你的 samples 里缺失的 task_id 数:", len(missing))
print(missing[:50])

print("\n在你的 samples 里但官方 problems 里不存在的 task_id 数:", len(extra))
print(extra[:50])
