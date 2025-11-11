#!/usr/bin/env python3
"""
测试 SQLite 连接池功能
"""
import time
import threading
from database import db_pool, get_user_id, get_user_credentials

def test_basic_connection():
    """测试基本连接获取和归还"""
    print("=" * 60)
    print("测试 1: 基本连接获取和归还")
    print("=" * 60)
    
    conn = db_pool.get_connection()
    print(f"✅ 成功获取连接: {conn}")
    
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()
    print(f"✅ 查询测试: {result}")
    
    db_pool.return_connection(conn)
    print("✅ 连接已归还到连接池")
    print()

def test_context_manager():
    """测试上下文管理器"""
    print("=" * 60)
    print("测试 2: 上下文管理器")
    print("=" * 60)
    
    with db_pool.get_cursor() as (conn, cursor):
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        print(f"✅ 用户数量: {count}")
    print("✅ 上下文管理器自动归还连接")
    print()

def test_concurrent_access():
    """测试并发访问"""
    print("=" * 60)
    print("测试 3: 并发访问 (10个线程)")
    print("=" * 60)
    
    results = []
    
    def query_database(thread_id):
        try:
            start = time.time()
            with db_pool.get_cursor() as (conn, cursor):
                cursor.execute("SELECT COUNT(*) FROM users")
                count = cursor.fetchone()[0]
                elapsed = time.time() - start
                results.append({
                    'thread_id': thread_id,
                    'count': count,
                    'elapsed': elapsed,
                    'success': True
                })
        except Exception as e:
            results.append({
                'thread_id': thread_id,
                'error': str(e),
                'success': False
            })
    
    threads = []
    start_time = time.time()
    
    for i in range(10):
        t = threading.Thread(target=query_database, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    total_time = time.time() - start_time
    
    success_count = sum(1 for r in results if r.get('success'))
    print(f"✅ 成功: {success_count}/10 个线程")
    print(f"✅ 总耗时: {total_time:.3f}秒")
    
    avg_time = sum(r.get('elapsed', 0) for r in results if r.get('success')) / success_count
    print(f"✅ 平均查询时间: {avg_time:.3f}秒")
    print()

def test_real_functions():
    """测试实际数据库函数"""
    print("=" * 60)
    print("测试 4: 实际数据库函数")
    print("=" * 60)
    
    # 测试 get_user_id
    user_id = get_user_id('admin')
    print(f"✅ get_user_id('admin'): {user_id}")
    
    # 测试 get_user_credentials
    if user_id:
        creds = get_user_credentials('admin')
        print(f"✅ get_user_credentials('admin'): {len(creds)} 个凭证")
    
    print()

def test_pool_stats():
    """测试连接池统计"""
    print("=" * 60)
    print("测试 5: 连接池统计")
    print("=" * 60)
    
    print(f"✅ 最大连接数: {db_pool.max_connections}")
    print(f"✅ 当前已创建连接数: {db_pool._created_connections}")
    print(f"✅ 池中可用连接数: {db_pool._pool.qsize()}")
    print()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("SQLite 连接池测试")
    print("=" * 60 + "\n")
    
    try:
        test_basic_connection()
        test_context_manager()
        test_concurrent_access()
        test_real_functions()
        test_pool_stats()
        
        print("=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
