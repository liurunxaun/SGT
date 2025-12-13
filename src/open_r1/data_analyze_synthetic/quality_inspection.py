import os
import re
import json
import asyncio
import pandas as pd
import networkx as nx
from openai import AsyncOpenAI, RateLimitError, APIConnectionError
from tqdm.asyncio import tqdm_asyncio

# ================= 配置区域 =================
# 输入文件（必须包含 graph_structured_reasoning 字段）
INPUT_FILE = "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/test_qwen3-max_graph_results_correct.xlsx"
OUTPUT_FILE = INPUT_FILE.replace(".xlsx", "_eval_scores.xlsx")

# 评测用模型配置 (建议使用能力较强的模型作为 Judge)
JUDGE_API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6" # ⚠️ 替换你的 Key
JUDGE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
JUDGE_MODEL = "qwen-max" # 或者 qwen-max, qwen3-next-80b-instruct

# 并发控制 (评测请求量 = 数据行数 * 平均节点数 * 2，建议控制并发)
MAX_CONCURRENCY = 20 

# ================= 1. 标签定义 (用于维度1评估) =================
LABEL_DEFINITIONS = {
    "known": "Known conditions that can be found in the question. Parents should be none.",
    "generate": "From the current reasoning state, generate one or more new reasoning steps. It represents a step forward.",
    "aggregate": "Merge multiple steps or jointly reason over them to produce a new reasoning step. Parent must be multiple nodes.",
    "feedback": "Go back to a previous reasoning step. Used to re-examine the correctness of a step or process.",
    "reflection": "Go back to a previous reasoning step. Used to re-examine the correctness of a step or process.", # 兼容 reflection/feedback
    "refine": "Improve the current node. It is a refined modification of a certain node's statement, without producing a substantial step forward.",
    "associative thinking": "Comparing the current reasoning graph structure with other similar graph structures/problems to facilitate reasoning.",
    "reverse thinking": "Starting from the goal of the problem, considering possible solution paths, and filtering them with given conditions. Building a path from unknown to known."
}

# ================= 2. 核心逻辑类 =================

