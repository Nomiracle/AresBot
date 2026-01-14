"""
通知服务
"""

import threading
from datetime import datetime
from typing import Optional


class NotificationService:
    """通知服务 - 异步发送通知"""
    
    def __init__(self, username: str):
        """
        初始化通知服务
        
        Args:
            username: 用户名
        """
        self.username = username
    
    def send_order_notification(
        self,
        side: str,
        symbol: str,
        price: float,
        quantity: float,
        order_id: str,
        market_info: Optional[str] = None,
        cost_info: Optional[str] = None
    ) -> None:
        """
        发送订单成交通知（异步执行）
        
        Args:
            side: 订单方向 ('BUY' 或 'SELL')
            symbol: 交易对
            price: 成交价格
            quantity: 成交数量
            order_id: 订单号
            market_info: 市场信息（可选）
            cost_info: 成本信息（可选）
        """
        if not self.username:
            return
        
        def _send():
            try:
                from notification import DingTalkNotification
                
                notifier = DingTalkNotification(username=self.username)
                side_emoji = "🟢" if side == 'BUY' else "🔴"
                side_text = "买" if side == 'BUY' else "卖"
                
                # 构建消息
                time_str = datetime.now().strftime("%H:%M:%S")
                msg = f"[{time_str}] {side_emoji} {symbol} {side_text} {price}"
                
                # 添加成本信息（卖单时显示）
                if cost_info:
                    msg = f"{msg} ({cost_info})"
                
                msg = f"{msg}@{quantity} - {order_id}"
                
                # 添加市场信息
                if market_info:
                    msg = f"[{market_info}] {msg}"
                
                notifier.send(msg)
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ⚠️ 发送钉钉通知失败: {e}")
        
        threading.Thread(target=_send, daemon=True).start()
