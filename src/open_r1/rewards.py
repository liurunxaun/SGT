# coding=utf-8
# Copyright 2025 The HuggingFace Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Reward functions for GRPO training."""

import asyncio
import json
import math
import re
from functools import partial, update_wrapper
from typing import Callable, Dict, Literal, Optional

from latex2sympy2_extended import NormalizationConfig
from math_verify import LatexExtractionConfig, parse, verify

from .utils.code_providers import get_provider
from .utils.competitive_programming import (
    SubtaskResult,
    add_includes,
    get_morph_client_from_env,
    get_piston_client_from_env,
)
from .utils.competitive_programming import patch_code as cf_patch_code
from .utils.competitive_programming import score_submission as cf_score_submission
from .utils.competitive_programming import score_subtask

from rewards_graph import construct_graph_and_score

import concurrent.futures
import re
import json
from typing import Optional
from openai import OpenAI, APIConnectionError, RateLimitError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from math_verify import parse, verify


# accuracy reward llm judge的Prompt
JUDGE_PROMPT_TEMPLATE = """
You are an excellent answer evaluator. I will give you a predicted answer, and the ground truth. And you need to decide wether the predicted answer is right or wrong based on the ground truth.
Input:
    Predicted Answer: {answer}
    Ground Truth: {ground_truth}
Output:
    right or wrong

There are some rules that you need to pay attention:
1. Do not allow any rounding, approximation, or tolerance. For example, 233.5 is wrong if the ground truth is 233.
2. Ignore formatting symbols like LaTeX syntax such as \( \), \\$, etc.
3. The predicted answer may be a sentence rather than just a number. I need you to understand the semantics and determine whether the predicted answer is consistent with the ground truth. 
4. If the predicted answer includes extra explanation or wording like but the numeric value matches, output 'right'.
5. For situations where the predicted answer and the ground truth have the same meaning but different expressions, please mark them as 'right'
6. Your output must be exactly either 'right' or 'wrong', nothing else.

Below are some examples:
1.
Input:
    Predicted Answer: 20.00
    Ground Truth: 20
Output:
    right

2.
Input:
    Predicted Answer: 1563
    Ground Truth: 1,563
Output:
    right

3.
Input:
    Predicted Answer: 2h20min
    Ground Truth: 140min
Output:
    right

4.
Input:
    Predicted Answer: 2$
    Ground Truth: 2.00
Output:
    right

5.
Input:
    Predicted Answer: 150%
    Ground Truth: 150
Output:
    right

6.
Input:
    Predicted Answer: Josh made a profit of $70,000.
    Ground Truth: 70000
Output:
    right
"""

@retry(
    stop=stop_after_attempt(5),               # 最多重试 5 次
    wait=wait_exponential(multiplier=1, min=1, max=10), # 指数退避
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APIError)) # 针对 OpenAI SDK 的异常重试
)
def call_llm_with_retry(query, client, model_name):
    """
    使用 OpenAI SDK 进行调用，融合了你的 Prompt 和重试机制
    """
    answer_parsed, gold_parsed = query
    
    # 填充你的 Prompt
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        answer=answer_parsed, 
        ground_truth=gold_parsed
    )

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0 # 保持 0 温度以获得确定性结果
        )
        
        # 获取结果，并进行清洗
        verdict = completion.choices[0].message.content.strip().lower()
        
        # 兼容性处理：如果模型输出了 "right." (带句号)，也算对
        if "right" in verdict:
            return 1.0
        return 0.0
        
    except Exception as e:
        # 如果是严重的逻辑错误（非网络错误），打印日志并向上抛出以便 tenacity 捕获或外层处理
        # print(f"LLM Call Error: {e}")
        raise e 


