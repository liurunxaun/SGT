import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from tqdm import tqdm  # 进度条库，没有请 pip install tqdm
from utils.llm_judge import llm_judge_via_api

# ================= 配置部分 =================
INPUT_FILE = "/data/home/the/rxliu/projects/open-r1-main/tests/results/Qwen3-8B_main_20251127.csv"   # 输入的CSV文件路径
OUTPUT_FILE = "/data/home/the/rxliu/projects/open-r1-main/tests/results/Qwen3-8B_main_20251127_judged_result.xlsx" # 输出文件名

# 阿里 DashScope 配置
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
JUDGE_MODEL = "qwen3-next-80b-a3b-instruct"

client = OpenAI(api_key=API_KEY, base_url=API_URL)

# ================= 数据处理函数 =================

def process_ground_truth(text):
    """
    处理 Ground Truth：提取 #### 之后的内容并去除空格
    """
    if not isinstance(text, str):
        return str(text)
    
    if "####" in text:
        # 分割并取最后一部分，去除前后空格
        return text.split("####")[-1].strip()
    else:
        # 如果没有 ####，则返回去除空格的原文本
        return text.strip()

def process_row(row):
    """
    处理单行数据的线程函数
    """
    # 1. 获取原始数据
    q = row.get('question', '')
    pred = row.get('predicted_answer', '') # 不做处理，直接读取
    raw_gt = row.get('ground_truth', '')
    
    # 2. 处理 Ground Truth (提取 #### 后面的)
    clean_gt = process_ground_truth(raw_gt)
    
    # 3. 调用 Judge
    is_correct = llm_judge_via_api(pred, clean_gt, API_URL, API_KEY, JUDGE_MODEL)
    
    # 4. 返回完整行数据（包含原有列和新结果）
    new_row = row.copy()
    new_row['processed_ground_truth'] = clean_gt # 方便你检查提取对不对
    new_row['is_correct_judge'] = is_correct     # 存入判断结果
    return new_row

# ================= 主程序 =================

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"错误：找不到文件 {INPUT_FILE}")
        return

    print(f"正在读取 {INPUT_FILE} ...")
    # 读取 CSV
    df = pd.read_csv(INPUT_FILE)
    
    # 转为字典列表以便并发处理
    data_list = df.to_dict('records')
    results = []

    print(f"开始处理 {len(data_list)} 条数据，并发数: 5")
    
    # 开启线程池并发处理
    with ThreadPoolExecutor(max_workers=5) as executor:
        # map 会按顺序返回结果，tqdm 显示进度条
        results = list(tqdm(executor.map(process_row, data_list), total=len(data_list)))

    # 保存结果
    result_df = pd.DataFrame(results)
    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"处理完成！结果已保存至 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()