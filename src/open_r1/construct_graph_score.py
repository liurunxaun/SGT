import re
import networkx as nx

def construct_graph_and_score(think_content):
  
  # 使用正则提取所有节点信息
  pattern = re.compile(r"\{\s*node_id:(\d+)\s*parents:([^\n]+)\s*content:(.*?)\}", re.DOTALL)
  nodes = []
  for match in pattern.finditer(think_content):
      node_id = int(match.group(1))
      parents = match.group(2).strip()
      content = match.group(3).strip()
      # 处理 parents 字段
      if parents.lower() == 'none':
          parent_list = []
      else:
          parent_list = [int(p.strip()) for p in parents.split(',')]
      # 保存节点信息
      nodes.append({'id': node_id, 'parents': parent_list, 'content': content})

  # 构建有向图
  G = nx.DiGraph()
  for node in nodes:
      G.add_node(node['id'], name=node['content'])
      for parent in node['parents']:
          G.add_edge(parent, node['id'])

  # 检查图的连通性（弱连通性适用于有向图）
  is_connected = nx.is_weakly_connected(G)

  # print(f"Nodes: {len(G.nodes)}")
  # print(f"Edges: {len(G.edges)}")
  # print(f"Weakly connected: {is_connected}")

  # # 打印节点信息示例
  # for n, data in G.nodes(data=True):
  #     print(f"Node {n}: {data['name']}")

  if is_connected:
    return 1
  else:
    return 0

if __name__ == "__main__":
  print(construct_graph_and_score())