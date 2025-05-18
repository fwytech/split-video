import os
import sys
import subprocess
import re
import time
from datetime import timedelta
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QFileDialog, QProgressBar, QTextEdit, 
                             QCheckBox, QMessageBox, QFrame, QSplitter)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QIcon

# 复用原有的时间处理函数
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

# 视频处理线程
class VideoProcessThread(QThread):
    # 定义信号
    progress_update = pyqtSignal(int, str)  # 进度更新信号 (片段索引, 状态消息)
    process_finished = pyqtSignal(bool, str, str, int, int)  # 处理完成信号 (是否成功, 消息, 输出目录, 成功数, 总数)
    log_message = pyqtSignal(str)  # 日志消息信号
    
    def __init__(self, video_path, cut_points_path, output_dir, noise_reduction):
        super().__init__()
        self.video_path = video_path
        self.cut_points_path = cut_points_path
        self.output_dir = output_dir
        self.noise_reduction = noise_reduction
        self.is_running = True
    
    def run(self):
        # 记录开始时间
        start_time = time.time()
        
        # 检查FFmpeg是否安装
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            self.log_message.emit("错误: 未找到FFmpeg。请确保FFmpeg已安装并添加到系统PATH中。")
            self.log_message.emit("您可以从 https://ffmpeg.org/download.html 下载FFmpeg。")
            self.process_finished.emit(False, "FFmpeg未安装", "", 0, 0)
            return
        
        # 确保输出目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # 读取切割点文件
        try:
            with open(self.cut_points_path, 'r', encoding='utf-8') as f:
                cut_points = f.readlines()
        except UnicodeDecodeError:
            # 尝试使用其他编码
            try:
                with open(self.cut_points_path, 'r', encoding='gbk') as f:
                    cut_points = f.readlines()
            except Exception as e:
                self.log_message.emit(f"读取切割点文件时出错: {e}")
                self.process_finished.emit(False, f"读取切割点文件时出错: {e}", "", 0, 0)
                return
        
        self.log_message.emit(f"正在处理视频: {self.video_path}")
        self.log_message.emit(f"共发现 {len(cut_points)} 个切割点")
        
        # 处理每个切割点
        successful_clips = 0
        total_valid_points = 0
        
        for i, point in enumerate(cut_points):
            if not self.is_running:
                self.log_message.emit("处理已取消")
                self.process_finished.emit(False, "处理已取消", self.output_dir, successful_clips, total_valid_points)
                return
                
            point = point.strip()
            if not point:
                continue
            
            # 修改正则表达式以匹配实际格式: 序号、开始时间~结束时间，视频名称
            match = re.match(r'\d+、([\d:,\.]+)~([\d:,\.]+)，(.+)', point)
            if match:
                total_valid_points += 1
                start_time_str, end_time_str, clip_name = match.groups()
                
                # 转换时间为秒
                start_time_sec = time_to_seconds(start_time_str)
                end_time_sec = time_to_seconds(end_time_str)
                duration = end_time_sec - start_time_sec
                
                # 格式化时间为FFmpeg可接受的格式
                start_time_fmt = format_time(start_time_sec)
                duration_fmt = format_time(duration)
                
                self.log_message.emit(f"正在处理第{i+1}个片段: {start_time_str}~{end_time_str}，{clip_name}")
                self.progress_update.emit(i, f"处理中: {clip_name}")
                
                # 设置输出文件名（添加序号前缀）
                output_filename = f"{i+1}-{clip_name}.mp4"
                output_path = os.path.join(self.output_dir, output_filename)
                
                # 使用FFmpeg切割视频
                self.log_message.emit(f"正在保存: {output_path}")
                
                # 构建FFmpeg命令
                cmd = [
                    'ffmpeg',
                    '-i', self.video_path,
                    '-ss', start_time_fmt,
                    '-t', duration_fmt,
                    '-c:v', 'libx264',  # 视频编码器
                    '-c:a', 'aac',      # 音频编码器
                ]
                
                # 添加音频降噪处理
                if self.noise_reduction:
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
                        self.log_message.emit(f"片段 {i+1} 处理完成")
                        successful_clips += 1
                    else:
                        self.log_message.emit(f"处理片段 {i+1} 时出错:")
                        self.log_message.emit(process.stderr)
                except Exception as e:
                    self.log_message.emit(f"处理片段 {i+1} 时发生异常: {e}")
            else:
                self.log_message.emit(f"警告: 无法解析切割点格式: {point}")
            
            # 更新进度
            self.progress_update.emit(i + 1, f"已完成: {successful_clips}/{total_valid_points}")
        
        # 计算总耗时
        end_time = time.time()
        total_time = end_time - start_time
        
        success_message = f"\n===== 视频切割完成 =====\n"
        success_message += f"成功处理片段数: {successful_clips}/{total_valid_points}\n"
        success_message += f"总耗时: {format_duration(total_time)}\n"
        success_message += f"输出目录: {self.output_dir}"
        
        self.log_message.emit(success_message)
        self.process_finished.emit(True, success_message, self.output_dir, successful_clips, total_valid_points)
    
    def stop(self):
        self.is_running = False

