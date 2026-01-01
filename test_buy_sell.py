"""
BTC Up/Down 15m 市场买卖测试脚本
用法:
    # 自动获取市价并完成买卖
    python test_buy_sell.py --api-key 0x... --api-secret 0x... --qty 5 --buy-offset -0.02 --sell-offset 0.05
    
    # 手动指定价格
    python test_buy_sell.py --api-key 0x... --api-secret 0x... --buy-price 0.25 --sell-price 0.42 --qty 5
"""
import os
import sys
import time
import argparse
import requests
from datetime import datetime

from exchanges.btc_updown_15m import BtcUpDown15m


def get_market_price(exchange):
    """使用 CLOB Price API 获取市场价格"""
    print(f"[{datetime.now().isoformat()}] 📊 获取市场价格...")
    
    token_id = exchange.symbol
    
    try:
        # 使用 /price API 获取买价和卖价
        buy_url = f"https://clob.polymarket.com/price?token_id={token_id}&side=BUY"
        sell_url = f"https://clob.polymarket.com/price?token_id={token_id}&side=SELL"
        
        # 获取买价
        buy_response = requests.get(buy_url, timeout=10)
        buy_response.raise_for_status()
        buy_data = buy_response.json()
        buy_price = float(buy_data.get('price', 0))
        
        # 获取卖价
        sell_response = requests.get(sell_url, timeout=10)
        sell_response.raise_for_status()
        sell_data = sell_response.json()
        sell_price = float(sell_data.get('price', 0))
        
        if buy_price <= 0 and sell_price <= 0:
            raise RuntimeError("无法获取有效价格")
        
        # 显示价格信息
        if buy_price > 0 and sell_price > 0:
            mid_price = (buy_price + sell_price) / 2
            print(f"[{datetime.now().isoformat()}] 📈 买入价: {buy_price:.4f}")
            print(f"[{datetime.now().isoformat()}] 📉 卖出价: {sell_price:.4f}")
            print(f"[{datetime.now().isoformat()}] ✅ 中间价: {mid_price:.4f}")
        elif buy_price > 0:
            print(f"[{datetime.now().isoformat()}] ✅ 当前价格 (买价): {buy_price:.4f}")
        else:
            print(f"[{datetime.now().isoformat()}] ✅ 当前价格 (卖价): {sell_price:.4f}")
        
        return buy_price, sell_price
        
    except Exception as e:
        raise RuntimeError(f"获取市场价格失败: {e}")


