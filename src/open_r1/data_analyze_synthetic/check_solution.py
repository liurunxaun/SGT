import pandas as pd

# 读取原始文件
df = pd.read_parquet("/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files/train_part_1_of_4.parquet")

print(f"总数据量: {len(df)}")
print(f"Solution 列为 NaN 的数量: {df['solution'].isna().sum()}")

# 检查空字符串或只有空白字符
def is_empty_or_whitespace(text):
    if pd.isna(text):
        return True
    if isinstance(text, str) and text.strip() == '':
        return True
    return False

empty_mask = df['solution'].apply(is_empty_or_whitespace)
empty_solution = df[empty_mask]
print(f"Solution 列为空字符串或空白的数量: {len(empty_solution)}")

# 检查非常短的 solution（少于10个字符）
short_mask = df['solution'].str.len() < 10
very_short = df[short_mask]
print(f"Solution 少于10个字符的数量: {len(very_short)}")

print("\n" + "="*80)
print("空或很短 Solution 的示例（前10个）:")
print("="*80)

examples = df[empty_mask | short_mask].head(10)
for idx in examples.index:
    row = df.loc[idx]
    print(f"\nID: {idx}")
    print(f"Problem: {row['problem'][:80]}...")
    print(f"Answer: {row['answer']}")
    print(f"Solution 长度: {len(str(row['solution']))}")
    print(f"Solution: '{row['solution']}'")
    print("-"*80)

# 检查第 8201 条
print("\n" + "="*80)
print("第 8201 条的详细信息:")
print("="*80)
if 8201 in df.index:
    row = df.loc[8201]
    print(f"Problem: {row['problem']}")
    print(f"Answer: {row['answer']}")
    print(f"Solution 类型: {type(row['solution'])}")
    print(f"Solution 长度: {len(str(row['solution']))}")
    print(f"Solution repr: {repr(row['solution'])}")
    print(f"Solution: '{row['solution']}'")
else:
    print("ID 8201 不存在")


# import pandas as pd

# # 检查原始数据
# df = pd.read_parquet("/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/train.parquet")

# print(f"总行数: {len(df)}")
# print(f"\n列名: {df.columns.tolist()}")
# print(f"\nsolution 列空值数量: {df['solution'].isna().sum()}")
# print(f"answer 列空值数量: {df['answer'].isna().sum()}")

# # 显示一些有空 solution 的例子
# empty_solution = df[df['solution'].isna()]
# if len(empty_solution) > 0:
#     print(f"\n空 solution 的问题示例 (前5个):")
#     print(empty_solution[['problem', 'solution', 'answer']].head())



# import pandas as pd

# # 读取原始文件
# df = pd.read_parquet("/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/train.parquet")

# # 查看第 8201 条
# row = df.loc[8201]

# print("Problem:")
# print(row['problem'])
# print("\n" + "="*80 + "\n")

# print("Answer:")
# print(row['answer'])
# print("\n" + "="*80 + "\n")

# print("Solution:")
# print(row['solution'])