def llm_judge_via_api_batch(queries, api_url, api_key, model_name):
    """
    并发批量调用
    """
    # 限制并发数为 3，防止打爆 Aliyun QPS (10/4 = 2.5)
    LIMIT_WORKERS = 3  
    
    # 初始化 OpenAI Client (这是线程安全的，可以在这里初始化一次)
    # 注意：Aliyun 兼容模式下 base_url 应该是 /v1 结尾
    client = OpenAI(
        api_key=api_key,
        base_url=api_url
    )
    
    results_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=LIMIT_WORKERS) as executor:
        # 提交任务
        future_to_idx = {
            executor.submit(call_llm_with_retry, q, client, model_name): i 
            for i, q in enumerate(queries)
        }
        
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                score = future.result()
                results_map[idx] = score
            except Exception as e:
                print(f"Judge failed for item {idx} after retries: {e}")
                results_map[idx] = 0.0
                
    # 按顺序返回
    return [results_map.get(i, 0.0) for i in range(len(queries))]


def accuracy_reward(completions: list[list[dict[str, str]]], solution: list[str], **kwargs) -> list[Optional[float]]:
    """
    最终优化版 Reward 函数：
    1. 正则 (Math-Verify) 优先
    2. LLM Judge 兜底 (使用你的 Prompt + 混合验证)
    """
    # 配置信息 - 注意 base_url 必须以 v1 结尾
    api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key = "sk-8d445207b1ab47efb83069ccc1b845b6"
    judge_model_name = "qwen3-next-80b-a3b-instruct"

    contents = [completion[0]["content"] for completion in completions]
    rewards = [0.0] * len(contents)
    
    to_judge_indices = []  
    to_judge_queries = []  

    for i, (content, sol) in enumerate(zip(contents, solution)):
        gold_parsed = sol 

        match = re.search(r"<answer>([\s\S]*?)</answer>", content)
        if match:
            answer_parsed = match.group(1).strip()
        else:
            rewards[i] = 0.0
            continue
            
        # === 阶段 1: 极速正则验证 ===
        try:
            if verify(parse(answer_parsed), parse(gold_parsed)):
                rewards[i] = 1.0
                continue 
        except Exception:
            pass
        
        # === 阶段 2: 准备 LLM 兜底 ===
        to_judge_indices.append(i)
        to_judge_queries.append((answer_parsed, gold_parsed))

    # === 阶段 3: 并发调用 LLM ===
    if to_judge_indices:
        llm_scores = llm_judge_via_api_batch(to_judge_queries, api_url, api_key, judge_model_name)
        for idx, score in zip(to_judge_indices, llm_scores):
            rewards[idx] = score

    return rewards

def graph_reward(script_args, completions, **kwargs) -> list[Optional[float]]:
    
    # print("caculating graph reward")
    
    rewards = []

    contents = [completion[0]["content"] for completion in completions]
    for content in contents:
        if content is None:
            rewards.append(0.0)
            print("graph reward: content is none")
            continue
        else:
            try:
                reward = float(construct_graph_and_score(content, script_args))
                rewards.append(reward)
            except Exception as e:
                print(f"Error constructing graph and scoring reward: {e}")
                rewards.append(0.0)  # or some default value in case of error
    return rewards


# def accuracy_reward(completions: list[list[dict[str, str]]], solution: list[str], **kwargs) -> list[Optional[float]]:
#     """Reward function that checks if the completion is the same as the ground truth."""
#     contents = [completion[0]["content"] for completion in completions]
#     rewards = []
#     for content, sol in zip(contents, solution):
#         gold_parsed = parse(
#             sol,
#             extraction_mode="first_match",
#         )
#         if len(gold_parsed) != 0:
#             # We require the answer to be provided in correct latex (no malformed operators)
#             answer_parsed = parse(
#                 content,
#                 extraction_config=[
#                     LatexExtractionConfig(
#                         normalization_config=NormalizationConfig(
#                             nits=False,
#                             malformed_operators=False,
#                             basic_latex=True,
#                             equations=True,
#                             boxed="all",
#                             units=True,
#                         ),
#                         # Ensures that boxed is tried first
#                         boxed_match_priority=0,
#                         try_extract_without_anchor=False,
#                     )
#                 ],
#                 extraction_mode="first_match",
#             )
#             # Compute binary rewards if verifiable, `None` otherwise to skip this example
#             try:
#                 reward = float(verify(gold_parsed, answer_parsed))
#             except Exception as e:
#                 print(f"verify failed: {e}, answer: {answer_parsed}, gold: {gold_parsed}")
#                 reward = None
#         else:
#             # If the gold solution is not parseable, we assign `None` to skip this example
#             reward = None
#             print("Failed to parse gold solution: ", sol)
#         rewards.append(reward)

