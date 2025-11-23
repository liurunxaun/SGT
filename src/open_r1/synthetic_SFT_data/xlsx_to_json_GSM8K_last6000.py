import pandas as pd
import json
import os

def xlsx_to_json(xlsx_file_path, json_file_path=None):
    """
    将xlsx文件转换为json文件
    逻辑修改：
    1. 按优先级判断，每行数据只提取第一个合格的prompt。
    2. 【追加模式】：如果json文件已存在，会将新数据追加到旧数据后。
    """
    try:
        # 处理默认输出路径
        if json_file_path is None:
            json_file_path = os.path.splitext(xlsx_file_path)[0] + '.json'

        # --- 步骤1：尝试读取已存在的JSON数据 ---
        existing_data = []
        if os.path.exists(json_file_path):
            try:
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 如果文件不为空，加载现有数据
                    if content.strip():
                        data = json.loads(content)
                        if isinstance(data, list):
                            existing_data = data
                        else:
                            print(f"警告：文件 {json_file_path} 格式不正确（不是列表），将覆盖旧文件。")
            except Exception as e:
                print(f"读取旧文件失败，将视为新文件创建: {str(e)}")
                existing_data = []

        # --- 步骤2：读取并处理新的Excel数据 ---
        df = pd.read_excel(xlsx_file_path)
        new_messages_list = []
        
        # 定义优先级顺序
        # 注意：根据你提供的代码，目前列表里只有一组。如果将来有 prompt2/judge2，直接加在下面即可。
        prompt_judge_pairs = [
            ('prompt', 'judge'),
        ]

        for index, row in df.iterrows():
            question_content = row['question']
            
            # 遍历优先级对
            for prompt_col, judge_col in prompt_judge_pairs:  
                judge_value = row[judge_col]
                
                # 健壮性判断：兼容 True (bool) 和 "True"/"true" (str) 以及 1 (int)
                is_true = (judge_value is True) or (str(judge_value).lower() == 'true') or (judge_value == 1)
                
                if is_true: 
                    prompt_content = row[prompt_col]
                    
                    message_record = {
                        "messages": [
                            {
                                "role": "user",
                                "content": question_content
                            },
                            {
                                "role": "assistant",
                                "content": prompt_content
                            }
                        ]
                    }
                    new_messages_list.append(message_record)
                    
                    # 找到一个合格的后，立即跳出当前的内层循环
                    break 

        # --- 步骤3：合并数据并保存 ---
        final_total_data = existing_data + new_messages_list

        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(final_total_data, f, ensure_ascii=False, indent=2)
        
        print("="*30)
        print(f"处理完成！")
        print(f"原有数据: {len(existing_data)} 条")
        print(f"新增数据: {len(new_messages_list)} 条")
        print(f"当前总计: {len(final_total_data)} 条")
        print(f"文件已保存至: {json_file_path}")
        print("="*30)
        
        return True
    
    except Exception as e:
        print(f"转换失败: {str(e)}")
        return False

# 使用示例
if __name__ == "__main__":
    xlsx_path = "/ssd5/rxliu/datasets/SFT-Data/result_data_GSM8K_last6000.xlsx"
    json_path = "/ssd5/rxliu/datasets/SFT-Data/result_data_GSM8K.json"    
    
    xlsx_to_json(xlsx_path, json_path)