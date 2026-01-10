# ccxt_backpack_spot_adapter.py - 使用 ccxt pro WebSocket 实现的 Backpack 现货适配器
from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict

import ccxt.pro as ccxtpro
import ccxt

from .ccxt_binance_spot_adapter import CcxtBinanceSpot


class CcxtBackpackSpot(CcxtBinanceSpot):
    """使用 ccxt 实现的 Backpack 现货交易适配器
    
    继承自 CcxtBinanceSpot，只需重写交易所特定的部分
    交易所名称: ccxt-backpack
    """

    def _create_sync_client(self, api_key: str, api_secret: str, testnet: bool):
        """创建 ccxt backpack 现货同步客户端（用于 REST 调用）"""
        print(f"{self._get_log_prefix()} 🔧 创建同步客户端: testnet={testnet}")
        client = ccxt.backpack({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": 15000,
        })
        # Backpack 没有测试网
        if testnet:
            print(f"{self._get_log_prefix()} ⚠️ Backpack 不支持测试网，使用生产环境")
        return client

    def _create_ws_client(self, api_key: str, api_secret: str, testnet: bool):
        """创建 ccxt pro backpack 现货异步客户端（用于 WebSocket）"""
        print(f"{self._get_log_prefix()} 🔧 创建WebSocket客户端: testnet={testnet}")
        client = ccxtpro.backpack({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })
        if testnet:
            print(f"{self._get_log_prefix()} ⚠️ Backpack 不支持测试网，使用生产环境")
        return client

    def _get_log_prefix(self) -> str:
        """生成日志前缀"""
        api_key_short = self.api_key[:6] if self.api_key else "NOKEY"
        return f"[{datetime.now().isoformat()}] [ccxt-backpack-{api_key_short}-{self.symbol}]"

    def cancel_replace_order(
        self,
        side: str,
        order_type: str,
        quantity: float,
        price: str,
        cancel_order_id: str,
        **kwargs,
    ) -> Dict:
        """取消并替换订单（Backpack 强制使用取消+新建模式）
        
        重写父类方法，强制使用 notusews=True，因为 Backpack 可能不支持 WebSocket 原子改单
        """
        print(f"{self._get_log_prefix()} 🔄 Backpack 取消并替换订单: cancel_id={cancel_order_id}, side={side}, qty={quantity}, price={price}")
        # 调用父类方法，强制使用取消+新建模式
        return super().cancel_replace_order(
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            cancel_order_id=cancel_order_id,
            notusews=True,  # 强制使用取消+新建模式
            **kwargs
        )

    @classmethod
    def get_exchange_info(cls) -> Dict:
        """获取交易所信息（类方法）"""
        return {
            'id': 'ccxt_backpack_spot',
            'name': 'Backpack-现货',
            'description': 'Backpack Exchange Spot Trading (CCXT)'
        }
