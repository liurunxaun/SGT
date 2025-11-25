from datasets import load_dataset
import os

OUT_DIR = "evalplus_data"
os.makedirs(OUT_DIR, exist_ok=True)

print(">>> Downloading HumanEval+ ...")
human = load_dataset("evalplus/humanevalplus")

save_path = os.path.join(OUT_DIR, "humanevalplus")
human.save_to_disk(save_path)
print(f">>> Saved HumanEval+ to {save_path}")
