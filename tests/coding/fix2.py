import json
import os
import re

# ================= 配置路径 =================
INPUT_FILE = "/ssd5/rxliu/projects/open-r1-main/results/inference-Qwen3-8B-Base-20251204-MbppPlus-SignatureFix-V1.jsonl"
OUTPUT_FILE = INPUT_FILE.replace(".jsonl", "_formatted.jsonl")

# ================= 核心处理函数 =================

def extract_code_from_tags(text):
    """
    1. 提取 <answer>...</answer> 之间的内容
    2. 去掉 markdown 代码块符号
    """
    if not isinstance(text, str):
        return ""
    
    # 1. 正则提取标签内容 (re.DOTALL 允许匹配换行)
    match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL)
    
    if match:
        content = match.group(1).strip()
    else:
        # 如果没找到标签，说明模型没按格式输出，暂时返回空字符串
        # 或者你可以改成 return text 来保留原始输出
        return ""
        
    # 2. 清洗 markdown (```python ... ```)
    # 去掉开头的 ```python 或 ```
    content = re.sub(r'^```(python|py)?\s*', '', content, flags=re.IGNORECASE)
    # 去掉结尾的 ```
    content = re.sub(r'\s*```$', '', content)
    
    return content.strip()

def main():
    print(f"正在处理: {INPUT_FILE}")
    
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 错误: 找不到文件 {INPUT_FILE}")
        return

    processed_data = []
    missing_tag_count = 0

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line: continue
            
            try:
                item = json.loads(line)
                
                # --- 1. 处理 ID ---
                # 兼容 "id": 0 或 "task_id": "Mbpp/0"
                raw_id = item.get("id")
                if raw_id is None:
                    raw_id = item.get("task_id")
                
                # 统一格式化为 "Mbpp/数字"
                if str(raw_id).startswith("Mbpp/"):
                    task_id = str(raw_id)
                else:
                    task_id = f"Mbpp/{raw_id}"

                # --- 2. 提取代码 (completion) ---
                response_text = item.get("response", "")
                extracted_code = extract_code_from_tags(response_text)
                
                if not extracted_code:
                    missing_tag_count += 1
                
                # --- 3. 构建目标格式 ---
                # 严格使用你要求的 "completion" 字段
                new_item = {
                    "task_id": task_id,
                    "completion": extracted_code
                }
                
                processed_data.append(new_item)

            except json.JSONDecodeError:
                print(f"⚠️ 第 {line_num+1} 行 JSON 解析失败，跳过")

    # --- 4. 写入结果 ---
    print(f"正在写入: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:
        for item in processed_data:
            f_out.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n✅ 处理完成！")
    print(f"共生成 {len(processed_data)} 条数据。")
    if missing_tag_count > 0:
        print(f"⚠️ 警告: 有 {missing_tag_count} 条数据没找到 <answer> 标签 (completion 为空)。")
    print(f"输出文件路径: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()