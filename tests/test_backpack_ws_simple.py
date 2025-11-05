"""
BackpackWsAccount 简单测试脚本

快速测试 WebSocket 连接和消息接收
"""
import asyncio
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


async def simple_test():
    """简单测试"""
    print("="*60)
    print("BackpackWsAccount 简单测试")
    print("="*60)
    
    symbol = "SOL_USDC"
    print(f"交易对: {symbol}")
    print(f"WebSocket URL: {BackpackWsAccount.WS_URL}\n")
    
    # 定义回调函数
    def on_message(data):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 📨 {data}")
    
    def on_error(error):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 错误: {error}")
    
    def on_open():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 连接成功\n")
    
    def on_close():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔌 连接关闭")
    
    # 创建客户端
    ws_client = BackpackWsAccount(
        symbol=symbol,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    
    try:
        # 连接
        print("🔄 正在连接...")
        await ws_client.connect()
        
        # 订阅并监听 10 秒
        print("📡 订阅最优买卖价 (bookTicker)...\n")
        await ws_client.subscribe_markPrice(on_message=on_message)
        
        await asyncio.sleep(10)
        ws_client.clean_up()
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if ws_client.ws:
            await ws_client.ws.close()
        print("\n" + "="*60)
        print("测试完成")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(simple_test())
