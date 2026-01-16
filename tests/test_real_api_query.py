"""
Real Polymarket API Query Test
Query real order data from Polymarket server to verify data processing
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchanges.polymarket_adapter import NativePolymarketSpot


def main():
    """Main test function"""
    
    # Order info from user
    order_info = {
        'order_id': '0x2e3ceefaa43fef8cee279b35fc24bafe040aeb438ebb0962c78c46923e6afb5a',
        'maker_address': '0x5354b9aF3980149e03Dd32c7e0b716382f7B92d8',
        'asset_id': '111687137513747780904882674372859005833329319415172086974117982617968875263437',
        'expected_price': '0.35',
        'side': 'BUY',
        'market' : '0xb06162f41ac058ce01583410f792f5bcd45adcb99482974ec3d597c6aabb7ccf'
    }
    
    print("=" * 80)
    print("Real Polymarket API Query Test")
    print("=" * 80)
    print("\nOrder Info:")
    print(f"  Order ID: {order_info['order_id']}")
    print(f"  Asset ID: {order_info['asset_id']}")
    print(f"  Expected Price: {order_info['expected_price']}")
    print(f"  Side: {order_info['side']}")
    
    # Get credentials
    print("\n" + "=" * 80)
    api_key = input("Enter Polymarket Proxy Wallet Address (or press Enter to use default): ").strip()
    if not api_key:
        api_key = order_info['maker_address']
        print(f"Using default address: {api_key}")
    
    api_secret = input("Enter Private Key (0x...): ").strip()
    if not api_secret:
        print("\nNo private key provided. Test aborted.")
        print("Note: Private key is required for API authentication")
        return
    
    try:
        print("\n" + "=" * 80)
        print("Step 1: Initialize Polymarket Client")
        print("=" * 80)
        
        adapter = NativePolymarketSpot(
            api_key=api_key,
            api_secret=api_secret,
            symbol=order_info['asset_id'],
            testnet=False
        )
        
        print("OK: Client initialized")
        
        print("\n" + "=" * 80)
        print("Step 2: Query Historical Orders")
        print("=" * 80)
        
        # Call real _get_last_filled_buy_price method
        buy_price = adapter._get_last_filled_buy_price(order_info['asset_id'])
        
        print(f"\nResult:")
        print(f"  Retrieved buy price: {buy_price}")
        print(f"  Expected price: {order_info['expected_price']}")
        
        if buy_price is not None:
            print(f"\nOK: Data processed successfully")
            
            expected_price = float(order_info['expected_price'])
            if abs(buy_price - expected_price) < 0.01:
                print(f"OK: Price matches: {buy_price} ~= {expected_price}")
            else:
                print(f"WARNING: Price mismatch: {buy_price} != {expected_price}")
                print("         (May have retrieved a different order)")
        else:
            print("WARNING: No buy price retrieved (no historical buy orders)")
        
        print("\n" + "=" * 80)
        print("Step 3: View Raw Order Data")
        print("=" * 80)
        
        # Query order list directly to see raw data structure
        from py_clob_client.clob_types import OpenOrderParams
        orders = adapter.client.get_orders(OpenOrderParams(asset_id=order_info['asset_id']))
        
        print(f"\nFound {len(orders)} orders")
        
        # Find matching buy orders
        buy_orders = [o for o in orders if o.get('side', '').upper() == 'BUY' and o.get('status', '').upper() == 'MATCHED']
        print(f"Including {len(buy_orders)} filled buy orders")
        
        if buy_orders:
            print("\nFilled Buy Orders Details:")
            for i, order in enumerate(buy_orders[:3], 1):
                print(f"\n  Order {i}:")
                print(f"    ID: {order.get('id', 'N/A')[:66]}...")
                print(f"    Price: {order.get('price', 'N/A')}")
                print(f"    Side: {order.get('side', 'N/A')}")
                print(f"    Status: {order.get('status', 'N/A')}")
                print(f"    Size: {order.get('original_size', 'N/A')}")
                print(f"    Matched: {order.get('size_matched', 'N/A')}")
                print(f"    Created: {order.get('created_at', order.get('timestamp', 'N/A'))}")
                
                # Check if this is the target order
                if order.get('id') == order_info['order_id']:
                    print(f"    >>> THIS IS THE TARGET ORDER <<<")
        
        print("\n" + "=" * 80)
        print("Test Completed!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nERROR: Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
