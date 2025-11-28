import pandas as pd
import os

def simple_json_to_parquet(json_path, parquet_path):
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"文件不存在: {json_path}")
    
    # JSONL 每行一个 JSON 对象
    df = pd.read_json(json_path, lines=True)
    
    # 保存 Parquet
    df.to_parquet(parquet_path, engine='pyarrow', index=False, compression='snappy')
    print(f"转换完成: {parquet_path}")

if __name__ == "__main__":
    simple_json_to_parquet(
        "/ssd5/rxliu/datasets/MATH-500/test.jsonl",
        "/ssd5/rxliu/datasets/MATH-500/test.parquet"
    )
