"""
测试 BackpackWsAccount WebSocket 连接

用法:
    python test_backpack_ws_account.py --symbol SOL_USDC
    
    或指定其他交易对:
    python test_backpack_ws_account.py --symbol BTC_USDC
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime

# 设置 Windows 控制台编码为 UTF-8
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from exchanges.backpack.backpack_ws_account import BackpackWsAccount


def on_message_callback(msg):
    """处理接收到的消息"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] 📨 收到消息:")
    
    # Backpack 返回格式: {'data': {...}, 'stream': '...'}
    # 提取实际数据
    data = msg.get('data', msg)
    
    # 解析消息类型
    event_type = data.get('e', 'unknown')
    
    if event_type == 'bookTicker':
        # 最优买卖价消息
        symbol = data.get('s', 'N/A')
        ask_price = data.get('a', 'N/A')
        ask_qty = data.get('A', 'N/A')
        bid_price = data.get('b', 'N/A')
        bid_qty = data.get('B', 'N/A')
        update_id = data.get('u', 'N/A')
        
        print(f"  事件类型: 最优买卖价更新 (bookTicker)")
        print(f"  交易对: {symbol}")
        print(f"  最优卖价: {ask_price} (数量: {ask_qty})")
        print(f"  最优买价: {bid_price} (数量: {bid_qty})")
        print(f"  更新ID: {update_id}")
    
    elif event_type == 'markPrice':
        # 标记价格消息
        symbol = data.get('s', 'N/A')
        mark_price = data.get('p', 'N/A')
        funding_rate = data.get('f', 'N/A')
        index_price = data.get('i', 'N/A')
        next_funding = data.get('n', 'N/A')
        
        print(f"  事件类型: 标记价格更新")
        print(f"  交易对: {symbol}")
        print(f"  标记价格: {mark_price}")
        print(f"  预估资金费率: {funding_rate}")
        print(f"  指数价格: {index_price}")
        print(f"  下次资金费时间: {next_funding}")
    
    elif event_type == 'depth':
        # 深度数据消息
        symbol = data.get('s', 'N/A')
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        
        print(f"  事件类型: 订单簿深度")
        print(f"  交易对: {symbol}")
        print(f"  买单数量: {len(bids)}")
        print(f"  卖单数量: {len(asks)}")
        
        if bids:
            print(f"  最高买价: {bids[0][0]} (数量: {bids[0][1]})")
        if asks:
            print(f"  最低卖价: {asks[0][0]} (数量: {asks[0][1]})")
    
    else:
        # 其他类型消息
        print(f"  事件类型: {event_type}")
        print(f"  原始数据: {data}")
    
    print()


def on_error_callback(error):
    """处理错误"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] ❌ WebSocket 错误: {error}")


def on_close_callback():
    """处理连接关闭"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] 🔌 WebSocket 连接已关闭")


def on_open_callback():
    """处理连接打开"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] ✅ WebSocket 连接已建立")


async def test_websocket(symbol: str, duration: int = 30):
    """测试 WebSocket 连接
    
    Args:
        symbol: 交易对符号，如 SOL_USDC
        duration: 测试持续时间（秒）
    """
    print(f"{'='*60}")
    print(f"BackpackWsAccount WebSocket 测试")
    print(f"{'='*60}")
    print(f"交易对: {symbol}")
    print(f"测试时长: {duration} 秒")
    print(f"WebSocket URL: {BackpackWsAccount.WS_URL}")
    print(f"{'='*60}\n")
    
    # 创建 WebSocket 客户端
    ws_client = BackpackWsAccount(
        symbol=symbol,
        on_error=on_error_callback,
        on_close=on_close_callback,
        on_open=on_open_callback
    )
    
    try:
        # 连接 WebSocket
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔄 正在连接 WebSocket...")
        await ws_client.connect()
        
        # 订阅标记价格
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📡 订阅标记价格...")
        
        # 创建订阅任务
        subscribe_task = asyncio.create_task(
            ws_client.subscribe_markPrice(on_message=on_message_callback)
        )
        
        # 等待指定时间
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ 监听消息 {duration} 秒...\n")
        
        try:
            await asyncio.wait_for(subscribe_task, timeout=duration)
        except asyncio.TimeoutError:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏱️ 测试时间到")
        
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ 用户中断")
    
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 关闭连接
        if ws_client.ws:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔌 关闭 WebSocket 连接...")
            await ws_client.ws.close()
        
        print(f"\n{'='*60}")
        print(f"测试完成！")
        print(f"{'='*60}")


def main():
    """主函数：解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='测试 BackpackWsAccount WebSocket 连接',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试 SOL_USDC 交易对（默认 30 秒）
  python test_backpack_ws_account.py --symbol SOL_USDC
  
  # 测试 BTC_USDC 交易对，持续 60 秒
  python test_backpack_ws_account.py --symbol BTC_USDC --duration 60
  
  # 测试 HYPE_USDC 交易对
  python test_backpack_ws_account.py --symbol HYPE_USDC
        """
    )
    
    parser.add_argument('--symbol', '-s',
                       default='SOL_USDC',
                       help='交易对符号 (默认: SOL_USDC)')
    
    parser.add_argument('--duration', '-d',
                       type=int,
                       default=30,
                       help='测试持续时间（秒，默认: 30）')
    
    args = parser.parse_args()
    
    # 运行异步测试
    try:
        asyncio.run(test_websocket(args.symbol, args.duration))
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        sys.exit(0)


if __name__ == "__main__":
    main()
