import pandas as pd
import json
from datasets import Dataset
import os

# ================= 配置 =================
TEST_FILE = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/generate_test/test_qwen3-max_graph_results_correct.xlsx"
OUTPUT_DIR = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/sft_format"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_conversation(row):
    """
    从数据行创建对话格式
    输入: problem
    输出: graph_structured_reasoning (包含 <think> 和 <answer>)
    """
    conversation = [
        {
            "role": "user",
            "content": f"Question: {row['problem']}"
        },
        {
            "role": "assistant",
            "content": row['graph_structured_reasoning']
        }
    ]
    return conversation

def main():
    print("="*80)
    print("转换 Test 数据集为 SFT 格式")
    print("="*80)
    
    # ========== 1. 读取文件 ==========
    print(f"\n📖 读取文件: {TEST_FILE}")
    
    if not os.path.exists(TEST_FILE):
        print(f"❌ 文件不存在: {TEST_FILE}")
        return
    
    # 根据文件扩展名选择读取方法
    if TEST_FILE.endswith('.xlsx'):
        df_test = pd.read_excel(TEST_FILE)
        print(f"✓ 读取 Excel 文件，共 {len(df_test)} 条记录")
    elif TEST_FILE.endswith('.parquet'):
        df_test = pd.read_parquet(TEST_FILE)
        print(f"✓ 读取 Parquet 文件，共 {len(df_test)} 条记录")
    else:
        print(f"❌ 不支持的文件格式: {TEST_FILE}")
        return
    
    # 显示列名
    print(f"✓ 数据列: {df_test.columns.tolist()}")
    
    # 检查必需的列
    required_cols = ['problem', 'graph_structured_reasoning']
    missing_cols = [col for col in required_cols if col not in df_test.columns]
    if missing_cols:
        print(f"❌ 缺少必需的列: {missing_cols}")
        return
    
    # ========== 2. 转换为对话格式 ==========
    print(f"\n🔄 转换为对话格式...")
    
    test_conversations = []
    for idx, row in df_test.iterrows():
        conversation = create_conversation(row)
        test_conversations.append({
            "messages": conversation,
            "source": "test_correct",
            "problem_id": row['id'] if 'id' in row else idx
        })
    
    print(f"✓ 成功转换 {len(test_conversations)} 条数据")
    
    # ========== 3. 保存为训练格式（只有 messages） ==========
    print(f"\n💾 保存训练格式（只有 messages 字段）...")
    
    # 只保留 messages 字段
    test_data_clean = [{"messages": item["messages"]} for item in test_conversations]
    
    # JSONL 格式
    test_jsonl = os.path.join(OUTPUT_DIR, "test.jsonl")
    with open(test_jsonl, 'w', encoding='utf-8') as f:
        for item in test_data_clean:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    print(f"✓ JSONL: {test_jsonl}")
    
    # Parquet 格式
    test_parquet = os.path.join(OUTPUT_DIR, "test.parquet")
    pd.DataFrame(test_data_clean).to_parquet(test_parquet, index=False)
    print(f"✓ Parquet: {test_parquet}")
    
    # HuggingFace Dataset 格式
    test_dataset = Dataset.from_pandas(pd.DataFrame(test_data_clean))
    test_dataset_dir = os.path.join(OUTPUT_DIR, "test_dataset")
    test_dataset.save_to_disk(test_dataset_dir)
    print(f"✓ HF Dataset: {test_dataset_dir}")
    
    # ========== 4. 保存完整版本（包含额外字段） ==========
    print(f"\n💾 保存完整版本（包含 source 和 problem_id）...")
    
    test_full_parquet = os.path.join(OUTPUT_DIR, "test_full.parquet")
    pd.DataFrame(test_conversations).to_parquet(test_full_parquet, index=False)
    print(f"✓ 完整版 Parquet: {test_full_parquet}")
    
    # ========== 5. 显示统计信息 ==========
    print(f"\n{'='*80}")
    print("📊 统计信息")
    print(f"{'='*80}")
    print(f"总数据量: {len(test_conversations)} 条")
    
    # 检查数据内容长度
    content_lengths = [len(item['messages'][1]['content']) for item in test_conversations]
    print(f"\n模型输出长度统计:")
    print(f"  - 最短: {min(content_lengths)} 字符")
    print(f"  - 最长: {max(content_lengths)} 字符")
    print(f"  - 平均: {sum(content_lengths)/len(content_lengths):.0f} 字符")
    
    # ========== 6. 显示示例 ==========
    print(f"\n{'='*80}")
    print("📝 数据示例（前2条）:")
    print(f"{'='*80}")
    
    for i, item in enumerate(test_data_clean[:2], 1):
        print(f"\n【示例 {i}】")
        print("-"*80)
        for msg in item['messages']:
            print(f"\n{msg['role'].upper()}:")
            content = msg['content']
            if len(content) > 300:
                print(content[:300] + "...")
            else:
                print(content)
        print("="*80)
    
    # ========== 7. 使用说明 ==========
    print(f"\n✅ 转换完成！")
    print(f"\n生成的文件:")
    print(f"【用于训练/评估】（只有 messages 字段）")
    print(f"  - test.jsonl          ← 推荐使用")
    print(f"  - test.parquet")
    print(f"  - test_dataset/")
    print(f"\n【用于分析】（包含额外字段）")
    print(f"  - test_full.parquet")
    print(f"\n保存位置: {OUTPUT_DIR}")
    print(f"\n使用方式:")
    print(f"python sft.py \\")
    print(f"    --dataset_name {OUTPUT_DIR}/train_mixed_shuffled.jsonl \\")
    print(f"    --eval_dataset_name {OUTPUT_DIR}/test.jsonl \\")
    print(f"    --eval_strategy steps \\")
    print(f"    --eval_steps 500 \\")
    print(f"    ...")

if __name__ == "__main__":
    main()