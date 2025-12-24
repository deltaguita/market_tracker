import os
import requests
from typing import Dict, List


class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    def _send_message(self, text: str, photo_url: str = None):
        """發送 Telegram 訊息"""
        if photo_url:
            # 發送圖片和文字
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            data = {
                "chat_id": self.chat_id,
                "photo": photo_url,
                "caption": text,
                "parse_mode": "HTML",
            }
        else:
            # 只發送文字
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}

        try:
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")
            return False

    def notify_new_product(self, product: Dict):
        """通知新商品上架"""
        # 根據實際提取的價格顯示
        price_parts = []
        if product.get("price_jpy", 0) > 0:
            price_parts.append(f"¥{product['price_jpy']:,}")
        if product.get("price_twd", 0) > 0:
            price_parts.append(f"NT${product['price_twd']:,}")
        price_str = " / ".join(price_parts) if price_parts else "價格未標示"

        message = (
            f"🆕 <b>新商品上架</b>\n\n"
            f"<b>{product['title']}</b>\n"
            f"💰 價格: {price_str}\n"
            f'🔗 <a href="{product["product_url"]}">查看商品</a>'
        )
        return self._send_message(message, product.get("image_url"))

    def notify_price_drop(self, product: Dict, old_price_jpy: int, old_price_twd: int = None):
        """通知價格降低（只以日幣價格作為比價基準）"""
        price_jpy = product.get("price_jpy", 0)
        price_twd = product.get("price_twd", 0)

        # 根據實際提取的價格顯示
        price_parts = []
        if price_jpy > 0:
            price_parts.append(f"¥{price_jpy:,}")
        if price_twd > 0:
            price_parts.append(f"NT${price_twd:,}")
        price_str = " / ".join(price_parts) if price_parts else "價格未標示"

        # 計算降價資訊（只以日幣價格計算，避免匯率變動造成的誤判）
        drop_str = ""
        if old_price_jpy > 0 and price_jpy > 0 and price_jpy < old_price_jpy:
            drop_jpy = old_price_jpy - price_jpy
            drop_percent_jpy = (drop_jpy / old_price_jpy) * 100
            # 確保百分比在合理範圍內（0-100%）
            if 0 <= drop_percent_jpy <= 100:
                drop_str = f"¥{drop_jpy:,} ({drop_percent_jpy:.1f}%)"

        # 原價資訊（只顯示日幣，因為比價基準是日幣）
        old_price_str = f"¥{old_price_jpy:,}" if old_price_jpy > 0 else "原價未標示"

        message = (
            f"📉 <b>價格降低</b>\n\n"
            f"<b>{product['title']}</b>\n"
            f"💰 價格: {price_str}\n"
            f"📊 降價: {drop_str}\n"
            f"📈 原價: {old_price_str}\n"
            f'🔗 <a href="{product["product_url"]}">查看商品</a>'
        )
        return self._send_message(message, product.get("image_url"))

    def notify_batch(self, new_products: List[Dict], price_dropped: List[Dict]):
        """批次通知"""
        success_count = 0
        total_count = len(new_products) + len(price_dropped)

        for product in new_products:
            if self.notify_new_product(product):
                success_count += 1

        for item in price_dropped:
            product = item["product"]
            # 只傳遞日幣價格作為比價基準
            if self.notify_price_drop(product, item["old_price_jpy"]):
                success_count += 1

        return success_count, total_count
