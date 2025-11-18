#!/usr/bin/env python3
"""
Frigate录像导出和备份脚本

该脚本用于:
1. 定时导出Frigate指定天数前的录像文件
2. 将导出的文件移动到目标目录
3. 清理指定天数之前的导出文件
4. 清理Frigate原始导出文件
"""

import os
import sys
import time
import shutil
import json
import requests
from datetime import datetime, timedelta
import signal
import argparse
import logging
import configparser

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 导入pytz用于时区处理
import pytz

# 全局配置变量（初始值为空字符串）
FRIGATE_API_URL = ""
SOURCE_PATH = ""
DEST_PATH = ""
EXPORT_RETENTION_DAYS = 30
EXPORT_DAYS_AGO = 1
TIMEZONE = "Asia/Shanghai"
CHINA_TZ = pytz.timezone('Asia/Shanghai')  # 默认时区

def load_config(config_file='config.ini'):
    """
    从配置文件加载配置参数
    
    Args:
        config_file: 配置文件路径
    """
    global FRIGATE_API_URL, SOURCE_PATH, DEST_PATH, EXPORT_RETENTION_DAYS, EXPORT_DAYS_AGO, TIMEZONE, CHINA_TZ
    
    config = configparser.ConfigParser()
    if not config.read(config_file, encoding='utf-8'):
        logger.error(f"无法读取配置文件 {config_file}")
        sys.exit(1)
    
    if 'frigate' not in config:
        logger.error(f"配置文件 {config_file} 中未找到 [frigate] 配置段")
        sys.exit(1)
    
    try:
        FRIGATE_API_URL = config.get('frigate', 'api_url')
        SOURCE_PATH = config.get('frigate', 'source_path')
        DEST_PATH = config.get('frigate', 'dest_path')
        EXPORT_RETENTION_DAYS = config.getint('frigate', 'export_retention_days')
        EXPORT_DAYS_AGO = config.getint('frigate', 'export_days_ago', fallback=1)
        TIMEZONE = config.get('frigate', 'timezone', fallback='Asia/Shanghai')
        
        # 设置时区
        try:
            CHINA_TZ = pytz.timezone(TIMEZONE)
            logger.info(f"已设置时区为: {TIMEZONE}")
        except pytz.exceptions.UnknownTimeZoneError:
            logger.warning(f"未知的时区: {TIMEZONE}, 使用默认时区 UTC")
            CHINA_TZ = pytz.UTC
        
        logger.info(f"已从配置文件 {config_file} 加载配置")
    except Exception as e:
        logger.error(f"读取配置文件 {config_file} 时出错: {e}")
        sys.exit(1)

# 加载配置
load_config()

# 全局变量用于优雅退出
should_exit = False

# 存储任务开始时间
export_start_times = {}

def signal_handler(sig, frame):
    """处理中断信号"""
    global should_exit
    logger.info('收到中断信号，正在退出...')
    should_exit = True
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_cameras():
    """
    获取所有摄像头列表
    """
    try:
        response = requests.get(f"{FRIGATE_API_URL}/api/config")
        response.raise_for_status()
        config = response.json()
        cameras = list(config.get('cameras', {}).keys())
        return cameras
    except Exception as e:
        logger.error(f"无法从配置获取摄像头列表: {e}")
        # 返回示例摄像头列表
        return ["tplink_ipc44aw"]

