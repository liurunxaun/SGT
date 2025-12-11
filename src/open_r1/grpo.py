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

import os
import sys
import logging

sys.path.append("/data/home/the/rxliu/projects/open-r1-main/src")

import datasets
import transformers
from transformers import set_seed
from transformers.trainer_utils import get_last_checkpoint

from open_r1.configs import GRPOConfig, GRPOScriptArguments
from open_r1.rewards import get_reward_funcs
from open_r1.utils import get_dataset, get_model, get_tokenizer
from open_r1.utils.callbacks import get_callbacks
from open_r1.utils.wandb_logging import init_wandb_training
from trl import GRPOTrainer, ModelConfig, TrlParser, get_peft_config


# 为了在evaluate时强制一条数据只采样一次，自定义一个GRPOTrainer类
class GRPOCustomTrainer(GRPOTrainer):
    def evaluate(self, eval_dataset=None, ignore_keys=None, metric_key_prefix="eval"):
        # 1. 保存训练时的设置 (比如 12)
        original_generations = self.num_generations

        # 2. 强制改为 1，让评估只生成一条
        #    这会同时影响 Sampler(采样器) 和 vLLM Generation(生成数量)
        self.num_generations = 1

        # 3. 清空 DataLoader 缓存！
        #    如果不清空，Trainer 可能会直接复用之前包含 "重复12次" 逻辑的旧 DataLoader
        if hasattr(self, "_eval_dataloaders"):
            self._eval_dataloaders = {}

        try:
            # 4. 执行正常的评估流程
            return super().evaluate(eval_dataset, ignore_keys, metric_key_prefix)
        finally:
            # 5. 【关键】恢复现场，确保不影响后续训练
            self.num_generations = original_generations

            # 再次清空缓存，确保下次训练或评估重新构建正确的 Sampler
            if hasattr(self, "_eval_dataloaders"):
                self._eval_dataloaders = {}


logger = logging.getLogger(__name__)


