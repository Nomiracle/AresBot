"""
交易命令接口
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class TradingCommand(ABC):
    """交易命令接口"""
    
    @abstractmethod
    def execute(self) -> Any:
        """
        执行命令
        
        Returns:
            执行结果
        """
        pass
    
    def rollback(self) -> None:
        """
        回滚命令（可选实现）
        """
        pass
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """
        验证命令（可选实现）
        
        Returns:
            (是否有效, 错误信息)
        """
        return True, None
