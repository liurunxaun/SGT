import pandas as pd
import json
import os

def xlsx_to_json(xlsx_file_path, json_file_path=None):
    """
    将xlsx文件转换为json文件
    
    参数:
    xlsx_file_path (str): xlsx文件的路径
    json_file_path (str, 可选): 输出json文件的路径，默认为与xlsx同目录同名称的json文件
    """
    try:
        # 读取xlsx文件
        df = pd.read_excel(xlsx_file_path)
        final_messages_list = []
        prompt_judge_pairs = [
        ('prompt1', 'judge1'),
        ('prompt2', 'judge2'),
        ('prompt3', 'judge3')
        ]
        for index,row in df.iterrows():
            question_content = row['question']
            for prompt_col, judge_col in prompt_judge_pairs:  
              judge_value = row[judge_col]
              print(judge_value)
              if judge_value == True:
                print("y")
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
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(final_messages_list, f, ensure_ascii=False, indent=2)
        
        print(f"转换成功！文件已保存至: {json_file_path}")
        return True
    
    except Exception as e:
        print(f"转换失败: {str(e)}")
        return False

# 使用示例
if __name__ == "__main__":
    # 替换为你的xlsx文件路径
    xlsx_path = "result_data_GSM8K.xlsx"
    # 可选：指定输出json文件路径，不指定则默认与xlsx同目录
    json_path = "result_data_GSM8K.json"
    
    # 调用转换函数
    xlsx_to_json(xlsx_path, json_path)