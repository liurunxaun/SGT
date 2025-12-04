from datasets import load_dataset

# 加载 MBPP+
ds = load_dataset("evalplus/mbppplus")

print(len(ds["train"]))  # 打印样本数量看是不是 399（或官方说的数量）