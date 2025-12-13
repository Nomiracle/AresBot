"""
ccxt pro 币安合约适配器验证脚本（WebSocket 模式）

用法：
  1. 安装依赖：pip install ccxt
  2. 运行：python test_ccxt_futures.py

注意：
  - 公开接口（ping/ticker/symbol_info）无需 API key
  - WebSocket 监控（watchTicker/watchOrders）需要真实 API key
  - 如果网络无法直连 Binance，请配置代理
"""

import time
from exchanges.ccxt_futures_adapter import CcxtFuturesAdapter


def test_public_api():
    """测试公开 REST 接口"""
    print("=" * 60)
    print("【公开 REST 接口测试】")
    print("=" * 60)

    adapter = CcxtFuturesAdapter(
        api_key="",
        api_secret="",
        symbol="BTCUSDT",
        testnet=False
    )

    print("\n1. ping 测试（加载市场信息）")
    ok = adapter.ping()
    print(f"   结果: {'✅ 成功' if ok else '❌ 失败'}")

    if not ok:
        print("   ⚠️ 无法连接 Binance，请检查网络或配置代理")
        return False

    print("\n2. 获取交易对信息")
    info = adapter.get_symbol_info()
    print(f"   symbol: {info.get('symbol', 'N/A')}")
    print(f"   precision: {info.get('precision', {})}")

    print("\n3. 获取当前价格（REST）")
    ticker = adapter.get_symbol_ticker()
    print(f"   {ticker}")

    print("\n4. 获取价格/数量精度")
    tick_size, price_decimals = adapter.get_price_precision(info)
    step_size, qty_decimals = adapter.get_quantity_precision(info)
    print(f"   tick_size={tick_size}, price_decimals={price_decimals}")
    print(f"   step_size={step_size}, qty_decimals={qty_decimals}")

    print("\n✅ 公开 REST 接口验证完成")
    return True


def test_websocket():
    """测试 WebSocket 实时推送（需要 API key）"""
    print("\n" + "=" * 60)
    print("【WebSocket 实时推送测试】")
    print("=" * 60)

    # ⚠️ 请填入你的 API key/secret
    API_KEY = ""
    API_SECRET = ""

    if not API_KEY or not API_SECRET:
        print("\n⚠️ 请在代码中填入 API_KEY 和 API_SECRET 后再运行 WebSocket 测试")
        print("   位置：test_ccxt_futures.py -> test_websocket() 函数")
        return

    adapter = CcxtFuturesAdapter(
        api_key=API_KEY,
        api_secret=API_SECRET,
        symbol="BTCUSDT",
        testnet=True  # 建议先用测试网
    )

    price_updates = []
    order_updates = []

    def on_price(price: float):
        price_updates.append(price)
        print(f"   💰 价格更新: {price}")

    def on_order(event: dict):
        order_updates.append(event)
        print(f"   📥 订单事件: {event}")

    print("\n启动 WebSocket 监控（watchTicker + watchOrders）...")
    adapter.start_ws(on_price, on_order)

    print("监听 10 秒...")
    time.sleep(10)

    print("\n停止 WebSocket 监控...")
    adapter.stop_ws()

    print(f"\n统计：收到 {len(price_updates)} 次价格更新，{len(order_updates)} 次订单事件")
    print("✅ WebSocket 测试完成")


def main():
    # 1. 测试公开 REST 接口
    if not test_public_api():
        return

    # 2. 测试 WebSocket（可选，需要 API key）
    test_websocket()


if __name__ == "__main__":
    main()
