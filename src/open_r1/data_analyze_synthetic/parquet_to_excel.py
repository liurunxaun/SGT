import pandas as pd
import os
import sys
import re

def clean_for_excel(df):
    """清理 DataFrame 中不兼容 Excel 的字符"""
    def clean_string(val):
        if isinstance(val, str):
            # 移除 Excel 不支持的控制字符
            return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', val)
        return val
    
    return df.applymap(clean_string)

def parquet_to_excel(parquet_file, excel_file=None, clean=True):
    """
    将 Parquet 文件转换为 Excel 文件
    
    参数:
        parquet_file: 输入的 parquet 文件路径
        excel_file: 输出的 excel 文件路径（如果为 None，则自动生成）
        clean: 是否清理不兼容的字符（推荐 True）
    """
    # 检查文件是否存在
    if not os.path.exists(parquet_file):
        print(f"❌ 错误: 文件不存在 - {parquet_file}")
        return False
    
    # 自动生成输出文件名
    if excel_file is None:
        excel_file = parquet_file.replace('.parquet', '.xlsx')
    
    try:
        print(f"📖 正在读取: {parquet_file}")
        df = pd.read_parquet(parquet_file)
        print(f"✓ 成功读取 {len(df)} 行, {len(df.columns)} 列")
        
        # 清理数据
        if clean:
            print("🧹 正在清理不兼容字符...")
            df = clean_for_excel(df)
        
        # 保存为 Excel
        print(f"💾 正在保存到: {excel_file}")
        df.to_excel(excel_file, index=False, engine='openpyxl')
        
        # 获取文件大小
        size_mb = os.path.getsize(excel_file) / (1024 * 1024)
        print(f"✅ 转换成功! 文件大小: {size_mb:.2f} MB")
        return True
        
    except Exception as e:
        print(f"❌ 转换失败: {str(e)}")
        return False

def batch_convert(directory, pattern="_all.parquet"):
    """
    批量转换目录中的 parquet 文件
    
    参数:
        directory: 目录路径
        pattern: 要转换的文件名模式
    """
    if not os.path.isdir(directory):
        print(f"❌ 错误: 目录不存在 - {directory}")
        return
    
    files = [f for f in os.listdir(directory) if f.endswith('.parquet') and pattern in f]
    
    if not files:
        print(f"⚠️  未找到匹配的文件 (模式: {pattern})")
        return
    
    print(f"找到 {len(files)} 个文件")
    print("="*60)
    
    success_count = 0
    for i, filename in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] 处理: {filename}")
        parquet_path = os.path.join(directory, filename)
        if parquet_to_excel(parquet_path):
            success_count += 1
    
    print("\n" + "="*60)
    print(f"✅ 完成! 成功转换 {success_count}/{len(files)} 个文件")

if __name__ == "__main__":
    # 使用方式 1: 转换单个文件
    if len(sys.argv) == 2:
        parquet_file = sys.argv[1]
        parquet_to_excel(parquet_file)
    
    # 使用方式 2: 批量转换目录中的文件
    elif len(sys.argv) == 3 and sys.argv[1] == "--batch":
        directory = sys.argv[2]
        batch_convert(directory)
    
    # 使用方式 3: 直接在代码中指定
    else:
        print("使用方式:")
        print("1. 转换单个文件:")
        print("   python parquet_to_excel.py your_file.parquet")
        print()
        print("2. 批量转换目录:")
        print("   python parquet_to_excel.py --batch /path/to/directory")
        print()
        print("3. 或者直接修改下面的代码:")
        print()
        
        # ====== 在这里修改你的文件路径 ======
        
        # 示例 1: 转换单个文件
        parquet_file = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files/train_part_1_of_4_qwen3-max_graph_results_all.parquet"
        parquet_to_excel(parquet_file)
        
        # 示例 2: 转换多个文件
        # files_to_convert = [
        #     "path/to/file1_all.parquet",
        #     "path/to/file1_correct.parquet",
        #     "path/to/file1_unsolved.parquet"
        # ]
        # for f in files_to_convert:
        #     parquet_to_excel(f)
        
        # 示例 3: 批量转换目录
        # batch_convert("/path/to/directory", pattern="_all.parquet")