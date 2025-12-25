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
        price_jpy = product.get("price_jpy", 0)
        price_twd = product.get("price_twd", 0)

        # 構建價格資訊
        price_lines = []
        if price_jpy > 0:
            price_lines.append(f"日幣：¥{price_jpy:,}")
        if price_twd > 0:
            price_lines.append(f"台幣：NT${price_twd:,}")

        price_str = "\n".join(price_lines) if price_lines else "價格未標示"

        message = (
            f"<b>新商品上架</b>\n\n"
            f"<b>{product['title']}</b>\n"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
        )
        return self._send_message(message, product.get("image_url"))

    def notify_price_drop(self, product: Dict, old_price_jpy: int):
        """通知價格降低（只以日幣價格作為比價基準）"""
        price_jpy = product.get("price_jpy", 0)
        price_twd = product.get("price_twd", 0)

        # 計算降價資訊（只以日幣價格計算，避免匯率變動造成的誤判）
        drop_str = ""
        if old_price_jpy > 0 and price_jpy > 0 and price_jpy < old_price_jpy:
            drop_jpy = old_price_jpy - price_jpy
            drop_percent_jpy = (drop_jpy / old_price_jpy) * 100
            # 確保百分比在合理範圍內（0-100%）
            if 0 <= drop_percent_jpy <= 100:
                drop_str = f"降價: ¥{drop_jpy:,} ({drop_percent_jpy:.1f}%)"

        # 構建日幣價格行（原價有刪除線，新價在箭頭後）
        jpy_line = ""
        if old_price_jpy > 0 and price_jpy > 0:
            jpy_line = f"日幣：<s>¥{old_price_jpy:,}</s> -> ¥{price_jpy:,}"
            if drop_str:
                jpy_line += f"  {drop_str}"
        elif price_jpy > 0:
            jpy_line = f"日幣：¥{price_jpy:,}"

        # 構建台幣價格行
        twd_line = ""
        if price_twd > 0:
            twd_line = f"台幣：NT${price_twd:,}"

        # 組合所有價格資訊
        price_lines = []
        if jpy_line:
            price_lines.append(jpy_line)
        if twd_line:
            price_lines.append(twd_line)

        price_str = "\n".join(price_lines) if price_lines else "價格未標示"

        message = (
            f"<b>價格降低</b>\n\n"
            f"<b>{product['title']}</b>\n"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
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
