import json
import re
import textwrap
import sys
from pathlib import Path

# ====== 配置区 ======
# 输入文件（你的原始结果）
INPUT_FILE = "tests/results_coding/samples_humanevalplus_structured_cot_11.27.jsonl"
# 输出文件（清洗后的结果）
OUTPUT_FILE = "tests/results_coding/samples_humanevalplus_CLEANED.jsonl"

def clean_code(code: str) -> str:
    """
    对模型生成的代码进行强力清洗，解决格式错误、缩进错误和 Unicode 问题。
    """
    if not code:
        return ""

    # 0. 【核心修复】Unicode 标准化：把 \u00a0 (NBSP) 变成标准空格
    # 这解决了解释器无法识别缩进的问题
    code = code.replace('\u00a0', ' ') 

    # 1. 移除 XML 标签 (针对 <think>, <answer> 等)
    code = re.sub(r'</?think>', '', code, flags=re.IGNORECASE)
    code = re.sub(r'</?answer>', '', code, flags=re.IGNORECASE)
    
    # 2. 移除 Markdown 代码块标记 (```python ... ```)
    code = re.sub(r'^```[a-zA-Z]*', '', code, flags=re.MULTILINE)
    code = re.sub(r'^```', '', code, flags=re.MULTILINE)
    code = code.replace('```', '') # 防止行尾残留
    
    # 3. 初步去除首尾空白
    code = code.strip()
    
    # 4. 智能去除公共缩进 (textwrap)
    # 这通常能解决大部分缩进问题
    code = textwrap.dedent(code)
    
    # 5. 【双重保险】强制左对齐
    # 如果 textwrap.dedent 没切干净（因为首行可能没缩进导致基准误判），这里手动计算最小缩进并切除
    lines = code.split('\n')
    if lines:
        cleaned_lines = []
        # 计算除空行外的最小缩进
        min_indent = float('inf')
        for line in lines:
            if line.strip(): # 只看非空行
                # 计算缩进空格数
                indent = len(line) - len(line.lstrip())
                if indent < min_indent:
                    min_indent = indent
        
        # 如果找到了全局多余的缩进，切掉它
        if min_indent != float('inf') and min_indent > 0:
            for line in lines:
                if len(line) >= min_indent:
                    cleaned_lines.append(line[min_indent:])
                else:
                    cleaned_lines.append(line)
            code = '\n'.join(cleaned_lines)

    return code.strip()

def main():
    # 支持命令行参数传入文件路径，方便复用
    if len(sys.argv) >= 2:
        in_path = Path(sys.argv[1])
        if len(sys.argv) >= 3:
            out_path = Path(sys.argv[2])
        else:
            # 默认输出文件名加 _cleaned 后缀
            out_path = in_path.with_name(in_path.stem + "_CLEANED" + in_path.suffix)
    else:
        # 使用配置区的默认路径
        in_path = Path(INPUT_FILE)
        out_path = Path(OUTPUT_FILE)
    
    if not in_path.exists():
        print(f"❌ 找不到输入文件: {in_path}")
        print(f"用法: python clean_results.py [输入文件] [输出文件]")
        return

    print(f"🧹 开始清洗: {in_path}")
    print(f"💾 输出目标: {out_path}")
    
    count = 0
    fixed_nbsp_count = 0
    
    with open(in_path, "r", encoding="utf-8") as fin, \
         open(out_path, "w", encoding="utf-8") as fout:
        
        for line in fin:
            line = line.strip()
            if not line:
                continue
                
            try:
                data = json.loads(line)
                original_solution = data.get("solution", "")
                
                # 统计一下原来的 dirty 数据
                if '\u00a0' in original_solution:
                    fixed_nbsp_count += 1

                # 执行清洗
                cleaned_solution = clean_code(original_solution)
                
                # 更新 solution
                data["solution"] = cleaned_solution
                
                # 写入新文件
                fout.write(json.dumps(data, ensure_ascii=False) + "\n")
                
                # 打印一个示例看看效果 (比如 HumanEval/3)
                if data["task_id"] == "HumanEval/3" and count == 0: # 只打一次
                    print("\n--- [示例检查 HumanEval/3] ---")
                    print("🔴 清洗前 (repr显示):")
                    print(repr(original_solution))
                    print("🟢 清洗后 (repr显示):")
                    print(repr(cleaned_solution))
                    print("----------------------------\n")
                
                count += 1
                
            except json.JSONDecodeError:
                print(f"⚠️ 跳过损坏的行: {line[:50]}...")
                continue

    print(f"✅ 清洗完成！共处理 {count} 条数据。")
    print(f"🔧 修复了包含 \\u00a0 (NBSP) 的代码: {fixed_nbsp_count} 处")
    print(f"👉 现在请运行 evalplus 命令评测新文件: {out_path}")

if __name__ == "__main__":
    main()