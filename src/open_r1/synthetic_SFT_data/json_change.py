# 加载模型对应的分词器，查看默认eos_token
from transformers import AutoTokenizer

# 模型路径和你命令中一致：/ssd5/rxliu/models/DeepSeek-R1-0528-Qwen3-8B
tokenizer = AutoTokenizer.from_pretrained("/ssd5/rxliu/models/DeepSeek-R1-0528-Qwen3-8B")

# 打印默认终止符及对应的ID
print("分词器默认eos_token：", tokenizer.eos_token)
print("默认eos_token的ID：", tokenizer.eos_token_id)