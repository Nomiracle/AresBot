"""
简单日志重定向
将所有 print 输出同时写入文件和控制台
"""

import sys
import os
from datetime import datetime


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
        self.file_error = False  # 标记文件操作是否失败
        
        # 创建日志目录
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
        except Exception as e:
            # 目录创建失败,只输出到终端
            self.file_error = True
            try:
                self.terminal.write(f"[Logger] 警告: 无法创建日志目录 {log_dir}: {e}\n")
                self.terminal.flush()
            except:
                pass  # 终端输出也失败,静默处理
        
        # 初始化日志文件
        self.current_date = None
        self.log_file = None
        if not self.file_error:
            self._open_log_file()
    
    def _open_log_file(self):
        """打开或切换日志文件（按日期）"""
        if self.file_error:
            return  # 已经标记为文件错误,不再尝试
        
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            # 如果日期变了或文件未打开，打开/切换日志文件
            if today != self.current_date or self.log_file is None:
                if self.log_file:
                    try:
                        self.log_file.close()
                    except Exception as e:
                        # 关闭失败,记录但继续
                        try:
                            self.terminal.write(f"[Logger] 警告: 关闭日志文件失败: {e}\n")
                        except:
                            pass
                
                log_filename = os.path.join(self.log_dir, f"{self.prefix}_{today}.log")
                self.log_file = open(log_filename, 'a', encoding='utf-8', buffering=1)
                self.current_date = today
        except Exception as e:
            # 文件操作失败,标记错误状态并降级到只输出终端
            self.file_error = True
            self.log_file = None
            try:
                self.terminal.write(f"[Logger] 错误: 无法打开日志文件: {e}\n")
                self.terminal.flush()
            except:
                pass  # 终端输出也失败,静默处理
    
    def write(self, message):
        """写入消息到控制台和文件"""
        # 优先写入控制台(最重要)
        try:
            self.terminal.write(message)
        except Exception as e:
            # 终端写入失败,尝试写入文件(如果可用)
            pass
        
        # 检查是否需要切换日志文件
        if not self.file_error:
            self._open_log_file()
        
        # 写入文件
        if self.log_file and not self.file_error:
            try:
                self.log_file.write(message)
                self.log_file.flush()  # 立即刷新到磁盘
            except Exception as e:
                # 文件写入失败,标记错误并降级
                self.file_error = True
                try:
                    self.terminal.write(f"[Logger] 错误: 写入日志文件失败: {e}\n")
                    self.terminal.flush()
                except:
                    pass
    
    def flush(self):
        """刷新缓冲区"""
        try:
            self.terminal.flush()
        except Exception:
            pass  # 终端刷新失败,静默处理
        
        if self.log_file and not self.file_error:
            try:
                self.log_file.flush()
            except Exception as e:
                # 刷新失败,标记错误
                self.file_error = True
                try:
                    self.terminal.write(f"[Logger] 错误: 刷新日志文件失败: {e}\n")
                except:
                    pass
    
    def close(self):
        """关闭日志文件"""
        if self.log_file:
            try:
                self.log_file.close()
            except Exception as e:
                # 关闭失败,记录但不抛出异常
                try:
                    self.terminal.write(f"[Logger] 警告: 关闭日志文件失败: {e}\n")
                except:
                    pass
            finally:
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
    
    print(f"[{datetime.now().isoformat()}] 日志系统已启动，日志目录: {log_dir}")
    
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
    
    print(f"[{datetime.now().isoformat()}] 日志系统已关闭")


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
