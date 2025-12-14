import os
import sys
import pandas as pd
import asyncio
import httpx
import time
import re
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APITimeoutError 
from tqdm.asyncio import tqdm_asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# ================= 1. 导入本地评测模块 =================
JUDGE_PATH = "/data/home/the/rxliu/projects/open-r1-main/tests/utils"
if JUDGE_PATH not in sys.path:
    sys.path.append(JUDGE_PATH)

try:
    from llm_judge import llm_judge_via_api
    print("成功导入 llm_judge_via_api")
except ImportError:
    print(f"【错误】无法从 {JUDGE_PATH} 导入 llm_judge_via_api")
    exit(1)

# ================= 2. 配置区域 =================
# 要处理的文件列表
INPUT_FILES = [
    "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files/train_part_2_of_4.parquet",
    "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files/train_part_3_of_4.parquet",
    "/ssd5/rxliu/datasets/SFT-Data/DeepScaleR/split_files/train_part_4_of_4.parquet",
]

# 生成模型配置
GEN_API_KEY = "sk-8d445207b1ab47efb83069ccc1b845b6"
GEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
GEN_MODEL_NAME = "qwen3-max" 

# 评测模型配置
JUDGE_API_KEY = GEN_API_KEY 
JUDGE_API_URL = GEN_BASE_URL 
JUDGE_MODEL_NAME = "qwen3-next-80b-a3b-instruct"

# --- 性能参数 ---
MAX_ATTEMPTS = 2  
MAX_CONCURRENCY = 50 
MAX_TOKENS = 32768 
REQUEST_TIMEOUT = 1200.0 

# --- 增量保存参数 ---
SAVE_INTERVAL = 1000  # 每处理 x 条保存一次

