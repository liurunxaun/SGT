from datasets import load_from_disk
import os

# 你的本地数据集路径
DATASET_PATH = "/ssd5/rxliu/datasets/humanevalplus"

def main():
    if not os.path.exists(DATASET_PATH):
        print(f"错误: 路径不存在 -> {DATASET_PATH}")
        return

    print(f"正在加载数据集: {DATASET_PATH} ...")
    try:
        ds = load_from_disk(DATASET_PATH)
        
        # HumanEval 通常只有 'test' 分割
        if 'test' not in ds:
            print("错误: 数据集中没找到 'test' split")
            print(f"当前有的 splits: {ds.keys()}")
            return
            
        test_data = ds['test']
        print(f"加载成功! 共包含 {len(test_data)} 条数据。")

        # 获取第一条数据来看看有哪些字段
        first_item = test_data[0]
        keys = list(first_item.keys())

        print("\n" + "="*30)
        print(" 数据集包含的字段列表 (Schema)")
        print("="*30)
        for k in keys:
            print(f"- {k}")
        
        print("\n" + "="*30)
        print(" 关键字段检查结果")
        print("="*30)
        
        # 检查 EvalPlus 运行必须的字段
        has_plus = 'plus_input' in keys
        has_contract = 'contract' in keys
        has_base = 'base_input' in keys

        print(f"['plus_input'] (扩展测试用例): \t{'✅ 存在' if has_plus else '❌ 缺失'}")
        print(f"['contract']   (断言/合约):   \t{'✅ 存在' if has_contract else '❌ 缺失'}")
        print(f"['base_input'] (基础测试用例): \t{'✅ 存在' if has_base else '❌ 缺失'}")

        print("\n" + "-"*30)
        if has_plus and has_contract:
            print("结论: 这是一个完整的 HumanEval+ 数据集。")
        else:
            print("结论: 这看起来像是原始的 HumanEval (非Plus版本)，或者字段命名不匹配。")
            print("注意: 如果这些字段缺失，EvalPlus 工具如果不联网下载就无法进行更严格的测试。")

    except Exception as e:
        print(f"读取出错: {e}")

if __name__ == "__main__":
    main()