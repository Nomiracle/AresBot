"""
测试 ccxt fetch_trading_fees 方法

用法: python test_fetch_trading_fees.py YOUR_API_KEY YOUR_API_SECRET
"""

import sys
import ccxt


def test_fetch_trading_fees(api_key, api_secret):
    """测试 fetch_trading_fees 方法"""
    
    # 测试交易对
    symbols = ['BTCUSDT', 'USDCUSDT']
    
    print("测试 fetch_trading_fees 方法")
    print("=" * 50)
    
    # 1. 测试现货费率
    print("\n=== 现货费率测试 ===")
    try:
        # 创建现货交易所实例
        spot_exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        for symbol in symbols:
            fees = spot_exchange.fetchTradingFee(symbol=symbol)
            print(f"✅ 现货 {symbol} 费率获取成功")
            print(f"原始数据: {fees}")
            
    except Exception as e:
        print(f"❌ 现货费率获取失败: {e}")
    
    # 2. 测试合约费率
    print("\n=== 合约费率测试 ===")
    try:
        # 创建合约交易所实例
        futures_exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        for symbol in symbols:
            fees = futures_exchange.fetchTradingFee(symbol=symbol)
            print(f"✅ 合约 {symbol} 费率获取成功")
            print(f"原始数据: {fees}")
            
    except Exception as e:
        print(f"❌ 合约费率获取失败: {e}")
        
        # 常见错误提示
        error_str = str(e).lower()
        if 'testnet' in error_str and 'sapi' in error_str:
            print("💡 Binance测试网不支持fetchTradingFee，请使用主网")
        elif 'invalid api key' in error_str:
            print("💡 API Key无效")
        elif 'permission' in error_str:
            print("💡 API权限不足")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python test_fetch_trading_fees.py YOUR_API_KEY YOUR_API_SECRET")
        sys.exit(1)
    
    api_key = sys.argv[1]
    api_secret = sys.argv[2]
    
    test_fetch_trading_fees(api_key, api_secret)

# 执行后输出：
# === 现货费率测试 ===
# ✅ 现货 BTCUSDT 费率获取成功
# 原始数据: {'info': {'symbol': 'BTCUSDT', 'makerCommission': '0.001', 'takerCommission': '0.001'}, 'symbol': 'BTC/USDT', 'maker': 0.001, 'taker': 0.001, 'percentage': None, 'tierBased': None}
# ✅ 现货 USDCUSDT 费率获取成功
# 原始数据: {'info': {'symbol': 'USDCUSDT', 'makerCommission': '0', 'takerCommission': '0'}, 'symbol': 'USDC/USDT', 'maker': 0.0, 'taker': 0.0, 'percentage': None, 'tierBased': None}

# === 合约费率测试 ===
# ✅ 合约 BTCUSDT 费率获取成功
# 原始数据: {'info': {'symbol': 'BTCUSDT', 'makerCommissionRate': '0.000200', 'takerCommissionRate': '0.000500', 'rpiCommissionRate': '0'}, 'symbol': 'BTC/USDT', 'maker': 0.0002, 'taker': 0.0005, 'percentage': None, 'tierBased': None}
# ✅ 合约 USDCUSDT 费率获取成功
# 原始数据: {'info': {'symbol': 'USDCUSDT', 'makerCommissionRate': '0.000200', 'takerCommissionRate': '0.000500', 'rpiCommissionRate': '0'}, 'symbol': 'USDC/USDT', 'maker': 0.0002, 'taker': 0.0005, 'percentage': None, 'tierBased': None}