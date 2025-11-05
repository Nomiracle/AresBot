# alpha_token_list.py
# 直接使用 requests 调用 Binance Alpha Token List（公开接口，无需 python-binance）
import requests
# https://developers.binance.com/docs/alpha/market-data/rest-api/token-list
def get_alpha_token_list():
    url = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("code") == "000000":
            return data["data"]
        else:
            print("API error:", data.get("message"))
            return None
    except Exception as e:
        print("Request failed:", e)
        return None

# 示例：构造交易对
def build_symbol(alpha_id: int, quote: str = "USDT") -> str:
    return f"ALPHA_{alpha_id}{quote.upper()}"

if __name__ == "__main__":
    tokens = get_alpha_token_list()
    if tokens:
        print(f"共 {len(tokens)} 个 Alpha 代币")
        for t in tokens[:5]:
            print(f"ID: {t['alphaId']:<4} Symbol: {t['symbol']:<8} → {build_symbol(t['alphaId'])}")
        
        # 查找 ZKJ 示例
        zkj = next((t for t in tokens if t["symbol"] == "ZKJ"), None)
        if zkj:
            print(f"\nZKJ 交易对: {build_symbol(zkj['alphaId'])}")