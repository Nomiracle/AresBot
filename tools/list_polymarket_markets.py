"""
Polymarket Token ID
"""
import sys
from py_clob_client.client import ClobClient

def main():
    client = ClobClient("https://clob.polymarket.com")
    
    try:
        print("Fetching markets...")
        response = client.get_markets()
        
        if isinstance(response, dict):
            markets = response.get('data', response.get('markets', []))
        elif isinstance(response, list):
            markets = response
        else:
            markets = []
        
        if not markets:
            print("No markets found")
            return
        
        print(f"\nFound {len(markets)} markets\n")
        print("="*100)
        
        for i, market in enumerate(markets[:20], 1):
            question = market.get('question', 'N/A')
            print(f"\n{i}. {question}")
            
            tokens = market.get('tokens', [])
            if tokens:
                for token in tokens:
                    outcome = token.get('outcome', 'Unknown')
                    token_id = token.get('token_id', 'N/A')
                    print(f"   [{outcome}] {token_id}")
            
            print("-"*100)
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
