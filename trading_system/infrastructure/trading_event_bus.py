"""
交易事件总线
"""

from typing import Callable, Dict, List, Any
from threading import Lock


class TradingEventBus:
    """交易事件总线 - 发布/订阅模式"""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = Lock()
    
    def subscribe(self, event_type: str, handler: Callable) -> None:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 事件处理器
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """
        取消订阅
        
        Args:
            event_type: 事件类型
            handler: 事件处理器
        """
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type].remove(handler)
    
    def publish(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        with self._lock:
            handlers = self._subscribers.get(event_type, []).copy()
        
        for handler in handlers:
            try:
                handler(event_data)
            except Exception as e:
                print(f"事件处理器错误 [{event_type}]: {e}")
    
    def clear(self) -> None:
        """清除所有订阅"""
        with self._lock:
            self._subscribers.clear()
