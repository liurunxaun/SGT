import pandas as pd

# 读取parquet文件
df = pd.read_parquet('/ssd5/rxliu/datasets/rcmu/new_math_data.parquet')

print(f"原始数据: {len(df)} 条记录")

# 1. 将id改为从0开始的整数
df['id'] = range(len(df))

# 2. 字段重命名
df = df.rename(columns={
    'answer': 'solution',
    'solution': 'solving_process'
})

# 3. 添加source字段
df['source'] = 'DeepScaleR5k'

# 4. 删除correct_cnt字段
df = df.drop(columns=['correct_cnt'])

# 5. 调整列顺序
df = df[['id', 'problem', 'solving_process', 'solution', 'source']]

# 保存处理后的文件
output_path = '/ssd5/rxliu/datasets/rcmu/new_math_data_processed.parquet'
df.to_parquet(output_path, index=False)

print(f"处理完成！共处理 {len(df)} 条记录")
print(f"输出文件: {output_path}")
print("\n前3条记录预览:")
print(df.head(3))