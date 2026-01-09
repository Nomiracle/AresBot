"""
交易所工厂类
根据配置创建对应的交易所适配器实例
"""
from typing import Optional, Dict
from .base import BaseExchange
from .polymarket_adapter import NativePolymarketSpot
from .polymarket_updown15m_adapter import UpDown15m, BtcUpDown15m
from .polymarket_updown4h_adapter import UpDown4h
from .ccxt_binance_futures_adapter import CcxtBinanceFutures
from .ccxt_binance_spot_adapter import CcxtBinanceSpot
from .ccxt_binance_futures_short_adapter import CcxtBinanceFuturesShort
from .ccxt_backpack_spot_adapter import CcxtBackpackSpot

class ExchangeFactory:
    """交易所工厂"""
    
    # 支持的交易所适配器类列表
    ADAPTER_CLASSES = [
        NativePolymarketSpot,
        UpDown15m,
        BtcUpDown15m,  # 向后兼容
        UpDown4h,
        CcxtBinanceSpot,
        CcxtBinanceFutures,
        CcxtBinanceFuturesShort,
        CcxtBackpackSpot,
    ]
    
    # 兼容旧名称的映射
    ALIAS_MAP = {
        'polymarket': 'native_polymarket_spot',
        'updown_15m': 'native_updown_15m',
        'btc_updown_15m': 'native_btc_updown_15m',
        'updown_4h': 'native_updown_4h',
        'ccxt_futures': 'ccxt_binance_futures',
        'ccxt_binance': 'ccxt_binance_spot',
        'backpack': 'ccxt_backpack_spot',
        'bpx': 'ccxt_backpack_spot',
    }
    
    @classmethod
    def get_exchange_id_map(cls) -> Dict[str, type]:
        """获取交易所ID到适配器类的映射"""
        id_map = {}
        for adapter_class in cls.ADAPTER_CLASSES:
            info = adapter_class.get_exchange_info()
            id_map[info['id']] = adapter_class
        return id_map
    
    @classmethod
    def create(cls, exchange_name: str, api_key: str, api_secret: str, 
               symbol: str, testnet: bool = True,
               min_price_threshold: float = None, market_close_threshold: int = None,
               username: str = None) -> Optional[BaseExchange]:
        """创建交易所适配器实例
        
        Args:
            exchange_name: 交易所名称 (如 'ccxt_binance_futures', 'polymarket', etc.)
                          做空适配器使用 '_short' 或 '-short' 后缀
                          例如: 'ccxt_futures_short'
            api_key: API密钥
            api_secret: API密钥
            symbol: 交易对（如 BTCUSDT）
                   对于 btc_updown_15m，symbol 应为 "Up" 或 "Down"
            testnet: 是否使用测试网
            min_price_threshold: 最低价格阈值（仅 Polymarket 类适配器使用）
            market_close_threshold: 市场关闭前阈值秒数（仅 UpDown15m 使用）
            username: 用户名（用于通知等功能）
            
        Returns:
            BaseExchange 实例，如果不支持则返回 None
        """
        # 首先检查是否是别名
        exchange_name = cls.ALIAS_MAP.get(exchange_name.lower(), exchange_name.lower())
        
        # 获取交易所ID映射
        id_map = cls.get_exchange_id_map()
        adapter_class = id_map.get(exchange_name)
        
        if adapter_class:
            # UpDown15m/UpDown4h 使用额外的阈值参数
            if adapter_class in (UpDown15m, BtcUpDown15m, UpDown4h):
                return adapter_class(api_key, api_secret, symbol, testnet,
                                    min_price_threshold=min_price_threshold,
                                    market_close_threshold=market_close_threshold,
                                    username=username)
            # Polymarket 使用价格阈值参数
            elif adapter_class == NativePolymarketSpot:
                return adapter_class(api_key, api_secret, symbol, testnet,
                                    min_price_threshold=min_price_threshold)
            else:
                return adapter_class(api_key, api_secret, symbol, testnet)
        return None
    
    @classmethod
    def get_supported_exchanges(cls) -> list:
        """获取支持的交易所列表"""
        id_map = cls.get_exchange_id_map()
        return list(id_map.keys())
