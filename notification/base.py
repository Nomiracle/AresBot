"""
消息通知基类
所有消息通知实现类需要继承这个抽象类
"""
from abc import ABC, abstractmethod


class BaseNotification(ABC):
    """消息通知抽象基类"""
    
    @abstractmethod
    def send(self, message: str) -> bool:
        """发送消息
        
        Args:
            message: 要发送的消息内容
            
        Returns:
            bool: 是否发送成功
        """
        pass
