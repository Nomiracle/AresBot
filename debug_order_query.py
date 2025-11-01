"""
快速诊断订单查询问题
"""
from database import get_db_connection
from bpx.account import Account

# 1. 从数据库获取配置
conn = get_db_connection()
cursor = conn.cursor()

# 获取 API 凭证
cursor.execute("SELECT api_key, api_secret FROM users WHERE username = 'admin'")
user_result = cursor.fetchone()

# 获取交易配置
cursor.execute("SELECT symbol FROM trading_configs WHERE username = 'admin' LIMIT 1")
config_result = cursor.fetchone()

# 获取 pending_buys
cursor.execute("SELECT order_id FROM orders WHERE status = 'NEW' ORDER BY created_at DESC LIMIT 1")
order_result = cursor.fetchone()

conn.close()

if not user_result:
    print("❌ 未找到用户凭证")
    exit(1)

api_key, api_secret = user_result
symbol_from_config = config_result[0] if config_result else "HYPEUSD"
order_id = order_result[0] if order_result else "16598636798"

print(f"{'='*60}")
print(f"从数据库读取的配置:")
print(f"  Symbol (配置): {symbol_from_config}")
print(f"  Order ID: {order_id}")
print(f"{'='*60}\n")

# 2. 初始化 Backpack 客户端
account = Account(public_key=api_key, secret_key=api_secret, debug=False, window=5000)

# 3. 测试不同的 symbol 格式
test_symbols = [
    symbol_from_config,
    "HYPE_USDC",
    "HYPEUSD",
    "HYPE_USD"
]

for test_symbol in test_symbols:
    print(f"\n{'='*60}")
    print(f"测试 Symbol: {test_symbol}")
    print(f"{'='*60}")
    
    try:
        # 转换 symbol（模拟 _convert_symbol）
        if '_' not in test_symbol:
            if test_symbol.endswith('USDT'):
                bpx_symbol = test_symbol[:-4] + '_USDC'
            elif test_symbol.endswith('USD'):
                bpx_symbol = test_symbol[:-3] + '_USDC'
            elif test_symbol.endswith('USDC'):
                bpx_symbol = test_symbol[:-4] + '_USDC'
            else:
                bpx_symbol = test_symbol
        else:
            parts = test_symbol.split('_')
            if len(parts) == 2 and parts[1] in ['USD', 'USDT']:
                bpx_symbol = f"{parts[0]}_USDC"
            else:
                bpx_symbol = test_symbol
        
        print(f"转换后: {bpx_symbol}")
        
        # 查询历史订单
        history = account.get_order_history(symbol=bpx_symbol, order_id=order_id)
        
        print(f"返回类型: {type(history)}")
        print(f"返回数量: {len(history) if isinstance(history, list) else 'N/A'}")
        
        if isinstance(history, list) and len(history) > 0:
            print(f"✅ 找到订单！")
            print(f"订单状态: {history[0].get('status')}")
            print(f"订单 ID: {history[0].get('id')}")
        elif isinstance(history, dict) and 'code' in history:
            print(f"❌ API 错误: {history.get('code')} - {history.get('message')}")
        else:
            print(f"⚠️ 未找到订单")
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}")
print("诊断完成！")
