"""
交易所工厂类
根据配置创建对应的交易所适配器实例
"""
from typing import Optional
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
    
    # 命名规则: 框架_交易所_市场
    # 框架: native(原生SDK) / ccxt
    # 交易所: binance / backpack / polymarket / ...
    # 市场: spot(现货) / futures(合约) / futures_short(合约做空)
    SUPPORTED_EXCHANGES = {
        # Native SDK 实现
        'native_polymarket_spot': NativePolymarketSpot,
        'native_updown_15m': UpDown15m,
        'native_btc_updown_15m': BtcUpDown15m,  # 向后兼容
        'native_updown_4h': UpDown4h,
        # CCXT 实现
        'ccxt_binance_spot': CcxtBinanceSpot,
        'ccxt_binance_futures': CcxtBinanceFutures,
        'ccxt_binance_futures_short': CcxtBinanceFuturesShort,
        'ccxt_backpack_spot': CcxtBackpackSpot,
        # 兼容旧名称（别名）
        'polymarket': NativePolymarketSpot,
        'updown_15m': UpDown15m,
        'btc_updown_15m': BtcUpDown15m,  # 向后兼容
        'updown_4h': UpDown4h,
        'ccxt_futures': CcxtBinanceFutures,
        'ccxt_binance': CcxtBinanceSpot,
        'backpack': CcxtBackpackSpot,
        'bpx': CcxtBackpackSpot,
    }
    
    @classmethod
    def create(cls, exchange_name: str, api_key: str, api_secret: str, 
               symbol: str, testnet: bool = True,
               min_price_threshold: float = None, market_close_threshold: int = None) -> Optional[BaseExchange]:
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
            
        Returns:
            BaseExchange 实例，如果不支持则返回 None
        """
        adapter_class = cls.SUPPORTED_EXCHANGES.get(exchange_name.lower())
        if adapter_class:
            # UpDown15m/UpDown4h 使用额外的阈值参数
            if adapter_class in (UpDown15m, BtcUpDown15m, UpDown4h):
                return adapter_class(api_key, api_secret, symbol, testnet,
                                    min_price_threshold=min_price_threshold,
                                    market_close_threshold=market_close_threshold)
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
        return list(cls.SUPPORTED_EXCHANGES.keys())
