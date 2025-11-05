import json
import asyncio
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from typing import Callable, Optional, Dict, Any
from cryptography.hazmat.primitives.asymmetric import ed25519
import base64
from typing import Dict, Any, List, Optional
from time import time

class BackpackWsAccount:
    """
    Base class for public WebSocket connections
    Provides methods to generate subscription messages for public streams
    """
    WS_URL = "wss://ws.backpack.exchange/"

    def __init__(self,symbol: str="",public_key: str="", secret_key: str="", window: int = 5000,
                    on_error: Optional[Callable] = None,
                    on_close: Optional[Callable] = None, 
                    on_open: Optional[Callable] = None):
        """
        Initialize async WebSocket public client (Singleton)
        
        Args:
            on_message: Async callback function for messages
            on_error: Async callback function for errors
            on_close: Async callback function for connection close
            on_open: Async callback function for connection open
        """
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self.symbol = symbol
        self.ws = None
        self.on_error_callback = on_error
        self.on_close_callback = on_close
        self.on_open_callback = on_open
        self.window = window
        self.debug = False
        self._initialized = True
        self.asyncios = {}

        if public_key != "" and secret_key != "":
            self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
                base64.b64decode(secret_key)
            )
            self.public_key = public_key

    
    def get_ws_url(self) -> str:
        """
        Returns the WebSocket URL for public streams
        """
        return self.WS_URL

    async def connect(self):
        """
        Establish WebSocket connection and start listening (only once)
        """
        try:
            self.ws = await websockets.connect(self.get_ws_url())
            if self.on_open_callback:
                self.on_open_callback()
        except Exception as e:
            if self.on_error_callback:
                self.on_error_callback(e)

    """
{
  "e": "bookTicker",          // Event type
  "E": 1694687965941000,      // Event time in microseconds
  "s": "SOL_USDC",            // Symbol
  "a": "18.70",               // Inside ask price
  "A": "1.000",               // Inside ask quantity
  "b": "18.67",               // Inside bid price
  "B": "2.000",               // Inside bid quantity
  "u": "111063070525358080",  // Update ID of event
  "T": 1694687965940999       // Engine timestamp in microseconds
}
    """
    async def subscribe_markPrice(self, on_message: Optional[Callable] = None):
        """订阅标记价格流
        
        Args:
            on_message: 消息回调函数
        """
        # Subscribe to the mark price stream
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": [f"bookTicker.{self.symbol}"]
        }
        print(f"subscribe_message: {subscribe_message}")
        await self.ws.send(json.dumps(subscribe_message))
        
        # 创建后台任务处理消息
        async def _message_loop():
            try:
                while True:
                    response = await self.ws.recv()
                    msg = json.loads(response)
                    # Backpack 返回格式: {'data': {...}, 'stream': '...'}
                    data = msg.get('data', msg)
                    if on_message and data.get("e") == "bookTicker" and data.get("s") == self.symbol:
                        on_message(msg)
            except asyncio.CancelledError:
                print(f"订阅 bookTicker.{self.symbol} 已取消")
            except (ConnectionClosedError, ConnectionClosedOK) as e:
                print(f"订阅 bookTicker.{self.symbol} 连接已关闭: {e}")
            except Exception as e:
                print(f"订阅 bookTicker.{self.symbol} 发生错误: {e}")
                if self.on_error_callback:
                    self.on_error_callback(e)
        
        # 将消息循环包装在 asyncio.create_task 中
        if "markPrice" not in self.asyncios:
            print(f"markPrice 不存在")
        else:
            print(f"markPrice 已存在")
            self.asyncios["markPrice"].cancel()
        self.asyncios["markPrice"] = asyncio.create_task(_message_loop())
    
    def _sign_ws_auth(self, timestamp: int) -> str:
        """
        Sign WebSocket authentication message
        
        Args:
            timestamp: Current timestamp in milliseconds
        
        Returns:
            Base64 encoded signature
        """
        sign_str = f"instruction=subscribe&timestamp={timestamp}&window={self.window}"
        
        if self.debug:
            print(f"WS Sign String: {sign_str}")
        
        signature_bytes = self.private_key.sign(sign_str.encode())
        encoded_signature = base64.b64encode(signature_bytes).decode()
        return encoded_signature

    async def subscribe_account_order_update(self, on_message: Optional[Callable] = None):
        """订阅账户订单更新
        
        Args:
            on_message: 消息回调函数
        """
        # Subscribe to account order updates (需要认证)
        timestamp = int(time() * 1e3)
        signature = self._sign_ws_auth(timestamp)
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": ["account.orderUpdate"],
            "signature": [self.public_key, signature, str(timestamp), str(self.window)]
        }
        print(f"subscribe_message: {subscribe_message}")
        await self.ws.send(json.dumps(subscribe_message))
        
        # 创建后台任务处理消息
        async def _message_loop():
            try:
                while True:
                    response = await self.ws.recv()
                    msg = json.loads(response)
                    # Backpack 返回格式: {'data': {...}, 'stream': '...'}
                    data = msg.get('data', msg)
                    if on_message and data.get("e") == "orderUpdate":
                        on_message(msg)
            except asyncio.CancelledError:
                print(f"订阅 account.orderUpdate 已取消")
            except (ConnectionClosedError, ConnectionClosedOK) as e:
                print(f"订阅 account.orderUpdate 连接已关闭: {e}")
            except Exception as e:
                print(f"订阅 account.orderUpdate 发生错误: {e}")
                if self.on_error_callback:
                    self.on_error_callback(e)
        
        # 将消息循环包装在 asyncio.create_task 中
        key = "subscribe_account_order_update"
        if key not in self.asyncios:
            print(f"{key} 不存在")
        else:
            print(f"{key} 已存在")
            self.asyncios[key].cancel()
        self.asyncios[key] = asyncio.create_task(_message_loop())


    def clean_up(self):
        """清理所有后台任务"""
        for key in self.asyncios:
            self.asyncios[key].cancel()
        self.asyncios = {}
