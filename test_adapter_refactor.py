"""
测试 adapter 重构后的功能
验证价格监听和订单监听是否正常工作
"""
import time
from exchanges.binance_adapter import BinanceAdapter
from exchanges.backpack_adapter import BackpackAdapter

def test_binance_adapter():
    """测试 Binance adapter 的监听功能"""
    print("=" * 60)
    print("测试 Binance Adapter")
    print("=" * 60)
    
    # 使用测试网配置（需要替换为真实的测试网密钥）
    adapter = BinanceAdapter(
        api_key="your_testnet_api_key",
        api_secret="your_testnet_api_secret",
        testnet=True
    )
    
    # 价格更新回调
    price_count = [0]
    def on_price_update(price: float):
        price_count[0] += 1
        if price_count[0] <= 3:  # 只打印前3次
            print(f"✅ 价格更新: {price}")
    
    # 订单更新回调
    def on_order_update(event: dict):
        print(f"✅ 订单更新: {event}")
    
    # 启动监听
    print("\n启动价格监听...")
    price_ok = adapter.start_price_monitor("BTCUSDT", on_price_update)
    print(f"价格监听启动: {'成功' if price_ok else '失败'}")
    
    print("\n启动订单监听...")
    order_ok = adapter.start_order_monitor("BTCUSDT", on_order_update)
    print(f"订单监听启动: {'成功' if order_ok else '失败'}")
    
    # 等待一段时间接收更新
    print("\n等待 5 秒接收更新...")
    time.sleep(5)
    
    # 停止监听
    print("\n停止监听...")
    adapter.stop_price_monitor()
    adapter.stop_order_monitor()
    print("监听已停止")
    
    print(f"\n总共接收到 {price_count[0]} 次价格更新")


def test_backpack_adapter():
    """测试 Backpack adapter 的监听功能"""
    print("\n" + "=" * 60)
    print("测试 Backpack Adapter")
    print("=" * 60)
    
    # 使用配置（需要替换为真实的密钥）
    adapter = BackpackAdapter(
        api_key="your_backpack_public_key",
        api_secret="your_backpack_secret_key",
        testnet=False
    )
    
    # 价格更新回调
    price_count = [0]
    def on_price_update(price: float):
        price_count[0] += 1
        if price_count[0] <= 3:  # 只打印前3次
            print(f"✅ 价格更新: {price}")
    
    # 订单更新回调
    def on_order_update(event: dict):
        print(f"✅ 订单更新: {event}")
    
    # 启动监听
    print("\n启动价格监听...")
    price_ok = adapter.start_price_monitor("SOL_USDC", on_price_update)
    print(f"价格监听启动: {'成功' if price_ok else '失败'}")
    
    print("\n启动订单监听...")
    order_ok = adapter.start_order_monitor("SOL_USDC", on_order_update)
    print(f"订单监听启动: {'成功' if order_ok else '失败'}")
    
    # 等待一段时间接收更新
    print("\n等待 5 秒接收更新...")
    time.sleep(5)
    
    # 测试 check_pending_orders
    print("\n测试 check_pending_orders...")
    pending_orders = []  # 空列表测试
    filled = adapter.check_pending_orders(pending_orders)
    print(f"已成交订单: {filled}")
    
    # 停止监听
    print("\n停止监听...")
    adapter.stop_price_monitor()
    adapter.stop_order_monitor()
    print("监听已停止")
    
    print(f"\n总共接收到 {price_count[0]} 次价格更新")


if __name__ == "__main__":
    print("⚠️ 注意：此测试需要真实的 API 密钥才能运行")
    print("⚠️ 请在代码中替换 'your_*_key' 为真实密钥\n")
    
    # 取消注释以运行测试
    # test_binance_adapter()
    # test_backpack_adapter()
    
    print("\n✅ 测试脚本已准备就绪")
    print("📝 重构总结:")
    print("   1. BaseExchange 添加了统一的监听接口")
    print("   2. BinanceAdapter 使用 WebSocket 实现监听")
    print("   3. BackpackAdapter 使用 HTTP 轮询实现监听")
    print("   4. trading.py 不再关心连接实现细节")
