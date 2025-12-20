import json
import glob
import os

# 你的数据路径
DATA_DIR = "/ssd5/rxliu/datasets/livecodebench_lite"

def check_columns():
    # 找文件
    files = glob.glob(os.path.join(DATA_DIR, "*.json*"))
    if not files:
        print("❌ Error: No json/jsonl files found in directory!")
        return

    target_file = files[0]
    print(f"📂 Inspecting file: {target_file}")

    sample = None
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            if target_file.endswith('.jsonl'):
                # JSONL: 读第一行
                line = f.readline()
                sample = json.loads(line)
            else:
                # JSON: 读整个文件取第一个
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    sample = data[0]
                elif isinstance(data, dict):
                    # 有时候数据集被包在类似 {'data': [...]} 里面
                    keys = list(data.keys())
                    print(f"⚠️ Root keys: {keys}")
                    if 'data' in keys or 'questions' in keys:
                        sample = data[keys[0]][0]
                    else:
                        sample = data
                        
        if sample:
            print("\n✅ Found Columns (Keys):")
            print("--------------------------------------------------")
            for key in sample.keys():
                # 打印 key 和 数据类型，方便确认
                content_preview = str(sample[key])[:50].replace('\n', ' ')
                print(f"🔑 {key:<20} | Type: {type(sample[key]).__name__:<5} | Ex: {content_preview}...")
            print("--------------------------------------------------")
            
            # 重点检查题目描述在哪
            print("\n🧐 Diagnosis:")
            if 'question_content' in sample:
                print("👍 Main Question found in: 'question_content'")
            elif 'content' in sample:
                print("👍 Main Question found in: 'content'")
            elif 'prompt' in sample:
                print("👍 Main Question found in: 'prompt'")
            else:
                print("❓ Cannot identify question column automatically. Please check the list above.")

    except Exception as e:
        print(f"❌ Error reading file: {e}")

if __name__ == "__main__":
    check_columns()