# 主窗口类
class VideoSplitterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # 设置默认路径
        self.default_video_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'video')
        self.default_cut_points_file = os.path.join(self.default_video_dir, '视频切割点.txt')
        self.default_output_dir = os.path.join(self.default_video_dir, 'output')
        
        # 确保默认目录存在
        if not os.path.exists(self.default_video_dir):
            try:
                os.makedirs(self.default_video_dir)
            except Exception as e:
                print(f"创建默认视频目录失败: {e}")
        
        # 确保默认输出目录存在
        if not os.path.exists(self.default_output_dir):
            try:
                os.makedirs(self.default_output_dir)
            except Exception as e:
                print(f"创建默认输出目录失败: {e}")
        
        self.init_ui()
        self.process_thread = None
        
        # 加载默认文件
        self.load_default_files()
    
    def init_ui(self):
        # 设置窗口属性
        self.setWindowTitle("Echo智剪")
        self.setGeometry(100, 100, 950, 850)  # 增加窗口高度
        self.setMinimumSize(850, 750)  # 增加最小高度
        
        # 设置应用图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'icon', 'Echo.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            # 尝试创建icon目录并提示缺少图标文件
            icon_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'icon')
            if not os.path.exists(icon_dir):
                try:
                    os.makedirs(icon_dir)
                    print(f"已创建图标目录: {icon_dir}，请将Echo.ico放入此目录")
                except Exception as e:
                    print(f"创建图标目录失败: {e}")
            print(f"警告: 未找到图标文件: {icon_path}")
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 标题标签
        title_label = QLabel("Echo.智语的一键分片工具")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 描述标签
        desc_label = QLabel("基于FFmpeg的智能视频分片工具，可以根据指定的时间点将一个视频文件切割成多个片段")
        desc_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(desc_label)
        
        # 默认路径说明
        default_info = QLabel("默认设置：\n· 视频文件：自动加载应用程序同目录下video文件夹中的MP4文件\n· 切割点文件：自动加载应用程序同目录下video文件夹中的视频切割点.txt文件\n· 输出目录：自动设置为应用程序同目录下video/output文件夹（如不存在将自动创建）")
        default_info.setStyleSheet("background-color: #e8f4ff; padding: 8px; border-radius: 4px; color: #333;")
        main_layout.addWidget(default_info)
        
        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)
        
        # 文件选择区域
        file_layout = QVBoxLayout()
        file_layout.setSpacing(10)
        
        # 视频文件选择
        video_layout = QHBoxLayout()
        self.video_path_label = QLabel("未选择视频文件")
        self.video_path_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-radius: 3px;")
        video_select_btn = QPushButton("选择视频文件")
        video_select_btn.clicked.connect(self.select_video_file)
        video_layout.addWidget(QLabel("视频文件:"))
        video_layout.addWidget(self.video_path_label, 1)
        video_layout.addWidget(video_select_btn)
        file_layout.addLayout(video_layout)
        
        # 切割点文件选择
        cut_points_layout = QHBoxLayout()
        self.cut_points_path_label = QLabel("未选择切割点文件")
        self.cut_points_path_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-radius: 3px;")
        cut_points_select_btn = QPushButton("选择切割点文件")
        cut_points_select_btn.clicked.connect(self.select_cut_points_file)
        cut_points_layout.addWidget(QLabel("切割点文件:"))
        cut_points_layout.addWidget(self.cut_points_path_label, 1)
        cut_points_layout.addWidget(cut_points_select_btn)
        file_layout.addLayout(cut_points_layout)
        
        # 输出目录选择
        output_layout = QHBoxLayout()
        self.output_dir_label = QLabel("未选择输出目录")
        self.output_dir_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-radius: 3px;")
        output_select_btn = QPushButton("选择输出目录")
        output_select_btn.clicked.connect(self.select_output_dir)
        output_layout.addWidget(QLabel("输出目录:"))
        output_layout.addWidget(self.output_dir_label, 1)
        output_layout.addWidget(output_select_btn)
        file_layout.addLayout(output_layout)
        
        main_layout.addLayout(file_layout)
        
        # 选项区域
        options_layout = QHBoxLayout()
        self.noise_reduction_checkbox = QCheckBox("应用音频降噪处理")
        self.noise_reduction_checkbox.setChecked(True)
        options_layout.addWidget(self.noise_reduction_checkbox)
        options_layout.addStretch(1)
        main_layout.addLayout(options_layout)
        
        # 进度条
        progress_layout = QVBoxLayout()
        progress_label = QLabel("处理进度:")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_status = QLabel("就绪")
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_status)
        main_layout.addLayout(progress_layout)
        
        # 日志区域
        log_layout = QVBoxLayout()
        log_label = QLabel("处理日志:")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #f5f5f5; font-family: Consolas, monospace;")
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_text)
        main_layout.addLayout(log_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        
        self.start_button = QPushButton("开始处理")
        self.start_button.setMinimumWidth(120)
        self.start_button.clicked.connect(self.start_processing)
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMinimumWidth(120)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.cancel_button.setEnabled(False)
        
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setMinimumWidth(120)
        self.open_output_button.clicked.connect(self.open_output_directory)
        self.open_output_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.open_output_button)
        button_layout.addStretch(1)
        
        main_layout.addLayout(button_layout)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
        
        # 初始化日志
        self.log_message("欢迎使用视频切割工具 v4.0")
        self.log_message("请选择视频文件和切割点文件开始处理")
    
    def select_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", self.default_video_dir if os.path.exists(self.default_video_dir) else "", 
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv);;所有文件 (*.*)"
        )
        if file_path:
            self.video_path_label.setText(file_path)
            # 自动设置默认输出目录为视频所在目录下的output文件夹
            default_output = os.path.join(os.path.dirname(file_path), 'output')
            self.output_dir_label.setText(default_output)
            
            # 尝试自动查找同目录下的切割点文件
            video_dir = os.path.dirname(file_path)
            possible_cut_files = [f for f in os.listdir(video_dir) if '切割点' in f and f.endswith('.txt')]
            if possible_cut_files:
                self.cut_points_path_label.setText(os.path.join(video_dir, possible_cut_files[0]))
                self.log_message(f"已自动选择切割点文件: {possible_cut_files[0]}")
    
    def select_cut_points_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择切割点文件", self.default_video_dir if os.path.exists(self.default_video_dir) else "", 
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if file_path:
            self.cut_points_path_label.setText(file_path)
    
    def select_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", 
                                                  self.default_output_dir if os.path.exists(self.default_output_dir) else "")
        if dir_path:
            self.output_dir_label.setText(dir_path)
    
    def log_message(self, message):
        self.log_text.append(message)
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def load_default_files(self):
        """加载默认文件和目录"""
        # 检查默认视频目录是否存在
        if os.path.exists(self.default_video_dir):
            # 查找默认视频目录下的MP4文件
            mp4_files = [f for f in os.listdir(self.default_video_dir) if f.lower().endswith('.mp4')]
            if mp4_files:
                default_video = os.path.join(self.default_video_dir, mp4_files[0])
                self.video_path_label.setText(default_video)
                self.log_message(f"已自动加载视频文件: {mp4_files[0]}")
            
            # 检查默认切割点文件是否存在
            if os.path.exists(self.default_cut_points_file):
                self.cut_points_path_label.setText(self.default_cut_points_file)
                self.log_message(f"已自动加载切割点文件: 视频切割点.txt")
            else:
                # 查找其他可能的切割点文件
                possible_cut_files = [f for f in os.listdir(self.default_video_dir) if '切割点' in f and f.endswith('.txt')]
                if possible_cut_files:
                    cut_file_path = os.path.join(self.default_video_dir, possible_cut_files[0])
                    self.cut_points_path_label.setText(cut_file_path)
                    self.log_message(f"已自动加载切割点文件: {possible_cut_files[0]}")
            
            # 设置默认输出目录
            self.output_dir_label.setText(self.default_output_dir)
            self.log_message(f"已设置默认输出目录: {os.path.join('video', 'output')}")
    
    def start_processing(self):
        # 获取文件路径
        video_path = self.video_path_label.text()
        cut_points_path = self.cut_points_path_label.text()
        output_dir = self.output_dir_label.text()
        
        # 如果未选择文件，尝试使用默认路径
        if video_path == "未选择视频文件" or not os.path.exists(video_path):
            # 查找默认视频目录下的MP4文件
            if os.path.exists(self.default_video_dir):
                mp4_files = [f for f in os.listdir(self.default_video_dir) if f.lower().endswith('.mp4')]
                if mp4_files:
                    video_path = os.path.join(self.default_video_dir, mp4_files[0])
                    self.video_path_label.setText(video_path)
                else:
                    self.log_message(f"在 {self.default_video_dir} 目录下未找到MP4文件")
                    return
            else:
                self.log_message(f"默认视频目录不存在: {self.default_video_dir}")
                return
        
        # 如果未选择切割点文件，尝试使用默认文件
        if cut_points_path == "未选择切割点文件" or not os.path.exists(cut_points_path):
            # 首先尝试使用默认切割点文件
            if os.path.exists(self.default_cut_points_file):
                cut_points_path = self.default_cut_points_file
                self.cut_points_path_label.setText(cut_points_path)
            else:
                # 查找其他可能的切割点文件
                video_dir = os.path.dirname(video_path)
                possible_cut_files = [f for f in os.listdir(video_dir) if '切割点' in f and f.endswith('.txt')]
                if possible_cut_files:
                    cut_points_path = os.path.join(video_dir, possible_cut_files[0])
                    self.cut_points_path_label.setText(cut_points_path)
                else:
                    self.log_message("未找到切割点文件")
                    return
        
        # 如果未选择输出目录，使用默认输出目录
        if output_dir == "未选择输出目录" or not os.path.exists(output_dir):
            output_dir = os.path.join(os.path.dirname(video_path), 'output')
            self.output_dir_label.setText(output_dir)
            # 确保输出目录存在
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
        
        # 获取降噪选项
        noise_reduction = self.noise_reduction_checkbox.isChecked()
        
        # 创建并启动处理线程
        self.process_thread = VideoProcessThread(
            video_path, cut_points_path, output_dir, noise_reduction
        )
        
        # 连接信号
        self.process_thread.progress_update.connect(self.update_progress)
        self.process_thread.process_finished.connect(self.process_finished)
        self.process_thread.log_message.connect(self.log_message)
        
        # 更新UI状态
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.open_output_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_status.setText("正在处理...")
        self.statusBar().showMessage("处理中...")
        
        # 启动线程
        self.process_thread.start()
        self.log_message("开始处理视频...")
    
    def cancel_processing(self):
        if self.process_thread and self.process_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认取消", "确定要取消当前处理吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.log_message("正在取消处理...")
                self.process_thread.stop()
                self.cancel_button.setEnabled(False)
    
    def update_progress(self, current, status):
        # 读取切割点文件以获取总数
        try:
            cut_points_path = self.cut_points_path_label.text()
            if os.path.exists(cut_points_path):
                with open(cut_points_path, 'r', encoding='utf-8') as f:
                    total_points = len([line for line in f.readlines() if line.strip()])
                if total_points > 0:
                    progress = int((current / total_points) * 100)
                    self.progress_bar.setValue(min(progress, 100))
        except Exception:
            # 如果无法读取文件，使用相对进度
            self.progress_bar.setValue(min(current, 100))
        
        self.progress_status.setText(status)
    
    def process_finished(self, success, message, output_dir, successful_clips, total_clips):
        # 更新UI状态
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.open_output_button.setEnabled(success and os.path.exists(output_dir))
        
        if success:
            self.progress_bar.setValue(100)
            self.progress_status.setText(f"完成: {successful_clips}/{total_clips}")
            self.statusBar().showMessage("处理完成")
            
            # 显示完成消息
            QMessageBox.information(self, "处理完成", 
                                  f"视频切割已完成！\n\n"
                                  f"成功处理片段数: {successful_clips}/{total_clips}\n"
                                  f"输出目录: {output_dir}")
        else:
            self.progress_status.setText("处理失败")
            self.statusBar().showMessage("处理失败")
    
    def open_output_directory(self):
        output_dir = self.output_dir_label.text()
        if os.path.exists(output_dir):
            # 使用系统默认文件管理器打开目录
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':  # macOS
                subprocess.run(['open', output_dir])
            else:  # Linux
                subprocess.run(['xdg-open', output_dir])
        else:
            QMessageBox.warning(self, "警告", f"输出目录不存在: {output_dir}")

# 应用程序入口
def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用Fusion风格，在所有平台上看起来都很现代
    
    # 设置应用程序样式表
    app.setStyleSheet("""
        QPushButton {
            background-color: #4a86e8;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #3a76d8;
        }
        QPushButton:pressed {
            background-color: #2a66c8;
        }
        QPushButton:disabled {
            background-color: #cccccc;
            color: #888888;
        }
        QProgressBar {
            border: 1px solid #cccccc;
            border-radius: 3px;
            text-align: center;
            height: 20px;
        }
        QProgressBar::chunk {
            background-color: #4a86e8;
            width: 10px;
            margin: 0.5px;
        }
    """)
    
    window = VideoSplitterApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()