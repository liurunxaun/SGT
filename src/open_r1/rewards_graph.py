import re
import networkx as nx
import requests
import json

# ============================================================
#                  构建图
# ============================================================

def construct_graph(think_content):
    """解析 think_content 并构建图，返回 G 和 node_dict"""

    section_pattern = re.compile(
        r"<(known|generate|aggregate|refine|feedback|associative thinking|reverse thinking)>\s*(.*?)\s*</\1>",
        re.DOTALL | re.IGNORECASE
    )
    node_pattern = re.compile(
        r"\{\s*node_id:(\d+)\s*parents:([^\n]+)\s*content:(.*?)\}",
        re.DOTALL
    )

    node_dict = {}
    for section_match in section_pattern.finditer(think_content):
        label = section_match.group(1).lower()
        section_body = section_match.group(2)

        for node_match in node_pattern.finditer(section_body):
            node_id = int(node_match.group(1))
            parents_raw = node_match.group(2).strip()
            content = node_match.group(3).strip()

            if parents_raw.lower() == "none":
                parents = []
            else:
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

    # 构建有向图
    G = nx.DiGraph()
    for node in node_dict.values():
        G.add_node(node["id"])
        for parent in node["parents"]:
            G.add_edge(parent, node["id"])

    return G, node_dict


# ============================================================
#                    工具函数
# ============================================================

def _get_start_end_nodes(node_dict):
    """根据标签顺序找 start/end 标签的节点"""
    labels_order = []
    for nid in sorted(node_dict.keys()):
        lab = node_dict[nid]["label"]
        if lab not in labels_order:
            labels_order.append(lab)

    if len(labels_order) < 2:
        return [], []

    start_label = labels_order[0]
    end_label = labels_order[-1]

    start_nodes = [nid for nid, info in node_dict.items() if info["label"] == start_label]
    end_nodes   = [nid for nid, info in node_dict.items() if info["label"] == end_label]

    return start_nodes, end_nodes


def llm_judge_semantic_coherence(parent_texts, node_text, child_texts):
        """
        输入父节点和子节点文本，让大模型给出 0~1 的连贯性分数。
        """

        api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        api_key = "sk-8d445207b1ab47efb83069ccc1b845b6"
        model = "qwen3-next-80b-a3b-instruct"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        parents_block = "\n".join([f"- {t}" for t in parent_texts]) if parent_texts else "None"
        children_block = "\n".join([f"- {t}" for t in child_texts]) if child_texts else "None"

        prompt = f"""
            You are an analytical evaluator. Your task is to judge whether a child's reasoning step logically follows and builds upon its parent step without introducing contradictions.

            ### Parent Nodes:
            {parents_block}

            ### Current Node:
            {node_text}

            ### Child Nodes:
            {children_block}

            ### Evaluation Criteria:
            1. Parents -> Current: the current node should logically build upon its parents.
            2. Current -> Children: children should follow logically from the current node.
            3. The child should logically build upon the parent without introducing contradictions.
            4. If the child repeats the parent’s idea with more detail, score should be high.
            5. If the child introduces a valid, additional reasoning step that logically follows, score should be high.
            6. If the child contradicts the parent (e.g., parent: 150%, child: 0.15), the score should be low.
            7. If the child introduces information that violates the parent’s logic, the score should be low.

            ### Output Format:
            Respond ONLY with a number between 0 and 1 representing the semantic coherence score.
            No explanation. No text around it.
        """

        data = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
        }

        try:
            response = requests.post(api_url, headers=headers, data=json.dumps(data))
            result = response.json()

            score_str = result["choices"][0]["message"]["content"].strip()
            score = float(score_str)

            score = max(0.0, min(1.0, score))
            return score

        except Exception as e:
            print("LLM semantic check error:", e)
            return 0.0
        

def count_tokens(text):
    
    return len(text)


# ============================================================
#                    奖励函数
# ============================================================

