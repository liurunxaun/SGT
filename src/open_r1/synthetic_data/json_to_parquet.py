import pandas as pd
import os

def simple_json_to_parquet(json_path, parquet_path):
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"文件不存在: {json_path}")
    
    # 一次性读取整个JSON数组（适合中等大小文件）
    df = pd.read_json(json_path, orient='records')  # orient='records'对应标准JSON数组格式 [{}, {}, ...]
    
    # 直接保存为Parquet
    df.to_parquet(parquet_path, engine='pyarrow', index=False, compression='snappy')
    print(f"转换完成: {parquet_path}")

if __name__ == "__main__":
    # 替换为你的文件路径
    simple_json_to_parquet(
        "/data/home/the/rxliu/projects/open-r1-main/sft-data/test.json",
        "/data/home/the/rxliu/projects/open-r1-main/sft-data-qwen/test.parquet"
    )