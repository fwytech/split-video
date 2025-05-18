import os
import subprocess
import re
import time
from datetime import timedelta

def time_to_seconds(time_str):
    """
    将时间字符串转换为秒数
    支持格式：HH:MM:SS,mmm 或 HH:MM:SS.mmm 或 MM:SS 或 SS
    """
    # 替换逗号为点，以便统一处理
    time_str = time_str.replace(',', '.')
    
    parts = time_str.split(':')
    if len(parts) == 3:  # HH:MM:SS.mmm
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:  # MM:SS
        return int(parts[0]) * 60 + float(parts[1])
    else:  # SS
        return float(parts[0])

def format_time(seconds):
    """
    将秒数转换为 HH:MM:SS.mmm 格式，适用于FFmpeg
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

def format_duration(seconds):
    """
    将秒数格式化为人类可读的时间格式
    """
    return str(timedelta(seconds=int(seconds)))

def split_video(video_path, cut_points_path, output_dir=None, noise_reduction=True):
    """
    使用FFmpeg根据切割点文件切割视频
    
    参数:
        video_path: 源视频路径
        cut_points_path: 切割点文件路径
        output_dir: 输出目录，默认为源视频所在目录下的'output'文件夹
        noise_reduction: 是否应用噪音降低处理
    """
    # 记录开始时间
    start_time = time.time()
    
    # 检查FFmpeg是否安装
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.SubprocessError, FileNotFoundError):
        print("错误: 未找到FFmpeg。请确保FFmpeg已安装并添加到系统PATH中。")
        print("您可以从 https://ffmpeg.org/download.html 下载FFmpeg。")
        return
    
    # 设置输出目录
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(video_path), 'output')
    
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 读取切割点文件
    try:
        with open(cut_points_path, 'r', encoding='utf-8') as f:
            cut_points = f.readlines()
    except UnicodeDecodeError:
        # 尝试使用其他编码
        with open(cut_points_path, 'r', encoding='gbk') as f:
            cut_points = f.readlines()
    
    print(f"正在处理视频: {video_path}")
    
    # 处理每个切割点
    successful_clips = 0
    for i, point in enumerate(cut_points):
        point = point.strip()
        if not point:
            continue
        
        # 修改正则表达式以匹配实际格式: 序号、开始时间~结束时间，视频名称
        # 匹配格式如: 1、00:00:00,033~00:10:13,500，线程间通讯基础及Emitter引入
        match = re.match(r'\d+、([\d:,\.]+)~([\d:,\.]+)，(.+)', point)
        if match:
            start_time_str, end_time_str, clip_name = match.groups()
            
            # 转换时间为秒
            start_time_sec = time_to_seconds(start_time_str)
            end_time_sec = time_to_seconds(end_time_str)
            duration = end_time_sec - start_time_sec
            
            # 格式化时间为FFmpeg可接受的格式
            start_time_fmt = format_time(start_time_sec)
            duration_fmt = format_time(duration)
            
            print(f"正在处理第{i+1}个片段: {start_time_str}~{end_time_str}，{clip_name}")
            
            # 设置输出文件名（添加序号前缀）
            output_filename = f"{i+1}-{clip_name}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            # 使用FFmpeg切割视频
            print(f"正在保存: {output_path}")
            
            # 构建FFmpeg命令
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', start_time_fmt,
                '-t', duration_fmt,
                '-c:v', 'libx264',  # 视频编码器
                '-c:a', 'aac',      # 音频编码器
            ]
            
            # 添加音频降噪处理
            if noise_reduction:
                cmd.extend([
                    '-af', 'highpass=f=200,lowpass=f=3000,afftdn=nf=-25',  # 音频滤镜：高通、低通和FFT降噪
                ])
            
            cmd.extend([
                '-b:a', '192k',     # 音频比特率
                '-avoid_negative_ts', '1',
                '-y',               # 覆盖已存在的文件
                output_path
            ])
            
            try:
                # 执行FFmpeg命令
                process = subprocess.run(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8'
                )
                
                if process.returncode == 0:
                    print(f"片段 {i+1} 处理完成")
                    successful_clips += 1
                else:
                    print(f"处理片段 {i+1} 时出错:")
                    print(process.stderr)
            except Exception as e:
                print(f"处理片段 {i+1} 时发生异常: {e}")
        else:
            print(f"警告: 无法解析切割点格式: {point}")
    
    # 计算总耗时
    end_time = time.time()
    total_time = end_time - start_time
    
    print("\n===== 视频切割完成 =====")
    print(f"成功处理片段数: {successful_clips}/{len(cut_points)}")
    print(f"总耗时: {format_duration(total_time)}")
    print(f"输出目录: {output_dir}")

if __name__ == "__main__":
    # 设置文件路径
    video_dir = os.path.join(os.getcwd(), "video")
    video_path = os.path.join(video_dir, "test.mp4")
    cut_points_path = os.path.join(video_dir, "视频切割点.txt")
    output_dir = os.path.join(video_dir, "output")
    
    # 执行视频切割（启用噪音降低）
    split_video(video_path, cut_points_path, output_dir, noise_reduction=True)