def export_previous_day_recordings(cameras=None, date=None, time_range=None):
    """
    导出指定日期和时间范围的所有录像
    
    Args:
        cameras: 指定要导出的摄像头列表，如果为None则导出所有摄像头
        date: 指定日期，格式为 YYYY-MM-DD，如果为None则使用默认天数前的日期
        time_range: 时间范围元组 (start_hour, end_hour)，如果为None则使用全天(0, 23)
    """
    # 获取中国时区的当前时间
    now_china = datetime.now(CHINA_TZ)
    
    # 处理日期参数
    if date:
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d')
            target_date = CHINA_TZ.localize(target_date)
        except ValueError:
            logger.error(f"日期格式错误: {date}，应为 YYYY-MM-DD 格式")
            return []
    else:
        # 使用配置的天数前的日期
        target_date = now_china - timedelta(days=EXPORT_DAYS_AGO)
    
    # 处理时间范围参数
    if time_range:
        start_hour, end_hour = time_range
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23 and start_hour <= end_hour):
            logger.error(f"时间范围错误: {time_range}，应为有效的小时数元组 (start_hour, end_hour)")
            return []
    else:
        # 默认使用全天
        start_hour, end_hour = 0, 23
    
    # 计算开始和结束时间戳（中国时区）
    start_of_target = CHINA_TZ.localize(datetime(target_date.year, target_date.month, target_date.day, start_hour, 0, 0))
    end_of_target = CHINA_TZ.localize(datetime(target_date.year, target_date.month, target_date.day, end_hour, 59, 59))
    
    start_timestamp = int(start_of_target.timestamp())
    end_timestamp = int(end_of_target.timestamp())
    
    logger.info(f"导出 {target_date.strftime('%Y-%m-%d')} 的录像文件")
    logger.info(f"时间范围: {start_of_target} ({start_timestamp}) 到 {end_of_target} ({end_timestamp})")
    
    # 获取摄像头列表
    if cameras is None:
        cameras = get_cameras()
        logger.info(f"发现摄像头: {', '.join(cameras)}")
    else:
        logger.info(f"指定摄像头: {', '.join(cameras)}")
    
    exported_files = []
    
    for camera in cameras:
        if should_exit:
            break
            
        try:
            # 发起导出请求
            export_data = {
                "playback": "realtime",
                "source": "recordings"
            }
            
            # 根据文档，应该是POST请求到这个端点
            export_url = f"{FRIGATE_API_URL}/api/export/{camera}/start/{start_timestamp}/end/{end_timestamp}"
            logger.info(f"正在导出摄像头 {camera} 的录像...")
            
            response = requests.post(export_url, json=export_data)
            if response.status_code in [200, 201]:
                logger.info(f"已成功发起摄像头 {camera} 的录像导出请求")
                # 记录导出开始时间
                export_start_times[camera] = time.time()
                exported_files.append({
                    "camera": camera,
                    "date": start_timestamp
                })
            else:
                logger.error(f"导出摄像头 {camera} 录像失败，状态码: {response.status_code}, 响应: {response.text}")
                
        except Exception as e:
            logger.error(f"导出摄像头 {camera} 录像时出错: {e}")
    
    return exported_files

