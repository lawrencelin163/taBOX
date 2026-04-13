"""
Telegram Bot 消息发送模块
"""

import os
import requests
from typing import Optional


class TelegramBot:
    """Telegram Bot 消息发送类"""
    
    def __init__(self, bot_token: str):
        """
        初始化 Telegram Bot
        
        Args:
            bot_token: Bot Token（从 @BotFather 获得）
        """
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, chat_id: str, message: str) -> dict:
        """
        发送文本消息
        
        Args:
            chat_id: 聊天ID（可以是用户ID或群组ID）
            message: 要发送的消息内容
            
        Returns:
            API 响应字典
        """
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"  # 支持 HTML 格式
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": str(e)}
    
    def send_message_markdown(self, chat_id: str, message: str) -> dict:
        """
        发送 Markdown 格式的消息
        
        Args:
            chat_id: 聊天ID
            message: Markdown 格式的消息
            
        Returns:
            API 响应字典
        """
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": str(e)}
    
    def get_me(self) -> dict:
        """获取 Bot 信息"""
        url = f"{self.api_url}/getMe"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": str(e)}


def send_telegram_message(message: str, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> dict:
    """
    快速发送 Telegram 消息的便捷函数
    
    Args:
        message: 消息内容
        bot_token: Bot Token（如果为空则从环境变量读取）
        chat_id: 聊天ID（如果为空则从环境变量读取）
        
    Returns:
        API 响应字典
    """
    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        return {
            "ok": False,
            "error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
        }
    
    bot = TelegramBot(bot_token)
    return bot.send_message(chat_id, message)


# 使用示例
if __name__ == "__main__":
    # 方式1：使用环境变量
    # 需要设置: TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
    bot_data  = [['Lawrence', '8346872200:AAHkzYwxPLjtTHv4gWkKZ4O_TXWDQeMleBE', '6426368377'],
                 ['Odatee',   '8660446164:AAGNnsYm5N2U6s0ToBsNtESsj_sCa6yjonY', '8627815136']]
    bot_i = bot_data[0]

    print(f"使用 Bot 編號: {bot_data.index(bot_i)} (名稱: {bot_i[0]})")
    result = send_telegram_message("早上好！From taBOX Server! 🎉", bot_token=bot_i[1], chat_id=bot_i[2])
    print("结果:", result)
    
    # 方式2：直接传入参数
    # bot = TelegramBot("YOUR_BOT_TOKEN")
    # response = bot.send_message("YOUR_CHAT_ID", "这是一条测试消息")
    # print(response)
