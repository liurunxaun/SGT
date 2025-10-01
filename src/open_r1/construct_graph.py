import re
import networkx as nx

# 假设 think_content 是你的 <think> 标签内的原始文本
think_content = """
  <known>
    {
      node_id:1
      parents:none
      content:b>9 
    },
    {
      node_id:2
      parents:none
      content:17_{b} is a divisor of 97_{b} 
    },
    {
      node_id:3
      parents:none
      content:b is an integer
    }
  </known>
  <generate>
    {
      node_id:4
      parents:2
      content:17_{b}=b+7
    },
    {
      node_id:5
      parents:2
      content:97_{b}=9*b+7
    },
  </generate>
  <aggregate>
    {
      node_id:6
      parents:2,4,5
      content: 9*b+7=k(b+7)，k>0,k is an integer
    },
  </aggregate>
  <aggeregate>
    {
      node_id:7
      parents:6
      content:b=(7-7k)/(k-9),1<k<9,k is an integer
    }
  </aggeregate>
  <associative thinking>
    {
      node_id:8
      parents:7
      content:When dealing with this type of problem before, I used the enumeration method, and I can apply the same method here as well.
    }
  </associative thinking>
  <generate>
    {
      node_id:9
      parents:1,7
      content:if k=2,b=1,false.
    },
    {
      node_id:10
      parents:1,3,7
      content:2. if k=3,b=14/6,false.
    },
    {
      node_id:11
      parents:1,3,7
      content:if k=4,b=21/5,false.
    },
    {
      node_id:12
      parents:1,7
      content:if k=5,b=7,false.
    },
    {
      node_id:13
      parents:3,7
      content:if k=6,b=35/3,false.
    },
    {
      node_id:14
      parents:7
      content:if k=7,b=21,true. 
    },
    {
      node_id:15
      parents:7
      content:if k=8,b=49,true.
    }
  </generate>
  <feedback>
    {
      node_id:16
      parents:14
      content:But wait: Also b+7=? and 9*b+7=? Possibly b+7=56 and 9*b+7=448? 448/56=8 Yes.
    }
  </feedback>
  <aggeregate>
    {
      node_id:17
      parents:9,10,11,12,13,14,15
      content:Sum=21+49=70
    }
  </aggeregate>
"""

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

print(f"Nodes: {len(G.nodes)}")
print(f"Edges: {len(G.edges)}")
print(f"Weakly connected: {is_connected}")

# 打印节点信息示例
for n, data in G.nodes(data=True):
    print(f"Node {n}: {data['name']}")