import json

# 你的文件路径
file_path = "/ssd5/rxliu/projects/open-r1-main/results/inference-Qwen3-8B-Base-20251204-MbppPlus-SignatureFix-V1.jsonl"

data = []

print(f"正在读取文件: {file_path} ...")

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        for index, line in enumerate(f):
            line = line.strip()
            if not line: continue
            
            try:
                item = json.loads(line)
                data.append(item)
            except json.JSONDecodeError:
                print(f"第 {index+1} 行 JSON 解析失败: {line[:50]}...")

    print(f"读取完成，共获取 {len(data)} 条记录。")

    # 打印第一条数据来看看字段结构
    if data:
        print("\n--- 第一条数据结构 ---")
        print(json.dumps(data[0], indent=4, ensure_ascii=False))
        
        # 检查是否符合 EvalPlus 的通常要求
        keys = data[0].keys()
        if "task_id" not in keys and "id" in keys:
            print("\n[注意] 检测到 'id' 字段但没有 'task_id'。")
            print("如果要使用 evalplus 评测，可能需要将 'id' 映射为 MBPP+ 的标准 task_id (例如 'Mbpp/1')。")

except FileNotFoundError:
    print(f"错误: 找不到文件 {file_path}")