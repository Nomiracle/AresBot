"""
简单日志重定向
将所有 print 输出同时写入文件和控制台
"""

import sys
import os
from datetime import datetime, timedelta


class Logger(object):
    """日志重定向类"""
    
    def __init__(self, log_dir='logs', prefix='trading', stream=sys.stdout):
        """
        初始化日志记录器
        
        Args:
            log_dir: 日志目录
            prefix: 日志文件前缀
            stream: 原始输出流（sys.stdout 或 sys.stderr）
        """
        self.terminal = stream
        self.log_dir = log_dir
        self.prefix = prefix
        
        # 创建日志目录
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 初始化日志文件
        self.current_date = None
        self.log_file = None
        self._open_log_file()
    
    def _open_log_file(self):
        """打开或切换日志文件（按日期）"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 如果日期变了，关闭旧文件，打开新文件
        if today != self.current_date:
            if self.log_file:
                self.log_file.close()
            
            log_filename = os.path.join(self.log_dir, f"{self.prefix}_{today}.log")
            self.log_file = open(log_filename, 'a', encoding='utf-8')
            self.current_date = today
            
            # 清理超过10天的旧日志文件
            self.cleanup_old_logs()
    
    def cleanup_old_logs(self, days_to_keep=10):
        """清理超过指定天数的旧日志文件
        
        Args:
            days_to_keep: 保留的天数，默认10天
        """
        try:
            if not os.path.exists(self.log_dir):
                return
            
            # 计算截止日期
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d')
            
            # 遍历日志目录中的文件
            deleted_count = 0
            for filename in os.listdir(self.log_dir):
                if filename.startswith(f"{self.prefix}_") and filename.endswith('.log'):
                    # 提取日期部分
                    try:
                        date_part = filename[len(f"{self.prefix}_"):-len('.log')]
                        file_date = datetime.strptime(date_part, '%Y-%m-%d')
                        
                        # 如果文件日期早于截止日期，删除文件
                        if file_date < cutoff_date:
                            file_path = os.path.join(self.log_dir, filename)
                            os.remove(file_path)
                            deleted_count += 1
                            print(f"[{datetime.now().isoformat()}] 🗑️ 已删除旧日志文件: {filename}")
                    except (ValueError, IndexError):
                        # 如果文件名格式不正确，跳过
                        continue
            
            if deleted_count > 0:
                print(f"[{datetime.now().isoformat()}] ✅ 已清理 {deleted_count} 个超过 {days_to_keep} 天的旧日志文件")
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 清理旧日志文件失败: {e}")
    
    def write(self, message):
        """写入消息到控制台和文件"""
        # 写入控制台
        self.terminal.write(message)
        
        # 检查是否需要切换日志文件
        self._open_log_file()
        
        # 写入文件
        if self.log_file:
            self.log_file.write(message)
            self.log_file.flush()  # 立即刷新到磁盘
    
    def flush(self):
        """刷新缓冲区"""
        self.terminal.flush()
        if self.log_file:
            self.log_file.flush()
    
    def close(self):
        """关闭日志文件"""
        if self.log_file:
            self.log_file.close()
            self.log_file = None


def setup_logging(log_dir='logs', prefix='trading'):
    """
    设置日志重定向
    
    Args:
        log_dir: 日志目录
        prefix: 日志文件前缀
    
    Returns:
        tuple: (stdout_logger, stderr_logger)
    """
    # 重定向标准输出
    stdout_logger = Logger(log_dir, f"{prefix}_stdout", sys.stdout)
    sys.stdout = stdout_logger
    
    # 重定向标准错误到同一个日志文件（使用 stdout_logger 的日志文件）
    stderr_logger = Logger(log_dir, f"{prefix}_stdout", sys.stderr)
    sys.stderr = stderr_logger
    
    # 初始化时清理旧日志文件
    stdout_logger.cleanup_old_logs(days_to_keep=10)
    
    print(f"[{datetime.now().isoformat()}] 📝 日志系统已启动，日志目录: {log_dir}")
    
    return stdout_logger, stderr_logger


def restore_logging(stdout_logger, stderr_logger):
    """
    恢复原始输出流
    
    Args:
        stdout_logger: stdout 日志记录器
        stderr_logger: stderr 日志记录器
    """
    # 恢复原始输出流
    sys.stdout = stdout_logger.terminal
    sys.stderr = stderr_logger.terminal
    
    # 关闭日志文件
    stdout_logger.close()
    stderr_logger.close()
    
    print(f"[{datetime.now().isoformat()}] 📝 日志系统已关闭")


# 使用示例
if __name__ == '__main__':
    # 设置日志
    stdout_logger, stderr_logger = setup_logging(log_dir='logs', prefix='test')
    
    # 测试输出
    print("这是一条普通消息")
    print("这是另一条消息")
    
    # 测试错误输出
    import sys
    print("这是一条错误消息", file=sys.stderr)
    
    # 恢复原始输出
    restore_logging(stdout_logger, stderr_logger)
    
    print("日志系统已关闭，这条消息不会记录到文件")
