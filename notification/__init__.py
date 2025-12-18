"""
消息通知模块
"""
from .base import BaseNotification
from .dingtalk import DingTalkNotification

__all__ = ['BaseNotification', 'DingTalkNotification']
