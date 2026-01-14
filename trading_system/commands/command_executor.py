"""
命令执行器
"""

from typing import Any, Optional
from .trading_command import TradingCommand


class CommandExecutor:
    """命令执行器"""
    
    def execute(self, command: TradingCommand) -> tuple[bool, Any, Optional[str]]:
        """
        执行命令
        
        Args:
            command: 交易命令
            
        Returns:
            (是否成功, 结果, 错误信息)
        """
        # 验证命令
        valid, error = command.validate()
        if not valid:
            return False, None, error
        
        # 执行命令
        try:
            result = command.execute()
            return True, result, None
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return False, None, error_msg
