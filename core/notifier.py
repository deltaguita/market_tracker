"""
通知服務模組

提供 Telegram 通知功能，支援多來源（Mercari JP、Amazon US）的價格格式化。
"""

import os
import time
import requests
from typing import Dict, List, Optional


class TelegramNotifier:
    """Telegram 通知服務"""

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    def _send_message(self, text: str, photo_url: str = None) -> bool:
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

    def send_photo_file(self, photo_path: str, caption: str = "") -> bool:
        """
        發送本地圖片檔案到 Telegram
        
        Args:
            photo_path: 圖片檔案路徑
            caption: 圖片說明文字
        
        Returns:
            是否發送成功
        """
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        
        try:
            with open(photo_path, "rb") as photo:
                files = {"photo": photo}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                response = requests.post(url, files=files, data=data, timeout=30)
                response.raise_for_status()
                return True
        except FileNotFoundError:
            print(f"Photo file not found: {photo_path}")
            return False
        except Exception as e:
            print(f"Failed to send photo file: {e}")
            return False

    def notify_timeout_error(
        self, source: str, url: str, error_message: str, screenshot_path: str
    ) -> bool:
        """
        通知 timeout 錯誤，包含截圖
        
        Args:
            source: 來源名稱
            url: 發生錯誤的 URL
            error_message: 錯誤訊息
            screenshot_path: 截圖檔案路徑
        
        Returns:
            是否發送成功
        """
        source_display = self._get_source_display_name(source)
        message = (
            f"<b>⚠️ Timeout 錯誤</b> [{source_display}]\n\n"
            f"<b>URL:</b> {url}\n"
            f"<b>錯誤:</b> {error_message}\n"
            f"<b>時間:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        return self.send_photo_file(screenshot_path, message)

    def _format_price(self, product: Dict, source: str) -> str:
        """
        根據來源格式化價格
        
        Args:
            product: 商品資訊字典
            source: 來源名稱 ("amazon_us", "mercari_jp")
        
        Returns:
            格式化後的價格字串
        """
        if source == "amazon_us":
            price_usd = product.get("price_usd", 0)
            if price_usd > 0:
                return f"USD ${price_usd:.2f}"
            return "價格未標示"
        elif source == "mercari_jp":
            lines = []
            price_jpy = product.get("price_jpy", 0)
            price_twd = product.get("price_twd", 0)
            if price_jpy > 0:
                lines.append(f"日幣：¥{price_jpy:,}")
            if price_twd > 0:
                lines.append(f"台幣：NT${price_twd:,}")
            return "\n".join(lines) if lines else "價格未標示"
        else:
            # 預設格式：嘗試顯示所有可用價格
            lines = []
            if product.get("price_usd", 0) > 0:
                lines.append(f"USD ${product['price_usd']:.2f}")
            if product.get("price_jpy", 0) > 0:
                lines.append(f"¥{product['price_jpy']:,}")
            if product.get("price_twd", 0) > 0:
                lines.append(f"NT${product['price_twd']:,}")
            return "\n".join(lines) if lines else "價格未標示"

    def _get_source_display_name(self, source: str) -> str:
        """取得來源的顯示名稱"""
        source_names = {
            "amazon_us": "Amazon US",
            "mercari_jp": "Mercari JP",
        }
        return source_names.get(source, source)

    def notify_new_product(
        self,
        product: Dict,
        source: str = "mercari_jp",
        is_within_budget: bool = False,
    ) -> bool:
        """
        通知新商品上架
        
        Args:
            product: 商品資訊字典
            source: 來源名稱 ("amazon_us", "mercari_jp")
            is_within_budget: 是否在預算內
        
        Returns:
            是否發送成功
        """
        price_str = self._format_price(product, source)
        source_display = self._get_source_display_name(source)

        # 根據是否在預算內選擇不同的標題
        title = "有預算內目標商品上架" if is_within_budget else "新商品上架"

        # 變體名稱（如果有）
        variant_info = ""
        if product.get("variant_name"):
            variant_info = f"款式：{product['variant_name']}\n"

        message = (
            f"<b>{title}</b> [{source_display}]\n\n"
            f"<b>{product['title']}</b>\n"
            f"{variant_info}"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
        )
        return self._send_message(message, product.get("image_url"))

    def notify_price_drop(
        self,
        product: Dict,
        old_price: float,
        source: str = "mercari_jp",
        old_price_twd: int = None,
        max_threshold: float = None,
    ) -> bool:
        """
        通知價格降低
        
        Args:
            product: 商品資訊字典
            old_price: 舊價格（USD for amazon_us, JPY for mercari_jp）
            source: 來源名稱 ("amazon_us", "mercari_jp")
            old_price_twd: 舊台幣價格（僅 mercari_jp 使用）
            max_threshold: 價格上限（USD for amazon_us, NTD for mercari_jp）
        
        Returns:
            是否發送成功
        """
        source_display = self._get_source_display_name(source)
        
        if source == "amazon_us":
            return self._notify_price_drop_amazon(
                product, old_price, source_display, max_threshold
            )
        else:
            return self._notify_price_drop_mercari(
                product, old_price, old_price_twd, source_display, max_threshold
            )

    def _notify_price_drop_amazon(
        self,
        product: Dict,
        old_price_usd: float,
        source_display: str,
        max_usd: float = None,
    ) -> bool:
        """Amazon 商品價格降低通知"""
        price_usd = product.get("price_usd", 0)
        
        # 判斷是否從超過預算降到預算內
        dropped_to_budget = False
        if max_usd is not None and old_price_usd > max_usd and price_usd <= max_usd:
            dropped_to_budget = True

        # 計算降價資訊
        drop_str = ""
        if old_price_usd > 0 and price_usd > 0 and price_usd < old_price_usd:
            drop_usd = old_price_usd - price_usd
            drop_percent = (drop_usd / old_price_usd) * 100
            if 0 <= drop_percent <= 100:
                drop_str = f"降價: ${drop_usd:.2f} ({drop_percent:.1f}%)"

        # 構建價格行
        price_line = ""
        if old_price_usd > 0 and price_usd > 0:
            price_line = f"USD: <s>${old_price_usd:.2f}</s> -> ${price_usd:.2f}"
            if drop_str:
                price_line += f"  {drop_str}"
        elif price_usd > 0:
            price_line = f"USD ${price_usd:.2f}"

        price_str = price_line if price_line else "價格未標示"

        # 根據情況選擇標題
        title = "降價至預算範圍" if dropped_to_budget else "價格降低"

        # 變體名稱（如果有）
        variant_info = ""
        if product.get("variant_name"):
            variant_info = f"款式：{product['variant_name']}\n"

        message = (
            f"<b>{title}</b> [{source_display}]\n\n"
            f"<b>{product['title']}</b>\n"
            f"{variant_info}"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
        )
        return self._send_message(message, product.get("image_url"))

    def _notify_price_drop_mercari(
        self,
        product: Dict,
        old_price_jpy: int,
        old_price_twd: int,
        source_display: str,
        max_ntd: int = None,
    ) -> bool:
        """Mercari 商品價格降低通知（保持原有邏輯）"""
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
            if 0 <= drop_percent_jpy <= 100:
                drop_str = f"降價: ¥{drop_jpy:,} ({drop_percent_jpy:.1f}%)"

        # 構建日幣價格行
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
        title = "降價至預算範圍" if dropped_to_budget else "價格降低"

        message = (
            f"<b>{title}</b> [{source_display}]\n\n"
            f"<b>{product['title']}</b>\n"
            f"{price_str}\n"
            f'<a href="{product["product_url"]}">查看商品</a>'
        )
        return self._send_message(message, product.get("image_url"))

    def notify_batch(
        self,
        new_products: List[Dict],
        price_dropped: List[Dict],
        source: str = "mercari_jp",
        max_threshold: float = None,
        price_dropped_with_old_twd: List[Dict] = None,
    ) -> tuple:
        """
        批次通知
        
        Args:
            new_products: 新商品列表
            price_dropped: 降價商品列表
            source: 來源名稱 ("amazon_us", "mercari_jp")
            max_threshold: 價格上限（USD for amazon_us, NTD for mercari_jp）
            price_dropped_with_old_twd: 包含舊台幣價格的降價商品列表（僅 mercari_jp 使用）
        
        Returns:
            (成功數, 總數)
        """
        success_count = 0
        total_count = len(new_products) + len(price_dropped)

        # 使用 price_dropped_with_old_twd 如果提供，否則使用 price_dropped
        price_dropped_list = (
            price_dropped_with_old_twd if price_dropped_with_old_twd else price_dropped
        )

        for product in new_products:
            # 檢查是否在預算內
            is_within_budget = False
            if max_threshold is not None:
                if source == "amazon_us":
                    price = product.get("price_usd", 0)
                else:
                    price = product.get("price_twd", 0)
                is_within_budget = price > 0 and price <= max_threshold

            if self.notify_new_product(product, source=source, is_within_budget=is_within_budget):
                success_count += 1

        for item in price_dropped_list:
            product = item["product"]
            
            if source == "amazon_us":
                old_price = item.get("old_price_usd", 0)
                old_price_twd = None
            else:
                old_price = item.get("old_price_jpy", 0)
                old_price_twd = item.get("old_price_twd")

            if self.notify_price_drop(
                product,
                old_price,
                source=source,
                old_price_twd=old_price_twd,
                max_threshold=max_threshold,
            ):
                success_count += 1

        return success_count, total_count


# 為了向後相容，保留舊的函數簽名
def format_usd_price(price: float) -> str:
    """
    格式化 USD 價格
    
    Args:
        price: USD 價格數值
    
    Returns:
        格式化後的價格字串，如 "USD $19.99"
    """
    if price > 0:
        return f"USD ${price:.2f}"
    return "價格未標示"
