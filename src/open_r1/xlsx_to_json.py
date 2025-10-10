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
        
        # 如果未指定json文件路径，则使用与xlsx相同的路径和名称
        if json_file_path is None:
            file_name = os.path.splitext(os.path.basename(xlsx_file_path))[0]
            json_file_path = os.path.join(os.path.dirname(xlsx_file_path), f"{file_name}.json")
        
        # 将数据转换为字典列表，然后保存为json
        data = df.to_dict('records')
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        print(f"转换成功！文件已保存至: {json_file_path}")
        return True
    
    except Exception as e:
        print(f"转换失败: {str(e)}")
        return False

# 使用示例
if __name__ == "__main__":
    # 替换为你的xlsx文件路径
    xlsx_path = "result_data_100.xlsx"
    # 可选：指定输出json文件路径，不指定则默认与xlsx同目录
    json_path = "result_data_100.json"
    
    # 调用转换函数
    xlsx_to_json(xlsx_path, json_path)