import os
import requests
from tqdm import tqdm

# =================配置区域=================
# 1. 目标保存路径
base_path = "/ssd5/rxliu/datasets/"
target_dir = os.path.join(base_path, "livecodebench_lite")

# 2. 核心文件列表 (LiveCodeBench 的数据就只有这几个关键文件)
# 根据官方仓库结构，我们需要下载这些 jsonl 和 Python 脚本
files_to_download = [
    "README.md",
    "code_generation_lite.py",
    "test.jsonl",   # v1
    "test2.jsonl",  # v2
    "test3.jsonl",  # v3
    "test4.jsonl",  # v4
    "test5.jsonl",  # v5
    "test6.jsonl",  # v6 (最新)
]

# 3. 镜像站直连 URL 前缀
base_url = "https://hf-mirror.com/datasets/livecodebench/code_generation_lite/resolve/main/"
# ==========================================

# 确保目录存在
os.makedirs(target_dir, exist_ok=True)

# 清除代理 (防止干扰直连镜像)
proxy_vars = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']
for p in proxy_vars:
    if p in os.environ:
        del os.environ[p]

print(f"📂 开始下载到: {target_dir}")
print("🚀 使用模式: 直接 URL 获取 (绕过 Hub API 错误)")

def download_file(filename):
    url = base_url + filename
    local_filepath = os.path.join(target_dir, filename)
    
    print(f"\n正在下载: {filename}")
    
    try:
        # stream=True 允许下载大文件
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status() # 检查 404 等错误
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(local_filepath, 'wb') as f, tqdm(
            desc=filename,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                bar.update(size)
        print(f"✅ {filename} 完成")
        
    except Exception as e:
        print(f"❌ 下载 {filename} 失败: {e}")

# 执行循环下载
for file in files_to_download:
    download_file(file)

print("\n" + "-"*30)
print("下载任务结束，请检查上方是否有报错。")
print(f"最终文件列表: {os.listdir(target_dir)}")