#     return rewards


# def accuracy_reward(completions: list[list[dict[str, str]]], solution: list[str], **kwargs) -> list[Optional[float]]:
#     # api_url
#     api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
#     # api key
#     api_key = "sk-8d445207b1ab47efb83069ccc1b845b6"
#     # 选择LLM Judge的模型
#     judge_model_name = "qwen3-next-80b-a3b-instruct"

#     """Reward function that checks if the completion is the same as the ground truth."""
#     contents = [completion[0]["content"] for completion in completions]
#     rewards = []
#     for content, sol in zip(contents, solution):
#         # 这要求在强化学习之前处理数据集，solution字段就是标准答案
#         gold_parsed = sol

#         if len(gold_parsed) != 0:
#             # We require the answer to be provided in correct latex (no malformed operators)
#             # 用正则提取 <answer>...</answer> 中的内容（包括换行）
#             match = re.search(r"<answer>([\s\S]*?)</answer>", content)
#             if match:
#                 answer_parsed = match.group(1).strip()
#             else:
#                 reward = 0.0
#                 rewards.append(reward)
#                 print("Cannot answer found in the output.")
#                 continue
#             # Compute binary rewards if verifiable, `None` otherwise to skip this example
#             try:
#                 reward = float(llm_judge_via_api(answer_parsed, gold_parsed, api_url, api_key, judge_model_name))
#             except Exception as e:
#                 print(f"verify failed: {e}, answer: {answer_parsed}, gold: {gold_parsed}")
#                 reward = 0.0
#         else:
#             # If the gold solution is not parseable, we assign `None` to skip this example
#             reward = 0.0
#             print("Failed to parse gold solution: ", sol)
        
#         rewards.append(reward)

#     return rewards


# def format_reward(completions, **kwargs):
#     """Reward function that checks if the reasoning process is enclosed within <think> and </think> tags, while the final answer is enclosed within <answer> and </answer> tags."""
#     pattern = r"^<think>\n.*?\n</think>\n<answer>\n.*?\n</answer>$"
#     completion_contents = [completion[0]["content"] for completion in completions]
#     matches = [re.match(pattern, content, re.DOTALL | re.MULTILINE) for content in completion_contents]
#     return [1.0 if match else 0.0 for match in matches]


def format_reward(completions, **kwargs):
    """Reward function that checks if the reasoning process is enclosed within <think> and </think> tags,
    the final answer is enclosed within <answer> and </answer> tags, 
    and at least one of the four reasoning labels (<generate>, <aggregate>, <feedback>, <refine>, <associative thinking>, <reverse thinking>, <known>) 
    appears inside <think>...</think>."""
    
    pattern = (
        r"^<think>.*?"
        r"(<generate>.*?</generate>|<aggregate>.*?</aggregate>|<feedback>.*?</feedback>|<refine>.*?</refine>)|<associative thinking>.*?</associative thinking>|<reverse thinking>.*?</reverse thinking>|<known>.*?</known>"
        r".*?</think>\n<answer>\n.*?\n</answer>$"
    )
    
    completion_contents = [completion[0]["content"] for completion in completions]
    matches = [re.match(pattern, content, re.DOTALL | re.MULTILINE) for content in completion_contents]
    return [1.0 if match else 0.0 for match in matches]


# def tag_count_reward(completions, **kwargs) -> list[float]:
#     """Reward function that checks if we produce the desired number of think and answer tags associated with `format_reward()`.

#     Adapted from: https://gist.github.com/willccbb/4676755236bb08cab5f4e54a0475d6fb#file-grpo_demo-py-L90
#     """
 
