"""
测试 Polymarket WebSocket 订阅功能
"""
import time
from exchanges.polymarket_adapter import NativePolymarketSpot

# 配置信息 (请替换为你的实际配置)
API_KEY = "your_proxy_wallet_address"  # Polymarket Proxy Wallet 地址
API_SECRET = "your_private_key"  # MetaMask 私钥
TOKEN_ID = "your_token_id"  # 市场 token_id

def test_market_ws():
    """测试市场数据 WebSocket"""
    print("=" * 50)
    print("测试市场数据 WebSocket")
    print("=" * 50)
    
    # 创建客户端
    client = NativePolymarketSpot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol=TOKEN_ID,
        testnet=False
    )
    
    # 定义回调函数
    def on_market_data(data):
        print(f"\n📊 收到市场数据:")
        print(f"  - 类型: {data.get('type')}")
        print(f"  - 数据: {data}")
    
    # 订阅市场数据
    client.subscribe_market_ws(callback=on_market_data)
    
    # 运行 30 秒
    print("\n等待市场数据... (30秒)")
    time.sleep(30)
    
    # 取消订阅
    client.unsubscribe_market_ws()
    print("\n✅ 市场数据测试完成")

def test_user_ws():
    """测试用户订单 WebSocket"""
    print("\n" + "=" * 50)
    print("测试用户订单 WebSocket")
    print("=" * 50)
    
    # 创建客户端
    client = NativePolymarketSpot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol=TOKEN_ID,
        testnet=False
    )
    
    # 定义回调函数
    def on_order_update(event):
        print(f"\n📬 收到订单更新:")
        print(f"  - 订单ID: {event.get('order_id')}")
        print(f"  - 状态: {event.get('status')}")
        print(f"  - 方向: {event.get('side')}")
        print(f"  - 价格: {event.get('price')}")
        print(f"  - 数量: {event.get('size')}")
        print(f"  - 已成交: {event.get('filled')}")
    
    # 订阅用户订单
    client.subscribe_user_ws(callback=on_order_update)
    
    # 运行 30 秒
    print("\n等待订单更新... (30秒)")
    print("提示: 在 Polymarket 网站上下单以触发订单更新")
    time.sleep(30)
    
    # 取消订阅
    client.unsubscribe_user_ws()
    print("\n✅ 用户订单测试完成")

def test_both_ws():
    """同时测试市场数据和用户订单 WebSocket"""
    print("\n" + "=" * 50)
    print("同时测试市场数据和用户订单 WebSocket")
    print("=" * 50)
    
    # 创建客户端
    client = NativePolymarketSpot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol=TOKEN_ID,
        testnet=False
    )
    
    # 定义回调函数
    def on_market_data(data):
        print(f"\n📊 市场数据: {data.get('type')}")
    
    def on_order_update(event):
        print(f"\n📬 订单更新: {event.get('order_id')} - {event.get('status')}")
    
    # 同时订阅
    client.subscribe_market_ws(callback=on_market_data)
    client.subscribe_user_ws(callback=on_order_update)
    
    # 运行 60 秒
    print("\n等待数据... (60秒)")
    time.sleep(60)
    
    # 取消订阅
    client.stop_ws()
    print("\n✅ 综合测试完成")

if __name__ == "__main__":
    print("Polymarket WebSocket 测试")
    print("请先修改脚本中的配置信息!")
    print()
    
    # 选择测试
    print("选择测试:")
    print("1. 测试市场数据 WebSocket")
    print("2. 测试用户订单 WebSocket")
    print("3. 同时测试两者")
    
    choice = input("\n请输入选择 (1/2/3): ").strip()
    
    if choice == "1":
        test_market_ws()
    elif choice == "2":
        test_user_ws()
    elif choice == "3":
        test_both_ws()
    else:
        print("无效选择")
