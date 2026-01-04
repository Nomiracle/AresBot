import sys
from py_clob_client.client import ClobClient

# 从命令行获取私钥
if len(sys.argv) < 2:
    print("使用方法: python testpmwebsocket.py <private_key>")
    print("示例: python testpmwebsocket.py 0x1234...")
    sys.exit(1)

key: str = sys.argv[1]  # 从命令行参数获取私钥
host: str = "https://clob.polymarket.com"
chain_id: int = 137
POLYMARKET_PROXY_ADDRESS: str = ''

# 移除 0x 前缀(如果有)
if key.startswith('0x'):
    key = key[2:]

# 使用 Proxy Wallet 模式初始化
client = ClobClient(host, key=key, chain_id=chain_id, signature_type=2, funder=POLYMARKET_PROXY_ADDRESS)

# 获取 API 凭证
api_creds = client.create_or_derive_api_creds()
print(f"API Key: {api_creds.api_key}")
print(f"API Secret: {api_creds.api_secret}")
print(f"API Passphrase: {api_creds.api_passphrase}")

from websocket import WebSocketApp
import json
import time
import threading

MARKET_CHANNEL = "market"
USER_CHANNEL = "user"


class WebSocketOrderBook:
    def __init__(self, channel_type, url, data, auth, message_callback, verbose):
        self.channel_type = channel_type
        self.url = url
        self.data = data
        self.auth = auth
        self.message_callback = message_callback
        self.verbose = verbose
        furl = url + "/ws/" + channel_type
        self.ws = WebSocketApp(
            furl,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open,
        )
        self.orderbooks = {}

    def on_message(self, ws, message):
        if message == "PONG":
            print(".", end="", flush=True)  # 心跳响应
            return
        print(f"\n收到消息: {message}")

    def on_error(self, ws, error):
        print(f"\n❌ WebSocket 错误: {error}")
        print(f"错误类型: {type(error)}")
        import traceback
        traceback.print_exc()

    def on_close(self, ws, close_status_code, close_msg):
        print(f"\n🔌 WebSocket 已关闭")
        print(f"状态码: {close_status_code}, 消息: {close_msg}")

    def on_open(self, ws):
        print(f"✅ WebSocket 已连接到 {self.channel_type} 频道")
        
        if self.channel_type == MARKET_CHANNEL:
            subscribe_msg = {"assets_ids": self.data, "type": MARKET_CHANNEL}
            print(f"📡 发送订阅消息: {subscribe_msg}")
            ws.send(json.dumps(subscribe_msg))
        elif self.channel_type == USER_CHANNEL and self.auth:
            subscribe_msg = {"markets": self.data, "type": USER_CHANNEL, "auth": self.auth}
            print(f"📡 发送订阅消息 (带认证)")
            ws.send(json.dumps(subscribe_msg))
        else:
            print("❌ 无效的频道类型")
            exit(1)

        print("🔄 启动心跳线程...")
        thr = threading.Thread(target=self.ping, args=(ws,))
        thr.daemon = True
        thr.start()

    def subscribe_to_tokens_ids(self, assets_ids):
        if self.channel_type == MARKET_CHANNEL:
            self.ws.send(json.dumps({"assets_ids": assets_ids, "operation": "subscribe"}))

    def unsubscribe_to_tokens_ids(self, assets_ids):
        if self.channel_type == MARKET_CHANNEL:
            self.ws.send(json.dumps({"assets_ids": assets_ids, "operation": "unsubscribe"}))


    def ping(self, ws):
        while True:
            ws.send("PING")
            time.sleep(10)

    def run(self):
        print(f"🔗 正在连接到: {self.url}/ws/{self.channel_type}")
        # 添加超时和重连设置
        self.ws.run_forever(
            ping_interval=10,
            ping_timeout=5,
            reconnect=3  # 重连次数
        )


if __name__ == "__main__":
    url = "wss://ws-subscriptions-clob.polymarket.com"

    # 使用从 client 获取的 API 凭证
    auth = {
        "apiKey": api_creds.api_key,
        "secret": api_creds.api_secret,
        "passphrase": api_creds.api_passphrase
    }

    asset_ids = [
        "77782241916139876608322118102070152444730633943431637211356496455406423367745",
    ]
    condition_ids = []  # 用户频道不需要过滤特定 condition

    print("\n开始连接 WebSocket...")
    print(f"订阅市场 Token ID: {asset_ids[0]}")

    market_connection = WebSocketOrderBook(
        MARKET_CHANNEL, url, asset_ids, auth, None, True
    )
    user_connection = WebSocketOrderBook(
        USER_CHANNEL, url, condition_ids, auth, None, True
    )

    # 可选: 订阅/取消订阅其他 token
    # market_connection.subscribe_to_tokens_ids(["123"])
    # market_connection.unsubscribe_to_tokens_ids(["123"])

    # 运行市场数据 WebSocket
    print("\n运行市场数据 WebSocket (按 Ctrl+C 退出)...")
    market_connection.run()

    # 或运行用户订单 WebSocket
    # user_connection.run()