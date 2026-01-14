"""
订单状态枚举
"""

from enum import Enum, auto


class OrderState(Enum):
    """订单状态"""
    PENDING = auto()      # 待下单
    PLACED = auto()       # 已下单
    FILLED = auto()       # 已成交
    CANCELLED = auto()    # 已取消
    REPRICING = auto()    # 改价中
    FAILED = auto()       # 失败


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"
