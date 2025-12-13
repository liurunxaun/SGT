import re, ast, json, sys, subprocess, tempfile, multiprocessing


# ============================================================
# Part 1: 代码执行与部分分 (Multiprocessing Safe)
# ============================================================

def _parse_kodcode_test(test_obj):
    """
    判定 KodCode test 形式：
    - pytest/assert 脚本：返回 ("pytest", test_script_str)
    - stdio 字典/字典字符串：返回 ("stdio", {"stdin":[...], "stdout":[...]})
    """
    # 已经是 dict 且有 stdin/stdout
    if isinstance(test_obj, dict) and "stdin" in test_obj and "stdout" in test_obj:
        return "stdio", test_obj

    # 是字符串：可能是 pytest 脚本，也可能是 "{'stdin':..., 'stdout':...}" 的字典字符串
    if isinstance(test_obj, str):
        s = test_obj.strip()

        # 尝试识别 stdio 的字典字符串
        if s.startswith("{") and (("'stdin'" in s) or ('"stdin"' in s)) and (("'stdout'" in s) or ('"stdout"' in s)):
            try:
                d = ast.literal_eval(s)  # 兼容单引号 dict 字符串（安全）
            except Exception:
                try:
                    d = json.loads(s)     # 兼容 JSON
                except Exception:
                    d = None

            if isinstance(d, dict) and "stdin" in d and "stdout" in d:
                return "stdio", d

        # 否则当 pytest/assert 脚本
        return "pytest", test_obj

    return "none", None


def _run_pytest_like(code: str, test_script: str) -> float:
    env = {}

    # 清洗测试脚本：去掉 from solution import ...
    test_script_clean = re.sub(
        r"^from solution import .*$", "", test_script, flags=re.MULTILINE
    )
    # 有些脚本还会写 solution.xxx，顺手去掉
    test_script_clean = re.sub(r"\bsolution\.", "", test_script_clean)

    exec(code, env, env)
    exec(test_script_clean, env, env)

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
                tf()
                passed_count += 1
            except Exception:
                pass
    else:
        # 兼容：脚本里直接 assert
        total_tests = 1
        passed_count = 1

    return passed_count / total_tests if total_tests > 0 else 0.0


def _normalize_out(s: str) -> str:
    # 忽略末尾空白/多余换行，适配 OJ 常见判题
    return "\n".join(line.rstrip() for line in s.strip().splitlines()).strip()


def _run_stdio_like(code: str, io_dict: dict, per_case_timeout: float = 2.0) -> float:
    ins = io_dict.get("stdin", [])
    outs = io_dict.get("stdout", [])
    total = min(len(ins), len(outs))
    if total == 0:
        return 0.0

    passed = 0

    # 写临时文件执行（更稳）
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    for i in range(total):
        try:
            proc = subprocess.run(
                [sys.executable, path],
                input=ins[i],
                text=True,
                capture_output=True,
                timeout=per_case_timeout,
            )
            pred = _normalize_out(proc.stdout)
            gold = _normalize_out(str(outs[i]))

            if proc.returncode == 0 and pred == gold:
                passed += 1
        except Exception:
            pass

    return passed / total


def _worker_exec(code, test_obj, return_dict, per_case_timeout=2.0):
    """
    独立进程中的测试执行器：同时支持
    - pytest/assert 脚本
    - stdio (stdin/stdout) 字典
    """
    try:
        kind, parsed = _parse_kodcode_test(test_obj)
        if kind == "pytest":
            return_dict["score"] = _run_pytest_like(code, parsed)
        elif kind == "stdio":
            return_dict["score"] = _run_stdio_like(code, parsed, per_case_timeout=per_case_timeout)
        else:
            return_dict["score"] = 0.0
    except Exception:
        return_dict["score"] = 0.0


def execute_kodcode_safe(code_snippet, test_obj, timeout=4.0, per_case_timeout=2.0):
    """
    多进程安全入口：在独立进程里跑用户代码 + 测试，防止死循环/阻塞。
    timeout: 整体超时
    per_case_timeout: stdio 每个用例的超时
    """
    manager = multiprocessing.Manager()
    return_dict = manager.dict(score=0.0)

    p = multiprocessing.Process(
        target=_worker_exec,
        args=(code_snippet, test_obj, return_dict, per_case_timeout),
    )
    p.start()
    p.join(timeout)

    if p.is_alive():
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
