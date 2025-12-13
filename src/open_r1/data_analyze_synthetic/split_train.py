import pandas as pd
import os

# 1. 原始文件路径和输出目录
input_file_path = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/train.parquet"
output_dir = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files"  # 将分割后的文件保存在当前目录下的 split_files 文件夹中

# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

try:
    # 2. 加载 Parquet 文件
    print(f"正在加载文件: {input_file_path}...")
    df = pd.read_parquet(input_file_path)
    total_rows = len(df)
    print(f"文件加载完成，总行数: {total_rows}。")

    # 3. 计算分割点
    num_parts = 4
    # 每份大约的行数，使用整数除法
    chunk_size = total_rows // num_parts
    # 分割点的索引列表
    split_indices = [i * chunk_size for i in range(1, num_parts)]

    # 分割并保存文件
    start_index = 0
    
    print("\n开始分割和保存文件...")
    for i in range(num_parts):
        # 确定当前部分的结束索引 (如果不是最后一份，就使用分割点；否则使用总行数)
        end_index = split_indices[i] if i < num_parts - 1 else total_rows
        
        # 提取当前部分的数据帧
        df_part = df.iloc[start_index:end_index]
        
        # 构造输出文件名
        output_file_name = f"train_part_{i+1}_of_{num_parts}.parquet"
        output_file_path = os.path.join(output_dir, output_file_name)
        
        # 保存为新的 Parquet 文件
        df_part.to_parquet(output_file_path, index=False)
        
        print(f"  - 已保存第 {i+1} 份: {output_file_path} (行数: {len(df_part)})")
        
        # 更新下一部分的起始索引
        start_index = end_index

    print("\n所有文件分割完成！")

except FileNotFoundError:
    print(f"错误：未找到文件 {input_file_path}。请检查路径是否正确。")
except Exception as e:
    print(f"处理文件时发生错误: {e}")