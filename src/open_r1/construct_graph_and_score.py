import re
import networkx as nx

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


# ============================================================
#                    奖励函数
# ============================================================

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


def reward_label_node(
    node_dict,
    w_node=0.25,
    w_parent=0.25,
    w_cross_ref=0.25
):
    """
    结构性奖励（逐项累加）：
    - 三项规则分别通过可得 w_count / w_parent / w_cross_ref 分（默认均为 0.25）。
    - 返回值为三项之和，最大值 = w_count + w_parent + w_cross_ref（默认 0.75）。

    规则：
    1. 标签节点数量要求
       - aggregate: 必须 1 个
       - refine:    必须 1 个

    2. 各标签节点的父节点数量要求
       - known: parents = 0
       - aggregate: parents > 1
       - refine: parents = 1

    3. 同一标签内的节点不能互相作为父节点（不能互相引用）
       - 若一个 label 下多个节点，任一节点的 parent 中不能包含该 label 的其他节点
    """

    score = 0.0

    # 规则1：标签数量要求
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



# ============================================================
#                     统一入口
# ============================================================

def construct_graph_and_score(
    think_content,
    wight_reachability = 0.6, 
    wight_connectivity = 0.2,
    wight_label_node = 0.2
):
    
    G, node_dict = construct_graph(think_content)

    reachability_reward = reward_reachability(G, node_dict)
    connectivity_reward = reward_connectivity(G)
    label_node_reward = reward_label_node(node_dict)

    graph_award = (
        wight_reachability * reachability_reward +
        wight_connectivity * connectivity_reward +
        wight_label_node * label_node_reward
    )

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

    <answer>
        Natalia sold a total of 72 clips in April and May.
    </answer>
    """
    print(construct_graph_and_score(think_content))
