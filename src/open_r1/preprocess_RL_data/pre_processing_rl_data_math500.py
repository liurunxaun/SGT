import pandas as pd
import os

# 目标文件路径
file_path = '/ssd5/rxliu/datasets/RL-Data/shuffled_10k_train9k_evalMATH500/test.parquet'

if os.path.exists(file_path):
    print(f"正在读取文件: {file_path}")
    df = pd.read_parquet(file_path)
    print(f"初始列名: {df.columns.tolist()}")

    # -------------------------------------------------
    # 1. 字段重命名逻辑 (带安全检查)
    # -------------------------------------------------
    # 只有当原始字段 "answer" 存在时，才执行重命名
    # 防止对已经处理过的文件重复执行导致数据错乱
    if 'answer' in df.columns:
        print("检测到原始字段 'answer'，正在执行重命名...")
        # 注意：先重命名 solution -> solving_process，再 answer -> solution
        # Pandas 的 rename 字典是原子的，可以直接一起写
        df = df.rename(columns={
            "solution": "solving_process",
            "answer": "solution"
        })
    else:
        print("未检测到 'answer' 字段，跳过重命名步骤 (可能已处理过)。")

    # -------------------------------------------------
    # 2. 删除多余字段
    # -------------------------------------------------
    cols_to_drop = ['subject', 'level', 'unique_id']
    df = df.drop(columns=cols_to_drop, errors='ignore')

    # -------------------------------------------------
    # 3. 添加/更新必要的字段
    # -------------------------------------------------
    # 添加 source 字段
    df['source'] = 'MATH500'
    
    # 添加 id 字段 (重新生成，确保从1开始)
    # 如果 id 已存在先覆盖，确保顺序正确
    df['id'] = range(1, len(df) + 1)

    # -------------------------------------------------
    # 4. 调整列顺序
    # -------------------------------------------------
    target_cols = ["id", "problem", "solving_process", "solution", "source"]
    
    # 检查是否所有目标列都存在
    missing_cols = [c for c in target_cols if c not in df.columns]
    
    if not missing_cols:
        df = df[target_cols]
        print(f"列顺序已调整为: {target_cols}")
        
        # -------------------------------------------------
        # 5. 覆盖保存文件
        # -------------------------------------------------
        df.to_parquet(file_path)
        print("\n处理成功！文件已覆盖保存。")
        print("最终数据预览 (前2行):")
        print(df.head(2))
    else:
        print(f"\n错误：无法调整顺序，因为缺少以下字段: {missing_cols}")
        print(f"当前拥有的字段: {df.columns.tolist()}")

else:
    print(f"错误：找不到文件 {file_path}")