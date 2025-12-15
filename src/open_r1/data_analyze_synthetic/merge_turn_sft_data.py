import pandas as pd
import json
from datasets import Dataset
import os
import random

# ================= 配置 =================
BASE_DIR = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files"
TEST_FILE = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/generate_test/test_qwen3-max_graph_results_correct.xlsx"
OUTPUT_DIR = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/sft_format"

# 4个文件的路径
FILE_PARTS = [
    "train_part_1_of_4",
    "train_part_2_of_4",
    "train_part_3_of_4",
    "train_part_4_of_4",
]

# 随机种子，确保可复现
RANDOM_SEED = 42

os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_conversation_from_correct(row):
    """
    从 correct 数据创建对话格式
    使用 graph_structured_reasoning（包含 <think> 和 <answer>）
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

def create_conversation_from_unsolved(row):
    """
    从 unsolved 数据创建对话格式
    使用 solution + answer（标准答案格式）
    """
    # 构建标准答案格式
    if pd.notna(row['ground_truth_solution']) and row['ground_truth_solution'].strip():
        # 有详细解题步骤
        assistant_content = f"<think>\n{row['ground_truth_solution']}\n</think>\n<answer>\n{row['ground_truth_answer']}\n</answer>"
    else:
        # 只有答案，没有详细步骤
        assistant_content = f"<answer>\n{row['ground_truth_answer']}\n</answer>"
    
    conversation = [
        {
            "role": "user",
            "content": f"Question: {row['problem']}"
        },
        {
            "role": "assistant",
            "content": assistant_content
        }
    ]
    return conversation

def main():
    print("="*80)
    print("开始转换 SFT 训练数据（处理4个文件 + test数据）")
    print("="*80)
    
    all_correct_conversations = []
    all_unsolved_conversations = []
    
    # ========== 1. 循环处理4个部分的文件（每部分有 correct 和 unsolved） ==========
    for part_name in FILE_PARTS:
        print(f"\n{'='*80}")
        print(f"📂 处理: {part_name}")
        print(f"{'='*80}")
        
        correct_file = os.path.join(BASE_DIR, f"{part_name}_qwen3-max_graph_results_correct.parquet")
        unsolved_file = os.path.join(BASE_DIR, f"{part_name}_qwen3-max_graph_results_unsolved.parquet")
        
        # --- 读取 correct 数据 ---
        print(f"\n📖 读取 correct 文件: {os.path.basename(correct_file)}")
        if os.path.exists(correct_file):
            df_correct = pd.read_parquet(correct_file)
            print(f"✓ 读取 {len(df_correct)} 条 correct 记录")
            
            # 转换为对话格式
            for idx, row in df_correct.iterrows():
                conversation = create_conversation_from_correct(row)
                all_correct_conversations.append({
                    "messages": conversation,
                    "source": "correct",
                    "part": part_name,
                    "problem_id": row['id']
                })
            print(f"✓ 本文件转换 {len(df_correct)} 条，累计 correct 数据: {len(all_correct_conversations)} 条")
        else:
            print(f"⚠️  文件不存在，跳过")
        
        # --- 读取 unsolved 数据 ---
        print(f"\n📖 读取 unsolved 文件: {os.path.basename(unsolved_file)}")
        if os.path.exists(unsolved_file):
            df_unsolved = pd.read_parquet(unsolved_file)
            print(f"✓ 读取 {len(df_unsolved)} 条 unsolved 记录")
            
            # 统计 solution 为空的数量
            empty_solution = df_unsolved['ground_truth_solution'].isna() | (df_unsolved['ground_truth_solution'].str.strip() == '')
            empty_count = empty_solution.sum()
            print(f"  - 其中 {empty_count} 条没有详细 solution")
            print(f"  - {len(df_unsolved) - empty_count} 条有详细 solution")
            
            # 转换为对话格式
            for idx, row in df_unsolved.iterrows():
                conversation = create_conversation_from_unsolved(row)
                all_unsolved_conversations.append({
                    "messages": conversation,
                    "source": "unsolved",
                    "part": part_name,
                    "problem_id": row['problem_id']
                })
            print(f"✓ 本文件转换 {len(df_unsolved)} 条，累计 unsolved 数据: {len(all_unsolved_conversations)} 条")
        else:
            print(f"⚠️  文件不存在，跳过")
    
    # ========== 2. 统计总数 ==========
    print(f"\n{'='*80}")
    print("📊 数据统计")
    print(f"{'='*80}")
    print(f"✓ Correct 数据总计: {len(all_correct_conversations)} 条")
    print(f"✓ Unsolved 数据总计: {len(all_unsolved_conversations)} 条")
    print(f"✓ 总数据量: {len(all_correct_conversations) + len(all_unsolved_conversations)} 条")
    
    # ========== 3. 保存分开的文件 ==========
    print(f"\n{'='*80}")
    print("💾 保存分开的文件（correct 和 unsolved）")
    print(f"{'='*80}")
    
    # 保存 correct 数据
    if all_correct_conversations:
        # JSONL
        correct_jsonl = os.path.join(OUTPUT_DIR, "train_correct_only.jsonl")
        with open(correct_jsonl, 'w', encoding='utf-8') as f:
            for item in all_correct_conversations:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"✓ Correct JSONL: {correct_jsonl}")
        
        # Parquet
        correct_parquet = os.path.join(OUTPUT_DIR, "train_correct_only.parquet")
        pd.DataFrame(all_correct_conversations).to_parquet(correct_parquet, index=False)
        print(f"✓ Correct Parquet: {correct_parquet}")
    
    # 保存 unsolved 数据
    if all_unsolved_conversations:
        # JSONL
        unsolved_jsonl = os.path.join(OUTPUT_DIR, "train_unsolved_only.jsonl")
        with open(unsolved_jsonl, 'w', encoding='utf-8') as f:
            for item in all_unsolved_conversations:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"✓ Unsolved JSONL: {unsolved_jsonl}")
        
        # Parquet
        unsolved_parquet = os.path.join(OUTPUT_DIR, "train_unsolved_only.parquet")
        pd.DataFrame(all_unsolved_conversations).to_parquet(unsolved_parquet, index=False)
        print(f"✓ Unsolved Parquet: {unsolved_parquet}")
    
    # ========== 4. 混合并打散数据 ==========
    print(f"\n{'='*80}")
    print("🔀 混合并打散数据")
    print(f"{'='*80}")
    
    all_conversations = all_correct_conversations + all_unsolved_conversations
    
    # 设置随机种子并打散
    random.seed(RANDOM_SEED)
    random.shuffle(all_conversations)
    print(f"✓ 使用随机种子 {RANDOM_SEED} 打散数据")
    print(f"✓ 打散后总计: {len(all_conversations)} 条")
    
    # ========== 5. 保存混合后的数据 ==========
    print(f"\n{'='*80}")
    print("💾 保存混合数据（已打散）")
    print(f"{'='*80}")
    
    # 只保留 messages 字段用于训练
    training_data = [{"messages": item["messages"]} for item in all_conversations]
    
    # JSONL 格式（训练用，只有 messages）
    mixed_jsonl = os.path.join(OUTPUT_DIR, "train_mixed_shuffled.jsonl")
    with open(mixed_jsonl, 'w', encoding='utf-8') as f:
        for item in training_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    print(f"✓ 混合 JSONL (训练用): {mixed_jsonl}")
    
    # Parquet 格式（训练用，只有 messages）
    mixed_parquet = os.path.join(OUTPUT_DIR, "train_mixed_shuffled.parquet")
    pd.DataFrame(training_data).to_parquet(mixed_parquet, index=False)
    print(f"✓ 混合 Parquet (训练用): {mixed_parquet}")
    
    # HuggingFace Dataset 格式（训练用，只有 messages）
    dataset = Dataset.from_pandas(pd.DataFrame(training_data))
    dataset_dir = os.path.join(OUTPUT_DIR, "train_mixed_shuffled_dataset")
    dataset.save_to_disk(dataset_dir)
    print(f"✓ HF Dataset (训练用): {dataset_dir}")
    
    # 保存完整版本（包含额外字段，用于分析）
    mixed_full_parquet = os.path.join(OUTPUT_DIR, "train_mixed_shuffled_full.parquet")
    pd.DataFrame(all_conversations).to_parquet(mixed_full_parquet, index=False)
    print(f"✓ 完整版 Parquet (包含source/part/id): {mixed_full_parquet}")
    
    # ========== 6. 最终统计 ==========
    print(f"\n{'='*80}")
    print("📊 最终统计")
    print(f"{'='*80}")
    
    # 统计各部分来源
    from collections import Counter
    part_counter = Counter([item['part'] for item in all_conversations])
    print("\n各文件贡献数据量:")
    for part, count in sorted(part_counter.items()):
        print(f"  - {part}: {count} 条")
    
    # 统计 correct/unsolved 占比
    source_counter = Counter([item['source'] for item in all_conversations])
    print("\n数据来源分布:")
    for source, count in source_counter.items():
        percentage = count / len(all_conversations) * 100
        print(f"  - {source}: {count} 条 ({percentage:.1f}%)")
    
    # ========== 7. 显示示例 ==========
    print(f"\n{'='*80}")
    print("📝 打散后的数据示例（前3条）:")
    print(f"{'='*80}")
    
    for i, item in enumerate(all_conversations[:3], 1):
        print(f"\n【示例 {i}】")
        print(f"来源: {item['source']} | 文件: {item['part']} | ID: {item['problem_id']}")
        print("-"*80)
        for msg in item['messages']:
            print(f"\n{msg['role'].upper()}:")
            content = msg['content']
            if len(content) > 200:
                print(content[:200] + "...")
            else:
                print(content)
        print("="*80)
    
    print("\n✅ 转换完成！")
    print(f"\n生成的文件:")
    print(f"【训练集】")
    print(f"  1. 分开保存:")
    print(f"     - Correct: train_correct_only.jsonl / .parquet")
    print(f"     - Unsolved: train_unsolved_only.jsonl / .parquet")
    print(f"  2. 混合打散:")
    print(f"     - 推荐使用: train_mixed_shuffled.jsonl")
    print(f"     - 或: train_mixed_shuffled.parquet")
    print(f"     - 或: train_mixed_shuffled_dataset/")
    print(f"\n【测试集】")
    print(f"     - test.jsonl")
    print(f"     - test.parquet")
    print(f"     - test_dataset/")
    print(f"\n保存位置: {OUTPUT_DIR}")

    # ========== 额外处理：转换 test 数据集 ==========
    print(f"\n{'='*80}")
    print("📂 处理 Test 数据集")
    print(f"{'='*80}")
    
    if os.path.exists(TEST_FILE):
        print(f"📖 读取: {os.path.basename(TEST_FILE)}")
        
        # 读取 Excel 或 Parquet（根据扩展名判断）
        if TEST_FILE.endswith('.xlsx'):
            df_test = pd.read_excel(TEST_FILE)
        elif TEST_FILE.endswith('.parquet'):
            df_test = pd.read_parquet(TEST_FILE)
        else:
            print(f"⚠️  不支持的文件格式，跳过")
            return
        
        print(f"✓ 读取 {len(df_test)} 条 test 记录")
        
        # 转换为对话格式
        test_conversations = []
        for idx, row in df_test.iterrows():
            conversation = create_conversation_from_correct(row)
            test_conversations.append({
                "messages": conversation,
                "source": "test_correct",
                "problem_id": row['id'] if 'id' in row else idx
            })
        
        print(f"✓ 转换 {len(test_conversations)} 条 test 数据")
        
        # 保存 test 数据（不打散，保持原顺序）
        print(f"\n💾 保存 test 数据...")
        
        # JSONL
        test_jsonl = os.path.join(OUTPUT_DIR, "test.jsonl")
        with open(test_jsonl, 'w', encoding='utf-8') as f:
            for item in test_conversations:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"✓ Test JSONL: {test_jsonl}")
        
        # Parquet
        test_parquet = os.path.join(OUTPUT_DIR, "test.parquet")
        pd.DataFrame(test_conversations).to_parquet(test_parquet, index=False)
        print(f"✓ Test Parquet: {test_parquet}")
        
        # HF Dataset
        test_dataset = Dataset.from_pandas(pd.DataFrame(test_conversations))
        test_dataset_dir = os.path.join(OUTPUT_DIR, "test_dataset")
        test_dataset.save_to_disk(test_dataset_dir)
        print(f"✓ Test HF Dataset: {test_dataset_dir}")
        
        print(f"\n📊 Test 数据统计: {len(test_conversations)} 条")
    else:
        print(f"⚠️  Test 文件不存在: {TEST_FILE}")
        print("   跳过 test 数据转换")

if __name__ == "__main__":
    main()