from vllm import LLM, SamplingParams
import json, os
from tqdm import tqdm
from llm_judge import llm_judge_via_api

model_dir = "/ssd5/rxliu/models/output/Qwen3-8B-Olympiads-2000+GSM8K-7200-sft-data-SFT"
test_path = "/ssd5/rxliu/datasets/MATH-500/test.jsonl"
save_path = "/ssd5/rxliu/models/output/Qwen3-8B-Olympiads-2000+GSM8K-7200-sft-data-SFT/MATH-500_results.json"

llm = LLM(model=model_dir, tensor_parallel_size=1,
    max_model_len=4096)
sampling = SamplingParams(temperature=0, max_tokens=512)

judge_api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
judge_key = "sk-8d445207b1ab47efb83069ccc1b845b6"
judge_model = "qwen3-next-80b-a3b-instruct"

correct = 0
total = 0

with open(test_path) as f, open(save_path, "w") as out:
    for line in tqdm(f):
        item = json.loads(line)
        q = item["problem"]
        gt = item["solution"]

        outputs = llm.generate(q, sampling)
        full = outputs[0].outputs[0].text
        print(q)
        print(full)

        if "Final Answer:" in full:
            pred = full.split("Final Answer:")[-1].strip()
        else:
            pred = full.strip()

        is_correct = llm_judge_via_api(pred, gt, judge_api_url, judge_key, judge_model)
        print(is_correct)
        total += 1
        correct += int(is_correct)

        out.write(json.dumps({
            "question": q,
            "ground_truth": gt,
            "prediction": pred,
            "raw_output": full,
            "correct": is_correct
        })+"\n")

print(f"ACC = {correct}/{total} = {correct/total:.4f}")
