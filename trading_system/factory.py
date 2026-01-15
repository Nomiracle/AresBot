"""
工厂类 - 创建交易上下文和编排器
"""

from typing import Dict, Any
from .domain import TradingContext, TradingConfig
from .orchestrator import TradingLoopOrchestrator


class TradingContextFactory:
    """交易上下文工厂"""
    
    @staticmethod
    def create_from_dict(username: str, user_id: str, config_dict: Dict[str, Any], exchange) -> TradingContext:
        """
        从字典创建交易上下文
        
        Args:
            username: 用户名
            user_id: 用户ID
            config_dict: 配置字典
            exchange: 交易所适配器
            
        Returns:
            交易上下文
        """
        # 创建配置对象
        config_kwargs: Dict[str, Any] = {
            'symbol': config_dict['symbol'],
            'exchange': config_dict.get('exchange', 'unknown'),
            'quantity': config_dict['quantity'],
            'interval': config_dict.get('interval', 1),
            'offset_percent': config_dict.get('offset_percent', -0.1),
            'sell_offset_percent': config_dict.get('sell_offset_percent', 0.5),
            'order_grid': config_dict.get('order_grid', 1),
            'sell_decay_count': config_dict.get('sell_decay_count', 0),
            'reprice_threshold_percent': config_dict.get('reprice_threshold_percent', 0.01),
            'simulate_trading': config_dict.get('simulate_trading', 0),
        }

        if config_dict.get('stop_loss_delay') is not None:
            config_kwargs['stop_loss_delay'] = config_dict.get('stop_loss_delay')

        if config_dict.get('min_price_threshold') is not None:
            config_kwargs['min_price_threshold'] = config_dict.get('min_price_threshold')

        config = TradingConfig(**config_kwargs)
        
        # 验证配置
        errors = config.validate()
        if errors:
            raise ValueError(f"配置验证失败: {', '.join(errors)}")
        
        # 创建上下文
        context = TradingContext(
            username=username,
            user_id=user_id,
            config=config,
            exchange=exchange
        )
        
        return context
    
    @staticmethod
    def create_orchestrator(context: TradingContext) -> TradingLoopOrchestrator:
        """
        创建编排器
        
        Args:
            context: 交易上下文
            
        Returns:
            交易循环编排器
        """
        return TradingLoopOrchestrator(context)
