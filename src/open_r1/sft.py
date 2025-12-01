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

"""
Supervised fine-tuning script for decoder language models.

Usage:

# One 1 node of 8 x H100s
export PYTHONPATH=~/rxliu/projects/open-r1-main/src:$PYTHONPATH
unset http_proxy
unset https_proxy
unset HTTP_PROXY
unset HTTPS_PROXY
unset all_proxy
unset ALL_PROXY
accelerate launch \
    --config_file=recipes/accelerate_configs/zero2.yaml \
    src/open_r1/sft.py \
    --model_name_or_path /ssd5/rxliu/models/Qwen3-8B \
    --dataset_name /ssd5/rxliu/datasets/SFT-Data/All-data-parquet \
    --dataset_config default \
    --learning_rate 3.0e-5 \
    --num_train_epochs 5 \
    --max_seq_length 8192 \
    --per_device_train_batch_size 8 \
    --gradient_checkpointing \
    --bf16 \
    --use_liger_kernel \
    --report_to wandb \
    --run_name Qwen3-8B-Math-SFT-Epoch5 \
    --logging_steps 1 \
    --output_dir /ssd5/rxliu/models/output/Qwen3-8B-all-data-sft-last-SFT \
    --eval_strategy epoch \
    --per_device_eval_batch_size 4

    accelerate launch \
    --config_file=recipes/accelerate_configs/zero2.yaml \
    src/open_r1/sft.py \
    --model_name_or_path /ssd5/rxliu/models/Qwen3-4B \
    --dataset_name /ssd5/rxliu/datasets/SFT-Data/All-data-parquet \
    --dataset_config default \
    --learning_rate 3.0e-5 \
    --num_train_epochs 5 \
    --max_seq_length 8192 \
    --per_device_train_batch_size 4 \
    --gradient_accumulation_steps 2 \
    --gradient_checkpointing \
    --bf16 \
    --packing \
    --use_liger_kernel \
    --report_to wandb \
    --run_name Qwen3-4B-Math-SFT-Packed \
    --logging_steps 1 \
    --output_dir /ssd5/rxliu/models/output/Qwen3-4B-all-data-SFT \
    --eval_strategy epoch \
    --per_device_eval_batch_size 1
"""

import logging
import os
import sys

import datasets
import transformers
from transformers import set_seed
from transformers.trainer_utils import get_last_checkpoint

from open_r1.configs import ScriptArguments, SFTConfig
from open_r1.utils import get_dataset, get_model, get_tokenizer
from open_r1.utils.callbacks import get_callbacks
from open_r1.utils.wandb_logging import init_wandb_training
from trl import ModelConfig, SFTTrainer, TrlParser, get_peft_config, setup_chat_format

# os.environ["WANDB_API_KEY"] = '7b5e421309a7f263058faebac5cb0bc4e74608f2'
# os.environ["WANDB_PROJECT"] = "2026ACL-Qwen3-4b-SFT-all-data-last"
os.environ["WANDB_PROJECT"] = "qwen3-8B-SFT-all-data-1201-2017"
logger = logging.getLogger(__name__)


def main(script_args, training_args, model_args):
    set_seed(training_args.seed)

    ###############
    # Setup logging
    ###############
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    log_level = training_args.get_process_log_level()
    logger.setLevel(log_level)
    datasets.utils.logging.set_verbosity(log_level)
    transformers.utils.logging.set_verbosity(log_level)
    transformers.utils.logging.enable_default_handler()
    transformers.utils.logging.enable_explicit_format()

    logger.info(f"Model parameters {model_args}")
    logger.info(f"Script parameters {script_args}")
    logger.info(f"Training parameters {training_args}")

    # Check for last checkpoint
    last_checkpoint = None
    if os.path.isdir(training_args.output_dir):
        last_checkpoint = get_last_checkpoint(training_args.output_dir)
    if last_checkpoint is not None and training_args.resume_from_checkpoint is None:
        logger.info(f"Checkpoint detected, resuming training at {last_checkpoint=}.")

    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    os.environ["WANDB_NAME"] = training_args.run_name + "-" + str(local_rank)
    # if local_rank == 0:
    #     # 主进程：如果有 wandb 就初始化
    #     if "wandb" in training_args.report_to:
    #         init_wandb_training(training_args)
            
    # else:
    #     # 非主进程：强制移除 "wandb"，防止 Trainer 内部再次初始化
    #     if "wandb" in training_args.report_to:
    #         training_args.report_to = [b for b in training_args.report_to if b != "wandb"]

    ######################################
    # Load dataset, tokenizer, and model #
    ######################################
    dataset = get_dataset(script_args)
    tokenizer = get_tokenizer(model_args, training_args)
    model = get_model(model_args, training_args)

    if tokenizer.chat_template is None:
        logger.info("No chat template provided, defaulting to ChatML.")
        model, tokenizer = setup_chat_format(model, tokenizer, format="chatml")

    ############################
    # Initialize the SFT Trainer
    ############################
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset[script_args.dataset_train_split],
        eval_dataset=(dataset[script_args.dataset_test_split] if training_args.eval_strategy != "no" else None),
        processing_class=tokenizer,
        peft_config=get_peft_config(model_args),
        callbacks=get_callbacks(training_args, model_args),
    )

    ###############
    # Training loop
    ###############
    logger.info("*** Train ***")
    checkpoint = None
    if training_args.resume_from_checkpoint is not None:
        checkpoint = training_args.resume_from_checkpoint
    elif last_checkpoint is not None:
        checkpoint = last_checkpoint
    train_result = trainer.train(resume_from_checkpoint=checkpoint)
    metrics = train_result.metrics
    metrics["train_samples"] = len(dataset[script_args.dataset_train_split])
    trainer.log_metrics("train", metrics)
    trainer.save_metrics("train", metrics)
    trainer.save_state()

    ##################################
    # Save model and create model card
    ##################################
    logger.info("*** Save model ***")
    # Align the model's generation config with the tokenizer's eos token
    # to avoid unbounded generation in the transformers `pipeline()` function
    trainer.model.generation_config.eos_token_id = tokenizer.eos_token_id
    trainer.save_model(training_args.output_dir)
    logger.info(f"Model saved to {training_args.output_dir}")

    # Save everything else on main process
    kwargs = {
        "dataset_name": script_args.dataset_name,
        "tags": ["open-r1"],
    }
    if trainer.accelerator.is_main_process:
        trainer.create_model_card(**kwargs)
        # Restore k,v cache for fast inference
        trainer.model.config.use_cache = True
        trainer.model.config.save_pretrained(training_args.output_dir)

    ##########
    # Evaluate
    ##########
    if training_args.do_eval:
        logger.info("*** Evaluate ***")
        metrics = trainer.evaluate()
        metrics["eval_samples"] = len(dataset[script_args.dataset_test_split])
        trainer.log_metrics("eval", metrics)
        trainer.save_metrics("eval", metrics)

    #############
    # push to hub
    #############
    if training_args.push_to_hub:
        logger.info("Pushing to hub...")
        trainer.push_to_hub(**kwargs)


if __name__ == "__main__":
    parser = TrlParser((ScriptArguments, SFTConfig, ModelConfig))
    script_args, training_args, model_args = parser.parse_args_and_config()
    main(script_args, training_args, model_args)
