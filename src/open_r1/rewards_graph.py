import re
import networkx as nx
import requests
import json
import wandb

# ============================================================
#                  构建图
# ============================================================

def construct_graph(think_content):
    """使用解析好的 think_content，构建图，返回 G 和 node_dict"""

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
        

def count_tokens(text):
    
    return len(text.split())


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

    # Step 1：SCC 分解（强连通成分），将有环节点压成 DAG
    scc_list = list(nx.strongly_connected_components(G))  # 每个 SCC 是一个节点集合
    scc_id = {}    # 每个节点对应其 SCC 编号
    scc_graph = nx.DiGraph()

    for i, comp in enumerate(scc_list):
        scc_graph.add_node(i)
        for node in comp:
            scc_id[node] = i

    for u, v in G.edges():
        if scc_id[u] != scc_id[v]:
            scc_graph.add_edge(scc_id[u], scc_id[v])  # Only inter-SCC edges

    # Step 2：在 SCC DAG 上求 start → end 的最长路径
    start_scc = {scc_id[s] for s in start_nodes}
    end_scc = {scc_id[e] for e in end_nodes}

    topo = list(nx.topological_sort(scc_graph))

    # DP：每个 SCC 的最长路径长度 + 路径
    dp_len = {i: -1 for i in topo}
    dp_path = {i: [] for i in topo}

    # 初始化所有 start_scc
    for s in start_scc:
        dp_len[s] = 0
        dp_path[s] = [s]

    # DAG DP
    for u in topo:
        if dp_len[u] < 0:
            continue
        for v in scc_graph.successors(u):
            if dp_len[u] + 1 > dp_len[v]:
                dp_len[v] = dp_len[u] + 1
                dp_path[v] = dp_path[u] + [v]

    # 找到最优终点
    best_scc_path = None
    best_length = -1
    for e in end_scc:
        if dp_len[e] > best_length:
            best_length = dp_len[e]
            best_scc_path = dp_path[e]

    if best_scc_path is None:
        return 0.0

    # 将 SCC 路径展开成“主路径节点序列”P
    main_path = []
    for comp_id in best_scc_path:
        # 取这个 SCC 中任意一个节点（你也可以取多个）
        comp_nodes = list(scc_list[comp_id])
        main_path.append(comp_nodes[0])

    P = main_path
    P_set = set(P)

    # Step 3：找所有从主路径分出去又能回来的“合法分支”
    branch_nodes = set()

    for u in P:
        for v in G.successors(u):
            if v in P_set:
                continue

            # BFS：从 v 出发，看看是否能回到主路径
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

    # Step 4：计算有效信息 token 占比
    effective_nodes = P_set | branch_nodes

    total_tokens = count_tokens(think_content)
    if total_tokens == 0:
        return 0.0

    effective_texts = "\n".join(node_dict[n]["content"] for n in effective_nodes)
    effective_tokens = count_tokens(effective_texts)

    return effective_tokens / total_tokens


def reward_search(G, node_dict):
    """
    遍历推理图, 节点对终点的可达性评分
    """

    # 节点对最终答案贡献情况评分：可达性评价：节点 → 最后一个节点

    # 直接取最后一个节点（编号最大）
    end_nodes = [max(node_dict.keys())]

    # 反向构图，从最终节点出发 BFS
    reverse_G = G.reverse()
    target_reachable = set()

    queue = end_nodes.copy()
    while queue:
        x = queue.pop(0)
        if x in target_reachable:
            continue
        target_reachable.add(x)
        for parent in reverse_G.successors(x):
            queue.append(parent)

    answer_contribution_avg = len(target_reachable) / len(node_dict)

    return answer_contribution_avg



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
        # 如果找不到 <think> 标签，说明格式严重错误
        # 直接返回 0.0，避免把 None 传给 construct_graph 导致报错
        print("Graph Reward: No <think> tag found.") # 可选日志
        return 0.0

    # 如果提取出的内容为空字符串，也直接返回 0
    if not think_content:
        return 0.0

    # step 1: 构图
    try:
        G, node_dict = construct_graph(think_content)
    except Exception as e:
        print(f"Graph construction error: {e}")
        return 0.0
        
    # 如果图是空的（没有节点），下面的计算(如 search)可能会除以0或报错，直接返回 0
    if not node_dict:
        return 0.0

    # step 2: reward 函数注册表
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
        norm_weights = [1/len(weights)] * len(weights)
    else:
        norm_weights = [w / weight_sum for w in weights]

    graph_award = 0.0
    
    # 收集子项指标
    metrics_log = {}

    # step 4: 动态调用 reward 函数
    for func_name, weight in zip(funcs, norm_weights):
        if func_name not in reward_func_registry:
            raise ValueError(f"Unknown reward function: {func_name}")

        try:
            # 计算原始奖励值
            reward_value = reward_func_registry[func_name]()
        except Exception as e:
            # 防止某个具体的 reward 函数内部报错（例如除以零）炸掉整个进程
            print(f"Error in reward func {func_name}: {e}")
            reward_value = 0.0
        
        metrics_log[f"train/rewards/graph_details/{func_name}"] = reward_value
        graph_award += weight * reward_value

    # 尝试发送到 WandB
    try:
        if wandb.run:
            wandb.log(metrics_log, commit=False)
    except Exception:
        pass 

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
