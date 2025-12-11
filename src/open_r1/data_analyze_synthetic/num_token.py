import pandas as pd
from transformers import AutoTokenizer
from tqdm import tqdm

# 配置路径
model_path = "/ssd5/rxliu/models/Qwen3-8B-Base"
data_path = "/ssd5/rxliu/datasets/SFT-Data/All-data-parquet/train.parquet"

# 如果您有自定义的 chat_template，可以在这里定义，否则默认使用 tokenizer 自带的
# 根据您之前的配置文件，如果 tokenizer_config.json 里没有包含正确的 template，
# 您可能需要取消下面这行的注释并替换为您 yaml 里的 template 字符串
custom_chat_template = "{%- if tools %}\n    {{- '<|im_start|>system\\n' }}\n    {%- if messages[0].role == 'system' %}\n        {{- messages[0].content + '\\n\\n' }}\n    {%- endif %}\n    {{- \"# Tools\\n\\nYou may call one or more functions to assist with the user query.\\n\\nYou are provided with function signatures within <tools></tools> XML tags:\\n<tools>\" }}\n    {%- for tool in tools %}\n        {{- \"\\n\" }}\n        {{- tool | tojson }}\n    {%- endfor %}\n    {{- \"\\n</tools>\\n\\nFor each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\\n<tool_call>\\n{\\\"name\\\": <function-name>, \\\"arguments\\\": <args-json-object>}\\n</tool_call><|im_end|>\\n\" }}\n{%- else %}\n    {%- if messages[0].role == 'system' %}\n        {{- '<|im_start|>system\\n' + messages[0].content + '<|im_end|>\\n' }}\n    {%- endif %}\n{%- endif %}\n{%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}\n{%- for message in messages[::-1] %}\n    {%- set index = (messages|length - 1) - loop.index0 %}\n    {%- if ns.multi_step_tool and message.role == \"user\" and not(message.content.startswith('<tool_response>') and message.content.endswith('</tool_response>')) %}\n        {%- set ns.multi_step_tool = false %}\n        {%- set ns.last_query_index = index %}\n    {%- endif %}\n{%- endfor %}\n{%- for message in messages %}\n    {%- if (message.role == \"user\") or (message.role == \"system\" and not loop.first) %}\n        {{- '<|im_start|>' + message.role + '\\n' + message.content + '<|im_end|>' + '\\n' }}\n    {%- elif message.role == \"assistant\" %}\n        {%- set content = message.content %}\n        {%- set reasoning_content = '' %}\n        {%- if message.reasoning_content is defined and message.reasoning_content is not none %}\n            {%- set reasoning_content = message.reasoning_content %}\n        {%- else %}\n            {%- if '</think>' in message.content %}\n                {%- set content = message.content.split('</think>')[-1].lstrip('\\n') %}\n                {%- set reasoning_content = message.content.split('</think>')[0].rstrip('\\n').split('<think>')[-1].lstrip('\\n') %}\n            {%- endif %}\n        {%- endif %}\n        {%- if loop.index0 > ns.last_query_index %}\n            {%- if loop.last or (not loop.last and reasoning_content) %}\n                {{- '<|im_start|>' + message.role + '\\n<think>\\n' + reasoning_content.strip('\\n') + '\\n</think>\\n\\n' + content.lstrip('\\n') }}\n            {%- else %}\n                {{- '<|im_start|>' + message.role + '\\n' + content }}\n            {%- endif %}\n        {%- else %}\n            {{- '<|im_start|>' + message.role + '\\n' + content }}\n        {%- endif %}\n        {%- if message.tool_calls %}\n            {%- for tool_call in message.tool_calls %}\n                {%- if (loop.first and content) or (not loop.first) %}\n                    {{- '\\n' }}\n                {%- endif %}\n                {%- if tool_call.function %}\n                    {%- set tool_call = tool_call.function %}\n                {%- endif %}\n                {{- '<tool_call>\\n{\"name\": \"' }}\n                {{- tool_call.name }}\n                {{- '\", \"arguments\": ' }}\n                {%- if tool_call.arguments is string %}\n                    {{- tool_call.arguments }}\n                {%- else %}\n                    {{- tool_call.arguments | tojson }}\n                {%- endif %}\n                {{- '}\\n</tool_call>' }}\n            {%- endfor %}\n        {%- endif %}\n        {{- '<|im_end|>\\n' }}\n    {%- elif message.role == \"tool\" %}\n        {%- if loop.first or (messages[loop.index0 - 1].role != \"tool\") %}\n            {{- '<|im_start|>user' }}\n        {%- endif %}\n        {{- '\\n<tool_response>\\n' }}\n        {{- message.content }}\n        {{- '\\n</tool_response>' }}\n        {%- if loop.last or (messages[loop.index0 + 1].role != \"tool\") %}\n            {{- '<|im_end|>\\n' }}\n        {%- endif %}\n    {%- endif %}\n{%- endfor %}\n{%- if add_generation_prompt %}\n    {{- '<|im_start|>assistant\\n' }}\n    {%- if enable_thinking is defined and enable_thinking is false %}\n        {{- '<think>\\n\\n</think>\\n\\n' }}\n    {%- endif %}\n{%- endif %}",
  
