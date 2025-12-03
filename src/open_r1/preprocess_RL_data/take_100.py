import pandas as pd
import os
import shutil

# 文件路径
file_path = "/ssd5/rxliu/datasets/RL-Data/shuffled_10k_train9k_eval300/test.parquet"

# 1. 为了安全，先备份原文件 (如果备份不存在的话)
backup_path = file_path + ".bak"
if not os.path.exists(backup_path):
    shutil.copy(file_path, backup_path)
    print(f"✅ 已自动备份原文件到: {backup_path}")
else:
    print(f"⚠️ 备份文件已存在，跳过备份步骤: {backup_path}")

# 2. 读取 Parquet 文件
df = pd.read_parquet(file_path)
print(f"原始数据行数: {len(df)}")

# 3. 截取前 100 条
df_100 = df.head(100)
print(f"截取后数据行数: {len(df_100)}")

# 4. 覆盖保存回原路径
df_100.to_parquet(file_path)
print(f"🎉 修改完成！文件已保存至: {file_path}")