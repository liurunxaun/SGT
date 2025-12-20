import os
import glob

def clean_files_only():
    # 获取当前目录下所有以 test 开头的文件或文件夹
    for path in glob.glob("test*"):
        # 关键判断：如果是文件则删除，如果是文件夹则跳过
        if os.path.isfile(path):
            try:
                os.remove(path)
                print(f"已删除文件: {path}")
            except Exception as e:
                print(f"删除 {path} 失败: {e}")
        else:
            print(f"跳过文件夹: {path}")

if __name__ == "__main__":
    clean_files_only()