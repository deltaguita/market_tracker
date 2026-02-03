import html
import os
import requests
from urllib.parse import quote
from typing import Dict, List, Optional


class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self._bot_username: Optional[str] = None
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    def _get_bot_username(self) -> Optional[str]:
        """取得 bot username，用於建構 ignore 連結"""
        if self._bot_username is not None:
            return self._bot_username
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                self._bot_username = data["result"].get("username")
                return self._bot_username
        except Exception as e:
            print(f"Failed to get bot username: {e}")
        return None

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

    def notify_new_product(self, product: Dict, is_within_budget: bool = False):
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

        # 根據是否在預算內選擇不同的標題
        title = "有預算內目標商品上架" if is_within_budget else "新商品上架"

        message = (
            f"<b>{title}</b>\n\n"
            f"<b>{product['title']}</b>\n"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
        )
        ignore_link = self._build_ignore_link(product["id"])
        if ignore_link:
            message += f"\n{ignore_link}"
        return self._send_message(message, product.get("image_url"))

    def notify_price_drop(
        self,
        product: Dict,
        old_price_jpy: int,
        old_price_twd: int = None,
        max_ntd: int = None,
    ):
        """通知價格降低（只以日幣價格作為比價基準）"""
        price_jpy = product.get("price_jpy", 0)
        price_twd = product.get("price_twd", 0)

        # 判斷是否從超過預算降到預算內
        dropped_to_budget = False
        if max_ntd is not None and old_price_twd is not None:
            if old_price_twd > max_ntd and price_twd <= max_ntd:
                dropped_to_budget = True

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

        # 根據情況選擇標題
        if dropped_to_budget:
            title = "降價至預算範圍"
        else:
            title = "價格降低"

        message = (
            f"<b>{title}</b>\n\n"
            f"<b>{product['title']}</b>\n"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
        )
        ignore_link = self._build_ignore_link(product["id"])
        if ignore_link:
            message += f"\n{ignore_link}"
        return self._send_message(message, product.get("image_url"))

    def _build_ignore_link(self, product_id: str) -> Optional[str]:
        """建構可點擊的 /ignore 連結，點擊後預填指令"""
        username = self._get_bot_username()
        if not username:
            return None
        text = quote(f"/ignore {product_id}")
        url = f"https://t.me/{username}?text={text}"
        display = html.escape(f"/ignore {product_id}")
        return f'<a href="{url}">{display}</a>'

    def notify_batch(
        self,
        new_products: List[Dict],
        price_dropped: List[Dict],
        max_ntd: int = None,
        price_dropped_with_old_twd: List[Dict] = None,
    ):
        """批次通知"""
        success_count = 0
        total_count = len(new_products) + len(price_dropped)

        # 使用 price_dropped_with_old_twd 如果提供，否則使用 price_dropped
        price_dropped_list = (
            price_dropped_with_old_twd if price_dropped_with_old_twd else price_dropped
        )

        for product in new_products:
            # 檢查是否在預算內
            is_within_budget = False
            if max_ntd is not None:
                price_twd = product.get("price_twd", 0)
                is_within_budget = price_twd > 0 and price_twd <= max_ntd

            if self.notify_new_product(product, is_within_budget=is_within_budget):
                success_count += 1

        for item in price_dropped_list:
            product = item["product"]
            old_price_jpy = item["old_price_jpy"]
            old_price_twd = item.get("old_price_twd")

            if self.notify_price_drop(product, old_price_jpy, old_price_twd, max_ntd):
                success_count += 1

        return success_count, total_count
