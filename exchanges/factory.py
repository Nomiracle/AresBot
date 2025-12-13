"""
交易所工厂类
根据配置创建对应的交易所适配器实例
"""
from typing import Optional
from .base import BaseExchange
from .binance_adapterv2 import BinanceAdapter
from .binance_futures_adapter import BinanceFuturesAdapter
from .backpack_adapter import BackpackAdapter
from .ccxt_futures_adapter import CcxtFuturesAdapter
from .ccxt_binance_adapter import CcxtBinanceAdapter

class ExchangeFactory:
    """交易所工厂"""
    
    SUPPORTED_EXCHANGES = {
        'binance': BinanceAdapter,
        'binance_futures': BinanceFuturesAdapter,
        'binance-futures': BinanceFuturesAdapter,  # 别名
        'backpack': BackpackAdapter,
        'bpx': BackpackAdapter,  # 别名
        'ccxt_futures': CcxtFuturesAdapter,
        'ccxt-futures': CcxtFuturesAdapter,  # 别名
        'ccxt_binance': CcxtBinanceAdapter,
        'ccxt-binance': CcxtBinanceAdapter,  # 别名
        # 未来可以添加其他交易所
        # 'okx': OKXAdapter,
        # 'bybit': BybitAdapter,
    }
    
    @classmethod
    def create(cls, exchange_name: str, api_key: str, api_secret: str, 
               symbol: str, testnet: bool = True) -> Optional[BaseExchange]:
        """创建交易所适配器实例
        
        Args:
            exchange_name: 交易所名称 ('binance', 'backpack', etc.)
            api_key: API密钥
            api_secret: API密钥
            symbol: 交易对（如 BTCUSDT）
            testnet: 是否使用测试网
            
        Returns:
            BaseExchange 实例，如果不支持则返回 None
        """
        adapter_class = cls.SUPPORTED_EXCHANGES.get(exchange_name.lower())
        if adapter_class:
            return adapter_class(api_key, api_secret, symbol, testnet)
        return None
    
    @classmethod
    def get_supported_exchanges(cls) -> list:
        """获取支持的交易所列表"""
        return list(cls.SUPPORTED_EXCHANGES.keys())
