#!/usr/bin/env python3
"""
自动化测试命令行工具
使用方法:
    python auto_test.py --model-path /path/to/model --checkpoint 240 --gpu 1 --port 30064
    python auto_test.py --model-path /path/to/model --gpu 1 --datasets GSM8K MATH500
"""

import subprocess
import time
import os
import sys
import pandas as pd
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.append("/data/home/the/rxliu/projects/open-r1-main/tests/utils")
from tqdm import tqdm
from llm_judge import llm_judge_via_api
from inference_sglang import inference_sglang
from openai import OpenAI


class AutoTestManager:
    """自动化测试管理器"""
    
    DATASETS = {
        "MATH500": {
            "path": "/ssd5/rxliu/datasets/MATH-500/test.parquet",
            "query_field": "problem",
            "answer_field": "answer",
            "repetitions": 16,
            "max_tokens": 32000,
            "process_gt": lambda x: x
        },
        "GSM8K": {
            "path": "/ssd5/rxliu/datasets/gsm8k/main/test-00000-of-00001.parquet",
            "query_field": "question",
            "answer_field": "answer",
            "repetitions": 3,
            "max_tokens": 30000,
            "process_gt": lambda text: text.split("####")[-1].strip() if isinstance(text, str) and "####" in text else str(text).strip()
        },
        "AIME24": {
            "path": "/ssd5/rxliu/datasets/AIME24/data/train-00000-of-00001.parquet",
            "query_field": "problem",
            "answer_field": "answer",
            "repetitions": 16,
            "max_tokens": 32000,
            "process_gt": lambda x: x
        },
        "AIME25": {
            "path": "/data/home/the/rxliu/projects/dataset_information.py",
            "query_field": "question",
            "answer_field": "answer",
            "repetitions": 16,
            "max_tokens": 32000,
            "process_gt": lambda x: x
        },
        "AMC23": {
            "path": "/ssd5/rxliu/datasets/AMC23/data/test-00000-of-00001.parquet",
            "query_field": "question",
            "answer_field": "answer",
            "repetitions": 16,
            "max_tokens": 32000,
            "process_gt": lambda x: x
        }
    }
    
    def __init__(self, model_path, checkpoint=None, cuda_device="1", port=30064,
                 temperature=0.6, base_output_dir="/data/home/the/rxliu/projects/open-r1-main/tests/results",
                 api_key="sk-8d445207b1ab47efb83069ccc1b845b6",
                 api_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                 judge_model="qwen3-next-80b-a3b-instruct", api_workers=4, conda_env=None):
        
        self.model_path = model_path
        self.checkpoint = checkpoint
        self.cuda_device = cuda_device
        self.port = port
        self.temperature = temperature
        self.base_output_dir = base_output_dir
        self.api_workers = api_workers
        self.conda_env = conda_env
        
        if checkpoint:
            self.full_model_path = os.path.join(model_path, f"checkpoint-{checkpoint}")
            self.model_name = f"{Path(model_path).name}-ckpt{checkpoint}"
        else:
            self.full_model_path = model_path
            self.model_name = Path(model_path).name
        
        self.api_key = api_key
        self.api_url = api_url
        self.judge_model = judge_model
        self.client = OpenAI(api_key=api_key, base_url=api_url)
        self.server_process = None
    
    def cleanup_port(self):
        """清理可能占用端口的进程"""
        print(f"🔍 检查端口 {self.port} 是否被占用...")
        try:
            # 查找占用该端口的进程
            result = subprocess.run(
                ["lsof", "-ti", f":{self.port}"],
                capture_output=True,
                text=True
            )
            
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                print(f"⚠️  发现端口 {self.port} 被以下进程占用: {pids}")
                
                for pid in pids:
                    try:
                        print(f"   正在终止进程 {pid}...")
                        subprocess.run(["kill", "-9", pid], check=True)
                        print(f"   ✅ 已终止进程 {pid}")
                    except subprocess.CalledProcessError:
                        print(f"   ⚠️  无法终止进程 {pid} (可能需要 sudo 权限)")
                
                # 等待端口释放
                time.sleep(2)
                print(f"✅ 端口 {self.port} 已清理\n")
            else:
                print(f"✅ 端口 {self.port} 未被占用\n")
                
        except FileNotFoundError:
            # lsof 命令不存在，尝试使用 fuser
            try:
                result = subprocess.run(
                    ["fuser", "-k", f"{self.port}/tcp"],
                    capture_output=True,
                    text=True
                )
                time.sleep(2)
                print(f"✅ 端口 {self.port} 已清理\n")
            except FileNotFoundError:
                print(f"⚠️  无法检查端口占用 (lsof/fuser 命令不可用)\n")
        except Exception as e:
            print(f"⚠️  清理端口时出错: {e}\n")
    
    def start_server(self):
        """启动SGLang服务器"""
        print(f"\n{'='*60}")
        print(f"🚀 正在启动SGLang服务器...")
        print(f"   模型路径: {self.full_model_path}")
        print(f"   端口: {self.port}")
        print(f"   GPU: {self.cuda_device}")
        if self.conda_env:
            print(f"   Conda环境: {self.conda_env}")
        print(f"{'='*60}\n")
        
        # 先清理端口
        self.cleanup_port()
        
        # 构建命令
        if self.conda_env:
            # 使用conda run来在指定环境中运行命令
            cmd = [
                "conda", "run", "-n", self.conda_env, "--no-capture-output",
                "python", "-m", "sglang.launch_server",
                "--model-path", self.full_model_path,
                "--port", str(self.port),
                "--trust-remote-code"
            ]
        else:
            cmd = [
                "python", "-m", "sglang.launch_server",
                "--model-path", self.full_model_path,
                "--port", str(self.port),
                "--trust-remote-code"
            ]
        
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(self.cuda_device)
        
        self.server_process = subprocess.Popen(
            cmd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True
        )
        
        print("⏳ 等待服务器启动...")
        
        # 健康检查：持续尝试连接服务器，最多等待5分钟
        import requests
        max_wait_time = 300  # 5分钟
        check_interval = 5   # 每5秒检查一次
        elapsed_time = 0
        server_ready = False
        
        while elapsed_time < max_wait_time:
            # 先等待一段时间
            time.sleep(check_interval)
            elapsed_time += check_interval
            
            # 检查进程是否还在运行
            if self.server_process.poll() is not None:
                stderr_output = self.server_process.stderr.read() if self.server_process.stderr else ""
                stdout_output = self.server_process.stdout.read() if self.server_process.stdout else ""
                print(f"❌ 服务器进程已退出!")
                if stderr_output:
                    print(f"错误信息:\n{stderr_output[:1000]}")
                if stdout_output:
                    print(f"输出信息:\n{stdout_output[:1000]}")
                raise RuntimeError("服务器启动失败!")
            
            # 尝试连接服务器
            try:
                response = requests.get(f"http://127.0.0.1:{self.port}/health", timeout=2)
                if response.status_code == 200:
                    server_ready = True
                    print(f"✅ 服务器启动成功! (等待时间: {elapsed_time}秒)\n")
                    break
            except:
                print(f"   等待中... ({elapsed_time}秒)")
                continue
        
        if not server_ready:
            print(f"❌ 服务器启动超时! (等待了{max_wait_time}秒)")
            # 输出服务器的stderr和stdout以便调试
            if self.server_process.poll() is None:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
            stderr_output = self.server_process.stderr.read() if self.server_process.stderr else ""
            stdout_output = self.server_process.stdout.read() if self.server_process.stdout else ""
            if stderr_output:
                print(f"服务器错误信息:\n{stderr_output[:1000]}")
            if stdout_output:
                print(f"服务器输出信息:\n{stdout_output[:1000]}")
            raise RuntimeError("服务器启动超时!")
        
        # 额外等待几秒确保完全就绪
        print("⏳ 额外等待10秒确保服务器完全就绪...")
        time.sleep(10)
        print("✅ 服务器已完全就绪!\n")
    
    def stop_server(self):
        """停止SGLang服务器"""
        if self.server_process:
            print("\n🛑 正在停止服务器...")
            
            # 先尝试优雅终止
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=10)
                print("✅ 服务器已停止\n")
            except subprocess.TimeoutExpired:
                # 如果10秒后还没停止，强制杀死
                print("⚠️  服务器未响应，强制终止...")
                self.server_process.kill()
                self.server_process.wait()
                print("✅ 服务器已强制停止\n")
            
            # 再次清理端口，确保没有遗留进程
            time.sleep(2)
            self.cleanup_port()
    
    def process_row(self, row, process_gt_func):
        """处理单行数据"""
        pred = row.get('predicted_answer', '')
        raw_gt = row.get('ground_truth', '')
        clean_gt = process_gt_func(raw_gt)
        is_correct = llm_judge_via_api(pred, clean_gt, self.api_url, self.api_key, self.judge_model)
        
        new_row = row.copy()
        new_row['processed_ground_truth'] = clean_gt
        new_row['is_correct_judge'] = is_correct
        return new_row
    
    def run_single_dataset(self, dataset_name, dataset_config):
        """运行单个数据集的测试"""
        print(f"\n{'#'*60}")
        print(f"📊 开始测试数据集: {dataset_name}")
        print(f"{'#'*60}\n")
        
        current_time_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        result_folder = os.path.join(self.base_output_dir, f"{self.model_name}-{dataset_name}-{current_time_str}")
        os.makedirs(result_folder, exist_ok=True)
        print(f"📁 结果保存路径: {result_folder}\n")
        
        accuracy_list = []
        repetitions = dataset_config["repetitions"]
        
        for i in range(1, repetitions + 1):
            print(f"--- 🧪 第 {i}/{repetitions} 次测试 ---")
            
            inference_output_path = os.path.join(result_folder, f"inference_run_{i}.xlsx")
            result_output_path = os.path.join(result_folder, f"result_run_{i}.xlsx")
            
            try:
                print(f"📄 执行推理...")
                # 直接传递 base_url 参数，不使用环境变量
                inference_sglang(
                    dataset_config["path"], 
                    "", 
                    dataset_config["query_field"],
                    dataset_config["answer_field"], 
                    inference_output_path,
                    self.model_name, 
                    self.temperature, 
                    dataset_config["max_tokens"],
                    base_url=f"http://127.0.0.1:{self.port}/v1"
                )
                    
            except Exception as e:
                print(f"🚨 推理失败: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            if not os.path.exists(inference_output_path):
                print(f"❌ 找不到推理结果文件,跳过")
                continue
            
            df = pd.read_excel(inference_output_path)
            data_list = df.to_dict('records')
            
            print(f"⚖️ 开始LLM Judge评测 ({len(data_list)}条数据)")
            with ThreadPoolExecutor(max_workers=self.api_workers) as executor:
                results = list(tqdm(
                    executor.map(lambda row: self.process_row(row, dataset_config["process_gt"]), data_list),
                    total=len(data_list)
                ))
            
            result_df = pd.DataFrame(results)
            num_correct = result_df["is_correct_judge"].sum()
            total = len(result_df)
            accuracy = num_correct / total if total > 0 else 0
            accuracy_list.append(accuracy)
            
            print(f"✅ 正确: {num_correct}/{total}, 准确率: {accuracy:.4f}\n")
            result_df.to_excel(result_output_path, index=False)
        
        if accuracy_list:
            avg_accuracy = sum(accuracy_list) / len(accuracy_list)
            print(f"\n{'='*60}")
            print(f"🎉 {dataset_name} 平均准确率: {avg_accuracy:.4f}")
            print(f"{'='*60}\n")
            
            summary_data = {
                'Run': [f'Run {j+1}' for j in range(len(accuracy_list))] + ['Average'],
                'Accuracy': [f'{acc:.4f}' for acc in accuracy_list] + [f'{avg_accuracy:.4f}']
            }
            summary_df = pd.DataFrame(summary_data)
            summary_output_path = os.path.join(result_folder, "summary_average_accuracy.xlsx")
            summary_df.to_excel(summary_output_path, index=False)
            return avg_accuracy
        
        return None
    
    def run_all_tests(self, datasets=None):
        """运行所有测试"""
        if datasets is None:
            datasets = list(self.DATASETS.keys())
        
        try:
            self.start_server()
            
            results = {}
            for dataset_name in datasets:
                if dataset_name not in self.DATASETS:
                    print(f"⚠️ 未知数据集: {dataset_name}, 跳过")
                    continue
                
                avg_acc = self.run_single_dataset(dataset_name, self.DATASETS[dataset_name])
                results[dataset_name] = avg_acc
            
            print("\n" + "="*60)
            print("🏆 所有测试完成! 总结:")
            print("="*60)
            for dataset, acc in results.items():
                if acc is not None:
                    print(f"  {dataset:15s}: {acc:.4f}")
                else:
                    print(f"  {dataset:15s}: 失败")
            print("="*60 + "\n")
            
        finally:
            self.stop_server()


def main():
    parser = argparse.ArgumentParser(
        description='自动化模型测试工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 测试所有数据集(指定conda环境)
  python auto_test.py --model-path /ssd5/rxliu/models/output/qwen3-8B-Base --checkpoint 240 --gpu 1 --port 30064 --conda-env openr1_rxliu

  # 只测试特定数据集
  python auto_test.py --model-path /ssd5/rxliu/models/output/qwen3-8B-Base --checkpoint 240 --gpu 1 --datasets AIME24 MATH500 --conda-env openr1_rxliu

  # 测试完整模型(不指定checkpoint)
  python auto_test.py --model-path /ssd5/rxliu/models/my-model --gpu 0 --conda-env openr1_rxliu

可用数据集: MATH500, AIME24, AIME25, AMC23
        """
    )
    
    parser.add_argument('--model-path', required=True, help='模型路径')
    parser.add_argument('--checkpoint', type=int, default=None, help='Checkpoint号(可选)')
    parser.add_argument('--gpu', default='1', help='GPU设备号(默认: 1)')
    parser.add_argument('--port', type=int, default=30064, help='服务器端口(默认: 30064)')
    parser.add_argument('--temperature', type=float, default=0.6, help='采样温度(默认: 0.6)')
    parser.add_argument('--datasets', nargs='+', default=None, 
                        help='要测试的数据集列表(默认: 全部)')
    parser.add_argument('--output-dir', default='/data/home/the/rxliu/projects/open-r1-main/tests/results',
                        help='结果输出目录')
    parser.add_argument('--api-workers', type=int, default=4, help='API并发数(默认: 4)')
    parser.add_argument('--conda-env', default=None, help='Conda环境名称(例如: openr1_rxliu)')
    
    args = parser.parse_args()
    
    # 显示配置信息
    print("\n" + "="*60)
    print("📋 测试配置")
    print("="*60)
    print(f"模型路径:    {args.model_path}")
    print(f"Checkpoint:  {args.checkpoint if args.checkpoint else '完整模型'}")
    print(f"GPU设备:     {args.gpu}")
    print(f"端口:        {args.port}")
    print(f"温度:        {args.temperature}")
    print(f"数据集:      {args.datasets if args.datasets else '全部'}")
    print(f"Conda环境:   {args.conda_env if args.conda_env else '当前环境'}")
    print(f"输出目录:    {args.output_dir}")
    print("="*60 + "\n")
    
    manager = AutoTestManager(
        model_path=args.model_path,
        checkpoint=args.checkpoint,
        cuda_device=args.gpu,
        port=args.port,
        temperature=args.temperature,
        base_output_dir=args.output_dir,
        api_workers=args.api_workers,
        conda_env=args.conda_env
    )
    
    manager.run_all_tests(datasets=args.datasets)


if __name__ == "__main__":
    main()