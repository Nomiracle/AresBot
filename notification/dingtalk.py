"""
钉钉消息通知实现类
"""
import requests
from datetime import datetime
from .base import BaseNotification


class DingTalkNotification(BaseNotification):
    """钉钉机器人消息通知"""
    
    DINGTALK_BASE_URL = "https://oapi.dingtalk.com/robot/send?access_token="
    
    def __init__(self, username: str = None, access_token: str = None):
        """初始化钉钉通知
        
        Args:
            username: 用户名，用于从数据库读取该用户的access_token
            access_token: 钉钉机器人 access_token，如传入则直接使用，否则从数据库读取
        """
        if access_token:
            self.webhook_url = self.DINGTALK_BASE_URL + access_token
        elif username:
            # 从数据库读取用户配置
            from database import get_system_config
            token = get_system_config(username, 'dingtalk_access_token')
            if token:
                self.webhook_url = self.DINGTALK_BASE_URL + token
            else:
                self.webhook_url = None
                print(f"[{datetime.now().isoformat()}] ⚠️ 钉钉access_token未配置，请在数据库中设置 (user={username})")
        else:
            self.webhook_url = None
            print(f"[{datetime.now().isoformat()}] ⚠️ 请提供username或access_token")
    
    def send(self, message: str) -> bool:
        """发送文本消息到钉钉
        
        Args:
            message: 要发送的消息内容
            
        Returns:
            bool: 是否发送成功
        """
        if not self.webhook_url:
            print(f"[{datetime.now().isoformat()}] ❌ 钉钉消息发送失败: webhook_url未配置")
            return False
        
        # 添加ares关键字前缀（钉钉机器人安全设置要求）
        message = f"[ares] {message}"
            
        try:
            headers = {"Content-Type": "application/json"}
            data = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }
            
            response = requests.post(
                self.webhook_url,
                headers=headers,
                json=data,
                timeout=10
            )
            
            result = response.json()
            if result.get("errcode") == 0:
                print(f"[{datetime.now().isoformat()}] ✅ 钉钉消息发送成功")
                return True
            else:
                print(f"[{datetime.now().isoformat()}] ❌ 钉钉消息发送失败: {result.get('errmsg')}")
                return False
                
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ 钉钉消息发送异常: {e}")
            return False


# 使用示例
if __name__ == '__main__':
    notifier = DingTalkNotification()
    notifier.send("这是一条测试消息")
