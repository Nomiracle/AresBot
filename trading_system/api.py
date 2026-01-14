"""
API接口 - 兼容原有trading.py的接口
"""

import threading
from typing import Dict, Any
from .factory import TradingContextFactory
from .domain import TradingContext
from .orchestrator import TradingLoopOrchestrator


# 全局用户机器人存储（兼容原有接口）
user_bots: Dict[str, Dict[str, Any]] = {}


def trading_loop(username: str, bot_key: str) -> None:
    """
    交易主循环（兼容原有接口）
    
    Args:
        username: 用户名
        bot_key: 机器人键
    """
    user_data = user_bots.get(username)
    if not user_data:
        return
    
    bot_data = user_data.get('bots', {}).get(bot_key)
    if not bot_data:
        return
    
    exchange = bot_data.get('exchange')
    config = bot_data.get('config', {})
    
    if not exchange or not config:
        print(f"[{username}-{bot_key}] ❌ 交易所或配置不存在")
        return
    
    try:
        # 从数据库获取user_id
        from database import get_user_id
        user_id = get_user_id(username)
        
        # 创建交易上下文
        context = TradingContextFactory.create_from_dict(
            username=username,
            user_id=user_id,
            config_dict=config,
            exchange=exchange
        )
        
        # 将上下文存储到bot_data（用于外部访问状态）
        bot_data['context'] = context
        bot_data['running'] = True
        
        # 创建编排器
        orchestrator = TradingContextFactory.create_orchestrator(context)
        
        # 运行交易循环
        orchestrator.run()
        
    except Exception as e:
        print(f"[{username}-{bot_key}] ❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
        
        if 'bot_data' in locals():
            bot_data['running'] = False


def start_trading_bot(username: str, bot_key: str, exchange, config: Dict[str, Any]) -> None:
    """
    启动交易机器人
    
    Args:
        username: 用户名
        bot_key: 机器人键
        exchange: 交易所适配器
        config: 配置字典
    """
    # 初始化用户数据
    if username not in user_bots:
        user_bots[username] = {'bots': {}}
    
    # 初始化机器人数据
    bot_data = {
        'exchange': exchange,
        'config': config,
        'running': False
    }
    
    user_bots[username]['bots'][bot_key] = bot_data
    
    # 启动交易循环线程
    thread = threading.Thread(
        target=trading_loop,
        args=(username, bot_key),
        daemon=True,
        name=f"TradingLoop-{username}-{bot_key}"
    )
    thread.start()
    
    # 保存线程引用，以便状态检查
    bot_data['thread'] = thread


def stop_trading_bot(username: str, bot_key: str) -> None:
    """
    停止交易机器人
    
    Args:
        username: 用户名
        bot_key: 机器人键
    """
    user_data = user_bots.get(username)
    if not user_data:
        return
    
    bot_data = user_data.get('bots', {}).get(bot_key)
    if not bot_data:
        return
    
    # 获取上下文并停止
    context: TradingContext = bot_data.get('context')
    if context:
        context.stop_trading()
    
    bot_data['running'] = False


def get_bot_status(username: str, bot_key: str) -> Dict[str, Any]:
    """
    获取机器人状态
    
    Args:
        username: 用户名
        bot_key: 机器人键
        
    Returns:
        状态字典
    """
    from .domain import OrderSide
    
    user_data = user_bots.get(username)
    if not user_data:
        return {}
    
    bot_data = user_data.get('bots', {}).get(bot_key)
    if not bot_data:
        return {}
    
    context: TradingContext = bot_data.get('context')
    if not context:
        return {'running': bot_data.get('running', False)}
    
    # 构建状态字典（兼容原有接口）
    return {
        'running': context.runtime.running,
        'current_price': context.market.current_price,
        'target_price': context.market.target_price,
        'is_placing_order': context.runtime.is_placing_order,
        'is_handling_buy_filled': context.runtime.is_handling_buy_filled,
        'last_error': context.runtime.last_error,
        'error_count': context.runtime.error_count,
        'last_error_time': context.runtime.last_error_time.isoformat() if context.runtime.last_error_time else None,
        'last_warning': context.runtime.last_warning,
        'pending_buys': [
            {
                'order_id': o.info.order_id,
                'price': o.info.price,
                'quantity': o.info.quantity,
                'grid_index': o.info.grid_index
            }
            for o in context.order_manager.get_active_orders(OrderSide.BUY)
        ],
        'pending_sells': [
            {
                'order_id': o.info.order_id,
                'price': o.info.price,
                'quantity': o.info.quantity,
                'buy_price': o.info.buy_price,
                'reprice_count': o.metrics.reprice_count
            }
            for o in context.order_manager.get_active_orders(OrderSide.SELL)
        ]
    }