def test_order_status(exchange, order_id):
    """测试订单状态查询"""
    print("=" * 60)
    print(f"[{datetime.now().isoformat()}] 🔍 查询订单状态")
    print("=" * 60)
    print(f"订单 ID: {order_id}")
    
    try:
        order_status = exchange.get_order(order_id)
        
        print(f"\n[{datetime.now().isoformat()}] 📊 订单信息:")
        print(f"  - 订单 ID: {order_status.get('orderId')}")
        print(f"  - 状态: {order_status.get('status')}")
        print(f"  - 方向: {order_status.get('side')}")
        print(f"  - 价格: {order_status.get('price')}")
        print(f"  - 原始数量: {order_status.get('origQty')}")
        print(f"  - 成交数量: {order_status.get('executedQty')}")
        
        if 'error' in order_status:
            print(f"  - 错误: {order_status.get('error')}")
        
        print("\n" + "=" * 60)
        print(f"[{datetime.now().isoformat()}] ✅ 查询完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[{datetime.now().isoformat()}] ❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()


def check_balance_allowance(exchange, token_id=None):
    """检查余额和授权"""
    from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
    
    print("=" * 60)
    print(f"[{datetime.now().isoformat()}] 💰 检查余额和授权")
    print("=" * 60)
    
    try:
        # 检查 USDC (Collateral) 余额和授权
        print(f"\n[{datetime.now().isoformat()}] 📊 USDC (Collateral):")
        collateral_params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL
        )
        collateral_result = exchange.client.get_balance_allowance(collateral_params)
        print(f"  - collateral_result: {collateral_result}")
        print(f"  - 余额: {collateral_result.get('balance')} USDC")
        print(f"  - 授权: {collateral_result.get('allowance')} USDC")
        
        # 检查 Conditional Token 余额和授权
        if token_id:
            print(f"\n[{datetime.now().isoformat()}] 📊 Conditional Token:")
            print(f"  - Token ID: {token_id}")
            conditional_params = BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=token_id
            )
            conditional_result = exchange.client.get_balance_allowance(conditional_params)
            print(f"  - conditional_result: {conditional_result}")
            print(f"  - 余额: {conditional_result.get('balance')}")
            print(f"  - 授权: {conditional_result.get('allowance')}")
        
        print("\n" + "=" * 60)
        print(f"[{datetime.now().isoformat()}] ✅ 检查完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[{datetime.now().isoformat()}] ❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="测试 BTC Up/Down 15m 市场买卖")
    parser.add_argument("--api-key", help="钱包地址 (或设置环境变量 PM_API_KEY)")
    parser.add_argument("--api-secret", help="私钥 (或设置环境变量 PM_API_SECRET)")
    parser.add_argument("--outcome", default="Up", choices=["Up", "Down"], help="交易方向")
    parser.add_argument("--buy-price", type=float, help="买入价格 (0-1),不指定则自动获取市价")
    parser.add_argument("--sell-price", type=float, help="卖出价格 (0-1),不指定则自动获取市价")
    parser.add_argument("--buy-offset", type=float, default=-0.02, help="买入价格偏移 (默认: -0.02, 即低于市价2%%)")
    parser.add_argument("--sell-offset", type=float, default=0.05, help="卖出价格偏移 (默认: 0.05, 即高于市价5%%)")
    parser.add_argument("--qty", type=float, help="交易数量")
    parser.add_argument("--wait", type=int, default=120, help="等待买单成交的最长时间(秒)")
    parser.add_argument("--poll", type=float, default=2.0, help="轮询间隔(秒)")
    parser.add_argument("--skip-sell", action="store_true", help="只测试买单,不测试卖单")
    parser.add_argument("--check-order", help="查询订单状态 (传入订单 ID)")
    parser.add_argument("--check-balance", action="store_true", help="检查余额和授权")
    args = parser.parse_args()

    # 获取 API 凭证
    api_key = args.api_key or os.getenv("PM_API_KEY")
    api_secret = args.api_secret or os.getenv("PM_API_SECRET")
    
    if not api_key or not api_secret:
        print("❌ 缺少 API 凭证")
        print("请通过 --api-key 和 --api-secret 参数传入")
        print("或设置环境变量: PM_API_KEY 和 PM_API_SECRET")
        sys.exit(1)

    # 初始化交易所
    print(f"\n[{datetime.now().isoformat()}] 📡 初始化 BTC Up/Down 15m 市场...")
    exchange = BtcUpDown15m(
        api_key=api_key,
        api_secret=api_secret,
        outcome=args.outcome,
        testnet=True
    )
    
    # 如果是查询订单状态模式
    if args.check_order:
        test_order_status(exchange, args.check_order)
        return
    
    # 如果是检查余额和授权模式
    if args.check_balance:
        check_balance_allowance(exchange, token_id=exchange.symbol)
        return

    # 正常买卖测试模式
    if not args.qty:
        print("❌ 缺少交易数量参数 --qty")
        sys.exit(1)

    print("=" * 60)
    print(f"[{datetime.now().isoformat()}] 🚀 开始测试")
    print("=" * 60)
    
    # 显示市场信息
    market_info = exchange.get_market_info()
    print(f"\n[{datetime.now().isoformat()}] 📊 市场信息:")
    print(f"  - 市场: {market_info.get('slug')}")
    print(f"  - Token ID: {market_info.get('token_id')}")
    print(f"  - 方向: {market_info.get('outcome')}")
    print(f"  - 结束时间: {market_info.get('end_time')}")
    if hasattr(exchange, 'condition_id'):
        print(f"  - Condition ID: {exchange.condition_id}")
    
    # 获取市价
    buy_price, sell_price = get_market_price(exchange)
    
    # 步骤 1: 下买单（使用卖价确保立即成交）
    print(f"\n[{datetime.now().isoformat()}] 📝 步骤 1: 下买单（市价成交）")
    print(f"  - 价格: {sell_price:.4f} (使用卖价确保立即成交)")
    print(f"  - 数量: {args.qty}")
    
    try:
        buy_order = exchange.order_limit_buy(quantity=args.qty, price=str(sell_price))
        buy_order_id = buy_order.get('orderId')
        print(f"\n[{datetime.now().isoformat()}] ✅ 买单创建成功")
        print(f"  - Order ID: {buy_order_id}")
    except Exception as e:
        print(f"\n[{datetime.now().isoformat()}] ❌ 买单创建失败: {e}")
        sys.exit(1)
    
    # 步骤 2: 轮询买单状态直到成交
    print(f"\n[{datetime.now().isoformat()}] ⏳ 步骤 2: 轮询买单状态...")
    
    max_wait = 30  # 最多等待30秒
    start_time = time.time()
    executed_qty = 0.0
    
    while time.time() - start_time < max_wait:
        try:

            order_status = exchange.get_order(buy_order_id)
            status = order_status.get('status')
            executed_qty = float(order_status.get('executedQty', 0))
            orig_qty = float(order_status.get('origQty', 0))
            
            print(f"[{datetime.now().isoformat()}] 📊 买单状态: {status}, 成交: {executed_qty}/{orig_qty}")
            
            if status == 'FILLED' and executed_qty >= args.qty:
                print(f"\n[{datetime.now().isoformat()}] ✅ 买单已完全成交!")
                print(f"  - 成交数量: {executed_qty}")
                break
            elif status in ['CANCELED', 'EXPIRED']:
                print(f"\n[{datetime.now().isoformat()}] ❌ 买单已取消或过期")
                sys.exit(1)
            
            time.sleep(1)  # 每秒轮询一次
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ 查询订单失败: {e}")
            time.sleep(1)
    
    if executed_qty == 0:
        print(f"\n[{datetime.now().isoformat()}] ❌ 买单未成交，无法继续测试卖单")
        sys.exit(1)
    elif executed_qty < args.qty:
        print(f"\n[{datetime.now().isoformat()}] ⚠️ 买单部分成交: {executed_qty}/{args.qty}")
        print("继续测试卖单...")
    
    # 步骤 3: 下卖单
    if args.skip_sell:
        print(f"\n[{datetime.now().isoformat()}] ⏭️ 跳过卖单测试 (--skip-sell)")
        print("=" * 60)
        print(f"[{datetime.now().isoformat()}] ✅ 测试完成 (仅买单)")
        print("=" * 60)
        return
    
    print(f"\n[{datetime.now().isoformat()}] 📝 步骤 3: 下卖单（市价成交）")
    
    from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
    
    # 循环检查 Token 余额
    print(f"[{datetime.now().isoformat()}] � 检查 Conditional Token 余额...")
    max_balance_wait = 30  # 最多等待30秒
    balance_start_time = time.time()
    token_balance = 0.0
    
    while time.time() - balance_start_time < max_balance_wait:
        try:
            # 检查 Conditional Token 余额
            conditional_params = BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=exchange.symbol
            )
            balance_result = exchange.client.get_balance_allowance(conditional_params)
            # Token 余额需要除以 10^6 转换为实际数量
            token_balance_raw = float(balance_result.get('balance', 0))
            token_balance = token_balance_raw / 1_000_000
            
            print(f"[{datetime.now().isoformat()}] 📊 Token 余额: {token_balance:.2f}/{executed_qty} (原始: {token_balance_raw})")
            
            # 如果余额等于成交数量，说明 token 已到账
            if token_balance >= executed_qty:
                print(f"[{datetime.now().isoformat()}] ✅ Token 已到账!")
                break
            
            # 如果没有余额，调用 update_balance_allowance 刷新缓存
            if token_balance == 0:
                print(f"[{datetime.now().isoformat()}] 🔄 刷新余额缓存...")
                try:
                    exchange.client.update_balance_allowance(conditional_params)
                except Exception as update_e:
                    print(f"[{datetime.now().isoformat()}] ⚠️ 刷新失败: {update_e}")
            
            time.sleep(1)
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ⚠️ 查询余额失败: {e}")
            time.sleep(1)
    
    # 检查余额是否足够
    if token_balance < executed_qty:
        print(f"\n[{datetime.now().isoformat()}] ❌ Token 余额不足: {token_balance}/{executed_qty}")
        print("无法继续测试卖单")
        sys.exit(1)
    
    print(f"\n[{datetime.now().isoformat()}] 📝 创建卖单")
    print(f"  - 价格: {buy_price:.4f} (使用买价确保立即成交)")
    print(f"  - 数量: {executed_qty}")
    
    try:
        sell_order = exchange.order_limit_sell(quantity=executed_qty, price=str(buy_price))
        sell_order_id = sell_order.get('orderId')
        print(f"\n[{datetime.now().isoformat()}] ✅ 卖单创建成功")
        print(f"  - Order ID: {sell_order_id}")
        
        # 等待卖单成交
        time.sleep(2)
        
        try:
            sell_status = exchange.get_order(sell_order_id)
            sell_exec_qty = float(sell_status.get('executedQty', 0))
            print(f"[{datetime.now().isoformat()}] 📊 卖单状态: {sell_status.get('status')}, 成交: {sell_exec_qty}/{executed_qty}")
            
            if sell_exec_qty >= executed_qty:
                print(f"\n[{datetime.now().isoformat()}] ✅ 卖单已完全成交!")
            else:
                print(f"\n[{datetime.now().isoformat()}] ⚠️ 卖单部分成交: {sell_exec_qty}/{executed_qty}")
        except Exception as status_e:
            print(f"[{datetime.now().isoformat()}] ⚠️ 查询卖单状态失败: {status_e}")
    except Exception as e:
        print(f"\n[{datetime.now().isoformat()}] ❌ 卖单创建失败: {e}")
        print("\n💡 常见原因:")
        print("  1. 余额不足: 买单成交的 token 可能还未到账")
        print("  2. 授权不足: 需要授权 conditional token")
        print("     - 访问 https://polymarket.com 点击 'Approve Tokens'")
        print("     - 或调用 client.set_conditional_token_allowance()")
        print("  3. Token ID 不匹配: 可能卖的是其他市场的 token")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print(f"[{datetime.now().isoformat()}] ✅ 测试完成")
    print("=" * 60)
    print(f"买单 ID: {buy_order_id}")
    print(f"卖单 ID: {sell_order_id}")


if __name__ == "__main__":
    main()
