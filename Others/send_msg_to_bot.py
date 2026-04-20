"""
Telegram Bot 消息发送模块
"""

from typing import Optional

import requests

from tabox_config import load_config


CONFIG = load_config()
TELEGRAM_CONFIG = CONFIG["telegram"]
BOT_LIST = CONFIG.get("bot_list", [])


class TelegramBot:
    """Telegram Bot 消息发送类"""
    
    def __init__(self, bot_token: str, api_base_url: Optional[str] = None, request_timeout_seconds: Optional[int] = None):
        """
        初始化 Telegram Bot
        
        Args:
            bot_token: Bot Token（从 @BotFather 获得）
        """
        self.bot_token = bot_token
        self.request_timeout_seconds = request_timeout_seconds or int(TELEGRAM_CONFIG["requests_timeout_seconds"])
        base_url = (api_base_url or TELEGRAM_CONFIG["base_url"]).rstrip("/")
        self.api_url = f"{base_url}/bot{bot_token}"
    
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
            response = requests.post(url, json=payload, timeout=self.request_timeout_seconds)
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
            response = requests.post(url, json=payload, timeout=self.request_timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": str(e)}
    
    def get_me(self) -> dict:
        """获取 Bot 信息"""
        url = f"{self.api_url}/getMe"
        try:
            response = requests.get(url, timeout=self.request_timeout_seconds)
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
    first_bot = BOT_LIST[0] if isinstance(BOT_LIST, list) and BOT_LIST else {}
    bot_token = bot_token or str(first_bot.get("bot_token", ""))
    chat_id = chat_id or str(first_bot.get("chat_id", ""))

    if not bot_token or not chat_id:
        return {
            "ok": False,
            "error": "Missing bot_list[0].bot_token or bot_list[0].chat_id in taBOX.json"
        }
    
    bot = TelegramBot(bot_token)
    return bot.send_message(chat_id, message)


# 使用示例
if __name__ == "__main__":
    if not isinstance(BOT_LIST, list) or not BOT_LIST:
        raise SystemExit("No bot_list configured in taBOX.json")

    bot_i = BOT_LIST[2]
    print(f"使用 Bot: {bot_i.get('name', 'unknown')}")
    result = send_telegram_message(
        "早上好！From taBOX Server! 🎉",
        bot_token=bot_i["bot_token"],
        chat_id=bot_i["chat_id"],
    )
    print("结果:", result)
    
    # 方式2：直接传入参数
    # bot = TelegramBot("YOUR_BOT_TOKEN")
    # response = bot.send_message("YOUR_CHAT_ID", "这是一条测试消息")
    # print(response)
