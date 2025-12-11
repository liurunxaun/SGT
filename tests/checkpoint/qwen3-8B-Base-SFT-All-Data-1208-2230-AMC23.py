import pandas as pd
import os
import sys

# 路径设置：请确保此路径在您的环境中是正确的
sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")

from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from tqdm import tqdm
from llm_judge import llm_judge_via_api
from inference_sglang import inference_sglang
import time as time_module # 导入time模块用于获取当前时间


# ================= 参数配置 =================

# 循环和结果目录参数
REPETITIONS = 3 # <--- 新增：重复执行的次数

# Sglang 推理参数
dataset_name = "AMC23"
dataset_path = "/ssd5/rxliu/datasets/AMC23/data/test-00000-of-00001.parquet"
query_field = "question"
model = "qwen3-8B-Base-SFT-All-Data-1208-2230-checkpoint-105"
temperature = 0.6
max_tokens = 8192
system_prompt = ""

# llm judge 配置
API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
JUDGE_MODEL = "qwen3-next-80b-a3b-instruct"
client = OpenAI(api_key=API_KEY, base_url=API_URL)
api_workers = 4

# 测试参数
answer_field = "answer"


# ================= 数据处理函数 (保持不变) =================

def process_ground_truth(text):

    return text


def process_row(row):
    """
    处理单行数据的线程函数
    """
    # 1. 获取原始数据
    pred = row.get('predicted_answer', '')
    raw_gt = row.get('ground_truth', '')
    
    # 2. 处理 Ground Truth
    clean_gt = process_ground_truth(raw_gt)
    
    # 3. 调用 Judge
    # 这里的 client 变量没有在函数内部使用，但为了与您的代码保持一致，暂时保留
    is_correct = llm_judge_via_api(pred, clean_gt, API_URL, API_KEY, JUDGE_MODEL)
    
    # 4. 返回完整行数据（包含原有列和新结果）
    new_row = row.copy()
    new_row['processed_ground_truth'] = clean_gt
    new_row['is_correct_judge'] = is_correct
    return new_row


# ================= 主程序 (主要修改部分) =================

def main():
    # 获取当前时间字符串用于文件夹命名
    current_time_str = time_module.strftime("%Y%m%d-%H%M%S")
    
    # 定义根输出文件夹路径
    base_output_dir = "/data/home/the/rxliu/projects/open-r1-main/tests/results"
    
    # 定义本次测试的专属文件夹路径
    result_folder = os.path.join(base_output_dir, f"{model}-{dataset_name}-{current_time_str}")
    
    # 创建结果文件夹
    os.makedirs(result_folder, exist_ok=True)
    print(f"所有结果将保存在文件夹: {result_folder}")

    accuracy_list = []

    for i in range(1, REPETITIONS + 1):
        print(f"\n--- 🧪 开始第 {i}/{REPETITIONS} 次测试 ---")
        
        # 1. 定义本次循环的输出文件路径
        inference_output_path = os.path.join(result_folder, f"inference_run_{i}.xlsx")
        result_output_path = os.path.join(result_folder, f"result_run_{i}.xlsx")
        
        # 2. sglang 推理
        print(f"开始第 {i} 次 SGLang 推理...")
        try:
            inference_sglang(dataset_path, system_prompt, query_field, answer_field, inference_output_path, model, temperature, max_tokens)
        except Exception as e:
            print(f"🚨 第 {i} 次推理失败: {e}")
            continue

        # 3. 读取推理结果
        if not os.path.exists(inference_output_path):
            print(f"错误：找不到文件 {inference_output_path}，跳过本次评测。")
            continue
            
        print(f"正在读取 {inference_output_path} ...")
        df = pd.read_excel(inference_output_path)
        
        # 4. LLM Judge 评测
        data_list = df.to_dict('records')
        results = []
        
        print(f"开始对 {len(data_list)} 条数据进行 LLM Judge 评测 (并发数: {api_workers})")
        with ThreadPoolExecutor(max_workers=api_workers) as executor:
            # map 按顺序返回结果，tqdm 显示进度条
            results = list(tqdm(executor.map(process_row, data_list), total=len(data_list)))

        # 5. 处理结果与计算准确率
        result_df = pd.DataFrame(results)

        num_correct = result_df["is_correct_judge"].sum()
        total = len(result_df)
        accuracy = num_correct / total if total > 0 else 0
        
        accuracy_list.append(accuracy) # 存储本次准确率
        
        print(f"\n第 {i} 次 Judge 正确数量：{num_correct}/{total}")
        print(f"第 {i} 次 Judge 准确率：{accuracy:.4f}")
        
        # 6. 保存本次结果至文件
        result_df.to_excel(result_output_path, index=False)
        print(f"第 {i} 次结果已保存至 {result_output_path}")

    # 7. 计算并保存最终平均结果
    if accuracy_list:
        avg_accuracy = sum(accuracy_list) / len(accuracy_list)
        
        print("\n" + "="*50)
        print(f"🎉 **所有 {len(accuracy_list)} 次测试的平均准确率：{avg_accuracy:.4f}**")
        print("="*50)

        # 创建一个汇总 DataFrame
        summary_data = {
            'Run': [f'Run {j+1}' for j in range(len(accuracy_list))] + ['Average'],
            'Accuracy': [f'{acc:.4f}' for acc in accuracy_list] + [f'{avg_accuracy:.4f}']
        }
        summary_df = pd.DataFrame(summary_data)
        
        # 保存汇总结果
        summary_output_path = os.path.join(result_folder, "summary_average_accuracy.xlsx")
        summary_df.to_excel(summary_output_path, index=False)
        print(f"汇总结果已保存至 {summary_output_path}")
    else:
        print("\n😔 没有成功完成的测试轮次，无法计算平均准确率。")

if __name__ == "__main__":
    main()