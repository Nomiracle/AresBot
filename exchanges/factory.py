"""
交易所工厂类
根据配置创建对应的交易所适配器实例
"""
from typing import Optional
from .base import BaseExchange
from .binance_adapter import BinanceAdapter
from .backpack_adapter import BackpackAdapter

class ExchangeFactory:
    """交易所工厂"""
    
    SUPPORTED_EXCHANGES = {
        'binance': BinanceAdapter,
        'backpack': BackpackAdapter,
        'bpx': BackpackAdapter,  # 别名
        # 未来可以添加其他交易所
        # 'okx': OKXAdapter,
        # 'bybit': BybitAdapter,
    }
    
    @classmethod
    def create(cls, exchange_name: str, api_key: str, api_secret: str, 
               testnet: bool = True, **kwargs) -> Optional[BaseExchange]:
        """创建交易所适配器实例
        
        Args:
            exchange_name: 交易所名称 ('binance', 'okx', etc.)
            api_key: API密钥
            api_secret: API密钥
            testnet: 是否使用测试网
            **kwargs: 其他交易所特定参数
            
        Returns:
            BaseExchange 实例，如果不支持则返回 None
        """
        adapter_class = cls.SUPPORTED_EXCHANGES.get(exchange_name.lower())
        if adapter_class:
            return adapter_class(api_key, api_secret, testnet, **kwargs)
        return None
    
    @classmethod
    def get_supported_exchanges(cls) -> list:
        """获取支持的交易所列表"""
        return list(cls.SUPPORTED_EXCHANGES.keys())
