"""
测试 Polymarket 连接
"""
import sys
import requests

def test_http_connection():
    """测试 HTTP 连接"""
    print("测试 HTTP 连接到 Polymarket...")
    try:
        response = requests.get("https://clob.polymarket.com/ok", timeout=10)
        print(f"✅ HTTP 连接成功: {response.status_code}")
        print(f"响应: {response.text}")
        return True
    except Exception as e:
        print(f"❌ HTTP 连接失败: {e}")
        return False

def test_websocket_connection():
    """测试 WebSocket 连接"""
    print("\n测试 WebSocket 连接...")
    try:
        import websocket
        
        def on_open(ws):
            print("✅ WebSocket 连接成功")
            ws.close()
        
        def on_error(ws, error):
            print(f"❌ WebSocket 错误: {error}")
        
        def on_close(ws, status, msg):
            print(f"🔌 WebSocket 已关闭")
        
        ws = websocket.WebSocketApp(
            "wss://ws-subscriptions-clob.polymarket.com/ws/market",
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )
        
        # 设置超时
        ws.run_forever(ping_timeout=10, timeout=10)
        
    except Exception as e:
        print(f"❌ WebSocket 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Polymarket 连接测试")
    print("=" * 60)
    
    # 测试 HTTP
    http_ok = test_http_connection()
    
    if http_ok:
        # 测试 WebSocket
        test_websocket_connection()
    else:
        print("\n⚠️ HTTP 连接失败,可能需要配置代理")
        print("如果在中国大陆,可能需要使用代理访问 Polymarket")
