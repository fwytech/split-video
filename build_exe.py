
import PyInstaller.__main__
import os

def build_exe():
    # 设置工作目录为脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # 确保video目录存在
    video_dir = os.path.join(script_dir, 'video')
    if not os.path.exists(video_dir):
        os.makedirs(video_dir)
    
    # PyInstaller参数
    params = [
        'video_splitter_gui.py',  # 主程序文件
        '--name=Echo智剪',  # 输出文件名
        '--windowed',  # 使用GUI模式
        '--onefile',  # 打包成单个文件
        '--clean',  # 清理临时文件
        '--icon=icon/Echo.ico',  # 设置应用程序图标
    ]
    
    # 运行PyInstaller
    PyInstaller.__main__.run(params)
    
    print('\n构建完成！\n可执行文件位于dist目录中。')

if __name__ == '__main__':
    build_exe()