def format_duration(seconds):
    """
    格式化持续时间
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的持续时间
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}小时{minutes}分钟{secs}秒"
    elif minutes > 0:
        return f"{minutes}分钟{secs}秒"
    else:
        return f"{secs}秒"

def get_real_file_path(video_path):
    """
    将容器内的路径转换为实际文件系统路径
    
    Args:
        video_path: 容器内的视频路径
        
    Returns:
        str: 实际文件系统中的路径
    """
    if not video_path:
        return ""
    
    # 提取文件名
    filename = os.path.basename(video_path)
    # 拼接实际路径
    real_path = os.path.join(SOURCE_PATH, filename)
    logger.debug(f"转换路径: {video_path} -> {real_path}")
    return real_path

def get_file_size(filepath):
    """
    获取文件大小并格式化为可读格式
    
    Args:
        filepath: 文件路径
        
    Returns:
        str: 格式化的文件大小
    """
    try:
        size = os.path.getsize(filepath)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    except:
        return "未知大小"

def check_export_status(cameras, max_wait_time=7200, date=None):
    """
    检查特定摄像头的导出状态直到完成或超时
    
    Args:
        cameras: 摄像头列表
        max_wait_time: 最大等待时间（秒），默认120分钟
        date: 指定日期，格式为 YYYY-MM-DD，如果为None则使用默认天数前的日期
    """
    start_time = time.time()
    logger.info(f"开始检查导出状态，最长等待 {max_wait_time // 60} 分钟...")
    
    # 获取目标日期
    if date:
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d')
            target_date_str = target_date.strftime('%Y-%m-%d')
        except ValueError:
            logger.error(f"日期格式错误: {date}，应为 YYYY-MM-DD 格式")
            return False
    else:
        # 使用配置的天数前的日期
        target_date_str = (datetime.now(CHINA_TZ) - timedelta(days=EXPORT_DAYS_AGO)).strftime('%Y-%m-%d')
    
    # 记录需要等待完成的摄像头
    pending_cameras = set(cameras)
    
    # 用于跟踪文件大小变化，确保文件写入完成
    file_sizes = {}
    
    while time.time() - start_time < max_wait_time and pending_cameras and not should_exit:
        try:
            # 获取导出列表
            response = requests.get(f"{FRIGATE_API_URL}/api/exports")
            response.raise_for_status()
            exports = response.json()
            logger.debug(f"当前导出任务: {json.dumps(exports, indent=2)}")
            # 初始化进度信息列表
            progress_info = []
            
            # 检查每个待处理的摄像头
            for camera in list(pending_cameras):  # 使用list复制，因为在循环中会修改set
                # 查找该摄像头相关的指定日期导出任务
                camera_exports = [e for e in exports 
                                if e.get("camera") == camera 
                                and target_date_str in e.get("name", "")]

                # 检查是否还有进行中的任务
                in_progress_exports = [e for e in camera_exports if e.get("in_progress", False)]
                logger.debug(f"in_progress_exports: {in_progress_exports}")
                if not in_progress_exports and camera_exports:
                    # 如果没有进行中的任务且存在相关导出任务，还需要确认文件已完成写入
                    all_files_stable = True
                    for export in camera_exports:
                        video_path = export.get("video_path", "未知路径")
                        real_path = get_real_file_path(video_path)
                        
                        if os.path.exists(real_path):
                            current_size = os.path.getsize(real_path)
                            last_size = file_sizes.get(real_path, current_size)
                            file_sizes[real_path] = current_size
                            
                            # 如果文件大小发生变化，说明还在写入中
                            if current_size != last_size:
                                all_files_stable = False
                                break
                    
                    if all_files_stable:
                        logger.info(f"摄像头 {camera} 的导出任务已完成")
                        pending_cameras.remove(camera)
                        # 清理该摄像头的文件大小记录
                        for export in camera_exports:
                            video_path = export.get("video_path", "")
                            real_path = get_real_file_path(video_path)
                            if real_path in file_sizes:
                                del file_sizes[real_path]
                    else:
                        logger.info(f"摄像头 {camera} 的导出任务API显示已完成，但文件仍在写入中...")
                elif not camera_exports:
                    # 如果没有找到任何相关导出任务，可能需要等待
                    logger.info(f"正在等待摄像头 {camera} 的导出任务开始...")
                else:
                    # 收集正在进行的导出任务信息用于后续显示
                    for export in in_progress_exports:
                        video_path = export.get("video_path", "未知路径")
                        # 转换为实际文件路径
                        real_path = get_real_file_path(video_path)
                        elapsed_time = time.time() - export_start_times.get(camera, time.time())
                        elapsed_formatted = format_duration(elapsed_time)
                        
                        if os.path.exists(real_path):
                            file_size = get_file_size(real_path)
                            progress_info.append(f"{camera}: {file_size}, 已执行: {elapsed_formatted}")
                            
                            # 更新文件大小记录
                            file_sizes[real_path] = os.path.getsize(real_path)
                        else:
                            progress_info.append(f"{camera}: 文件不存在, 已执行: {elapsed_formatted}")
            
            # 显示进度信息
            if progress_info:
                for info in progress_info:
                    logger.info(f"  - {info}")
                    
            if pending_cameras:
                logger.info(f"仍有 {len(pending_cameras)} 个摄像头的导出任务未完成: {', '.join(pending_cameras)}")
                logger.info("继续等待导出任务完成...")
                time.sleep(30)  # 等待30秒再检查
            else:
                logger.info("所有摄像头的导出任务已完成")
                return True
                
        except Exception as e:
            logger.error(f"检查导出状态时出错: {e}")
            time.sleep(30)
    
    if pending_cameras:
        logger.warning(f"等待导出完成超时，以下摄像头任务未完成: {', '.join(pending_cameras)}")
    else:
        logger.info("所有导出任务已完成")
    
    return not bool(pending_cameras)

def check_and_move_exported_files(cameras, date=None):
    """
    检查已完成的导出文件并将其移动到目标目录
    
    Args:
        cameras: 摄像头列表
        date: 指定日期，格式为 YYYY-MM-DD，如果为None则使用默认天数前的日期
    """
    try:
        # 获取导出列表
        response = requests.get(f"{FRIGATE_API_URL}/api/exports")
        response.raise_for_status()
        exports = response.json()
        
        # 创建目标目录（如果不存在）
        os.makedirs(DEST_PATH, exist_ok=True)
        
        moved_files = 0
        # 获取目标日期
        if date:
            try:
                target_date = datetime.strptime(date, '%Y-%m-%d')
                target_date_str = target_date.strftime('%Y-%m-%d')
            except ValueError:
                logger.error(f"日期格式错误: {date}，应为 YYYY-MM-DD 格式")
                return
        else:
            # 使用配置的天数前的日期
            target_date_str = (datetime.now(CHINA_TZ) - timedelta(days=EXPORT_DAYS_AGO)).strftime('%Y-%m-%d')
        
        # 只处理指定摄像头和日期的导出任务
        target_exports = [e for e in exports 
                         if e.get("camera") in cameras 
                         and not e.get("in_progress", False)
                         and target_date_str in e.get("name", "")]
        
        logger.info(f"找到 {len(target_exports)} 个 {target_date_str} 已完成的导出任务")
        
        for export in target_exports:
            if should_exit:
                break
                
            # 获取导出文件路径
            video_path = export.get("video_path", "")
            # 转换为实际文件路径
            real_path = get_real_file_path(video_path)
            
            if not video_path or not os.path.exists(real_path):
                logger.warning(f"导出文件不存在或路径无效: {real_path}")
                continue
            
            # 显示文件信息
            file_size = get_file_size(real_path)
            camera = export.get("camera", "Unknown")
            elapsed_time = time.time() - export_start_times.get(camera, time.time())
            elapsed_formatted = format_duration(elapsed_time)
            logger.info(f"处理文件: {real_path} (大小: {file_size}, 总耗时: {elapsed_formatted})")
            
            # 构造目标文件路径
            filename = os.path.basename(real_path)
            dest_file = os.path.join(DEST_PATH, filename)
            
            # 移动文件到目标目录
            try:
                shutil.move(real_path, dest_file)
                logger.info(f"已将 {filename} 移动到 {DEST_PATH}")
                moved_files += 1
                
                # 可选：删除Frigate中的导出记录
                export_id = export.get("id", "")
                if export_id:
                    try:
                        delete_response = requests.delete(f"{FRIGATE_API_URL}/api/export/{export_id}")
                        if delete_response.status_code in [200, 204]:
                            logger.info(f"已从Frigate中删除导出记录: {export_id}")
                    except Exception as e:
                        logger.error(f"删除导出记录 {export_id} 时出错: {e}")
                
            except Exception as e:
                logger.error(f"移动文件 {filename} 时出错: {e}")
        
        logger.info(f"共移动了 {moved_files} 个文件")
                
    except Exception as e:
        logger.error(f"检查导出文件时出错: {e}")

def clean_old_exports():
    """
    清理目标目录中超过指定天数的导出文件
    """
    try:
        # 获取中国时区的当前时间
        now_china = datetime.now(CHINA_TZ)
        cutoff_date = now_china - timedelta(days=EXPORT_RETENTION_DAYS)
        logger.info(f"清理 {cutoff_date.strftime('%Y-%m-%d')} 之前的历史文件")
        
        if not os.path.exists(DEST_PATH):
            logger.warning(f"目标目录 {DEST_PATH} 不存在")
            return
        
        cleaned_files = 0
        for filename in os.listdir(DEST_PATH):
            if should_exit:
                break
                
            file_path = os.path.join(DEST_PATH, filename)
            if os.path.isfile(file_path):
                # 根据文件修改时间判断
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                # 确保比较的是相同类型的datetime对象
                if file_modified.tzinfo is None:
                    file_modified = CHINA_TZ.localize(file_modified)
                else:
                    file_modified = file_modified.astimezone(CHINA_TZ)
                    
                if file_modified < cutoff_date:
                    try:
                        os.remove(file_path)
                        logger.info(f"已删除过期文件: {filename}")
                        cleaned_files += 1
                    except Exception as e:
                        logger.error(f"删除文件 {filename} 时出错: {e}")
        
        logger.info(f"共清理了 {cleaned_files} 个过期文件")
                        
    except Exception as e:
        logger.error(f"清理旧导出文件时出错: {e}")


def main():
    """
    主函数
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Frigate录像导出和备份工具')
    parser.add_argument('--cameras', '-c', nargs='+', help='指定要导出的摄像头列表（默认导出所有摄像头）')
    parser.add_argument('--date', help='指定导出日期，格式为 YYYY-MM-DD（默认为配置的天数前）')
    parser.add_argument('--start-hour', type=int, default=0, help='导出开始时间（小时，0-23，默认为0）')
    parser.add_argument('--end-hour', type=int, default=23, help='导出结束时间（小时，0-23，默认为23）')
    parser.add_argument('--config', help='指定配置文件路径')
    args = parser.parse_args()
    
    # 如果指定了配置文件，则重新加载配置
    if args.config:
        load_config(args.config)
    
    # 检查必要配置是否存在
    if not all([FRIGATE_API_URL, SOURCE_PATH, DEST_PATH, EXPORT_RETENTION_DAYS]):
        logger.error("配置不完整，请检查配置文件")
        sys.exit(1)
    
    # 设置中国时区
    now_china = datetime.now(CHINA_TZ)
    logger.info(f"开始执行 Frigate 导出任务: {now_china.strftime('%Y-%m-%d %H:%M:%S')} (中国时区)")
    logger.info(f"Frigate API地址: {FRIGATE_API_URL}")
    logger.info(f"导出文件保存路径: {DEST_PATH}")
    logger.info(f"导出 {EXPORT_DAYS_AGO} 天前的录像")
    
    # 获取摄像头列表
    if args.cameras is None:
        cameras = get_cameras()
        logger.info(f"发现摄像头: {', '.join(cameras)}")
    else:
        cameras = args.cameras
        logger.info(f"指定摄像头: {', '.join(cameras)}")
    
    # 处理时间范围参数
    time_range = None
    if args.start_hour != 0 or args.end_hour != 23:
        time_range = (args.start_hour, args.end_hour)
    
    # 步骤1: 导出指定日期和时间范围的录像
    exported_cameras = export_previous_day_recordings(cameras, args.date, time_range)
    exported_camera_names = [item["camera"] for item in exported_cameras]
    
    if should_exit:
        return
    
    # 步骤2: 等待导出完成
    if exported_cameras:
        logger.info("等待导出完成...")
        check_export_status(exported_camera_names, date=args.date)
    
    if should_exit:
        return
    
    # 步骤3: 检查并移动已完成的导出文件
    logger.info("检查并移动导出文件...")
    check_and_move_exported_files(exported_camera_names, date=args.date)
    
    if should_exit:
        return
    
    # 步骤4: 清理超过指定天数的旧导出文件
    logger.info("清理旧导出文件...")
    clean_old_exports()
    
    logger.info("Frigate 导出任务完成")

if __name__ == "__main__":
    main()