#     def count_tags(text: str) -> float:
#         count = 0.0
#         if text.count("<think>\n") == 1:
#             count += 0.25
#         if text.count("\n</think>\n") == 1:
#             count += 0.25
#         if text.count("\n<answer>\n") == 1:
#             count += 0.25
#         if text.count("\n</answer>") == 1:
#             count += 0.25
#         return count

#     contents = [completion[0]["content"] for completion in completions]
#     return [count_tags(c) for c in contents]

def tag_count_reward(completions, **kwargs) -> list[float]:
    """Reward function that checks if we produce the desired number of think and answer tags associated with `format_reward()`.

    Adapted from: https://gist.github.com/willccbb/4676755236bb08cab5f4e54a0475d6fb#file-grpo_demo-py-L90
    """
 
    def count_tags(text: str) -> float:
        count = 0.0
        if text.count("<think>\n") == 1:
            count += 0.20
        if text.count("\n</think>\n") == 1:
            count += 0.20
        if text.count("\n<answer>\n") == 1:
            count += 0.20
        if text.count("\n</answer>") == 1:
            count += 0.20
        if text.count("<generate>") + text.count("</generate>") + text.count("<aggregate>") + text.count("</aggregate>") + text.count("<feedback>") + text.count("</feedback>") + text.count("<refine>") + text.count("</refine>") + text.count("<associative thinking>") + text.count("</associative thinking>") + text.count("<reverse thinking>") + text.count("</reverse thinking>") >= 2:
            count += 0.20
        return count

    contents = [completion[0]["content"] for completion in completions]
    return [count_tags(c) for c in contents]


def reasoning_steps_reward(completions, **kwargs):
    r"""Reward function that checks for clear step-by-step reasoning.
    Regex pattern:
        Step \d+: - matches "Step 1:", "Step 2:", etc.
        ^\d+\. - matches numbered lists like "1.", "2.", etc. at start of line
        \n- - matches bullet points with hyphens
        \n\* - matches bullet points with asterisks
        First,|Second,|Next,|Finally, - matches transition words
    """
    pattern = r"(Step \d+:|^\d+\.|\n-|\n\*|First,|Second,|Next,|Finally,)"
    completion_contents = [completion[0]["content"] for completion in completions]
    matches = [len(re.findall(pattern, content)) for content in completion_contents]

    # Magic number 3 to encourage 3 steps and more, otherwise partial reward
    return [min(1.0, count / 3) for count in matches]


def len_reward(completions: list[Dict[str, str]], solution: list[str], **kwargs) -> float:
    """Compute length-based rewards to discourage overthinking and promote token efficiency.

    Taken from the Kimi 1.5 tech report: https://huggingface.co/papers/2501.12599

    Args:
        completions: List of model completions
        solution: List of ground truth solutions

    Returns:
        List of rewards where:
        - For correct answers: reward = 0.5 - (len - min_len)/(max_len - min_len)
        - For incorrect answers: reward = min(0, 0.5 - (len - min_len)/(max_len - min_len))
    """
    contents = [completion[0]["content"] for completion in completions]

    # First check correctness of answers
    correctness = []
    for content, sol in zip(contents, solution):
        gold_parsed = parse(
            sol,
            extraction_mode="first_match",
            extraction_config=[LatexExtractionConfig()],
        )
        if len(gold_parsed) == 0:
            # Skip unparseable examples
            correctness.append(True)  # Treat as correct to avoid penalizing
            print("Failed to parse gold solution: ", sol)
            continue

        answer_parsed = parse(
            content,
            extraction_config=[
                LatexExtractionConfig(
                    normalization_config=NormalizationConfig(
                        nits=False,
                        malformed_operators=False,
                        basic_latex=True,
                        equations=True,
                        boxed=True,
                        units=True,
                    ),
                    boxed_match_priority=0,
                    try_extract_without_anchor=False,
                )
            ],
            extraction_mode="first_match",
        )
        correctness.append(verify(answer_parsed, gold_parsed))

    # Calculate lengths
    lengths = [len(content) for content in contents]
    min_len = min(lengths)
    max_len = max(lengths)

    # If all responses have the same length, return zero rewards
    if max_len == min_len:
        return [0.0] * len(completions)

    rewards = []
    for length, is_correct in zip(lengths, correctness):
        lambda_val = 0.5 - (length - min_len) / (max_len - min_len)

        if is_correct:
            reward = lambda_val
        else:
            reward = min(0, lambda_val)

        rewards.append(float(reward))

    return rewards


