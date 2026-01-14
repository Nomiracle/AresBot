#!/usr/bin/env python3
"""
快速索引优化脚本
在应用运行时执行，无需重启
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools.dynamic_index_manager import DynamicIndexManager
    print("✅ 成功导入动态索引管理器")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)

def quick_optimize():
    """快速优化索引"""
    print("🚀 开始快速索引优化...")
    print(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    manager = DynamicIndexManager()
    
    # 1. 创建性能索引
    print("\n1️⃣ 创建性能索引")
    created = manager.create_performance_indexes()
    
    # 2. 分析查询性能
    print("\n2️⃣ 分析查询性能")
    manager.analyze_query_performance()
    
    # 3. 显示查询计划
    print("\n3️⃣ 显示查询计划")
    manager.show_query_plan()
    
    # 4. 列出所有索引
    print("\n4️⃣ 索引统计")
    manager.list_all_indexes()
    
    print("\n" + "=" * 50)
    if created:
        print("🎉 索引优化完成！盈利统计页面性能应该已显著提升")
        print("💡 无需重启应用，索引已立即生效")
    else:
        print("ℹ️  所有索引已存在，无需创建")
    
    print("💡 提示: 如果性能仍不满意，可以运行 'python tools/dynamic_index_manager.py optimize' 进行数据库优化")

if __name__ == '__main__':
    from datetime import datetime
    quick_optimize()
