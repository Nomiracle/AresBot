"""
Polymarket 市场 Token ID 查询工具
用于查找和显示 Polymarket 市场的 token_id
"""
from py_clob_client.client import ClobClient
from typing import List, Dict, Optional
import json


class PolymarketTokenFinder:
    """Polymarket Token ID 查询器"""
    
    def __init__(self):
        """初始化客户端"""
        self.client = ClobClient("https://clob.polymarket.com")
    
    def get_all_markets(self) -> List[Dict]:
        """获取所有市场"""
        try:
            response = self.client.get_markets()
            # API 返回的可能是字典,需要提取实际的市场列表
            if isinstance(response, dict):
                markets = response.get('data', response.get('markets', []))
            elif isinstance(response, list):
                markets = response
            else:
                markets = []
            return markets if markets else []
        except Exception as e:
            print(f"[错误] 获取市场失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def search_markets(self, keyword: str, limit: int = 10) -> List[Dict]:
        """搜索包含关键词的市场
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            
        Returns:
            匹配的市场列表
        """
        markets = self.get_all_markets()
        keyword_lower = keyword.lower()
        
        results = []
        for market in markets:
            question = market.get('question', '').lower()
            description = market.get('description', '').lower()
            
            if keyword_lower in question or keyword_lower in description:
                results.append(market)
                if len(results) >= limit:
                    break
        
        return results
    
    def display_market_info(self, market: Dict) -> None:
        """显示单个市场的详细信息"""
        print(f"\n{'='*80}")
        print(f"[市场] {market.get('question', 'N/A')}")
        print(f"{'='*80}")
        
        # 基本信息
        print(f"市场ID: {market.get('condition_id', 'N/A')}")
        print(f"描述: {market.get('description', 'N/A')[:100]}...")
        
        # Token 信息
        tokens = market.get('tokens', [])
        if tokens:
            print(f"\n[Token 信息]")
            for i, token in enumerate(tokens, 1):
                outcome = token.get('outcome', f'Token {i}')
                token_id = token.get('token_id', 'N/A')
                print(f"  {i}. {outcome}")
                print(f"     Token ID: {token_id}")
        
        # 交易信息
        print(f"\n[交易信息]")
        print(f"  是否活跃: {'是' if market.get('active') else '否'}")
        print(f"  是否已关闭: {'是' if market.get('closed') else '否'}")
        
        # 时间信息
        if market.get('end_date_iso'):
            print(f"  结束时间: {market.get('end_date_iso')}")
    
    def list_popular_markets(self, limit: int = 10) -> None:
        """列出热门市场"""
        print(f"\n{'='*80}")
        print(f"[Polymarket 热门市场] (前 {limit} 个)")
        print(f"{'='*80}\n")
        
        markets = self.get_all_markets()
        
        if not markets:
            print("[错误] 未能获取市场数据")
            return
        
        for i, market in enumerate(markets[:limit], 1):
            print(f"{i}. {market.get('question', 'N/A')}")
            
            tokens = market.get('tokens', [])
            if tokens:
                for token in tokens:
                    outcome = token.get('outcome', 'Unknown')
                    token_id = token.get('token_id', 'N/A')
                    print(f"   [{outcome}] Token ID: {token_id}")
            
            print()
    
    def search_and_display(self, keyword: str, limit: int = 5) -> None:
        """搜索并显示市场信息"""
        print(f"\n[搜索] 关键词: '{keyword}'")
        
        results = self.search_markets(keyword, limit)
        
        if not results:
            print(f"[提示] 未找到包含 '{keyword}' 的市场")
            return
        
        print(f"[成功] 找到 {len(results)} 个相关市场\n")
        
        for i, market in enumerate(results, 1):
            print(f"\n[{i}] {market.get('question', 'N/A')}")
            
            tokens = market.get('tokens', [])
            if tokens:
                for token in tokens:
                    outcome = token.get('outcome', 'Unknown')
                    token_id = token.get('token_id', 'N/A')
                    print(f"    [{outcome}] Token ID: {token_id}")
    
    def get_token_by_market_id(self, condition_id: str) -> Optional[Dict]:
        """根据市场ID获取token信息"""
        markets = self.get_all_markets()
        
        for market in markets:
            if market.get('condition_id') == condition_id:
                return market
        
        return None
    
    def export_markets_to_json(self, filename: str = "polymarket_markets.json", limit: int = 50) -> None:
        """导出市场数据到JSON文件"""
        markets = self.get_all_markets()[:limit]
        
        export_data = []
        for market in markets:
            market_info = {
                'question': market.get('question'),
                'condition_id': market.get('condition_id'),
                'description': market.get('description'),
                'active': market.get('active'),
                'closed': market.get('closed'),
                'end_date': market.get('end_date_iso'),
                'tokens': []
            }
            
            for token in market.get('tokens', []):
                market_info['tokens'].append({
                    'outcome': token.get('outcome'),
                    'token_id': token.get('token_id')
                })
            
            export_data.append(market_info)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        print(f"[成功] 已导出 {len(export_data)} 个市场到 {filename}")


def main():
    """主函数 - 交互式菜单"""
    finder = PolymarketTokenFinder()
    
    while True:
        print(f"\n{'='*80}")
        print("Polymarket Token ID 查询工具")
        print(f"{'='*80}")
        print("1. 列出热门市场")
        print("2. 搜索市场 (关键词)")
        print("3. 导出市场数据到JSON")
        print("4. 退出")
        print(f"{'='*80}")
        
        choice = input("\n请选择操作 (1-4): ").strip()
        
        if choice == '1':
            limit = input("显示数量 (默认10): ").strip()
            limit = int(limit) if limit.isdigit() else 10
            finder.list_popular_markets(limit)
            
        elif choice == '2':
            keyword = input("请输入搜索关键词: ").strip()
            if keyword:
                limit = input("显示数量 (默认5): ").strip()
                limit = int(limit) if limit.isdigit() else 5
                finder.search_and_display(keyword, limit)
            else:
                print("[错误] 关键词不能为空")
        
        elif choice == '3':
            filename = input("文件名 (默认: polymarket_markets.json): ").strip()
            filename = filename if filename else "polymarket_markets.json"
            limit = input("导出数量 (默认50): ").strip()
            limit = int(limit) if limit.isdigit() else 50
            finder.export_markets_to_json(filename, limit)
        
        elif choice == '4':
            print("\n再见!")
            break
        
        else:
            print("[错误] 无效选择,请重试")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序已退出")
    except Exception as e:
        print(f"\n[错误] 发生错误: {e}")