# ================= 3. 定义图结构推理的 System Prompt =================
GRAPH_SYSTEM_PROMPT = r"""
You are a helpful AI Assistant that provides well-reasoned and detailed responses. You first think about the reasoning process as an internal monologue and then provide the user with the answer. Respond in the following format: <think>\n...\n</think>\n<answer>\n...\n</answer>

Besides, you must comply with below conditions:
1.During the <think> phase you should organize the chain of thought using below tags:
- known: known conditions that can be found in the question.
- generate: from the current reasoning state, generate one or more new reasoning steps. It represents a step forward in the process of reasoning.
- aggregate: merge multiple steps or jointly reason over them to produce a new reasoning step.
- reflection: go back to a previous reasoning step. Used to re-examine the correctness of a step or process.
- refine: improve the current node. It is a refined modification of a certain node's statement, without producing a substantial step forward in the reasoning process.
- associative thinking: comparing the curent reasoning graph structure with other similar graph structures, in order to facilitate the current reasoning process. For example, when solving a math problem, recalling the solution methods used in previous similar problems.
- reverse thinking: starting from the goal of the problem, considering possible solution paths, and filtering them with the given conditions. This builds a abstruct reverse reasoning path from the goal to the conditions, from the unknown to the known. At this stage, you do not need to perform specific actions to get the answer. You just need to use reverse thinking to think about the reasoning method. The specific reasoning will be performed in the following tags.
2.At each further reasoning step you must choose one of these tags and wrap that step's output with the chosen tag. For example: <generate>...</generate>
3.The complete think phase must start with <known>...</konwn>, and the final inference tag must include the final result of the question.
4.The tag content inside is a series of thinking steps, organized in a node based manner with node_id and parents. You need to ensure that the thinking process is coherent and effective, and ultimately these nodes can be organized into a directed graph. The format example for each node is as follows:
{
    node_id:The unique identifier of a node, usually an integer, increasing from 1.
    parents:A list of parent node IDs for this node, used to establish inference dependencies. If there is no parent node, you can fill in none.
    content:The content of this step
}
5.For the content wrapped in different tags, there are the following formal requirements:
- konwn:It wraps one or more nodes, and the parents of these nodes should all be "none".
- generate:It wraps one or more nodels, (1) If it wraps one node, the parents of this nodes should be a single node. (2) If it wraps two or more nodes, the parents of these nodes should be a same single node.
- aggregate: It wraps one node, and the parent of this node should be multiple nodes.
- reflection: It wraps one node, and the parent of this node should be one or more nodes. Its parent_ids must include the last node of the current reasoning chain.
- refine: It wraps one node, and the parent of this node should be the last node in the current reasoning chain.
- associative thinking: It wraps one node, and the parent of this node should be one or more nodes.
- reverse thinking:It wraps one node, and the parent of this node should be one or more nodes.
6.If a tag contains multiple nodes, the parents of these nodes cannot contain other nodes in the tag.
7.If a tag contains multiple nodes, the nodes should be separated by commas. Within a node, different tags do not require commas and should be separated by line breaks. 

Please strictly follow the above format and requirements.
Below I'll give you two examples:

question 1:
Find the smallest number \( n \) such that given any \( n \) distinct numbers from \(\{1, 2, 3, \ldots, 999\}\), one can choose four different numbers \( a, b, c, d \) such that \( a + 2b + 3c = d \).

response:
<think>
    <known>
        {
            node_id:1
            parents:none
            content:The set is {1, 2, ..., 999}
        },
        {
            node_id:2
            parents:none
            content:We are to find the smallest n such that any subset of size n contains distinct a,b,c,d with a + 2b + 3c = d
        },
        {
            node_id:3
            parents:none
            content:a, b, c, d must be distinct elements from the chosen n numbers
        }
    </known>

    <reverse thinking>
        {
            node_id:4
            parents:2
            content:To find the minimal n that forces the equation a + 2b + 3c = d to hold among any n-element subset, we consider the maximal size of a subset that avoids this equation; then n is one more than that maximum.
        }
    </reverse thinking>

    <generate>
        {
            node_id:5
            parents:4
            content:Let S ⊆ {1,...,999} be a subset with no four distinct elements satisfying a + 2b + 3c = d. We want to maximize |S|.
        }
    </generate>

    <associative thinking>
        {
            node_id:6
            parents:5
            content:This resembles extremal combinatorics problems like Schur's theorem or sum-free sets. In such problems, choosing large numbers often avoids linear equations because the RHS (d) would exceed the universe bound.
        }
    </associative thinking>

    <generate>
        {
            node_id:7
            parents:6
            content:If we choose only large numbers, say all numbers > T, then a + 2b + 3c ≥ 1*T + 2*T + 3*T = 6T, so if 6T > 999, then d = a + 2b + 3c ∉ {1,...,999}, hence cannot be in S.
        }
    </generate>
......
I omitted the subsequent reasoning and answer generation process. In this example, you mainly learned how to use reverse thinking and associative thinking.


question 2:
Find the sum of all integer bases b>9 for which 17_{b} is a divisor of 97_{b}

response:
<think>

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
            content: 9*b+7=k(b+7),k>0,k is an integer
        },
    </aggeregate>
    <generate>
        {
            node_id:7
            parents:6
            content:b=(7-7k)/(k-9),1<k<9,k is an integer
        }
    </generate>
    <associative thinking>
        {
            node_id:8
            parents:7
            content:When dealing with this type of problem before, I used the enumeration method, and I can apply the same method here as well.
        }
    </associative thinking>
    <aggregate>
        {
            node_id:9
            parents:1,3,7,8
            content:Next, I should enumerate k under the condition that 1<k<9, k is an integer, and calculate when b satisfies the condition that b>9 and b is an integer.
        },
    </aggeregate>
    <generate>
        {
            node_id:10
            parents:9
            content:1.if k=2,b=1,false.
        },
        {
            node_id:11
            parents:9
            content:2. if k=3,b=14/6,false.
        },
        {
            node_id:12
            parents:9
            content:3. if k=4,b=21/5,false.
        },
        {
            node_id:13
            parents:9
            content:4. if k=5,b=7,false.
        },
        {
            node_id:14
            parents:9
            content:5. if k=6,b=35/3,false.
        },
        {
            node_id:15
            parents:9
            content:6. if k=7,b=21,true.
        },
        {
            node_id:16
            parents:9
            content:7.if k=8,b=49,true.
        }
    </generate>
    <reflection>
        {
            node_id:17
            parents:6,16
            content:But wait: Also b+7=? and 9*b+7=? Possibly b+7=56 and 9*b+7=448? 448/56=8 Yes.
        }
    </reflection>
    <aggeregate>
        {
            node_id:18
            parents:10,11,12,13,14,15,16
            content:Sum=21+49=70
        }
    </aggeregate>

</think>

<answer>
    70
</answer>
"""

# ===========================================

judge_executor = ThreadPoolExecutor(max_workers=32) 

def run_judge_sync(predicted, ground_truth):
    """同步评测函数"""
    try:
        if not predicted: return False
        is_correct = llm_judge_via_api(
            predicted, 
            ground_truth, 
            JUDGE_API_URL, 
            JUDGE_API_KEY, 
            JUDGE_MODEL_NAME
        )
        return is_correct
    except Exception as e:
        return False

