import json
import pandas as pd
from sklearn.model_selection import train_test_split # 更专业的拆分方法

# --- 配置 ---
input_file = '/data/home/the/rxliu/projects/open-r1-main/data/GSM8K-pre1000*3-sft-data-json-all/all.json'
train_output_file = '/data/home/the/rxliu/projects/open-r1-main/data/GSM8K-pre1000*3-sft-data-json/train.json'
test_output_file = '/data/home/the/rxliu/projects/open-r1-main/data/GSM8K-pre1000*3-sft-data-json/test.json'

# 1:9 的比例，意味着测试集占 10% (0.1)，训练集占 90% (0.9)
TEST_SIZE = 0.1
RANDOM_STATE = 42 # 确保每次运行拆分结果都一样

# ----------------------------------------------------

# 1. 读取 JSON 文件
with open(input_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 将数据转换为 Pandas DataFrame (方便操作)
df = pd.DataFrame(data)

# 3. 使用 train_test_split 进行 1:9 随机拆分
# test_size=0.1 表示测试集占 10% (1/10)
# stratify=None 表示不分层抽样，直接随机
train_df, test_df = train_test_split(
    df, 
    test_size=TEST_SIZE, 
    random_state=RANDOM_STATE
)

# 4. 将拆分后的 DataFrame 转换回 JSON 格式 (list of dictionaries)
train_data = train_df.to_dict(orient='records')
test_data = test_df.to_dict(orient='records')

# 5. 写入新的 JSON 文件
with open(train_output_file, 'w', encoding='utf-8') as f:
    json.dump(train_data, f, ensure_ascii=False, indent=2)

with open(test_output_file, 'w', encoding='utf-8') as f:
    json.dump(test_data, f, ensure_ascii=False, indent=2)

# 6. 打印结果摘要
print(f"成功从 {input_file} 拆分数据：")
print(f"  - 训练集 ({train_output_file})：{len(train_data)} 条记录")
print(f"  - 测试集 ({test_output_file})：{len(test_data)} 条记录")
print(f"  - 拆分比例 (Test:Train) 约为 1:{len(train_data)/len(test_data):.2f}")