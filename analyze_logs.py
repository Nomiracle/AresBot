#!/usr/bin/env python3
"""
日志分析工具 - 排查挂单成交但未挂卖单的问题
"""
import re
import sys
from datetime import datetime
from collections import defaultdict

def analyze_log_file(log_file_path):
    """分析日志文件"""
    
    print("=" * 80)
    print("📊 AresBot 日志分析工具")
    print("=" * 80)
    print()
    
    # 统计数据
    stats = {
        'buy_orders_placed': [],      # 已下买单
        'buy_orders_filled': [],       # 买单成交
        'sell_orders_placed': [],      # 已下卖单
        'sell_order_errors': [],       # 卖单错误
        'ws_status': None,             # WebSocket 状态
        'pending_buys': [],            # pending_buys 记录
        'api_errors': [],              # API 错误
        'order_reprice': [],           # 改价记录
    }
    
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"❌ 找不到日志文件: {log_file_path}")
        print()
        print("💡 提示：")
        print("   1. 如果使用控制台输出，请复制日志到文件")
        print("   2. 或者使用重定向运行: python app.py > logs.txt 2>&1")
        return
    except Exception as e:
        print(f"❌ 读取日志文件失败: {e}")
        return
    
    print(f"📁 分析文件: {log_file_path}")
    print(f"📝 总行数: {len(lines)}")
    print()
    
    # 逐行分析
    for i, line in enumerate(lines, 1):
        # 买单下单
        if '✅ [SUCCESS] 真实买单已下' in line or '新订单ID=' in line:
            match = re.search(r'新订单ID=(\S+)', line)
            if match:
                order_id = match.group(1).rstrip('**').rstrip(',')
                stats['buy_orders_placed'].append({
                    'line': i,
                    'order_id': order_id,
                    'text': line.strip()
                })
        
        # 买单改价
        if '✅ [REPRICE] 订单' in line and '已替换为新价格' in line:
            match = re.search(r'订单 (\S+) 已替换为新价格 (\S+)，新订单ID=(\S+)', line)
            if match:
                old_id, price, new_id = match.groups()
                stats['order_reprice'].append({
                    'line': i,
                    'old_id': old_id,
                    'new_id': new_id,
                    'price': price,
                    'text': line.strip()
                })
        
        # 买单成交（WebSocket）
        if '✅ [WS] 买单' in line and '成交，自动挂卖单' in line:
            match = re.search(r'买单 (\S+) 成交，自动挂卖单 (\S+) @ (\S+)', line)
            if match:
                buy_id, sell_id, price = match.groups()
                stats['buy_orders_filled'].append({
                    'line': i,
                    'buy_order_id': buy_id,
                    'sell_order_id': sell_id,
                    'price': price,
                    'mode': 'WebSocket',
                    'text': line.strip()
                })
        
        # 买单成交（REST）
        if '✅ [REST-FALLBACK] 买单' in line and '成交，自动挂卖单' in line:
            match = re.search(r'买单 (\S+) 成交，自动挂卖单 (\S+) @ (\S+)', line)
            if match:
                buy_id, sell_id, price = match.groups()
                stats['buy_orders_filled'].append({
                    'line': i,
                    'buy_order_id': buy_id,
                    'sell_order_id': sell_id,
                    'price': price,
                    'mode': 'REST',
                    'text': line.strip()
                })
        
        # 卖单错误（WebSocket）
        if '❌ [WS SELL ERR]' in line:
            stats['sell_order_errors'].append({
                'line': i,
                'mode': 'WebSocket',
                'text': line.strip()
            })
        
        # 卖单错误（REST）
        if '❌ [SELL ERR]' in line:
            stats['sell_order_errors'].append({
                'line': i,
                'mode': 'REST',
                'text': line.strip()
            })
        
        # 卖单下单失败但保留 pending
        if '已成交但卖单下单失败，保留在 pending_buys 中等待重试' in line:
            match = re.search(r'买单 (\S+) 已成交', line)
            if match:
                order_id = match.group(1)
                stats['pending_buys'].append({
                    'line': i,
                    'order_id': order_id,
                    'text': line.strip()
                })
        
        # WebSocket 状态
        if 'WebSocket 暂不支持' in line or '用户数据流未启用' in line:
            stats['ws_status'] = 'REST轮询'
        
        # API 错误
        if '❌ [Backpack] API 错误响应' in line:
            # 读取接下来的几行获取完整错误信息
            error_lines = [line.strip()]
            for j in range(i, min(i+5, len(lines))):
                if '错误代码:' in lines[j] or '错误信息:' in lines[j]:
                    error_lines.append(lines[j].strip())
            stats['api_errors'].append({
                'line': i,
                'text': '\n'.join(error_lines)
            })
    
    # 输出分析结果
    print("=" * 80)
    print("📈 分析结果")
    print("=" * 80)
    print()
    
    # 1. WebSocket 状态
    print("1️⃣ WebSocket 状态")
    print("-" * 80)
    if stats['ws_status']:
        print(f"   ⚠️ 当前使用: {stats['ws_status']}")
        print(f"   💡 Backpack 不支持 WebSocket，使用 REST 轮询检测订单成交")
    else:
        print(f"   ✅ WebSocket 已启用")
    print()
    
    # 2. 买单统计
    print("2️⃣ 买单统计")
    print("-" * 80)
    print(f"   📤 已下买单: {len(stats['buy_orders_placed'])} 笔")
    if stats['buy_orders_placed']:
        for order in stats['buy_orders_placed'][-5:]:  # 显示最近5笔
            print(f"      行 {order['line']}: 订单ID={order['order_id']}")
    print()
    print(f"   🔄 改价记录: {len(stats['order_reprice'])} 次")
    if stats['order_reprice']:
        for reprice in stats['order_reprice'][-5:]:
            print(f"      行 {reprice['line']}: {reprice['old_id']} -> {reprice['new_id']} @ {reprice['price']}")
    print()
    print(f"   ✅ 成交买单: {len(stats['buy_orders_filled'])} 笔")
    if stats['buy_orders_filled']:
        for order in stats['buy_orders_filled']:
            print(f"      行 {order['line']}: 买单={order['buy_order_id']}, 卖单={order['sell_order_id']}, 模式={order['mode']}")
    print()
    
    # 3. 卖单错误
    print("3️⃣ 卖单错误")
    print("-" * 80)
    print(f"   ❌ 卖单错误: {len(stats['sell_order_errors'])} 次")
    if stats['sell_order_errors']:
        for error in stats['sell_order_errors']:
            print(f"      行 {error['line']}: {error['text']}")
    print()
    
    # 4. pending_buys 保留记录
    print("4️⃣ pending_buys 保留记录")
    print("-" * 80)
    print(f"   ⚠️ 保留记录: {len(stats['pending_buys'])} 笔")
    if stats['pending_buys']:
        print(f"   💡 这些买单已成交但卖单下单失败，系统会在下次循环重试")
        for pb in stats['pending_buys']:
            print(f"      行 {pb['line']}: 订单ID={pb['order_id']}")
    print()
    
    # 5. API 错误
    print("5️⃣ API 错误")
    print("-" * 80)
    print(f"   ❌ API 错误: {len(stats['api_errors'])} 次")
    if stats['api_errors']:
        for error in stats['api_errors']:
            print(f"      行 {error['line']}:")
            print(f"      {error['text']}")
    print()
    
    # 6. 问题诊断
    print("=" * 80)
    print("🔍 问题诊断")
    print("=" * 80)
    print()
    
    # 检查是否有买单成交但没有对应的卖单
    buy_filled_count = len(stats['buy_orders_filled'])
    sell_error_count = len(stats['sell_order_errors'])
    pending_count = len(stats['pending_buys'])
    
    if buy_filled_count == 0:
        print("❓ 未检测到买单成交记录")
        print("   可能原因：")
        print("   1. 买单还未成交")
        print("   2. 日志不完整")
        print("   3. 使用了 REST 轮询但轮询间隔太长")
        print()
    elif sell_error_count > 0:
        print("⚠️ 检测到卖单下单错误！")
        print(f"   买单成交: {buy_filled_count} 笔")
        print(f"   卖单错误: {sell_error_count} 次")
        print()
        print("   💡 建议检查：")
        print("   1. API 权限是否包含交易权限")
        print("   2. 账户余额是否足够")
        print("   3. 交易对精度设置是否正确")
        print("   4. 网络连接是否稳定")
        print()
    elif pending_count > 0:
        print("⚠️ 有买单保留在 pending_buys 中")
        print(f"   保留数量: {pending_count} 笔")
        print()
        print("   💡 这些订单会在下次循环重试挂卖单")
        print("   💡 如果一直重试失败，请检查上述卖单错误日志")
        print()
    else:
        print("✅ 未发现明显问题")
        print(f"   买单成交: {buy_filled_count} 笔")
        print(f"   卖单错误: {sell_error_count} 次")
        print()
    
    # 7. 建议操作
    print("=" * 80)
    print("💡 建议操作")
    print("=" * 80)
    print()
    print("1. 查看完整错误信息：")
    print("   grep -i 'SELL ERR' logs.txt")
    print()
    print("2. 查看 API 错误：")
    print("   grep -i 'API 错误' logs.txt")
    print()
    print("3. 查看订单流程：")
    print("   grep -E '(买单|卖单|订单ID)' logs.txt")
    print()
    print("4. 实时监控（如果程序正在运行）：")
    print("   tail -f logs.txt | grep -E '(买单|卖单|ERROR|ERR)'")
    print()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        # 默认日志文件路径
        log_file = 'logs.txt'
        print(f"未指定日志文件，使用默认路径: {log_file}")
        print(f"用法: python analyze_logs.py <日志文件路径>")
        print()
    
    analyze_log_file(log_file)
