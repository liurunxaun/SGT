import re
import multiprocessing

# ============================================================
# Part 1: 代码执行与部分分 (Multiprocessing Safe)
# ============================================================

def _worker_exec(code, test_script, return_dict):
    """
    独立进程中的测试执行器，支持部分分 (Partial Credit)
    """
    try:
        # 用一个 env 同时作为 globals / locals
        env = {}

        # 1. 清洗测试脚本 (比如去掉 KodCode 里的 `from solution import ...` 之类)
        test_script_clean = re.sub(
            r"^from solution import .*$", "", test_script, flags=re.MULTILINE
        )

        # 2. 执行用户代码（定义 increment_list / sortStack 等函数）
        exec(code, env, env)

        # 3. 执行测试定义（定义 test_xxx，并调用上面的函数）
        exec(test_script_clean, env, env)

        # 4. 查找并运行测试用例
        # 策略：优先找 test_ 开头的函数，如果没有，则认为脚本全是 assert
        test_funcs = [
            v for k, v in env.items()
            if k.startswith("test_") and callable(v)
        ]

        passed_count = 0
        total_tests = 0

        if test_funcs:
            total_tests = len(test_funcs)
            for tf in test_funcs:
                try:
                    tf()   # 运行单个测试函数
                    passed_count += 1
                except Exception:
                    # 某个测试挂了就算这个用例没通过，但继续下一个
                    pass
        else:
            # 兼容「直接在脚本里写 assert」的情况：
            # 能跑到这里说明所有 assert 都没炸，就直接给 1 分。
            total_tests = 1
            passed_count = 1

        if total_tests > 0:
            return_dict["score"] = passed_count / total_tests
        else:
            return_dict["score"] = 0.0

    except Exception:
        # 语法错误 / 运行时错误
        return_dict["score"] = 0.0


def execute_kodcode_safe(code_snippet, test_script, timeout=2.0):
    """
    多进程安全入口：在独立进程里跑用户代码 + 测试，防止死循环/阻塞。
    """
    manager = multiprocessing.Manager()
    return_dict = manager.dict()
    return_dict["score"] = 0.0

    p = multiprocessing.Process(
        target=_worker_exec,
        args=(code_snippet, test_script, return_dict),
    )
    p.start()
    p.join(timeout)

    if p.is_alive():
        # 超时，杀掉子进程
        p.terminate()
        p.join()
        return 0.0

    return float(return_dict["score"])


# ============================================================
# Part 2: 代码块提取
# ============================================================

def extract_code_block(text):
    """从模型输出中提取 Markdown 代码块"""
    # 优先匹配 ```python
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1)

    # 降级匹配任意 ``` ... ```
    match = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1)

    return ""

def extract_code_from_answer(text: str) -> str:
    """
    从完整模型输出中抽取要执行的 Python 代码：
    1) 截取 <answer>...</answer> 之间的内容
    2) 去掉首尾空白后直接作为源码返回
    """
    if not isinstance(text, str):
        return ""

    m = re.search(r"<answer>\s*(.*?)\s*</answer>", text,
                  flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return ""

    code = m.group(1)
    return code.strip()
# ============================================================
# Part 3: OpenR1 / TRL 奖励入口（Code-only）
# ============================================================

def code_graph_reward_func(completions, **kwargs):
    """
    OpenR1 / TRL 自定义 Reward 函数入口
    现在是 **纯代码正确性 reward**，不再使用 graph reward。
    """
    print("[Config] Code Reward Only (Graph OFF)")

    # 获取测试用例 (兼容 'test' 和 'test_case' 两种列名)
    test_scripts = kwargs.get("test", [])
    if not test_scripts:
        test_scripts = kwargs.get("test_case", [])

    if not test_scripts:
        test_scripts = [""] * len(completions)
    else:
        test_scripts = list(test_scripts)
        n_comp = len(completions)
        n_test = len(test_scripts)

        if n_test == n_comp:
            # 正好一一对应，什么都不用做
            pass
        elif n_test > 0 and n_comp % n_test == 0:
            # 假设 GRPO 没有帮你展开，这里按 group 复制
            repeat = n_comp // n_test
            test_scripts = [
                ts for ts in test_scripts for _ in range(repeat)
            ]
        else:
            # 实在对不上，就退回你之前的“补空/截断”策略
            if n_test < n_comp:
                test_scripts += [""] * (n_comp - n_test)
            elif n_test > n_comp:
                test_scripts = test_scripts[:n_comp]

    # Debug 看看 kwargs 里都有啥
    print(f"[Debug] kwargs keys: {list(kwargs.keys())}")

    rewards = []

    # ✅ 正确遍历方式：enumerate + zip（两路）
    for i, (completion, test_script) in enumerate(zip(completions, test_scripts)):
        # 兼容 chat 格式 [{"role":...}] 和纯文本
        content = completion[-1]["content"] if isinstance(completion, list) else completion

        # --- 1. 提取代码块 ---
        code_block = extract_code_from_answer(content)
        code_score = 0.0
        if code_block:
            code_score = execute_kodcode_safe(code_block, test_script)

        # 现在 total_reward 就等于 code_score，本质上就是 pass 率
        total_reward = code_score
        rewards.append(total_reward)

        # Debug：只打印前 0~100 条样本
        # if i < 5:  # 只看前 5 个样本，避免刷屏
        #     print("\n" + "=" * 50)
        #     print(f"[Reward Debug] Sample #{i}")
        #     print(f"  Total: {total_reward:.4f}")
        #     print(f"  Code Score: {code_score} (Block found: {bool(code_block)})")
           

        #     print("\n  --- Test Script Preview ---")
        #     print(test_script[:300])

        #     if code_block:
        #         print("\n  --- Extracted Code Block ---")
        #         print(code_block[:600])
        #     else:
        #         print("\n  --- No Code Block, Raw Content Preview ---")
        #         print(content[:400])
        #     print("=" * 50 + "\n")
    return rewards