def get_cosine_scaled_reward(
    min_value_wrong: float = -1.0,
    max_value_wrong: float = -0.5,
    min_value_correct: float = 0.5,
    max_value_correct: float = 1.0,
    max_len: int = 1000,
):
    def cosine_scaled_reward(completions, solution, **kwargs):
        """Reward function that scales based on completion length using a cosine schedule.

        Shorter correct solutions are rewarded more than longer ones.
        Longer incorrect solutions are penalized less than shorter ones.

        Args:
            completions: List of model completions
            solution: List of ground truth solutions

        This function is parameterized by the following arguments:
            min_value_wrong: Minimum reward for wrong answers
            max_value_wrong: Maximum reward for wrong answers
            min_value_correct: Minimum reward for correct answers
            max_value_correct: Maximum reward for correct answers
            max_len: Maximum length for scaling
        """
        contents = [completion[0]["content"] for completion in completions]
        rewards = []

        for content, sol in zip(contents, solution):
            gold_parsed = parse(
                sol,
                extraction_mode="first_match",
                extraction_config=[LatexExtractionConfig()],
            )
            if len(gold_parsed) == 0:
                rewards.append(1.0)  # Skip unparseable examples
                print("Failed to parse gold solution: ", sol)
                continue

            answer_parsed = parse(
                content,
                extraction_config=[
                    LatexExtractionConfig(
                        normalization_config=NormalizationConfig(
                            nits=False,
                            malformed_operators=False,
                            basic_latex=True,
                            equations=True,
                            boxed=True,
                            units=True,
                        ),
                        boxed_match_priority=0,
                        try_extract_without_anchor=False,
                    )
                ],
                extraction_mode="first_match",
            )

            is_correct = verify(answer_parsed, gold_parsed)
            gen_len = len(content)

            # Apply cosine scaling based on length
            progress = gen_len / max_len
            cosine = math.cos(progress * math.pi)

            if is_correct:
                min_value = min_value_correct
                max_value = max_value_correct
            else:
                # Swap min/max for incorrect answers
                min_value = max_value_wrong
                max_value = min_value_wrong

            reward = min_value + 0.5 * (max_value - min_value) * (1.0 + cosine)
            rewards.append(float(reward))

        return rewards

    return cosine_scaled_reward


def get_repetition_penalty_reward(ngram_size: int, max_penalty: float, language: str = "en"):
    """
    Computes N-gram repetition penalty as described in Appendix C.2 of https://huggingface.co/papers/2502.03373.
    Reference implementation from: https://github.com/eddycmu/demystify-long-cot/blob/release/openrlhf/openrlhf/reward/repetition.py

    Args:
    ngram_size: size of the n-grams
    max_penalty: Maximum (negative) penalty for wrong answers
    language: Language of the text, defaults to `en`. Used to choose the way to split the text into n-grams.
    """
    if max_penalty > 0:
        raise ValueError(f"max_penalty {max_penalty} should not be positive")

    if language == "en":

        def zipngram(text: str, ngram_size: int):
            words = text.lower().split()
            return zip(*[words[i:] for i in range(ngram_size)]), words

    elif language == "zh":
        from transformers.utils.import_utils import _is_package_available

        if not _is_package_available("jieba"):
            raise ValueError("Please install jieba to use Chinese language")

        def zipngram(text: str, ngram_size: int):
            import jieba

            seg_list = list(jieba.cut(text))
            return zip(*[seg_list[i:] for i in range(ngram_size)]), seg_list

    else:
        raise ValueError(
            f"Word splitting for language `{language}` is not yet implemented. Please implement your own zip-ngram function."
        )

    def repetition_penalty_reward(completions, **kwargs) -> float:
        """
        reward function the penalizes repetitions
        ref implementation: https://github.com/eddycmu/demystify-long-cot/blob/release/openrlhf/openrlhf/reward/repetition.py

        Args:
            completions: List of model completions
        """

        contents = [completion[0]["content"] for completion in completions]
        rewards = []
        for completion in contents:
            if completion == "":
                rewards.append(0.0)
                continue

            ngrams = set()
            total = 0
            ngram_array, words = zipngram(completion, ngram_size)

            if len(words) < ngram_size:
                rewards.append(0.0)
                continue

            for ng in ngram_array:
                ngrams.add(ng)
                total += 1

            scaling = 1 - len(ngrams) / total
            reward = scaling * max_penalty
            rewards.append(reward)
        return rewards

    return repetition_penalty_reward


