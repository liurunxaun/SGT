import json
import argparse
import numpy as np
from transformers import AutoTokenizer
from tqdm import tqdm
import os

def calculate_token_lengths(data_path, model_path):
    print(f"Loading tokenizer from: {model_path}")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    except Exception as e:
        print(f"Error loading tokenizer: {e}")
        return

    print(f"Loading data from: {data_path}")
    with open(data_path, 'r', encoding='utf-8') as f:
        # 处理可能的 JSONL 格式或标准 JSON 列表格式
        try:
            data = json.load(f)
            if not isinstance(data, list):
                print("Error: JSON content is not a list.")
                return
        except json.JSONDecodeError:
            # 尝试读取 JSONL
            f.seek(0)
            data = [json.loads(line) for line in f]

    print(f"Total samples: {len(data)}")
    
    lengths = []
    
    print("Calculating token lengths...")
    for item in tqdm(data):
        text_content = ""
        
        # 自动识别常见格式
        # 1. 常见的 ShareGPT/ChatML 格式 (conversations / messages)
        if "conversations" in item:
            msgs = item["conversations"]
            # 使用 tokenizer 的模版处理，这样最准（包含特殊字符）
            if hasattr(tokenizer, "apply_chat_template"):
                try:
                    # 我们只算 token 长度，不需要生成
                    encoded = tokenizer.apply_chat_template(msgs, tokenize=True)
                    lengths.append(len(encoded))
                    continue
                except:
                    pass # 如果模版失败，回退到文本拼接
            
            # 手动拼接 fallback
            for msg in msgs:
                text_content += str(msg.get("value", "")) or str(msg.get("content", ""))

        elif "messages" in item:
            msgs = item["messages"]
            if hasattr(tokenizer, "apply_chat_template"):
                try:
                    encoded = tokenizer.apply_chat_template(msgs, tokenize=True)
                    lengths.append(len(encoded))
                    continue
                except:
                    pass
            for msg in msgs:
                text_content += str(msg.get("content", ""))

        # 2. Alpaca 格式 (instruction / input / output)
        elif "instruction" in item and "output" in item:
            text_content = item["instruction"] + "\n" + item.get("input", "") + "\n" + item["output"]
            
        # 3. 纯文本格式 (text)
        elif "text" in item:
            text_content = item["text"]
            
        else:
            # 实在不知道啥格式，就把所有 value 拼起来算个大概
            text_content = " ".join([str(v) for v in item.values()])

        # Tokenize
        token_ids = tokenizer.encode(text_content, add_special_tokens=True)
        lengths.append(len(token_ids))

    if not lengths:
        print("No valid data found.")
        return

    # 统计分析
    lengths = np.array(lengths)
    max_len = np.max(lengths)
    min_len = np.min(lengths)
    avg_len = np.mean(lengths)
    p50 = np.percentile(lengths, 50)
    p90 = np.percentile(lengths, 90)
    p95 = np.percentile(lengths, 95)
    p98 = np.percentile(lengths, 98)
    p99 = np.percentile(lengths, 99)

    print("\n" + "="*40)
    print("📊 数据长度统计报告 (Tokens)")
    print("="*40)
    print(f"数据总量: {len(lengths)}")
    print(f"最小长度: {int(min_len)}")
    print(f"平均长度: {int(avg_len)}")
    print(f"最大长度: {int(max_len)}  <-- 只有这个数很大吗？")
    print("-" * 20)
    print(f"P50 (中位数): {int(p50)}")
    print(f"P90 (涵盖90%): {int(p90)}")
    print(f"P95 (涵盖95%): {int(p95)}")
    print(f"P98 (涵盖98%): {int(p98)}")
    print(f"P99 (涵盖99%): {int(p99)}")
    print("="*40)

    # 给出建议
    recommended = int(p98)
    # 向上取整到最近的 256 倍数 (显卡友好)
    recommended = ((recommended // 256) + 1) * 256
    
    # 设置一个下限，比如不少于 2048
    if recommended < 2048: recommended = 2048
    
    print(f"💡 建议设置 max_seq_length: {recommended}")
    
    if max_len > recommended * 2:
        print(f"⚠️ 注意: 你最大的数据 ({int(max_len)}) 远超建议值。")
        print(f"   如果你设置 {recommended}，将会有约 2% 的超长数据被截断。")
        print("   如果这部分超长数据很重要，请考虑设大一点；如果只是噪音，直接截断即可提速。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", type=str, required=True, help="Path to json file")
    parser.add_argument("--model_path", type=str, required=True, help="Path to HF model")
    args = parser.parse_args()

    calculate_token_lengths(args.data_path, args.model_path)