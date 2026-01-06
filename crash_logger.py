"""
崩溃日志记录器 - 确保致命错误能被记录到文件
即使标准输出失败也能记录错误信息
"""

import os
import traceback
from datetime import datetime


def log_crash(error, context="", log_dir="logs"):
    """
    记录崩溃信息到专门的崩溃日志文件
    
    Args:
        error: 异常对象
        context: 上下文信息(如用户名、交易对等)
        log_dir: 日志目录
    """
    try:
        # 确保日志目录存在
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 生成崩溃日志文件名
        crash_log_file = os.path.join(log_dir, "crash.log")
        
        # 构建错误信息
        timestamp = datetime.now().isoformat()
        error_type = type(error).__name__
        error_msg = str(error)
        stack_trace = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        
        # 写入崩溃日志
        with open(crash_log_file, 'a', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"[{timestamp}] 💥 程序崩溃\n")
            if context:
                f.write(f"上下文: {context}\n")
            f.write(f"错误类型: {error_type}\n")
            f.write(f"错误信息: {error_msg}\n")
            f.write("-" * 80 + "\n")
            f.write("完整堆栈:\n")
            f.write(stack_trace)
            f.write("=" * 80 + "\n\n")
        
        # 同时打印到控制台(如果可能)
        print(f"[{timestamp}] 💥 崩溃信息已记录到: {crash_log_file}")
        
    except Exception as log_error:
        # 如果连日志记录都失败了,尝试写入临时文件
        try:
            emergency_file = "/tmp/aresbot_crash.log"
            with open(emergency_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] 日志记录失败: {log_error}\n")
                f.write(f"原始错误: {error}\n")
        except:
            pass  # 实在没办法了


def log_warning(message, context="", log_dir="logs"):
    """
    记录警告信息
    
    Args:
        message: 警告消息
        context: 上下文信息
        log_dir: 日志目录
    """
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        warning_log_file = os.path.join(log_dir, "warnings.log")
        timestamp = datetime.now().isoformat()
        
        with open(warning_log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] ⚠️ {context}: {message}\n")
            
    except:
        pass  # 警告日志失败不影响主流程
