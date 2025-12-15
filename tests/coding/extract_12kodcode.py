import os
import pandas as pd
from datasets import load_from_disk, Dataset

# ================= 配置区域 =================
# 1. 输入和输出路径
INPUT_PATH = "/ssd5/rxliu/datasets/KodCode-V1-SFT-R1/train"
OUTPUT_PATH = "/ssd5/rxliu/datasets/KodCode-V1-SFT-R1/filtered_12k_test"

# 2. 总目标数量
TOTAL_SAMPLES = 120

# 3. Style 的比例分布 (4.5 : 4.5 : 1)
STYLE_RATIOS = {
    "complete": 0.45,
    "instruct": 0.45,
    "online_judge": 0.10
}

# 4. Difficulty 的比例分布 (4 : 2 : 2) -> (50% : 25% : 25%)
# 警告：这里假设了难度标签为 'easy', 'medium', 'hard'。
# 如果你的实际标签不同（例如首字母大写），请修改下方的 Key。
# 这里的逻辑是：想要最多的(4)放第一个，其余(2)放后面。
DIFFICULTY_RATIOS = {
    # 假设想要抽取最多的是 easy，请根据实际列值修改键名
    "easy": 0.50,   # 对应比例 4
    "medium": 0.25, # 对应比例 2
    "hard": 0.25    # 对应比例 2
}

# ===========================================

def extract_data():
    print(f"正在从 {INPUT_PATH} 加载数据...")
    # 加载 Arrow 数据集
    ds = load_from_disk(INPUT_PATH)
    
    # 为了方便进行复杂的条件筛选，暂时转换为 Pandas DataFrame
    # 12000条数据对于内存来说非常小，Pandas 处理最快
    print("正在转换为 Pandas DataFrame 以便处理...")
    df = ds.to_pandas()
    
    # 打印一下当前的列值分布，供核对
    print("\n原始数据 style 分布:")
    print(df['style'].value_counts())
    print("\n原始数据 gpt_difficulty 分布:")
    print(df['gpt_difficulty'].value_counts())

    final_dfs = []
    
    print("\n开始分层抽样...")
    
    # 第一层循环：遍历 Style
    for style, s_ratio in STYLE_RATIOS.items():
        # 计算该 style 需要的总数
        n_style_target = int(TOTAL_SAMPLES * s_ratio)
        
        # 筛选出该 style 的所有数据
        style_df = df[df['style'] == style]
        
        print(f"--> 处理 Style: {style}, 目标总数: {n_style_target}")
        
        # 第二层循环：遍历 Difficulty
        for diff, d_ratio in DIFFICULTY_RATIOS.items():
            # 计算在该 style 下，特定 difficulty 需要的数量
            n_diff_target = int(n_style_target * d_ratio)
            
            # 筛选出特定 style 和 difficulty 的数据
            subset = style_df[style_df['gpt_difficulty'] == diff]
            
            # 检查是否有足够的数据
            available_count = len(subset)
            if available_count < n_diff_target:
                print(f"    [警告] {style}-{diff} 数据不足! 需求: {n_diff_target}, 实际: {available_count}。将全部取用。")
                sampled_subset = subset
            else:
                # 随机抽样 (random_state 保证可复现)
                sampled_subset = subset.sample(n=n_diff_target, random_state=42)
            
            final_dfs.append(sampled_subset)
            print(f"    已提取 {style} - {diff}: {len(sampled_subset)} 条")

    # 合并所有抽样结果
    final_df = pd.concat(final_dfs)
    
    # 这里的总数可能会因为取整误差或数据不足略有偏差，通常在 12000 上下浮动极小
    print(f"\n抽样完成。最终数据总行数: {len(final_df)}")
    
    # 验证最终分布
    print("\n最终 Style 分布:")
    print(final_df['style'].value_counts(normalize=True))
    
    # 转换回 Huggingface Dataset 对象
    print(f"\n正在保存数据到 {OUTPUT_PATH} ...")
    final_dataset = Dataset.from_pandas(final_df)
    
    # 如果 Pandas 生成了 __index_level_0__ 列，移除它
    if "__index_level_0__" in final_dataset.column_names:
        final_dataset = final_dataset.remove_columns(["__index_level_0__"])
        
    # 保存到磁盘 (Arrow 格式，保持和原来一致)
    final_dataset.save_to_disk(OUTPUT_PATH)
    
    # 如果你需要 jsonl 格式以便直接做 SFT 训练，取消下面这行的注释
    # final_dataset.to_json(os.path.join(OUTPUT_PATH, "data.jsonl"), orient="records", lines=True)
    
    print(f"处理完毕！数据已保存。")

if __name__ == "__main__":
    extract_data()