import json
from collections import Counter

file_path = '/ssd5/rxliu/datasets/rcmu/new_math_data.jsonl'

# 初始化计数器
cnt_counter = Counter()

# 逐行读取并统计，这样即使文件很大也不会占用过多内存
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                # 获取 correct_cnt 的值
                c_cnt = item.get('correct_cnt')
                # 只有在值为 1, 2, 3, 4 时才统计（如果需要统计所有值，去掉这个判断即可）
                if c_cnt in [1, 2, 3, 4]:
                    cnt_counter[c_cnt] += 1
            except json.JSONDecodeError:
                continue # 跳过无法解析的行
            except Exception as e:
                continue

    # 输出结果
    print("统计结果：")
    for i in [1, 2, 3, 4]:
        print(f"correct_cnt 为 {i} 的数量: {cnt_counter[i]}")

except FileNotFoundError:
    print(f"找不到文件: {file_path}")