def main():
    print(f"正在加载分词器: {model_path} ...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        if custom_chat_template:
            tokenizer.chat_template = custom_chat_template
    except Exception as e:
        print(f"分词器加载失败: {e}")
        return

    print(f"正在加载数据: {data_path} ...")
    try:
        # 使用 pandas 读取 parquet
        df = pd.read_parquet(data_path)
    except Exception as e:
        print(f"数据加载失败: {e}")
        return
    
    # 检查列名，通常是 'messages' 或 'conversations'，但也可能是您之前提到的列结构
    # 这里假设数据是标准的 List[Dict] 格式，列名可能是 'messages'
    # 如果您的 parquet 直接就是平铺的，请根据实际情况修改
    target_col = None
    for col in ['messages', 'conversations', 'data', 'text']:
        if col in df.columns:
            target_col = col
            break
            
    if target_col is None:
        # 如果找不到常见列名，打印一下列名让用户看，默认取第一列
        print(f"未找到常见列名 (messages/conversations)，当前列: {df.columns.tolist()}")
        target_col = df.columns[0]
        print(f"默认使用列: {target_col}")

    print("开始统计 Token 数量...")
    token_counts = []
    
    # 遍历数据
    for _, row in tqdm(df.iterrows(), total=len(df)):
        messages = row[target_col]
        
        # 处理不同的数据格式
        if isinstance(messages, str):
            # 如果是纯文本，直接 tokenize
            text = messages
        elif isinstance(messages, list):
            # 如果是对话列表，使用 apply_chat_template
            try:
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            except Exception as e:
                # 容错：如果模板应用失败，可能格式不对，尝试直接转字符串
                text = str(messages)
        else:
            text = str(messages)
            
        # 计算 token id 数量
        ids = tokenizer.encode(text, add_special_tokens=True)
        token_counts.append(len(ids))

    if not token_counts:
        print("没有统计到数据。")
        return

    max_len = max(token_counts)
    min_len = min(token_counts)
    avg_len = sum(token_counts) / len(token_counts)

    print("\n" + "="*30)
    print("统计结果")
    print("="*30)
    print(f"数据总量: {len(token_counts)}")
    print(f"最大长度 (Max Tokens): {max_len}")
    print(f"最小长度 (Min Tokens): {min_len}")
    print(f"平均长度 (Avg Tokens): {avg_len:.2f}")
    print("="*30)

    # 额外提示：是否超过了 max_seq_length
    max_seq_len = 8192
    over_limit = sum(1 for x in token_counts if x > max_seq_len)
    if over_limit > 0:
        print(f"⚠️ 注意：有 {over_limit} 条数据超过了 {max_seq_len} 的限制，训练时可能会被截断。")
    else:
        print(f"✅ 所有数据均在 {max_seq_len} 限制范围内。")

if __name__ == "__main__":
    main()