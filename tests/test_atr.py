# -*- coding: utf-8 -*-
"""
ATR Test - Get ATR from exchange using ccxt only (no pandas needed)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ccxt


def calculate_atr(ohlcv, period=14):
    """
    Calculate ATR from OHLCV data
    ohlcv: list of [timestamp, open, high, low, close, volume]
    """
    if len(ohlcv) < period + 1:
        raise ValueError(f"Need at least {period + 1} candles, got {len(ohlcv)}")
    
    true_ranges = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i][2]
        low = ohlcv[i][3]
        prev_close = ohlcv[i-1][4]
        
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    
    # Simple Moving Average of TR
    atr = sum(true_ranges[-period:]) / period
    return atr


def get_atr_from_exchange(symbol='BTC/USDT', timeframe='1h', 
                          period=14, exchange_id='binance'):
    """Get ATR from exchange using ccxt"""
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({'enableRateLimit': True})
    
    limit = period + 50
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    
    current_price = ohlcv[-1][4]  # close price
    atr_value = calculate_atr(ohlcv, period)
    atr_percent = (atr_value / current_price) * 100
    
    # Suggested parameters
    suggested_offset = -round(atr_percent * 0.15, 3)
    suggested_sell_offset = max(0.2, round(atr_percent * 0.4, 3))
    
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'current_price': current_price,
        'atr': round(atr_value, 8),
        'atr_percent': round(atr_percent, 4),
        'suggested_offset': suggested_offset,
        'suggested_sell_offset': suggested_sell_offset,
        'period': period
    }


def analyze_symbol(symbol, exchange_id='binance'):
    """Analyze symbol"""
    print(f"\n{'='*60}")
    print(f"Symbol: {symbol} @ {exchange_id.upper()}")
    print(f"{'='*60}")
    
    timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
    
    for tf in timeframes:
        try:
            data = get_atr_from_exchange(symbol, tf, 14, exchange_id)
            print(f"\n[{tf}]:")
            print(f"   Price: ${data['current_price']:,.2f}")
            print(f"   ATR: ${data['atr']:.4f} ({data['atr_percent']:.4f}%)")
            print(f"   -> Suggested offset: {data['suggested_offset']}%")
            print(f"   -> Suggested sell_offset: {data['suggested_sell_offset']}%")
        except Exception as e:
            print(f"   Error {tf}: {e}")


def main():
    print("ATR Analysis Tool (ccxt only)")
    print("=" * 60)
    
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    for symbol in symbols:
        analyze_symbol(symbol)
    
    print("\n" + "=" * 60)
    print("Parameter Guide:")
    print("   offset = -ATR% * 0.15 (buy below current price)")
    print("   sell_offset = ATR% * 0.4 (sell above buy price, min 0.2%)")


if __name__ == "__main__":
    main()