class GraphEvaluator:
    def __init__(self, api_key, base_url, model):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    def construct_graph(self, think_content):
        """
        解析 XML/JSON 混合格式，构建图结构
        """
        if not isinstance(think_content, str):
            return None, {}

        # 提取 <think>...</think>
        match = re.search(r"<think>(.*?)</think>", think_content, re.DOTALL)
        if not match:
            # 尝试直接解析完整内容（如果只有 think 部分）
            inner_content = think_content
        else:
            inner_content = match.group(1)

        section_pattern = re.compile(
            r"<(known|generate|aggregate|refine|feedback|reflection|associative thinking|reverse thinking)>\s*(.*?)\s*</\1>",
            re.DOTALL | re.IGNORECASE
        )
        # 注意：这里稍微放宽了正则，以防大模型输出多余空格
        node_pattern = re.compile(
            r"\{\s*node_id:(\d+)\s*parents:([^\n]+)\s*content:(.*?)\}",
            re.DOTALL
        )

        node_dict = {}
        
        for section_match in section_pattern.finditer(inner_content):
            label = section_match.group(1).lower()
            section_body = section_match.group(2)

            for node_match in node_pattern.finditer(section_body):
                try:
                    node_id = int(node_match.group(1))
                    parents_raw = node_match.group(2).strip()
                    content = node_match.group(3).strip()

                    if parents_raw.lower() == "none":
                        parents = []
                    else:
                        # 处理可能出现的非数字字符
                        parents = [
                            int(p.strip())
                            for p in parents_raw.split(",")
                            if p.strip().isdigit()
                        ]

                    node_dict[node_id] = {
                        "id": node_id,
                        "parents": parents,
                        "content": content,
                        "label": label,
                    }
                except Exception:
                    continue

        if not node_dict:
            return None, {}

        try:
            G = nx.DiGraph()
            for node in node_dict.values():
                G.add_node(node["id"], content=node["content"], label=node["label"])
                for parent in node["parents"]:
                    if parent in node_dict: # 确保父节点存在
                        G.add_edge(parent, node["id"])
            return G, node_dict
        except Exception:
            return None, {}

    async def _call_llm_judge(self, system_prompt, user_prompt):
        """通用 LLM 调用函数"""
        async with self.semaphore:
            retries = 3
            for attempt in range(retries):
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.0, # 评测需要确定性
                        max_tokens=10
                    )
                    content = response.choices[0].message.content.strip()
                    # 尝试提取数字
                    score_match = re.search(r"(\d+(\.\d+)?)", content)
                    if score_match:
                        val = float(score_match.group(1))
                        return max(0.0, min(1.0, val))
                    return 0.0
                except (RateLimitError, APIConnectionError) as e:
                    if attempt < retries - 1:
                        await asyncio.sleep(2 * (attempt + 1))
                    else:
                        print(f"API Error after retries: {e}")
                        return 0.0
                except Exception as e:
                    print(f"Unexpected Error: {e}")
                    return 0.0
            return 0.0

    async def check_label_compliance(self, node_info):
        """
        维度 1: 节点内容是否符合标签定义
        """
        label = node_info['label']
        content = node_info['content']
        definition = LABEL_DEFINITIONS.get(label, "Standard reasoning step.")

        system_prompt = f"""You are a strict logic evaluator. 
        Your task is to determine if the content of a reasoning node COMPLIES with the definition of its assigned tag.
        
        Tag: <{label}>
        Definition: {definition}
        
        Respond ONLY with a score between 0.0 and 1.0.
        1.0 = Perfectly matches the definition.
        0.0 = Completely irrelevant or contradicts the definition.
        """
        
        user_prompt = f"Node Content: {content}"
        return await self._call_llm_judge(system_prompt, user_prompt)

    async def check_semantic_coherence(self, parent_contents, child_content):
        """
        维度 2: 语义连贯性 (复用你的逻辑)
        """
        if not parent_contents:
            return 1.0 # 无父节点（如 known），默认连贯

        parents_text = "\n".join([f"- {p}" for p in parent_contents])
        
        system_prompt = """You are an analytical evaluator. Your task is to judge whether a child's reasoning step logically follows and builds upon its parent step(s) without introducing contradictions.

        Evaluation Criteria:
        1. The child should logically build upon the parent without introducing contradictions.
        2. If the child repeats the parent’s idea with more detail, score should be high.
        3. If the child introduces a valid, additional reasoning step that logically follows, score should be high.
        4. If the child contradicts the parent (e.g., parent: 150%, child: 0.15), the score should be low.
        5. If the child introduces information that violates the parent’s logic, the score should be low.
        
        Respond ONLY with a number between 0.0 and 1.0 representing the semantic coherence score.
        """
        
        user_prompt = f"### Parent Nodes:\n{parents_text}\n\n### Child Node:\n{child_content}"
        return await self._call_llm_judge(system_prompt, user_prompt)

    async def evaluate_row(self, idx, row):
        """
        评估单行数据
        """
        think_content = row.get('graph_structured_reasoning')
        if not think_content:
            return {
                "id": row.get('id'), 
                "parse_success": False, 
                "avg_label_score": 0, 
                "avg_coherence_score": 0,
                "low_quality_nodes": "Empty content"
            }

        G, node_dict = self.construct_graph(think_content)
        if not node_dict:
            return {
                "id": row.get('id'), 
                "parse_success": False, 
                "avg_label_score": 0, 
                "avg_coherence_score": 0,
                "low_quality_nodes": "Parse failed"
            }

        label_scores = []
        coherence_scores = []
        low_quality_log = []

        # 创建该行所有节点的评测任务
        tasks = []
        
        for node_id, info in node_dict.items():
            # 1. Label Check Task
            tasks.append(("label", node_id, self.check_label_compliance(info)))
            
            # 2. Coherence Check Task
            parent_contents = [node_dict[pid]['content'] for pid in info['parents'] if pid in node_dict]
            tasks.append(("coherence", node_id, self.check_semantic_coherence(parent_contents, info['content'])))

        # 并发执行该图的所有评测
        results = await asyncio.gather(*[t[2] for t in tasks])
        
        # 整理结果
        temp_scores = {} # node_id -> {'label': val, 'coherence': val}
        
        for i, res in enumerate(results):
            task_type, node_id, _ = tasks[i]
            score = res
            
            if node_id not in temp_scores: 
                temp_scores[node_id] = {}
            
            temp_scores[node_id][task_type] = score
            
            # 记录低分节点
            if score < 0.6:
                low_quality_log.append(f"Node {node_id} ({task_type}): {score:.2f}")

        # 计算平均分
        for scores in temp_scores.values():
            if 'label' in scores: label_scores.append(scores['label'])
            if 'coherence' in scores: coherence_scores.append(scores['coherence'])

        avg_label = sum(label_scores) / len(label_scores) if label_scores else 0
        avg_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0

        return {
            "id": row.get('id'),
            "parse_success": True,
            "node_count": len(node_dict),
            "avg_label_score": round(avg_label, 4),
            "avg_coherence_score": round(avg_coherence, 4),
            "low_quality_nodes": "; ".join(low_quality_log)
        }

# ================= 3. 主流程 =================

async def main():
    print(f"Loading data from {INPUT_FILE}...")
    if INPUT_FILE.endswith('.xlsx'):
        df = pd.read_excel(INPUT_FILE)
    else:
        df = pd.read_parquet(INPUT_FILE)
    
    # 为了测试，可以只取前10条
    # df = df.head(10)
    print(f"Loaded {len(df)} rows. Starting evaluation...")

    evaluator = GraphEvaluator(JUDGE_API_KEY, JUDGE_BASE_URL, JUDGE_MODEL)
    
    tasks = []
    for idx, row in df.iterrows():
        tasks.append(evaluator.evaluate_row(idx, row))

    results = await tqdm_asyncio.gather(*tasks)
    
    # 合并结果
    result_df = pd.DataFrame(results)
    final_df = pd.merge(df, result_df, on='id', how='left')
    
    print(f"Saving evaluation results to {OUTPUT_FILE}...")
    final_df.to_excel(OUTPUT_FILE, index=False)
    
    # 打印简报
    print("\n=== Evaluation Summary ===")
    print(f"Average Label Compliance: {result_df['avg_label_score'].mean():.4f}")
    print(f"Average Semantic Coherence: {result_df['avg_coherence_score'].mean():.4f}")
    print(f"Parse Success Rate: {result_df['parse_success'].mean():.2%}")

if __name__ == "__main__":
    asyncio.run(main())