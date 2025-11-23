import json

# 定义文件路径
file_paths = ['/ssd5/rxliu/datasets/SFT-Data/Olympiads-pre2000-sft-data-json/test.json', '/ssd5/rxliu/datasets/SFT-Data/GSM8K-sft-data-json/test.json']
output_file = '/ssd5/rxliu/datasets/SFT-Data/Olympiads-2000+GSM8K-7200-json/test.json'

# 用于存放所有数据的空列表
merged_data = []

# 1. 循环读取每个文件并将数据添加到列表中
for file_path in file_paths:
    with open(file_path, 'r', encoding='utf-8') as f:
        # 假设每个JSON文件内容是一个列表（list of objects）
        data = json.load(f)
        if isinstance(data, list):
            merged_data.extend(data)
        else:
            # 如果文件内容不是列表，而是单个对象，可以根据需要处理
            # 比如，直接添加到列表中作为一个元素
            merged_data.append(data)

# 2. 将合并后的数据写入新的 JSON 文件
with open(output_file, 'w', encoding='utf-8') as outfile:
    # 使用 indent=4 使输出的JSON文件更易读
    json.dump(merged_data, outfile, ensure_ascii=False, indent=2)

print(f"成功合并 {file_paths} 到 {output_file}。")