def main(script_args, training_args, model_args):
    # Set seed for reproducibility
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

    # Log on each process a small summary
    logger.warning(
        f"Process rank: {training_args.local_rank}, device: {training_args.device}, n_gpu: {training_args.n_gpu}"
        + f" distributed training: {bool(training_args.local_rank != -1)}, 16-bits training: {training_args.fp16}"
    )
    logger.info(f"Model parameters {model_args}")
    logger.info(f"Script parameters {script_args}")
    logger.info(f"Training parameters {training_args}")

    # Check for last checkpoint
    last_checkpoint = None
    if os.path.isdir(training_args.output_dir):
        last_checkpoint = get_last_checkpoint(training_args.output_dir)
    if last_checkpoint is not None and training_args.resume_from_checkpoint is None:
        logger.info(f"Checkpoint detected, resuming training at {last_checkpoint=}.")

    if "wandb" in training_args.report_to:
        init_wandb_training(training_args)

    # Load the dataset
    dataset = get_dataset(script_args)

    ################
    # Load tokenizer
    ################
    tokenizer = get_tokenizer(model_args, training_args)

    ##############
    # Load model #
    ##############
    logger.info("*** Loading model ***")
    model = get_model(model_args, training_args)

    # Get reward functions from the registry
    reward_funcs = get_reward_funcs(script_args)

    # Format into conversation
    def make_conversation(example, prompt_column: str = script_args.dataset_prompt_column):
        prompt = []

        if training_args.system_prompt is not None:
            prompt.append({"role": "system", "content": training_args.system_prompt})

        if prompt_column not in example:
            raise ValueError(f"Dataset Question Field Error: {prompt_column} is not supported.")

        prompt.append({"role": "user", "content": example[prompt_column]})
        return {"prompt": prompt}

    # 先统一做 map（Dataset / DatasetDict 都支持）
    dataset = dataset.map(make_conversation)

    # 兼容 DatasetDict 和 单个 Dataset 两种情况，去掉 messages 列
    if isinstance(dataset, datasets.DatasetDict):
        for split_name in dataset:
            if "messages" in dataset[split_name].column_names:
                dataset[split_name] = dataset[split_name].remove_columns("messages")
    elif isinstance(dataset, datasets.Dataset):
        if "messages" in dataset.column_names:
            dataset = dataset.remove_columns("messages")
    else:
        raise ValueError(f"Unexpected dataset type: {type(dataset)}")

    #############################
    # 准备 train_dataset / eval_dataset
    #############################
    train_dataset = None
    eval_dataset = None

    need_eval = training_args.do_eval and str(getattr(training_args, "eval_strategy", "no")) != "no"

    # 情况 1：多表 DatasetDict（原来就能跑的 RL 数据集）
    if isinstance(dataset, datasets.DatasetDict):
        if script_args.dataset_train_split not in dataset:
            raise ValueError(
                f"Train split '{script_args.dataset_train_split}' not found in dataset. "
                f"Available splits: {list(dataset.keys())}"
            )

        # 先拿到 train split
        train_dataset = dataset[script_args.dataset_train_split]

        if need_eval:
            # 优先用用户指定的 test split
            if script_args.dataset_test_split in dataset:
                eval_dataset = dataset[script_args.dataset_test_split]
            else:
                # 没有 test split：从 train 里自动切一部分做 eval
                if len(train_dataset) < 2:
                    logger.warning(
                        "DatasetDict 只有一个 train split 且样本数过少，无法切分 eval，"
                        "将强制关闭 evaluation_strategy/do_eval。"
                    )
                    eval_dataset = None
                    training_args.eval_strategy = "no"
                    training_args.do_eval = False
                    need_eval = False
                else:
                    split_ratio = 0.02  # 2% 做 eval，你可以视情况改大点
                    tmp_split = train_dataset.train_test_split(
                        test_size=split_ratio, seed=training_args.seed
                    )
                    train_dataset = tmp_split["train"]
                    eval_dataset = tmp_split["test"]
                    logger.warning(
                        f"DatasetDict 中没有 '{script_args.dataset_test_split}'，"
                        f"自动从 train 切出 {split_ratio*100:.1f}% 样本作为 eval "
                        f"({len(eval_dataset)} 条)。"
                    )
        else:
            eval_dataset = None

    # 情况 2：单表 Dataset（比如 KodCode-Light-RL-10K）
    elif isinstance(dataset, datasets.Dataset):
        if need_eval:
            if len(dataset) < 2:
                logger.warning(
                    "单表 Dataset 样本数过少，无法切分 eval，"
                    "将强制关闭 evaluation_strategy/do_eval。"
                )
                train_dataset = dataset
                eval_dataset = None
                training_args.eval_strategy = "no"
                training_args.do_eval = False
                need_eval = False
            else:
                split_ratio = 0.02  # 2% 做 eval，你可以视情况改
                tmp_split = dataset.train_test_split(
                    test_size=split_ratio, seed=training_args.seed
                )
                train_dataset = tmp_split["train"]
                eval_dataset = tmp_split["test"]
                logger.warning(
                    f"检测到单表 Dataset，且 eval_strategy!=no，"
                    f"自动从全量数据切出 {split_ratio*100:.1f}% 样本作为 eval "
                    f"({len(eval_dataset)} 条)。"
                )
        else:
            train_dataset = dataset
            eval_dataset = None

    else:
        raise ValueError(f"Unexpected dataset type when building train/eval: {type(dataset)}")

    #############################
    # Initialize the GRPO trainer
    #############################
    print("GRPOTrainer (Customized for Fast Eval)")
    trainer = GRPOCustomTrainer(
        model=model,
        reward_funcs=reward_funcs,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=(eval_dataset if need_eval else None),
        peft_config=get_peft_config(model_args),
        callbacks=get_callbacks(training_args, model_args),
        processing_class=tokenizer,
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
    metrics["train_samples"] = len(train_dataset)
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
    if training_args.do_eval and eval_dataset is not None:
        logger.info("*** Evaluate ***")
        metrics = trainer.evaluate()
        metrics["eval_samples"] = len(eval_dataset)
        trainer.log_metrics("eval", metrics)
        trainer.save_metrics("eval", metrics)
    elif training_args.do_eval and eval_dataset is None and trainer.accelerator.is_main_process:
        logger.warning("do_eval=True 但没有可用的 eval_dataset，已在上游强制关闭 eval。")

    #############
    # push to hub
    #############
    if training_args.push_to_hub:
        logger.info("Pushing to hub...")
        trainer.push_to_hub(**kwargs)


if __name__ == "__main__":
    parser = TrlParser((GRPOScriptArguments, GRPOConfig, ModelConfig))
    script_args, training_args, model_args = parser.parse_args_and_config()
    main(script_args, training_args, model_args)