def reward_label_structure(
    node_dict,
    w_node=0.33,
    w_parent=0.33,
    w_cross_ref=0.33
):
    """
    各种标签内节点的结构的奖励：
    - 返回值为三项之和，w_count + w_parent + w_cross_ref。

    规则：
    1. 标签节点数量要求
       - aggregate: 必须 1 个
       - refine:    必须 1 个

    2. 各标签节点的父节点数量要求
       - known: parents = 0
       - aggregate: parents > 1
       - refine: parents = 1
       - feedback: parents里必须有当前的last node

    3. 同一标签内的节点不能互相作为父节点（不能互相引用）
       - 若一个 label 下多个节点，任一节点的 parent 中不能包含该 label 的其他节点
    """

    score = 0.0

    # 规则1：标签内节点数量要求
    def rule_node_number():
        label_require = {"aggregate": 1, "refine": 1}
        for lb, required in label_require.items():
            actual = sum(1 for x in node_dict.values() if x["label"] == lb)
            if actual != required:
                return 0.0
        return 1.0

    # 规则2：父节点数量要求（全通过为 1，否则 0）
    def rule_parent_num():
        for nid, info in node_dict.items():
            label = info["label"]
            pnum = len(info["parents"])

            if label == "known":
                if pnum != 0:
                    return 0.0
            elif label == "aggregate":
                if pnum <= 1:
                    return 0.0
            elif label == "refine":
                if pnum != 1:
                    return 0.0
            elif label == "feedback":
                # 当前节点 nid 的父节点必须包含 nid - 1
                if (nid - 1) not in info["parents"]:
                    return 0.0
        return 1.0

    # 规则3：同标签内节点不能互相引用（全通过为 1，否则 0）
    def rule_cross_reference():
        groups = {}
        for nid, info in node_dict.items():
            groups.setdefault(info["label"], []).append(nid)

        for lb, nodes in groups.items():
            if len(nodes) <= 1:
                continue
            node_set = set(nodes)
            for nid in nodes:
                if set(node_dict[nid]["parents"]) & node_set:
                    return 0.0
        return 1.0

    # 叠加得分
    score += w_node * rule_node_number()
    score += w_parent * rule_parent_num()
    score += w_cross_ref * rule_cross_reference()

    return score


def reward_connectivity(G):
    """连通子图数量越少越好： reward = 1 / num_components"""
    if not G.nodes:
        return 0.0
    num_cc = nx.number_weakly_connected_components(G)
    return 1.0 / num_cc


def reward_reachability(G, node_dict):
    """从第一个标签 → 最后一个标签 若存在可达路径则 reward = 1，否则 = 0"""

    start_nodes, end_nodes = _get_start_end_nodes(node_dict)

    if not start_nodes or not end_nodes:
        return 0.0

    for s in start_nodes:
        for e in end_nodes:
            if nx.has_path(G, s, e):
                return 1.0

    return 0.0


def reward_effective_subgraph_information_proportion(think_content, G, node_dict):
    """
    计算有效推理子图的信息量占比。
    1. 找 start → end 的最长路径 P
    2. 找所有从 P 分出去、最终又回到 P 的分支节点 B
    3. E = P ∪ B
    4. 计算 token 信息量： sum(E) / sum(all)
    """

    # Step 1: start/end 节点
    start_nodes, end_nodes = _get_start_end_nodes(node_dict)
    if not start_nodes or not end_nodes:
        return 0.0

    # Step 2: 找 start → end 的最长路径 P
    best_path = None
    best_length = -1    # ⭐ 初始为 -1 ，这样任何路径长度都比它大

    for s in start_nodes:
        for e in end_nodes:
            try:
                # 遍历所有 simple path（自动避免环）
                for path in nx.all_simple_paths(G, s, e):
                    if len(path) > best_length:
                        best_path = path
                        best_length = len(path)
            except nx.NetworkXNoPath:
                continue


    # 如果完全找不到路径
    if best_path is None:
        return 0.0

    P = best_path
    P_set = set(P)

    # Step 3: 找合法分支：从 P 分出去，又回到 P
    branch_nodes = set()

    for u in P:
        # 所有孩子
        for v in G.successors(u):
            if v in P_set:
                continue  # 仍在主路径

            # BFS 看是否能从 v 回到 P
            visited = set()
            queue = [v]

            can_return = False

            while queue:
                x = queue.pop(0)
                if x in visited:
                    continue
                visited.add(x)

                if x in P_set:
                    can_return = True
                    break

                for y in G.successors(x):
                    if y not in visited:
                        queue.append(y)

            if can_return:
                branch_nodes.update(visited)

    # Step 4: 有效子图节点集合 E
    effective_nodes = P_set | branch_nodes

    # Step 5: 基于 think_content 计算 token 比例
    
    # 全部 token
    total_tokens = count_tokens(think_content)
    # 有效 token：将 effective_nodes 的内容拼接
    effective_texts = []
    for nid in effective_nodes:
        effective_texts.append(node_dict[nid]["content"])

    effective_tokens = count_tokens("\n".join(effective_texts))

    if total_tokens == 0:
        return 0.0

    return effective_tokens / total_tokens


