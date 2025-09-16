print("First Time!")

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

print("finished loading transformers")

# 模型路径
model_path = "/data/home/the/rxliu/projects/open-r1-main/output/DeepSeek-R1-0528-Qwen3-8B-AIME24-GRPO-Label_only"

# 加载 tokenizer 和模型
tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=False)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    device_map="auto",   # 自动放到GPU上
    torch_dtype=torch.bfloat16  # 如果显卡支持BF16
)

print("finished loading model")

# 构造一个query
query = "Find the sum of all integer bases $b>9$ for which $17_{b}$ is a divisor of $97_{b}$."

# Qwen 是 chat 模型，建议用 chat 模式
messages = [
    {"role": "system", "content": """
    You are a helpful AI Assistant that provides well-reasoned and detailed responses. When replying, produce exactly two blocks in this format (with newlines as shown):

  <think>
  ...structured DAG-style internal reasoning (see conventions below)...
  </think>
  <answer>
  ...concise user-facing final answer...
  </answer>

  CONVENTIONS for the <think> block (represent internal reasoning as a directed acyclic graph):

  1. Nodes:
     - Represent each reasoning state as a node using:
       <Node id="nX">
       <content>
       Short summary of the node's state (one brief paragraph).
       </content>
       <parents>comma-separated parent node IDs (optional)</parents>
       </Node>
     - Node ids must be unique (n0, n1, ...). Use the same ids when referring to parents.

  2. Operations:
     - When you perform an operation, include the exact operation tags:
       <Generate> ... </Generate>
       <Aggregate> ... </Aggregate>
       <Feedback> ... </Feedback>
       <Refine> ... </Refine>
     - Each operation block should describe which node(s) it reads from and which node(s) it produces or modifies.
     - Example usage patterns (use one or more as needed, any order, any number of times):
       - <Generate> creates new <Node id="..."> blocks and sets their <parents>.
       - <Aggregate> merges several existing nodes and produces a new <Node>.
       - <Feedback> indicates returning to/revising an earlier node (reference its id).
       - <Refine> improves the content of an existing node (include the updated <Node> with same id).

  3. Graph rules:
     - The structure should form a DAG (avoid cycles).
     - Operations may appear in any order and can be repeated.
     - Keep each <content> concise (1–3 short sentences).
     - Use newlines exactly after opening and before closing tags so that the outer <think> and <answer> blocks are on their own lines.

  4. Final answer:
     - After finishing the <think> block, provide a concise <answer> block that contains only the final user-facing answer (do not repeat internal reasoning).

  Be consistent and machine-friendly in tag usage so that the reasoning graph can be parsed automatically.
  """},
    {"role": "user", "content": query}
]

text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

print("finished loading tokenizer")

# 转tensor
inputs = tokenizer(text, return_tensors="pt").to(model.device)

print("finished loading inputs")

# 生成
with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=2000,
        do_sample=True,
        temperature=0.7
    )

# 解码输出
print(tokenizer.decode(outputs[0], skip_special_tokens=True))