def _init_event_loop():
    """Initialize or get the current event loop."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def ioi_code_reward(completions, test_batch_size: int = 1, provider_type: str = "piston", **kwargs) -> list[float]:
    """Reward function that evaluates IOI problems using a specified execution client.

    Assumes the dataset has the same format as hf.co/datasets/open-r1/ioi

    Args:
        completions: List of model completions to evaluate
        test_batch_size: Evaluate these many test cases in parallel, then check if any of them failed (0 score):
                       if so stop evaluating; otherwise continue with the next batch of test cases.
        provider_type: The execution provider to use (default: "piston"). Supported values: "piston", "morph"
        **kwargs: Additional arguments passed from the dataset
    """
    # Get the appropriate client based on provider_type
    if provider_type == "morph":
        execution_client = get_morph_client_from_env()
    else:
        # for info on setting up piston workers, see slurm/piston/README.md
        execution_client = get_piston_client_from_env()

    code_snippets = [
        # note: grading is automatically skipped if no code is extracted
        add_includes(extract_code(completion[-1]["content"], "cpp"), problem_id)
        for completion, problem_id in zip(completions, kwargs["id"])
    ]

    async def run_catch_exceptions(task):
        try:
            return await task
        except Exception as e:
            print(f"Error from {provider_type} worker: {e}")
            return SubtaskResult()

    problems_data = [dict(zip(kwargs.keys(), values)) for values in zip(*kwargs.values())]

    loop = _init_event_loop()
    evals = [
        loop.create_task(
            run_catch_exceptions(
                score_subtask(
                    execution_client,
                    problem_data,
                    code,
                    test_batch_size=test_batch_size,
                )
            )
        )
        for problem_data, code in zip(problems_data, code_snippets)
    ]
    results = loop.run_until_complete(asyncio.gather(*evals))

    return [result.score for result in results]


def cf_code_reward(
    completions,
    test_batch_size: int = 1,
    patch_code: bool = False,
    scoring_mode: Literal["pass_fail", "partial", "weighted_sum"] = "weighted_sum",
    **kwargs,
) -> list[float]:
    """Reward function that evaluates Codeforces problems using Piston+our CF package.

    Assumes the dataset has the same format as hf.co/datasets/open-r1/codeforces (verifiable-prompts subset)

    test_batch_size: evaluate these many test cases in parallel, then check if any of them failed (0 score): if so stop evaluating; otherwise continue with the next batch of test cases.
    """
    # for info on setting up piston workers, see slurm/piston/README.md
    piston_client = get_piston_client_from_env()

    languages = kwargs["language"] if "language" in kwargs else [None] * len(completions)
    code_snippets = [
        # note: grading is automatically skipped if a problem has no tests
        cf_patch_code(extract_code(completion[-1]["content"], language), language)
        if patch_code
        else extract_code(completion[-1]["content"], language)
        for completion, language in zip(completions, languages)
    ]

    async def run_catch_exceptions(task):
        try:
            return await task
        except Exception as e:
            print(f"Error from Piston worker: {e}")
            return None

    # load problem data. undo separating kwargs by column
    problems_data = [dict(zip(kwargs.keys(), values)) for values in zip(*kwargs.values())]

    loop = _init_event_loop()
    evals = [
        loop.create_task(
            run_catch_exceptions(
                cf_score_submission(
                    piston_client,
                    problem_data,
                    code,
                    test_batch_size=test_batch_size,
                    scoring_mode=scoring_mode,
                    submission_language=problem_data.get("language", None),
                )
            )
        )
        for problem_data, code in zip(problems_data, code_snippets)
    ]
    results = loop.run_until_complete(asyncio.gather(*evals))

    return results


def extract_code(completion: str, language: str | None = "python") -> str:
    if language is None:
        return ""
    pattern = re.compile(rf"```{language}\n(.*?)```", re.DOTALL)
    matches = pattern.findall(completion)
    extracted_answer = matches[-1] if len(matches) >= 1 else ""
    return extracted_answer


def binary_code_reward(
    completions,
    num_parallel: int = 2,
    provider_type: str = "e2b",
    enforce_same_language: bool = False,
    **kwargs,
) -> list[float]:
    rewards = code_reward(
        completions,
        num_parallel=num_parallel,
        provider_type=provider_type,
        enforce_same_language=enforce_same_language,
        **kwargs,
    )
    BINARY_THRESHOLD = 0.99

    output = []
    for reward in rewards:
        if reward is None:
            output.append(None)
        else:
            output.append(1.0 if reward > BINARY_THRESHOLD else 0.0)

    return output


def code_reward(
    completions,
    num_parallel: int = 2,
    provider_type: str = "e2b",
    enforce_same_language: bool = False,
    **kwargs,
) -> list[float]:
    """Reward function that evaluates code snippets using a code execution provider.

    Assumes the dataset contains a `verification_info` column with test cases.

    Args:
        completions: List of model completions to evaluate
        num_parallel: Number of parallel code executions (default: 2)
        provider_type: Which code execution provider to use (default: "e2b")
        enforce_same_language: If True, verify all problems use the same language (default: False)
        **kwargs: Additional arguments passed to the verification
    """
    evaluation_script_template = """
    import subprocess
    import json

    def evaluate_code(code, test_cases):
        passed = 0
        total = len(test_cases)
        exec_timeout = 5

        for case in test_cases:
            process = subprocess.run(
                ["python3", "-c", code],
                input=case["input"],
                text=True,
                capture_output=True,
                timeout=exec_timeout
            )

            if process.returncode != 0:  # Error in execution
                continue

            output = process.stdout.strip()

            # TODO: implement a proper validator to compare against ground truth. For now we just check for exact string match on each line of stdout.
            all_correct = True
            for line1, line2 in zip(output.split('\\n'), case['output'].split('\\n')):
                all_correct = all_correct and line1.strip() == line2.strip()

            if all_correct:
                passed += 1

        success_rate = (passed / total)
        return success_rate

    code_snippet = {code}
    test_cases = json.loads({test_cases})

    evaluate_code(code_snippet, test_cases)
    """

    code_snippets = [extract_code(completion[-1]["content"]) for completion in completions]
    verification_info = kwargs["verification_info"]

    template = evaluation_script_template

    scripts = [
        template.format(code=json.dumps(code), test_cases=json.dumps(json.dumps(info["test_cases"])))
        for code, info in zip(code_snippets, verification_info)
    ]

    language = verification_info[0]["language"]

    if enforce_same_language:
        all_same_language = all(v["language"] == language for v in verification_info)
        if not all_same_language:
            raise ValueError("All verification_info must have the same language", verification_info)

    execution_provider = get_provider(
        provider_type=provider_type,
        num_parallel=num_parallel,
        **kwargs,
    )

    return execution_provider.execute_scripts(scripts, ["python"] * len(scripts))


def get_code_format_reward(language: str = "python"):
    """Format reward function specifically for code responses.

    Args:
        language: Programming language supported by E2B https://e2b.dev/docs/code-interpreting/supported-languages
    """

    def code_format_reward(completions, **kwargs):
        # if there is a language field, use it instead of the default language. This way we can have mixed language training.
        languages = kwargs["language"] if "language" in kwargs else [language] * len(completions)

        completion_contents = [completion[0]["content"] for completion in completions]
        matches = [
            re.match(
                rf"^<think>\n.*?\n</think>\n<answer>\n.*?```{sample_language}.*?```.*?\n</answer>$",
                content,
                re.DOTALL | re.MULTILINE,
            )
            for content, sample_language in zip(completion_contents, languages)
        ]
        return [1.0 if match else 0.0 for match in matches]

    return code_format_reward


def get_soft_overlong_punishment(max_completion_len, soft_punish_cache):
    """
    Reward function that penalizes overlong completions. It is used to penalize overlong completions,
    but not to reward shorter completions. Reference: Eq. (13) from the DAPO paper (https://huggingface.co/papers/2503.14476)

    Args:
        max_completion_len: Maximum length of the completion
        soft_punish_cache: Minimum length of the completion. If set to 0, no minimum length is applied.
    """

    def soft_overlong_punishment_reward(completion_ids: list[list[int]], **kwargs) -> list[float]:
        """Reward function that penalizes overlong completions."""
        rewards = []
        for ids in completion_ids:
            completion_length = len(ids)
            if completion_length <= max_completion_len - soft_punish_cache:
                rewards.append(0.0)
            elif max_completion_len - soft_punish_cache < completion_length <= max_completion_len:
                rewards.append((max_completion_len - soft_punish_cache - completion_length) / soft_punish_cache)
            else:
                rewards.append(-1.0)
        return rewards

    return soft_overlong_punishment_reward


def get_reward_funcs(script_args) -> list[Callable]:
    REWARD_FUNCS_REGISTRY = {
        "graph": update_wrapper(
            partial(graph_reward, script_args=script_args),
            graph_reward,
        ),
        "accuracy": accuracy_reward,
        "format": format_reward,
        "reasoning_steps": reasoning_steps_reward,
        "cosine": get_cosine_scaled_reward(
            min_value_wrong=script_args.cosine_min_value_wrong,
            max_value_wrong=script_args.cosine_max_value_wrong,
            min_value_correct=script_args.cosine_min_value_correct,
            max_value_correct=script_args.cosine_max_value_correct,
            max_len=script_args.cosine_max_len,
        ),
        "repetition_penalty": get_repetition_penalty_reward(
            ngram_size=script_args.repetition_n_grams,
            max_penalty=script_args.repetition_max_penalty,
        ),
        "length": len_reward,
        "code": update_wrapper(
            partial(
                code_reward,
                num_parallel=script_args.parallel_code_exec_per_proc,
                provider_type=script_args.code_provider,
                enforce_same_language=getattr(script_args, "enforce_same_language", False),
            ),
            code_reward,
        ),
        "binary_code": update_wrapper(
            partial(
                binary_code_reward,
                num_parallel=script_args.parallel_code_exec_per_proc,
                provider_type=script_args.code_provider,
                enforce_same_language=getattr(script_args, "enforce_same_language", False),
            ),
            binary_code_reward,
        ),
        "ioi_code": update_wrapper(
            partial(
                ioi_code_reward,
                test_batch_size=script_args.code_eval_test_batch_size,
                provider_type=getattr(script_args, "ioi_provider", "piston"),
            ),
            ioi_code_reward,
        ),
        "cf_code": update_wrapper(
            partial(
                cf_code_reward,
                test_batch_size=script_args.code_eval_test_batch_size,
                scoring_mode=script_args.code_eval_scoring_mode,
            ),
            cf_code_reward,
        ),
        "code_format": get_code_format_reward(language=script_args.code_language),
        "tag_count": tag_count_reward,
        "soft_overlong_punishment": get_soft_overlong_punishment(
            max_completion_len=script_args.max_completion_len,
            soft_punish_cache=script_args.soft_punish_cache,
        ),
    }
    reward_funcs = [REWARD_FUNCS_REGISTRY[func] for func in script_args.reward_funcs]

    return reward_funcs