def reward_search(G, node_dict):
    """
    综合两部分：
    1. LLM 语义连贯性评分（每个节点：父 → 当前 → 子）
    2. 节点对终点标签节点（最后一个标签的节点集合）的可达性评分

    最终 reward = ( semantic_avg + reachability_avg ) / 2
    """
    # Part 1: 语义连贯性评分
    semantic_scores = []

    for nid, info in node_dict.items():
        node_text = info["content"]

        # 父节点文本
        parent_texts = [node_dict[p]["content"] for p in info["parents"]]

        # 子节点文本
        child_ids = list(G.successors(nid)) if nid in G else []
        child_texts = [node_dict[c]["content"] for c in child_ids]

        # LLM 语义连贯性
        score = llm_judge_semantic_coherence(parent_texts, node_text, child_texts)
        semantic_scores.append(score)

    semantic_avg = sum(semantic_scores) / len(semantic_scores) if semantic_scores else 0.0

    # Part 2: 可达性评分：节点 → 最后一个标签的任意节点
    # 找最后一个标签
    labels_order = []
    for nid in sorted(node_dict.keys()):
        lb = node_dict[nid]["label"]
        if lb not in labels_order:
            labels_order.append(lb)

    if len(labels_order) < 1:
        return semantic_avg  # fallback

    final_label = labels_order[-1]

    # 最终目标节点集合
    end_nodes = [nid for nid, info in node_dict.items() if info["label"] == final_label]

    reach_scores = []

    for nid in node_dict.keys():
        reachable = False
        for e in end_nodes:
            try:
                if nx.has_path(G, nid, e):
                    reachable = True
                    break
            except:
                pass
        
        reach_scores.append(1.0 if reachable else 0.0)

    reachability_avg = sum(reach_scores) / len(reach_scores) if reach_scores else 0.0

    # Final reward = 综合两部分平均
    final_reward = (semantic_avg + reachability_avg) / 2
    return final_reward



# ============================================================
#                     统一入口
# ============================================================

def construct_graph_and_score(content, script_args):
    """
    根据 script_args.graph_reward_funcs 和 script_args.graph_reward_weights
    动态计算图奖励，并对权重做归一化处理。
    """
    # step 0: 提取think内容
    match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
    if match:
        think_content = match.group(1).strip()
    else:
        think_content = None

    # step 1: 构图
    G, node_dict = construct_graph(think_content)

    # step 2: reward 函数注册表，新增函数需要在这里注册
    reward_func_registry = {
        "reachability": lambda: reward_reachability(G, node_dict),
        "connectivity": lambda: reward_connectivity(G),
        "label_structure": lambda: reward_label_structure(node_dict),
        "effective_subgraph_information_proportion": lambda: reward_effective_subgraph_information_proportion(think_content, G, node_dict),
        "search": lambda: reward_search(G, node_dict),
        }

    funcs = script_args.graph_reward_funcs
    weights = script_args.graph_reward_weights

    assert len(funcs) == len(weights), \
        f"Length mismatch: funcs={len(funcs)}, weights={len(weights)}"

    # step 3: 权重归一化
    weight_sum = sum(weights)

    if weight_sum == 0:
        # 如果用户配置全 0，则变成均匀分配
        norm_weights = [1/len(weights)] * len(weights)
    else:
        norm_weights = [w / weight_sum for w in weights]

    graph_award = 0.0

    # step 4: 动态调用 reward 函数
    for func_name, weight in zip(funcs, norm_weights):
        if func_name not in reward_func_registry:
            raise ValueError(f"Unknown reward function: {func_name}")

        reward_value = reward_func_registry[func_name]()
        graph_award += weight * reward_value

    return graph_award



# ============================================================
#                     示例
# ============================================================

if __name__ == "__main__":
    think_content = """
    <think>

        <known>

            {
                node_id:1
                parents:none
                content:Natalia sold clips to 48 of her friends in April.
            },

            {
                node_id:2
                parents:none
                content:In May, Natalia sold half as many clips as she did in April.
            }

        </known>

        <generate>

            {
                node_id:3
                parents:1
                content:Clips sold in April = 48
            },

            {
                node_id:4
                parents:2
                content:Clips sold in May = 48 / 2 = 24
            }

        </generate>

        <aggregate>

            {
                node_id:5
                parents:3,4
                content:Total clips sold in April and May = 48 + 24
            }

        </aggregate>

        <refine>

            {
                node_id:6
                parents:5
                content:Total clips sold in April and May = 72
            }

        </refine>

    </think>
    """
    print(construct_graph_and_score(think_content))
