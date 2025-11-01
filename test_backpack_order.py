"""
测试 Backpack get_order_history 方法

用法:
    python test_backpack_order.py --api-key YOUR_API_KEY --api-secret YOUR_API_SECRET --symbol HYPE_USDC --order-id 16598636798
    
    或从数据库读取:
    python test_backpack_order.py --username admin --symbol HYPE_USDC --order-id 16598636798
"""
from bpx.account import Account
import json
import argparse
import sys

def get_api_credentials_from_db(username):
    """从数据库获取 API 凭证"""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT api_key, api_secret, exchange 
            FROM users 
            WHERE username = ?
        ''', (username,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'api_key': result[0],
                'api_secret': result[1],
                'exchange': result[2]
            }
    except Exception as e:
        print(f"❌ 从数据库读取失败: {e}")
    return None

def test_get_order_history(api_key, api_secret, symbol, order_id):
    """测试查询历史订单"""
    
    print(f"{'='*60}")
    print(f"测试参数:")
    print(f"  API Key 长度: {len(api_key)}")
    print(f"  API Secret 长度: {len(api_secret)}")
    print(f"  Symbol: {symbol}")
    print(f"  Order ID: {order_id}")
    print(f"{'='*60}\n")
    
    # 1. 初始化 Backpack 客户端
    try:
        account = Account(
            public_key=api_key,
            secret_key=api_secret,
            debug=False,
            window=5000
        )
        print("✅ Backpack 客户端初始化成功\n")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return
    
    # 2. 测试不同的查询方式
    
    # 方式 1：只用 symbol 和 limit
    print("📋 方式 1: get_order_history(symbol, limit=3)")
    try:
        history1 = account.get_order_history(symbol=symbol, limit=3)
        print(f"✅ 返回类型: {type(history1)}")
        print(f"✅ 返回数量: {len(history1) if isinstance(history1, list) else 'N/A'}")
        
        if isinstance(history1, list):
            for i, order in enumerate(history1):
                print(f"\n订单 {i}:")
                print(f"  ID: {order.get('id')}")
                print(f"  状态: {order.get('status')}")
                print(f"  方向: {order.get('side')}")
                print(f"  价格: {order.get('price')}")
                print(f"  数量: {order.get('quantity')}")
                print(f"  所有字段: {list(order.keys())}")
        else:
            print(f"⚠️ 返回内容: {history1}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 方式 2：尝试加上 order_id 参数
    print(f"\n{'='*60}")
    print("📋 方式 2: get_order_history(symbol, limit=3, order_id=...)")
    try:
        history2 = account.get_order_history(symbol=symbol, limit=3, order_id=order_id)
        print(f"✅ 返回类型: {type(history2)}")
        print(f"✅ 返回数量: {len(history2) if isinstance(history2, list) else 'N/A'}")
        
        if isinstance(history2, list):
            for i, order in enumerate(history2):
                print(f"\n订单 {i}:")
                print(f"  ID: {order.get('id')}")
                print(f"  状态: {order.get('status')}")
        else:
            print(f"⚠️ 返回内容: {history2}")
    except TypeError as e:
        print(f"⚠️ order_id 参数不支持: {e}")
        print("💡 提示: get_order_history 可能不支持 order_id 参数")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 方式 3：查询更多历史订单并手动过滤
    print(f"\n{'='*60}")
    print("📋 方式 3: get_order_history(symbol, limit=100) 然后手动查找")
    try:
        history3 = account.get_order_history(symbol=symbol, limit=100)
        print(f"✅ 返回类型: {type(history3)}")
        print(f"✅ 返回数量: {len(history3) if isinstance(history3, list) else 'N/A'}")
        
        if isinstance(history3, list):
            # 查找特定订单
            found = False
            for order in history3:
                if str(order.get('id')) == str(order_id):
                    print(f"\n✅ 找到订单 {order_id}:")
                    print(f"  状态: {order.get('status')}")
                    print(f"  方向: {order.get('side')}")
                    print(f"  价格: {order.get('price')}")
                    print(f"  数量: {order.get('quantity')}")
                    print(f"  已成交数量: {order.get('executedQuantity')}")
                    print(f"\n完整订单数据:")
                    print(json.dumps(order, indent=2, ensure_ascii=False))
                    found = True
                    break
            
            if not found:
                print(f"⚠️ 在最近 {len(history3)} 个订单中未找到 {order_id}")
                print(f"最近的订单 ID:")
                for i, order in enumerate(history3[:5]):
                    print(f"  {i+1}. {order.get('id')} - {order.get('status')}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("测试完成！")

def main():
    """主函数：解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='测试 Backpack get_order_history 方法',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 直接提供 API 密钥
  python test_backpack_order.py --api-key YOUR_KEY --api-secret YOUR_SECRET --symbol HYPE_USDC --order-id 16598636798
  
  # 从数据库读取（需要 username）
  python test_backpack_order.py --username admin --symbol HYPE_USDC --order-id 16598636798
  
  # 只测试最近的订单
  python test_backpack_order.py --username admin --symbol HYPE_USDC
        """
    )
    
    # API 凭证参数（二选一）
    auth_group = parser.add_mutually_exclusive_group(required=True)
    auth_group.add_argument('--username', '-u', 
                           help='从数据库读取 API 凭证的用户名')
    auth_group.add_argument('--api-key', '-k',
                           help='Backpack API Key (公钥)')
    
    parser.add_argument('--api-secret', '-s',
                       help='Backpack API Secret (私钥，使用 --api-key 时必需)')
    
    # 测试参数
    parser.add_argument('--symbol', '-m',
                       default='HYPE_USDC',
                       help='交易对符号 (默认: HYPE_USDC)')
    
    parser.add_argument('--order-id', '-o',
                       help='要查询的订单 ID（可选）')
    
    args = parser.parse_args()
    
    # 获取 API 凭证
    if args.username:
        # 从数据库读取
        print(f"📖 从数据库读取用户 '{args.username}' 的凭证...")
        creds = get_api_credentials_from_db(args.username)
        if not creds:
            print(f"❌ 未找到用户 '{args.username}' 的凭证")
            sys.exit(1)
        
        api_key = creds['api_key']
        api_secret = creds['api_secret']
        print(f"✅ 成功读取凭证 (交易所: {creds['exchange']})\n")
    else:
        # 使用命令行提供的凭证
        if not args.api_secret:
            print("❌ 使用 --api-key 时必须同时提供 --api-secret")
            sys.exit(1)
        
        api_key = args.api_key
        api_secret = args.api_secret
    
    # 运行测试
    test_get_order_history(
        api_key=api_key,
        api_secret=api_secret,
        symbol=args.symbol,
        order_id=args.order_id or "16598636798"  # 默认订单ID
    )

if __name__ == "__main__":
    main()
