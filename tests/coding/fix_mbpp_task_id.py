import json
from pathlib import Path

# 原始 samples 文件（你的那个）
src = Path("/ssd5/rxliu/projects/open-r1-main/results/samples-Qwen3-8B-Base-MbppPlus-20251203-MbppPlus.jsonl")
# 修正后的文件
dst = Path("/ssd5/rxliu/projects/open-r1-main/results/samples-Qwen3-8B-Base-MbppPlus-20251203-MbppPlus_fixed.jsonl")

print("读取:", src)

n_lines = 0
n_changed = 0

with src.open("r", encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
    for line in fin:
        if not line.strip():
            continue
        obj = json.loads(line)
        tid = obj.get("task_id")

        if tid is None:
            # 如果这一行根本没有 task_id，就直接原样写回去（理论上不应该发生）
            fout.write(line)
            continue

        # 统一转成字符串
        tid_str = str(tid)

        # 如果没有前缀 Mbpp/，就加上
        if not tid_str.startswith("Mbpp/"):
            tid_new = f"Mbpp/{tid_str}"
            obj["task_id"] = tid_new
            n_changed += 1
        else:
            # 已经是 Mbpp/xxx 的就不动
            obj["task_id"] = tid_str

        fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        n_lines += 1

print(f"总行数: {n_lines}")
print(f"修改了 task_id 的行数: {n_changed}")
print("已写入:", dst)
