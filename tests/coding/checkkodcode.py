from datasets import load_from_disk

# 1. 加载你的本地数据集
path = "/ssd5/rxliu/datasets/KodCode-Light-RL-10K"
ds = load_from_disk(path)

# 2. 查看所有分片 (train/test) 的列名
print("=== Dataset Columns ===")
if 'train' in ds:
    print(f"Train columns: {ds['train'].column_names}")
    # 打印第一条数据看看长什么样
    print("\n=== First Example ===")
    print(ds['train'][0].keys())
else:
    # 也许你的数据集没有分 split，直接就是个 Dataset
    print(f"Columns: {ds.column_names}")
    print(ds[0].keys())