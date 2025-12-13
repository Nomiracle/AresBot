#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance Futures 价格获取调试脚本

用于诊断价格 WebSocket 连接问题
"""

import time
import sys
from exchanges.binance_futures_adapter import BinanceFuturesAdapter

# 配置参数 - 请根据实际情况修改
API_KEY = "your_api_key_here"
API_SECRET = "your_api_secret_here"
SYMBOL = "SOLUSDT"
TESTNET = True  # True=测试网, False=主网

# 价格更新计数器
price_update_count = 0
last_price = None

def on_price_update(price: float):
    """价格更新回调"""
    global price_update_count, last_price
    price_update_count += 1
    last_price = price
    print(f"✅ [回调] 价格更新 #{price_update_count}: {price}")

def on_order_update(event: dict):
    """订单更新回调"""
    print(f"📨 [回调] 订单事件: {event.get('event_type')} - {event.get('order_id')}")

def main():
    print("=" * 60)
    print("Binance Futures 价格获取调试工具")
    print("=" * 60)
    
    # 检查配置
    if API_KEY == "your_api_key_here":
        print("❌ 错误: 请先在脚本中配置 API_KEY 和 API_SECRET")
        print("   编辑文件: test_futures_price_debug.py")
        sys.exit(1)
    
    print(f"\n配置信息:")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Testnet: {TESTNET}")
    print(f"  API Key: {API_KEY[:6]}...{API_KEY[-4:]}")
    print()
    
    try:
        # 创建适配器
        print("步骤 1: 创建 BinanceFuturesAdapter...")
        adapter = BinanceFuturesAdapter(
            api_key=API_KEY,
            api_secret=API_SECRET,
            symbol=SYMBOL,
            testnet=TESTNET
        )
        print("✅ 适配器创建成功\n")
        
        # 测试 ping
        print("步骤 2: 测试连接 (ping)...")
        if adapter.ping():
            print("✅ Ping 成功 - 网络连接正常\n")
        else:
            print("❌ Ping 失败 - 网络连接异常\n")
            return
        
        # 测试 HTTP 获取价格
        print("步骤 3: 测试 HTTP 获取价格...")
        ticker = adapter.get_symbol_ticker()
        if ticker:
            print(f"✅ HTTP 价格获取成功: {ticker.get('price')}\n")
        else:
            print("❌ HTTP 价格获取失败\n")
        
        # 获取交易对信息
        print("步骤 4: 获取交易对信息...")
        symbol_info = adapter.get_symbol_info()
        if symbol_info:
            print(f"✅ 交易对信息获取成功: {symbol_info.get('symbol')}")
            print(f"   状态: {symbol_info.get('status')}")
            print(f"   合约类型: {symbol_info.get('contractType')}\n")
        else:
            print("❌ 交易对信息获取失败\n")
        
        # 启动 WebSocket
        print("步骤 5: 启动 WebSocket 监控...")
        print("=" * 60)
        success = adapter.start_ws(
            on_price_update=on_price_update,
            on_order_update=on_order_update
        )
        
        if not success:
            print("❌ WebSocket 启动失败")
            return
        
        print("\n✅ WebSocket 已启动，等待价格消息...")
        print("   (如果 30 秒内没有收到消息，说明可能有问题)")
        print("=" * 60)
        
        # 等待并监控
        for i in range(60):
            time.sleep(1)
            
            # 每 10 秒检查一次状态
            if i > 0 and i % 10 == 0:
                print(f"\n⏱️  已运行 {i} 秒")
                print(f"   收到价格更新: {price_update_count} 次")
                if last_price:
                    print(f"   最新价格: {last_price}")
                
                # 获取 WebSocket 状态
                status = adapter.get_ws_status()
                
                if price_update_count == 0 and i >= 20:
                    print("\n⚠️  警告: 20秒内未收到任何价格更新")
                    print("   可能的原因:")
                    print("   1. WebSocket 连接未建立")
                    print("   2. 订阅的消息类型不正确")
                    print("   3. 网络问题或防火墙拦截")
                    print("   4. Binance API 限流")
        
        print("\n" + "=" * 60)
        print("测试完成!")
        print(f"总共收到 {price_update_count} 次价格更新")
        if last_price:
            print(f"最后价格: {last_price}")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        print("\n清理资源...")
        try:
            adapter.stop_ws()
            print("✅ WebSocket 已停止")
        except:
            pass

if __name__ == "__main__":
    main()
