import time
import asyncio
import ccxt.pro

c = ccxt.pro.binanceusdm()
# c.verbose = True  # 关闭详细日志

symbol = "BTC/USDT:USDT"

async def test_watch_ticker():
    """watch_ticker - 单个币种，使用 markPrice 流"""
    print("=== watch_ticker (markPrice) ===")
    count = 0
    start = time.time()
    while count < 20:
        ticker = await c.watch_ticker(symbol)
        count += 1
        print(f"[{count}] {ticker['last']:.2f} @ {time.time()-start:.3f}s")

async def test_watch_bids_asks():
    """watch_bids_asks - bookTicker 流，bid/ask 实时更新"""
    print("=== watch_bids_asks (bookTicker) ===")
    count = 0
    start = time.time()
    while count < 20:
        bids_asks = await c.watch_bids_asks([symbol])
        count += 1
        ba = bids_asks.get(symbol, {})
        print(f"[{count}] bid={ba.get('bid'):.2f}, ask={ba.get('ask'):.2f} @ {time.time()-start:.3f}s")

async def test_watch_trades():
    """watch_trades - 成交流，最实时"""
    print("=== watch_trades ===")
    count = 0
    start = time.time()
    while count < 20:
        trades = await c.watch_trades(symbol)
        for t in trades[-1:]:  # 只取最新一笔
            count += 1
            print(f"[{count}] price={t['price']:.2f}, amount={t['amount']} @ {time.time()-start:.3f}s")
            if count >= 20:
                break

async def main():
    print(f"测试不同 WebSocket 流的更新速度: {symbol}\n")
    
    # 选择测试哪种方式（取消注释）
    # await test_watch_ticker()      # markPrice 流
    await test_watch_bids_asks()     # bookTicker 流 - 最快
    # await test_watch_trades()      # 成交流
    
    await c.close()

asyncio.run(main())