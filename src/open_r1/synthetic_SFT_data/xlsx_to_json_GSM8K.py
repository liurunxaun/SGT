import pandas as pd
import json
import os

def xlsx_to_json(xlsx_file_path, json_file_path=None):
    """
    将xlsx文件转换为json文件
    逻辑修改：按优先级(1->2->3)判断，每行数据只提取第一个合格的prompt。
    """
    try:
        # 处理默认输出路径 (修复了原代码中未处理None的逻辑漏洞)
        if json_file_path is None:
            json_file_path = os.path.splitext(xlsx_file_path)[0] + '.json'

        # 读取xlsx文件
        df = pd.read_excel(xlsx_file_path)
        final_messages_list = []
        
        # 定义优先级顺序：先看1，再看2，最后看3
        prompt_judge_pairs = [
            ('prompt1', 'judge1'),
            ('prompt2', 'judge2'),
            ('prompt3', 'judge3')
        ]

        for index, row in df.iterrows():
            question_content = row['question']
            
            # 遍历优先级对
            for prompt_col, judge_col in prompt_judge_pairs:  
                judge_value = row[judge_col]
                
                # 这里建议增加一点健壮性，防止Excel里的True是字符串格式
                # 只要 judge_value 为真 (True 或 1)
                if judge_value == True: 
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
                    final_messages_list.append(message_record)
                    
                    # 【关键修改】找到一个合格的后，立即跳出当前的内层循环
                    # 这样就不会再去判断后面的 judge2 或 judge3 了
                    break 

        # 保存文件
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(final_messages_list, f, ensure_ascii=False, indent=2)
        
        print(f"转换成功！共处理 {len(final_messages_list)} 条数据。")
        print(f"文件已保存至: {json_file_path}")
        return True
    
    except Exception as e:
        print(f"转换失败: {str(e)}")
        return False

# 使用示例
if __name__ == "__main__":
    xlsx_path = "/ssd5/rxliu/datasets/SFT-Data/result_data_GSM8K.xlsx"
    json_path = "/ssd5/rxliu/datasets/SFT-Data/result_data_GSM8K.json"    
    xlsx_to_json(xlsx_path, json_path)