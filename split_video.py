import os
# 尝试这些导入方式
import moviepy
from moviepy.editor import *
import re

def time_to_seconds(time_str):
    """
    将时间字符串转换为秒数
    支持格式：HH:MM:SS 或 MM:SS 或 SS
    """
    parts = time_str.split(':')
    if len(parts) == 3:  # HH:MM:SS
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:  # MM:SS
        return int(parts[0]) * 60 + float(parts[1])
    else:  # SS
        return float(parts[0])

def split_video(video_path, cut_points_path, output_dir=None):
    """
    根据切割点文件切割视频
    
    参数:
        video_path: 源视频路径
        cut_points_path: 切割点文件路径
        output_dir: 输出目录，默认为源视频所在目录下的'output'文件夹
    """
    # 设置输出目录
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(video_path), 'output')
    
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 读取切割点文件
    with open(cut_points_path, 'r', encoding='utf-8') as f:
        cut_points = f.readlines()
    
    # 加载视频
    print(f"正在加载视频: {video_path}")
    video = mpy.VideoFileClip(video_path)
    
    # 处理每个切割点
    for i, point in enumerate(cut_points):
        point = point.strip()
        if not point:
            continue
        
        # 解析切割点格式: 开始时间点~结束时间点，视频名称
        match = re.match(r'([\d:\.]+)~([\d:\.]+)，(.+)', point)
        if match:
            start_time_str, end_time_str, clip_name = match.groups()
            
            # 转换时间为秒
            start_time = time_to_seconds(start_time_str)
            end_time = time_to_seconds(end_time_str)
            
            print(f"正在处理第{i+1}个片段: {start_time_str}~{end_time_str}，{clip_name}")
            
            # 提取视频片段
            clip = video.subclip(start_time, end_time)
            
            # 设置输出文件名
            output_filename = f"{clip_name}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            # 保存视频片段
            print(f"正在保存: {output_path}")
            clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile="temp-audio.m4a",
                remove_temp=True,
                preset="medium",  # 可选: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
                threads=4
            )
            
            # 释放内存
            clip.close()
        else:
            print(f"警告: 无法解析切割点格式: {point}")
    
    # 关闭视频
    video.close()
    print("视频切割完成!")

if __name__ == "__main__":
    # 设置文件路径
    video_dir = os.path.join(os.getcwd(), "video")
    video_path = os.path.join(video_dir, "test.mp4")
    cut_points_path = os.path.join(video_dir, "视频切割点.txt")
    output_dir = os.path.join(video_dir, "output")
    
    # 执行视频切割
    split_video(video_path, cut_points_path, output_dir)