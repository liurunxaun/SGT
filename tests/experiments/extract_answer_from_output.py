import re

def extract_boxed_content(output: str):
    pattern = r"\\boxed\{"
    start_iter = re.finditer(pattern, output)
    last_content = None

    for m in start_iter:
        start = m.end()  # 起始位置（在 '{' 之后）
        brace_level = 1
        i = start
        while i < len(output) and brace_level > 0:
            if output[i] == "{":
                brace_level += 1
            elif output[i] == "}":
                brace_level -= 1
            i += 1
        if brace_level == 0:
            content = output[start:i-1].strip()
            last_content = content  # 只保留最后一个 boxed 内容
    return last_content
