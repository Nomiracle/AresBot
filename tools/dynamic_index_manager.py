#!/usr/bin/env python3
"""
数据库索引动态管理工具
无需重启应用即可创建和管理索引
"""

import sqlite3
import sys
import os
from datetime import datetime
from contextlib import contextmanager

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import DB_FILE
except ImportError:
    print("❌ 无法导入配置文件")
    sys.exit(1)

class DynamicIndexManager:
    """动态索引管理器"""
    
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.connection_pool = []
        
    @contextmanager
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def check_index_exists(self, index_name):
        """检查索引是否存在"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA index_list(orders)")
            indexes = [row[1] for row in cursor.fetchall()]
            return index_name in indexes
    
    def create_performance_indexes(self):
        """创建性能优化索引"""
        print("🔧 开始创建性能索引...")
        
        indexes = [
            # 盈利统计查询优化索引（最重要）
            {
                'name': 'idx_orders_user_side_status',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_user_side_status ON orders(user_id, side, status)',
                'description': '盈利统计查询优化'
            },
            # 排序优化索引
            {
                'name': 'idx_orders_id_desc', 
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_id_desc ON orders(id DESC)',
                'description': '订单排序优化'
            },
            # 时间戳查询优化
            {
                'name': 'idx_orders_timestamp',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_timestamp ON orders(timestamp)',
                'description': '时间戳查询优化'
            },
            # 订单查询优化
            {
                'name': 'idx_orders_order_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)',
                'description': '订单ID查询优化'
            },
            # 用户订单统计优化
            {
                'name': 'idx_orders_user_id',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)',
                'description': '用户订单统计优化'
            },
            # 交易对查询优化
            {
                'name': 'idx_orders_symbol',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol)',
                'description': '交易对查询优化'
            },
            # 交易所查询优化
            {
                'name': 'idx_orders_exchange',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_orders_exchange ON orders(exchange)',
                'description': '交易所查询优化'
            }
        ]
        
        created_count = 0
        skipped_count = 0
        
        for index_info in indexes:
            name = index_info['name']
            sql = index_info['sql']
            description = index_info['description']
            
            if self.check_index_exists(name):
                print(f"⏭️  索引 {name} 已存在 - {description}")
                skipped_count += 1
            else:
                try:
                    with self.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(sql)
                        conn.commit()
                    print(f"✅ 创建索引: {name} - {description}")
                    created_count += 1
                except Exception as e:
                    print(f"❌ 创建索引失败 {name}: {e}")
        
        print(f"\n📊 索引创建完成: 新建 {created_count} 个，跳过 {skipped_count} 个")
        return created_count > 0
    
    def analyze_query_performance(self):
        """分析查询性能"""
        print("\n📊 查询性能分析")
        
        # 分析数据库统计信息
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("ANALYZE")
            
            # 获取表统计信息
            cursor.execute("SELECT COUNT(*) FROM orders")
            total_rows = cursor.fetchone()[0]
            
            print(f"📋 orders 表总行数: {total_rows}")
            
            if total_rows > 0:
                # 测试盈利统计查询
                start_time = datetime.now()
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM orders 
                    WHERE user_id=1 AND side='SELL' AND status IN ('FILLED', 'order_filled')
                """)
                count = cursor.fetchone()[0]
                end_time = datetime.now()
                
                query_time = (end_time - start_time).total_seconds() * 1000
                print(f"⚡ 盈利统计查询时间: {query_time:.2f} ms")
                print(f"📈 匹配记录数: {count}")
                
                # 性能评估
                if query_time < 10:
                    print("🟢 查询性能优秀")
                elif query_time < 50:
                    print("🟡 查询性能良好")
                elif query_time < 200:
                    print("🟠 查询性能一般")
                else:
                    print("🔴 查询性能较差")
            else:
                print("ℹ️  orders 表为空，无法测试查询性能")
    
    def show_query_plan(self):
        """显示查询计划"""
        print("\n🔍 查询计划分析")
        
        test_query = """
            SELECT symbol, price, quantity, buy_price, fee, exchange, timestamp, updated_at, order_id,
                   offset_percent, sell_offset_percent, interval, 
                   min_price_diff_percent, max_price_diff_percent, avg_price_diff_percent,
                   sell_min_price_diff_percent, sell_max_price_diff_percent, sell_avg_price_diff_percent
            FROM orders 
            WHERE user_id=? AND side='SELL' AND status IN ('FILLED', 'order_filled')
            ORDER BY id DESC
        """
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"EXPLAIN QUERY PLAN {test_query}", (1,))
            plan = cursor.fetchall()
            
            print("当前查询计划:")
            for step in plan:
                operation = step[3] if len(step) > 3 else step[0]
                print(f"  {operation}")
                
            # 判断是否使用了索引
            plan_str = str(plan)
            if 'INDEX' in plan_str:
                print("✅ 查询使用了索引")
            else:
                print("⚠️  查询未使用索引（全表扫描）")
    
    def list_all_indexes(self):
        """列出所有索引"""
        print("\n📋 数据库索引列表")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取所有表的索引
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            total_indexes = 0
            
            for table in tables:
                cursor.execute(f"PRAGMA index_list({table})")
                indexes = cursor.fetchall()
                
                if indexes:
                    print(f"\n📁 表 {table}:")
                    for idx in indexes:
                        index_name = idx[1]
                        is_unique = idx[2]
                        
                        # 获取索引详情
                        cursor.execute(f"PRAGMA index_info({index_name})")
                        columns = cursor.fetchall()
                        column_names = [col[2] for col in columns]
                        
                        unique_str = "UNIQUE" if is_unique else ""
                        print(f"  🔑 {index_name} {unique_str} ({', '.join(column_names)})")
                        
                        total_indexes += 1
            
            print(f"\n📊 总索引数: {total_indexes}")
    
    def drop_index(self, index_name):
        """删除索引"""
        if not self.check_index_exists(index_name):
            print(f"❌ 索引 {index_name} 不存在")
            return False
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.commit()
            print(f"✅ 删除索引: {index_name}")
            return True
        except Exception as e:
            print(f"❌ 删除索引失败 {index_name}: {e}")
            return False
    
    def optimize_database(self):
        """优化数据库"""
        print("\n🔧 数据库优化")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # 分析表统计信息
                cursor.execute("ANALYZE")
                print("✅ 数据库分析完成")
                
                # 清理数据库碎片
                cursor.execute("VACUUM")
                print("✅ 数据库碎片清理完成")
                
                # 重新构建索引
                cursor.execute("REINDEX")
                print("✅ 索引重建完成")
                
                conn.commit()
                print("🎉 数据库优化完成")
                
            except Exception as e:
                print(f"❌ 数据库优化失败: {e}")
                conn.rollback()

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='数据库索引动态管理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 创建索引命令
    create_parser = subparsers.add_parser('create', help='创建性能索引')
    create_parser.add_argument('--force', action='store_true', help='强制重建所有索引')
    
    # 分析性能命令
    analyze_parser = subparsers.add_parser('analyze', help='分析查询性能')
    
    # 查询计划命令
    plan_parser = subparsers.add_parser('plan', help='显示查询计划')
    
    # 列出索引命令
    list_parser = subparsers.add_parser('list', help='列出所有索引')
    
    # 删除索引命令
    drop_parser = subparsers.add_parser('drop', help='删除索引')
    drop_parser.add_argument('name', help='索引名称')
    
    # 优化数据库命令
    optimize_parser = subparsers.add_parser('optimize', help='优化数据库')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = DynamicIndexManager()
    
    try:
        if args.command == 'create':
            if args.force:
                print("⚠️  强制重建模式：删除所有现有索引后重建")
                # 这里可以添加强制重建逻辑
            manager.create_performance_indexes()
            manager.analyze_query_performance()
            
        elif args.command == 'analyze':
            manager.analyze_query_performance()
            
        elif args.command == 'plan':
            manager.show_query_plan()
            
        elif args.command == 'list':
            manager.list_all_indexes()
            
        elif args.command == 'drop':
            manager.drop_index(args.name)
            
        elif args.command == 'optimize':
            manager.optimize_database()
            
    except Exception as e:
        print(f"❌ 执行命令时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
