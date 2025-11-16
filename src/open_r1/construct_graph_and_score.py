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
    """从第一个标签 → 最后一个标签 任意节点可达 = 1，否则 0"""

    # 根据 node_id 顺序读取标签序列
    labels_order = []
    for nid in sorted(node_dict.keys()):
        lab = node_dict[nid]["label"]
        if lab not in labels_order:
            labels_order.append(lab)

    if len(labels_order) < 2:
        return 0.0

    start_label = labels_order[0]
    end_label = labels_order[-1]

    start_nodes = [nid for nid, info in node_dict.items() if info["label"] == start_label]
    end_nodes   = [nid for nid, info in node_dict.items() if info["label"] == end_label]

    for s in start_nodes:
        for e in end_nodes:
            if nx.has_path(G, s, e):
                return 1.0
    return 0.0


def reward_short_path(G, node_dict):
    """路径越短越好： 1 / (1 + min_distance)"""
    start_nodes, end_nodes = _get_start_end_nodes(node_dict)
    if not start_nodes or not end_nodes:
        return 0.0

    min_len = float("inf")
    for s in start_nodes:
        for e in end_nodes:
            try:
                dist = nx.shortest_path_length(G, s, e)
                min_len = min(min_len, dist)
            except nx.NetworkXNoPath:
                continue

    if min_len == float("inf"):
        return 0.0

    return 1.0 / (1 + min_len)


def reward_long_path(G, node_dict):
    """路径越长越好： 1 - 1/(1 + max_distance)"""
    start_nodes, end_nodes = _get_start_end_nodes(node_dict)
    if not start_nodes or not end_nodes:
        return 0.0

    max_len = -1
    for s in start_nodes:
        for e in end_nodes:
            try:
                dist = nx.shortest_path_length(G, s, e)
                max_len = max(max_len, dist)
            except nx.NetworkXNoPath:
                continue

    if max_len < 0:
        return 0.0

    return 1.0 - 1.0 / (1 + max_len)


# ============================================================
#                     统一入口
# ============================================================

def construct_graph_and_score(
    think_content,
    w_reach=0.6, 
    w_short=0.1,
    w_long=0.1,
    w_conn=0.2
):
    
    G, node_dict = construct_graph(think_content)

    reach_r = reward_reachability(G, node_dict)
    short_r = reward_short_path(G, node_dict)
    long_r  = reward_long_path(G, node_dict)
    conn_r  = reward_connectivity(G)

    graph_award = (
        w_reach * reach_r +
        w_short * short_r +
        w_long * long_r +
        w_conn * conn_r
    )

    return graph_award


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