def parse_model_output(text):
    """解析模型输出，分离 <think> 和 <answer> 标签内容"""
    if not text:
        return "", ""
    
    think_match = re.search(r'<think>(.*?)</think>', text, re.DOTALL)
    think_content = think_match.group(1).strip() if think_match else ""
    
    answer_match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL)
    answer_content = answer_match.group(1).strip() if answer_match else ""
    
    if not answer_content and not think_content:
        answer_content = text
    elif not answer_content and think_content:
        parts = text.split('</think>')
        if len(parts) > 1:
            answer_content = parts[1].strip()

    return think_content, answer_content

async def get_qwen_response_async(client, prompt):
    messages = [
        {"role": "system", "content": GRAPH_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {prompt}"}
    ]
    
    try:
        response = await client.chat.completions.create(
            model=GEN_MODEL_NAME,
            messages=messages,
            stream=False, 
            max_tokens=MAX_TOKENS 
        )

        choice = response.choices[0]
        
        if choice.finish_reason == "length":
            return "", "", "", "LENGTH_EXCEEDED"

        full_content = choice.message.content if choice.message.content else ""
        reasoning, answer = parse_model_output(full_content)
        
        return reasoning, answer, full_content, None

    except RateLimitError:
        return "", "", "", "RATE_LIMIT"
    except APIConnectionError:
        return "", "", "", "CONNECTION_ERROR"
    except APITimeoutError:
        return "", "", "", "TIMEOUT"
    except Exception as e:
        return "", "", "", f"Error: {str(e)}"

async def process_single_problem(sem, client, idx, row):
    async with sem:
        problem_text = row['problem']
        ground_truth = row['answer']
        problem_results = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            retry_wait = 2
            
            while True:
                reasoning, answer, full_content, error = await get_qwen_response_async(client, problem_text)
                
                if error == "RATE_LIMIT":
                    await asyncio.sleep(retry_wait)
                    retry_wait = min(retry_wait * 2, 60)
                    continue
                elif error in ["CONNECTION_ERROR", "TIMEOUT"]:
                    await asyncio.sleep(5)
                    continue
                elif error:
                    reasoning = f"[API Error] {error}"
                    full_content = f"[API Error] {error}"
                    break
                else:
                    break 

            judge_input = None
            judge_type = "fail"
            
            if not error:
                if answer:
                    judge_input = answer
                    judge_type = "answer_tag"
                else:
                    judge_input = full_content
                    judge_type = "full_content"
            
            if judge_input:
                loop = asyncio.get_running_loop()
                is_correct = await loop.run_in_executor(
                    judge_executor, 
                    run_judge_sync, 
                    judge_input,
                    ground_truth
                )
            else:
                is_correct = False

            record = {
                "id": idx,
                "problem": problem_text,
                "ground_truth": ground_truth,
                "attempt": attempt,
                "qwen_reasoning": reasoning,
                "qwen_answer": answer,
                "judge_input_type": judge_type,
                "is_correct": is_correct,
                "graph_structured_reasoning": full_content,
            }
            problem_results.append(record)

            if is_correct:
                break
        
        return problem_results

def save_incremental_results(all_results, output_base, is_final=False):
    """增量保存结果到 Parquet 文件"""
    if not all_results:
        return
    
    df_res = pd.DataFrame(all_results).sort_values(by=['id', 'attempt'])
    
    all_file = output_base + "_all.parquet"
    print(f"{'[最终保存]' if is_final else '[增量保存]'} 所有记录 ({len(df_res)} 条) -> {all_file}")
    df_res.to_parquet(all_file, index=False)
    
    df_correct = df_res[df_res['is_correct'] == True]
    correct_file = output_base + "_correct.parquet"
    print(f"{'[最终保存]' if is_final else '[增量保存]'} 正确记录 ({len(df_correct)} 条) -> {correct_file}")
    df_correct.to_parquet(correct_file, index=False)

async def process_single_file(input_file, file_index, total_files):
    """处理单个文件"""
    output_base = input_file.replace(".parquet", "_qwen3-max_graph_results")
    
    print("\n" + "="*80)
    print(f"📂 [{file_index}/{total_files}] 开始处理: {os.path.basename(input_file)}")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENCY + 50, max_connections=MAX_CONCURRENCY + 100)
    http_client = httpx.AsyncClient(limits=limits, timeout=REQUEST_TIMEOUT)
    
    client = AsyncOpenAI(api_key=GEN_API_KEY, base_url=GEN_BASE_URL, http_client=http_client)

    try:
        df = pd.read_parquet(input_file)
        print(f"✓ 成功加载，共 {len(df)} 条数据。")
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        await http_client.aclose()
        return

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    
    print(f"🚀 模型: {GEN_MODEL_NAME} | 并发: {MAX_CONCURRENCY} | 增量保存: 每 {SAVE_INTERVAL} 条")
    print("-"*80)

    tasks = [process_single_problem(sem, client, idx, row) for idx, row in df.iterrows()]
    
    start_time = time.time()
    all_results = []
    completed_count = 0
    
    for coro in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc=f"Part {file_index}"):
        result = await coro
        all_results.extend(result)
        completed_count += 1
        
        if completed_count % SAVE_INTERVAL == 0:
            print(f"\n💾 已完成 {completed_count}/{len(df)} 条，触发增量保存...")
            save_incremental_results(all_results, output_base, is_final=False)
    
    elapsed = time.time() - start_time

    if not all_results:
        print("⚠️  没有结果生成。")
        await http_client.aclose()
        return
    
    # 最终保存
    print("\n" + "="*80)
    print("✅ 处理完成，执行最终保存...")
    print("="*80)
    
    df_res = pd.DataFrame(all_results).sort_values(by=['id', 'attempt'])
    
    print(f"正在保存所有记录 ({len(df_res)} 条)...")
    df_res.to_parquet(output_base + "_all.parquet", index=False)
    
    df_correct = df_res[df_res['is_correct'] == True]
    df_correct.to_parquet(output_base + "_correct.parquet", index=False)
    
    # 保存未解决问题
    solved_ids = df_correct['id'].unique()
    all_ids = df.index.tolist()
    unsolved_ids = set(all_ids) - set(solved_ids)
    
    df_unsolved_last_attempts = []
    
    for problem_id in unsolved_ids:
        last_attempt = df_res[
            (df_res['id'] == problem_id) & (df_res['attempt'] == MAX_ATTEMPTS)
        ]
        
        if not last_attempt.empty:
            record = last_attempt.iloc[0]
            original_row = df.loc[problem_id]

            df_unsolved_last_attempts.append({
                "problem_id": problem_id,
                "problem": record['problem'],
                "original_solution": original_row['solution'], 
                "original_answer": original_row['answer'],
                "qwen_last_answer": record['qwen_answer'],
                "qwen_last_reasoning": record['qwen_reasoning'],
                "last_attempt_correct": record['is_correct'], 
                "failure_type": record['graph_structured_reasoning'].split('\n')[0].replace("[API Error] ", "") if isinstance(record['graph_structured_reasoning'], str) else "Unknown"
            })

    if df_unsolved_last_attempts:
        df_unsolved = pd.DataFrame(df_unsolved_last_attempts)
        
        final_cols = ['problem_id', 'problem', 'original_solution', 'original_answer', 'qwen_last_answer', 'failure_type']
        df_unsolved_final = df_unsolved[final_cols].rename(columns={
            'original_solution': 'ground_truth_solution',
            'original_answer': 'ground_truth_answer',
            'qwen_last_answer': 'model_answer_on_failure',
            'failure_type': 'failure_type'
        })
        
        UNSOLVED_FILE = output_base + "_unsolved.parquet"
        print(f"正在保存未解决问题 ({len(df_unsolved_final)} 条) 到 {UNSOLVED_FILE}...")
        df_unsolved_final.to_parquet(UNSOLVED_FILE, index=False)
    else:
        print("🎉 恭喜！所有问题都在尝试次数内解决。")

    # 统计
    uniq_correct = len(df_correct['id'].unique())
    print("-" * 80)
    print(f"⏱️  耗时: {elapsed:.1f}s | 吞吐: {len(df)/elapsed:.2f} TPS")
    print(f"📊 准确率: {uniq_correct}/{len(df)} ({uniq_correct/len(df):.2%})")
    print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    await http_client.aclose()

async def main():
    """主函数：按顺序处理所有文件"""
    total_files = len(INPUT_FILES)
    overall_start = time.time()
    
    print("\n" + "="*80)
    print("🎯 批量处理任务开始")
    print(f"📋 共 {total_files} 个文件待处理")
    print(f"⏰ 总开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    for idx, input_file in enumerate(INPUT_FILES, 1):
        if not os.path.exists(input_file):
            print(f"⚠️  跳过不存在的文件: {input_file}")
            continue
        
        await process_single_file(input_file, idx, total_files)
    
    overall_elapsed = time.time() - overall_start
    
    print("\n" + "="*80)
    print("🎊 所有文件处理完成！")
    print(f"⏱️  总耗时: {overall_elapsed/3600:.2f} 小时")
    print(f"⏰ 总结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    judge_executor.shutdown()

if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except: pass
    asyncio.run(main())