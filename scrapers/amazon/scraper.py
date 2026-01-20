"""
Amazon US 爬蟲模組

繼承 BaseScraper，實作 Amazon 美國網站的商品爬取邏輯。
支援：
- 單一商品頁面爬取
- 商品變體（顏色/尺寸）提取
- ASIN 提取
- 加購商品過濾
- 美國地區設定以確保 USD 價格
"""

import re
import time
import os
from datetime import datetime
from typing import List, Dict, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from core.base_scraper import BaseScraper


class AmazonScraper(BaseScraper):
    """
    Amazon US 爬蟲
    
    繼承 BaseScraper，實作 Amazon 美國網站特定的爬取邏輯。
    支援商品變體提取和加購商品過濾。
    """
    
    # 美國郵遞區號，用於設定配送地址以確保顯示 USD 價格
    US_ZIP_CODE = "19720"  # Delaware, USA (免稅州)
    
    # ASIN 提取的 URL 模式
    ASIN_PATTERNS = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
        r'/ASIN/([A-Z0-9]{10})',
        r'asin=([A-Z0-9]{10})',
    ]
    
    # 需要忽略的加購商品區塊選擇器
    ADDON_SECTION_SELECTORS = [
        '#similarities_feature_div',           # "Customers who viewed this item also viewed"
        '#sims-fbt',                            # "Frequently bought together"
        '#sp_detail',                           # "Sponsored products related to this item"
        '#anonCarousel',                        # "More items to explore"
        '#brand-snapshot-widget',              # "From the brand"
        '#HLCXComparisonWidget_feature_div',   # "Compare with similar items"
        '#sims-consolidated-1_feature_div',    # "Products related to this item"
        '#sims-consolidated-2_feature_div',    # More related products
        '#rhf',                                 # "Your recently viewed items"
        '#day0-sims-feature',                  # Day 0 recommendations
        '#p13n-asin-recommendations',          # Personalized recommendations
        '#sponsoredProducts2_feature_div',     # More sponsored products
        '#amsDetailRight_feature_div',         # Right side ads
        '#productAlert_feature_div',           # Product alerts
        '#almComparisonWidget_feature_div',    # "4 stars and above" comparison
    ]
    
    # 加購區塊的文字標識
    ADDON_SECTION_TEXTS = [
        'frequently bought together',
        'customers who viewed this item also viewed',
        'sponsored products related to this item',
        'more items to explore',
        'from the brand',
        'compare with similar items',
        'products related to this item',
        'your recently viewed items',
        '4 stars and above',
        'customers also search',
    ]
    
    def __init__(self, headless: bool = True, notifier=None):
        """
        初始化 Amazon 爬蟲
        
        Args:
            headless: 是否以無頭模式運行瀏覽器
            notifier: TelegramNotifier 實例（可選，用於發送 timeout 通知）
        """
        super().__init__(headless=headless)
        self.notifier = notifier
    
    @property
    def source_name(self) -> str:
        """返回來源名稱"""
        return "amazon_us"
    
    def get_product_id(self, url: str) -> Optional[str]:
        """
        從 URL 提取 ASIN (Amazon Standard Identification Number)
        
        支援多種 Amazon URL 格式：
        - https://www.amazon.com/dp/B013HLGTL2
        - https://www.amazon.com/gp/product/B013HLGTL2
        - https://www.amazon.com/product/B013HLGTL2
        - https://www.amazon.com/dp/B013HLGTL2?ref=something
        
        Args:
            url: Amazon 商品頁面 URL
            
        Returns:
            ASIN 字串（10 位英數字），若無法提取則返回 None
        """
        if not url:
            return None
        
        for pattern in self.ASIN_PATTERNS:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def parse_product(self, element) -> Optional[Dict]:
        """
        解析單一商品元素
        
        此方法主要用於內部調用，從頁面元素中提取商品資訊。
        
        Args:
            element: Playwright Locator 元素
            
        Returns:
            商品資訊字典，若解析失敗則返回 None
        """
        # Amazon 爬蟲主要使用 _extract_main_product 和 _extract_variants
        # 此方法提供一個簡化版本供外部調用
        return None
    
    def scrape(self, url: str) -> List[Dict]:
        """
        爬取 Amazon 商品頁面，返回所有變體
        
        流程：
        1. 初始化瀏覽器
        2. 載入頁面
        3. 處理可能的 CAPTCHA
        4. 設定美國地區以確保 USD 價格
        5. 提取主商品資訊
        6. 提取所有變體
        7. 返回商品列表
        
        Args:
            url: Amazon 商品頁面 URL
            
        Returns:
            商品資訊字典列表
        """
        self._init_browser()
        try:
            # 載入頁面
            print(f"Loading Amazon URL: {url}")
            self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 處理可能的 CAPTCHA
            self._handle_captcha()
            
            # 設定美國地區以確保 USD 價格
            self._set_us_location()
            
            # 確保關閉所有彈出視窗（location popover 等）
            self._close_all_popovers()
            
            # 等待頁面穩定
            time.sleep(2)
            
            # 提取 ASIN
            asin = self.get_product_id(url)
            if not asin:
                # 嘗試從頁面中提取 ASIN
                asin = self._extract_asin_from_page()
            
            if not asin:
                print("Warning: Could not extract ASIN from URL or page")
                return []
            
            print(f"Extracted ASIN: {asin}")
            
            # 提取所有變體
            variants = self._extract_variants(asin)
            
            if variants:
                print(f"Found {len(variants)} variants")
                return variants
            
            # 如果沒有變體，提取主商品資訊
            main_product = self._extract_main_product(asin)
            if main_product:
                print("No variants found, returning main product")
                return [main_product]
            
            return []
            
        except PlaywrightTimeoutError as e:
            error_msg = str(e)
            print(f"Error scraping Amazon page: {error_msg}")
            # 截圖並發送通知
            self._handle_timeout_error("scrape", error_msg, url)
            return []
        except Exception as e:
            print(f"Error scraping Amazon page: {e}")
            return []
        finally:
            self._close_browser()
    
    def _handle_timeout_error(self, operation: str, error_message: str, url: str = None) -> None:
        """
        處理 timeout 錯誤：截圖並發送 Telegram 通知
        
        Args:
            operation: 發生錯誤的操作名稱
            error_message: 錯誤訊息
            url: 當前 URL（可選）
        """
        if not self._page:
            return
        
        try:
            # 創建截圖目錄
            screenshot_dir = "data/screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            
            # 生成截圖檔名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = os.path.join(
                screenshot_dir, f"timeout_{operation}_{timestamp}.png"
            )
            
            # 截圖
            self._page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")
            
            # 發送 Telegram 通知（如果配置了 notifier）
            if self.notifier:
                current_url = url or self._page.url
                self.notifier.notify_timeout_error(
                    source=self.source_name,
                    url=current_url,
                    error_message=f"{operation}: {error_message}",
                    screenshot_path=screenshot_path,
                )
                print("Timeout notification sent to Telegram")
            else:
                print("Telegram notifier not configured, skipping notification")
                
        except Exception as e:
            print(f"Error handling timeout: {e}")
    
    def _handle_captcha(self) -> None:
        """
        處理可能的 CAPTCHA 驗證頁面
        
        檢測並嘗試處理 Amazon 的機器人驗證頁面。
        如果檢測到 CAPTCHA，嘗試點擊 "Continue shopping" 按鈕。
        """
        try:
            # 檢查是否在 CAPTCHA 頁面
            captcha_indicators = [
                'input[name="captcha"]',
                '#captchacharacters',
                'form[action*="validateCaptcha"]',
                'img[src*="captcha"]',
            ]
            
            for selector in captcha_indicators:
                if self._page.locator(selector).count() > 0:
                    print("Warning: CAPTCHA detected!")
                    
                    # 嘗試點擊 "Continue shopping" 或類似按鈕
                    continue_buttons = [
                        'input[type="submit"]',
                        'button:has-text("Continue")',
                        'a:has-text("Continue shopping")',
                    ]
                    
                    for btn_selector in continue_buttons:
                        btn = self._page.locator(btn_selector).first
                        if btn.count() > 0 and btn.is_visible():
                            print("Attempting to click continue button...")
                            btn.click()
                            time.sleep(3)
                            break
                    
                    return
            
            # 檢查是否被重定向到登入頁面
            if '/ap/signin' in self._page.url or '/ap/cvf' in self._page.url:
                print("Warning: Redirected to sign-in page")
                # 嘗試返回商品頁面
                self._page.go_back()
                time.sleep(2)
                
        except Exception as e:
            print(f"Warning: Error handling CAPTCHA: {e}")
    
    def _set_us_location(self) -> None:
        """
        設定美國配送地址以確保顯示 USD 價格
        
        流程：
        1. 點擊配送地址選擇器
        2. 選擇美國
        3. 輸入美國郵遞區號 (19720 - Delaware)
        4. 套用設定
        """
        try:
            # 點擊配送地址選擇器
            delivery_selector = self._page.locator("#nav-global-location-popover-link")
            
            if delivery_selector.count() > 0 and delivery_selector.is_visible():
                print("Setting US delivery location...")
                delivery_selector.click()
                
                # 等待彈出視窗
                time.sleep(1)
                
                # 嘗試找到並點擊「選擇國家」下拉選單
                try:
                    # 先嘗試選擇美國（如果有國家選擇器）
                    country_dropdown = self._page.locator("#GLUXCountryList, #GLUXCountryListDropdown")
                    if country_dropdown.count() > 0:
                        country_dropdown.click()
                        time.sleep(0.5)
                        
                        # 選擇美國
                        us_option = self._page.locator("a[data-value='US'], li:has-text('United States')")
                        if us_option.count() > 0:
                            us_option.first.click()
                            time.sleep(1)
                except Exception:
                    pass
                
                # 等待郵遞區號輸入框
                try:
                    self._page.wait_for_selector("#GLUXZipUpdateInput", timeout=30000)
                    
                    # 輸入美國郵遞區號
                    zip_input = self._page.locator("#GLUXZipUpdateInput")
                    if zip_input.count() > 0:
                        zip_input.fill("")  # 清空
                        zip_input.fill(self.US_ZIP_CODE)
                        print(f"Entered ZIP code: {self.US_ZIP_CODE}")
                        
                        # 點擊套用按鈕
                        apply_button = self._page.locator(
                            "#GLUXZipUpdate input[type='submit'], "
                            "#GLUXZipUpdate-announce, "
                            "span[data-action='GLUXPostalUpdateAction']"
                        )
                        
                        if apply_button.count() > 0:
                            apply_button.first.click()
                            print("Applied ZIP code")
                            time.sleep(3)  # 等待確認訊息出現
                            
                            # 關閉彈出視窗（確認按鈕）
                            # 確認按鈕可能在確認訊息出現後才可見
                            close_selectors = [
                                "#GLUXConfirmClose",
                                "input#GLUXConfirmClose[type='submit']",
                                "button[data-action='a-popover-close']",
                                ".a-popover-close",
                            ]
                            
                            closed = False
                            for selector in close_selectors:
                                close_btn = self._page.locator(selector).first
                                if close_btn.count() > 0:
                                    try:
                                        # 等待按鈕可見
                                        close_btn.wait_for(state="visible", timeout=3000)
                                        close_btn.click(timeout=2000)
                                        print("Closed location popover")
                                        closed = True
                                        time.sleep(1)
                                        break
                                    except Exception:
                                        # 如果不可見，嘗試 force 點擊
                                        try:
                                            close_btn.click(timeout=2000, force=True)
                                            print("Closed location popover (force)")
                                            closed = True
                                            time.sleep(1)
                                            break
                                        except Exception:
                                            continue
                            
                            # 如果還是沒關閉，嘗試按 ESC
                            if not closed:
                                try:
                                    self._page.keyboard.press("Escape")
                                    time.sleep(1)
                                except Exception:
                                    pass
                            
                            # 重新載入頁面以套用地區設定
                            print("Reloading page to apply location settings...")
                            self._page.reload(wait_until="domcontentloaded")
                            time.sleep(2)
                            
                except PlaywrightTimeoutError as e:
                    error_msg = f"Timeout 30000ms exceeded."
                    print(f"Warning: {error_msg}")
                    # 截圖並發送通知
                    self._handle_timeout_error("_set_us_location", error_msg)
                    # 嘗試關閉彈出視窗
                    self._close_all_popovers()
                        
        except PlaywrightTimeoutError as e:
            error_msg = str(e)
            print(f"Warning: Failed to set US location: {error_msg}")
            # 截圖並發送通知
            self._handle_timeout_error("_set_us_location", error_msg)
            # 繼續執行，可能已經是 USD 價格
        except Exception as e:
            print(f"Warning: Failed to set US location: {e}")
            # 繼續執行，可能已經是 USD 價格
    
    def _close_all_popovers(self) -> None:
        """
        關閉所有彈出視窗（location popover 等）
        
        確保在提取變體之前沒有彈出視窗擋住元素。
        """
        try:
            # 檢查是否有彈出視窗
            popover = self._page.locator(".a-popover, [data-action='a-popover-floating-close']").first
            if popover.count() == 0:
                return  # 沒有彈出視窗
            
            # 嘗試關閉 location popover
            close_selectors = [
                "#GLUXConfirmClose",
                "button[data-action='a-popover-close']",
                ".a-popover-close",
                "button[aria-label='Close']",
            ]
            
            for selector in close_selectors:
                close_btn = self._page.locator(selector).first
                if close_btn.count() > 0:
                    try:
                        # 使用 force 點擊，即使被其他元素擋住
                        close_btn.click(timeout=2000, force=True)
                        time.sleep(0.5)
                        break
                    except Exception:
                        continue
            
            # 如果還有彈出視窗，嘗試按 ESC 鍵
            try:
                self._page.keyboard.press("Escape")
                time.sleep(0.5)
            except Exception:
                pass
            
            # 再次檢查是否關閉
            popover = self._page.locator(".a-popover, [data-action='a-popover-floating-close']").first
            if popover.count() > 0:
                # 如果還存在，嘗試點擊頁面其他地方關閉
                try:
                    self._page.click("body", position={"x": 10, "y": 10}, timeout=1000)
                    time.sleep(0.5)
                except Exception:
                    pass
                
        except Exception as e:
            print(f"Warning: Error closing popovers: {e}")

    
    def _extract_asin_from_page(self) -> Optional[str]:
        """
        從頁面內容中提取 ASIN
        
        當無法從 URL 提取 ASIN 時，嘗試從頁面元素中提取。
        
        Returns:
            ASIN 字串，若無法提取則返回 None
        """
        try:
            # 嘗試從頁面 URL 提取（可能已重定向）
            current_url = self._page.url
            asin = self.get_product_id(current_url)
            if asin:
                return asin
            
            # 嘗試從頁面元素提取
            # 方法 1: 從 product details 表格
            detail_bullets = self._page.locator("#productDetails_detailBullets_sections1")
            if detail_bullets.count() > 0:
                text = detail_bullets.inner_text()
                match = re.search(r'ASIN[:\s]+([A-Z0-9]{10})', text, re.IGNORECASE)
                if match:
                    return match.group(1).upper()
            
            # 方法 2: 從 hidden input
            asin_input = self._page.locator("input[name='ASIN'], input[id='ASIN']")
            if asin_input.count() > 0:
                asin_value = asin_input.get_attribute("value")
                if asin_value and len(asin_value) == 10:
                    return asin_value.upper()
            
            # 方法 3: 從 data 屬性
            dp_container = self._page.locator("#dp, #dp-container")
            if dp_container.count() > 0:
                data_asin = dp_container.get_attribute("data-asin")
                if data_asin and len(data_asin) == 10:
                    return data_asin.upper()
            
            # 方法 4: 從頁面 HTML 中搜尋
            html = self._page.content()
            match = re.search(r'"ASIN"\s*:\s*"([A-Z0-9]{10})"', html, re.IGNORECASE)
            if match:
                return match.group(1).upper()
                
        except Exception as e:
            print(f"Warning: Error extracting ASIN from page: {e}")
        
        return None
    
    def _extract_main_product(self, asin: str) -> Optional[Dict]:
        """
        提取主商品資訊
        
        從 #dp 容器提取商品的標題、價格、圖片等資訊。
        
        Args:
            asin: 商品 ASIN
            
        Returns:
            商品資訊字典，若提取失敗則返回 None
        """
        try:
            # 提取標題
            title = self._extract_title()
            if not title:
                print("Warning: Could not extract product title")
                return None
            
            # 提取價格
            price_usd = self._extract_price()
            
            # 提取圖片 URL
            image_url = self._extract_image_url()
            
            # 構建商品 URL
            product_url = f"https://www.amazon.com/dp/{asin}"
            
            # 檢查庫存狀態
            availability = self._extract_availability()
            
            product = {
                "id": asin,
                "title": title,
                "price_usd": price_usd,
                "image_url": image_url,
                "product_url": product_url,
                "variant_name": None,
                "availability": availability,
            }
            
            return product
            
        except Exception as e:
            print(f"Error extracting main product: {e}")
            return None
    
    def _extract_title(self) -> Optional[str]:
        """提取商品標題"""
        selectors = [
            "#productTitle",
            "h1#title span",
            "h1.product-title-word-break",
            "#title",
            "h1",
        ]
        
        for selector in selectors:
            element = self._page.locator(selector).first
            if element.count() > 0:
                try:
                    title = element.inner_text().strip()
                    if title and len(title) > 3:
                        return title
                except Exception:
                    continue
        
        return None
    
    def _extract_price(self) -> Optional[float]:
        """
        提取商品價格（USD）
        
        嘗試多種選擇器以適應不同的頁面結構。
        
        Returns:
            價格（浮點數），若無法提取則返回 None
        """
        return self._extract_price_from_page(self._page)
    
    def _extract_price_from_page(self, page) -> Optional[float]:
        """
        從指定頁面提取商品價格（USD）
        
        Args:
            page: Playwright Page 對象
            
        Returns:
            價格（浮點數），若無法提取則返回 None
        """
        price_selectors = [
            # 主要價格選擇器
            ".a-price .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#priceblock_saleprice",
            "#corePrice_feature_div .a-price .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
            "#apex_offerDisplay_desktop .a-price .a-offscreen",
            "span.a-price span.a-offscreen",
            # 備用選擇器
            "#price_inside_buybox",
            "#newBuyBoxPrice",
            ".offer-price",
            "#buyNewSection .a-price .a-offscreen",
        ]
        
        for selector in price_selectors:
            elements = page.locator(selector).all()
            for element in elements:
                try:
                    # 檢查元素是否在加購區塊中（僅對主頁面檢查）
                    if page == self._page and self._is_in_addon_section(element):
                        continue
                    
                    price_text = element.inner_text().strip()
                    price = self._parse_usd_price(price_text)
                    if price is not None and price > 0:
                        return price
                except Exception:
                    continue
        
        return None
    
    def _parse_usd_price(self, price_text: str) -> Optional[float]:
        """
        解析 USD 價格文字
        
        支援格式：
        - $19.99
        - $1,234.56
        - USD 19.99
        - 19.99
        
        Args:
            price_text: 價格文字
            
        Returns:
            價格浮點數，若解析失敗則返回 None
        """
        if not price_text:
            return None
        
        # 移除貨幣符號和空白
        cleaned = price_text.replace("$", "").replace("USD", "").replace(",", "").strip()
        
        # 嘗試提取數字
        match = re.search(r'(\d+\.?\d*)', cleaned)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        return None
    
    def _extract_image_url(self) -> Optional[str]:
        """提取商品主圖 URL"""
        selectors = [
            "#landingImage",
            "#imgTagWrapperId img",
            "#main-image",
            "#imgBlkFront",
            ".a-dynamic-image",
        ]
        
        for selector in selectors:
            element = self._page.locator(selector).first
            if element.count() > 0:
                try:
                    # 優先使用 data-old-hires（高解析度圖片）
                    src = element.get_attribute("data-old-hires")
                    if src:
                        return src
                    
                    # 其次使用 src
                    src = element.get_attribute("src")
                    if src and not src.startswith("data:"):
                        return src
                except Exception:
                    continue
        
        return None
    
    def _extract_availability(self) -> str:
        """
        提取商品庫存狀態
        
        Returns:
            "in_stock", "out_of_stock", 或 "unknown"
        """
        try:
            # 檢查庫存狀態元素
            availability_element = self._page.locator("#availability, #availability span").first
            if availability_element.count() > 0:
                text = availability_element.inner_text().lower()
                if "in stock" in text or "有庫存" in text:
                    return "in_stock"
                elif "out of stock" in text or "unavailable" in text or "無庫存" in text:
                    return "out_of_stock"
            
            # 檢查是否有加入購物車按鈕
            add_to_cart = self._page.locator("#add-to-cart-button, #buy-now-button")
            if add_to_cart.count() > 0 and add_to_cart.is_visible():
                return "in_stock"
            
        except Exception:
            pass
        
        return "unknown"

    
    def _extract_variants(self, base_asin: str) -> List[Dict]:
        """
        提取所有顏色/尺寸變體
        
        從變體選擇器（顏色、尺寸等）提取所有變體資訊。
        每個變體生成一個獨立的商品記錄。
        
        Args:
            base_asin: 基礎商品 ASIN
            
        Returns:
            變體商品列表
        """
        variants = []
        
        try:
            # 提取基礎商品資訊（標題、圖片）
            base_title = self._extract_title()
            base_image = self._extract_image_url()
            
            # 嘗試提取顏色變體
            color_variants = self._extract_color_variants(base_asin, base_title, base_image)
            if color_variants:
                variants.extend(color_variants)
            
            # 嘗試提取尺寸變體（如果沒有顏色變體）
            if not variants:
                size_variants = self._extract_size_variants(base_asin, base_title, base_image)
                if size_variants:
                    variants.extend(size_variants)
            
            # 嘗試提取樣式變體
            if not variants:
                style_variants = self._extract_style_variants(base_asin, base_title, base_image)
                if style_variants:
                    variants.extend(style_variants)
            
        except Exception as e:
            print(f"Error extracting variants: {e}")
        
        return variants
    
    def _extract_color_variants(self, base_asin: str, base_title: str, base_image: str) -> List[Dict]:
        """提取顏色變體"""
        variants = []
        
        # 顏色選擇器的可能位置
        color_selectors = [
            "#variation_color_name li",
            "#variation_color_name ul li",
            "#twister-plus-inline-twister-card li.dimension-value-list-item-square-image",
            "#twister-plus-inline-twister-card li",
            "[data-action='variationSelect'] li",
            "#tp-inline-twister-dim-values-container li",
        ]
        
        for selector in color_selectors:
            color_items = self._page.locator(selector).all()
            if not color_items:
                continue
            
            print(f"Found {len(color_items)} color options using: {selector}")
            
            for item in color_items:
                try:
                    # 檢查是否在加購區塊中
                    if self._is_in_addon_section(item):
                        continue
                    
                    variant = self._extract_variant_from_element(item, base_asin, base_title, base_image, "color")
                    if variant:
                        variants.append(variant)
                        
                except Exception as e:
                    print(f"Warning: Error extracting color variant: {e}")
                    continue
            
            if variants:
                break
        
        return variants
    
    def _extract_size_variants(self, base_asin: str, base_title: str, base_image: str) -> List[Dict]:
        """提取尺寸變體"""
        variants = []
        
        size_selectors = [
            "#variation_size_name li",
            "#variation_size_name ul li",
            "#native_dropdown_selected_size_name option",
        ]
        
        for selector in size_selectors:
            size_items = self._page.locator(selector).all()
            if not size_items:
                continue
            
            print(f"Found {len(size_items)} size options using: {selector}")
            
            for item in size_items:
                try:
                    if self._is_in_addon_section(item):
                        continue
                    
                    variant = self._extract_variant_from_element(item, base_asin, base_title, base_image, "size")
                    if variant:
                        variants.append(variant)
                        
                except Exception:
                    continue
            
            if variants:
                break
        
        return variants
    
    def _extract_style_variants(self, base_asin: str, base_title: str, base_image: str) -> List[Dict]:
        """提取樣式變體"""
        variants = []
        
        style_selectors = [
            "#variation_style_name li",
            "#variation_pattern_name li",
            "#variation_configuration li",
        ]
        
        for selector in style_selectors:
            style_items = self._page.locator(selector).all()
            if not style_items:
                continue
            
            print(f"Found {len(style_items)} style options using: {selector}")
            
            for item in style_items:
                try:
                    if self._is_in_addon_section(item):
                        continue
                    
                    variant = self._extract_variant_from_element(item, base_asin, base_title, base_image, "style")
                    if variant:
                        variants.append(variant)
                        
                except Exception:
                    continue
            
            if variants:
                break
        
        return variants
    
    def _extract_variant_from_element(
        self, 
        element, 
        base_asin: str, 
        base_title: str, 
        base_image: str,
        variant_type: str
    ) -> Optional[Dict]:
        """
        從變體元素中提取資訊
        
        Args:
            element: 變體元素
            base_asin: 基礎 ASIN
            base_title: 基礎標題
            base_image: 基礎圖片
            variant_type: 變體類型 (color, size, style)
            
        Returns:
            變體商品字典
        """
        try:
            # 提取變體名稱
            variant_name = self._get_variant_name(element)
            if not variant_name:
                return None
            
            # 生成變體 ID
            variant_identifier = self._normalize_variant_identifier(variant_name)
            variant_id = f"{base_asin}_{variant_identifier}"
            
            # 嘗試提取變體專屬 ASIN
            variant_asin = self._get_variant_asin(element)
            if variant_asin and variant_asin != base_asin:
                variant_id = f"{variant_asin}_{variant_identifier}"
            
            # 提取變體價格
            # 優先方法：直接從變體元素本身提取價格（不需要點擊）
            variant_price = self._get_variant_price(element)
            
            # 如果從元素本身無法提取價格，才嘗試其他方法
            if variant_price is None:
                # 備用方法：如果變體有專屬 ASIN，直接訪問該變體的 URL 獲取價格
                if variant_asin and variant_asin != base_asin:
                    try:
                        variant_url = f"https://www.amazon.com/dp/{variant_asin}"
                        context = self._page.context
                        new_page = context.new_page()
                        try:
                            new_page.goto(variant_url, wait_until="domcontentloaded", timeout=30000)
                            # 處理可能的 CAPTCHA
                            try:
                                captcha_btn = new_page.locator('input[type="submit"], button:has-text("Continue")').first
                                if captcha_btn.count() > 0 and captcha_btn.is_visible():
                                    captcha_btn.click(timeout=2000)
                                    time.sleep(1)
                            except Exception:
                                pass
                            time.sleep(2)
                            variant_price = self._extract_price_from_page(new_page)
                            if variant_price:
                                print(f"  Extracted price ${variant_price} for {variant_name} from variant URL")
                        finally:
                            new_page.close()
                    except Exception as e:
                        print(f"Warning: Could not fetch price from variant URL: {e}")
                
                # 最後備用：點擊變體並等待價格更新（不推薦，因為可能被彈出視窗擋住）
                if variant_price is None:
                    try:
                        self._close_all_popovers()
                        if element.is_visible():
                            old_price = self._extract_price()
                            # 使用 JavaScript 觸發變體選擇
                            try:
                                variant_asin_attr = element.get_attribute("data-asin") or element.get_attribute("data-defaultasin")
                                if variant_asin_attr:
                                    self._page.evaluate("""
                                        (asin) => {
                                            const variant = document.querySelector(`[data-asin="${asin}"], [data-defaultasin="${asin}"]`);
                                            if (variant) {
                                                variant.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                                                variant.dispatchEvent(new Event('change', { bubbles: true }));
                                            }
                                        }
                                    """, variant_asin_attr)
                                else:
                                    element.evaluate("element => element.click()")
                            except Exception:
                                try:
                                    element.click(timeout=5000, force=True)
                                except Exception:
                                    pass
                            
                            # 等待價格更新
                            for i in range(8):
                                time.sleep(0.5)
                                new_price = self._extract_price()
                                if new_price is not None and new_price != old_price:
                                    variant_price = new_price
                                    print(f"  Extracted price ${variant_price} for {variant_name} after selection")
                                    break
                                elif new_price is not None and i >= 3:
                                    variant_price = new_price
                                    break
                            
                            if variant_price is None:
                                variant_price = self._extract_price()
                    except Exception as e:
                        print(f"Warning: Error selecting variant: {e}")
            
            if variant_price:
                print(f"  Extracted price ${variant_price} for {variant_name}")
            
            # 提取變體圖片
            variant_image = self._get_variant_image(element) or base_image
            
            # 構建商品 URL
            product_url = f"https://www.amazon.com/dp/{variant_asin or base_asin}"
            
            # 檢查庫存狀態
            availability = self._get_variant_availability(element)
            
            return {
                "id": variant_id,
                "title": f"{base_title} - {variant_name}" if base_title else variant_name,
                "price_usd": variant_price,
                "image_url": variant_image,
                "product_url": product_url,
                "variant_name": variant_name,
                "availability": availability,
            }
            
        except Exception as e:
            print(f"Warning: Error extracting variant: {e}")
            return None
    
    def _get_variant_name(self, element) -> Optional[str]:
        """從變體元素提取名稱"""
        try:
            # 嘗試從 title 屬性
            title = element.get_attribute("title")
            if title:
                # 清理 "Click to select" 等前綴
                title = re.sub(r'^Click to select\s*', '', title, flags=re.IGNORECASE)
                if title:
                    return title.strip()
            
            # 嘗試從 aria-label
            aria_label = element.get_attribute("aria-label")
            if aria_label:
                return aria_label.strip()
            
            # 嘗試從 alt 屬性（圖片）
            img = element.locator("img").first
            if img.count() > 0:
                alt = img.get_attribute("alt")
                if alt:
                    return alt.strip()
            
            # 嘗試從文字內容
            text = element.inner_text().strip()
            if text and len(text) < 100:  # 避免取到太長的文字
                return text
            
        except Exception:
            pass
        
        return None
    
    def _get_variant_asin(self, element) -> Optional[str]:
        """從變體元素提取專屬 ASIN"""
        try:
            # 嘗試從 data-defaultasin
            asin = element.get_attribute("data-defaultasin")
            if asin and len(asin) == 10:
                return asin.upper()
            
            # 嘗試從 data-dp-url
            dp_url = element.get_attribute("data-dp-url")
            if dp_url:
                asin = self.get_product_id(dp_url)
                if asin:
                    return asin
            
            # 嘗試從 href
            link = element.locator("a").first
            if link.count() > 0:
                href = link.get_attribute("href")
                if href:
                    asin = self.get_product_id(href)
                    if asin:
                        return asin
            
        except Exception:
            pass
        
        return None
    
    def _get_variant_price(self, element) -> Optional[float]:
        """
        從變體元素提取價格
        
        根據截圖，每個變體元素本身就有顯示價格，不需要點擊。
        實際售價通常出現在 "with X percent savings" 之前，或是最小的價格。
        """
        try:
            # 使用 JavaScript 查找元素內所有包含 $ 的文字（優先）
            # 優先選擇實際售價（通常是最小的價格，或出現在 "with X percent savings" 之前的價格）
            price_text = element.evaluate("""
                (element) => {
                    // 查找所有價格
                    const allText = element.innerText || element.textContent;
                    const priceMatches = allText.match(/\\$[\\d,]+\\.[\\d]{2}/g);
                    
                    if (!priceMatches || priceMatches.length === 0) {
                        return null;
                    }
                    
                    // 如果只有一個價格，直接返回
                    if (priceMatches.length === 1) {
                        return priceMatches[0];
                    }
                    
                    // 如果有多個價格，優先選擇：
                    // 1. 出現在 "with X percent savings" 之前的價格（實際售價）
                    // 2. 最小的價格（實際售價通常比 List Price 小）
                    
                    // 檢查是否有 "with X percent savings" 的文字
                    const savingsMatch = allText.match(/\\$[\\d,]+\\.[\\d]{2}\\s+with\\s+\\d+\\s+percent\\s+savings/i);
                    if (savingsMatch) {
                        // 返回 "with X percent savings" 之前的價格
                        return savingsMatch[0].match(/\\$[\\d,]+\\.[\\d]{2}/)[0];
                    }
                    
                    // 如果沒有 savings 文字，選擇最小的價格
                    const prices = priceMatches.map(p => {
                        const num = parseFloat(p.replace(/[\\$,]/g, ''));
                        return { text: p, num: num };
                    });
                    
                    // 排序並返回最小的（實際售價）
                    prices.sort((a, b) => a.num - b.num);
                    return prices[0].text;
                }
            """)
            
            if price_text:
                price = self._parse_usd_price(price_text)
                if price:
                    return price
        except Exception:
            pass
        
        return None
    
    def _get_variant_image(self, element) -> Optional[str]:
        """從變體元素提取圖片 URL"""
        try:
            img = element.locator("img").first
            if img.count() > 0:
                # 優先使用高解析度圖片
                src = img.get_attribute("data-old-hires")
                if src:
                    return src
                
                src = img.get_attribute("src")
                if src and not src.startswith("data:"):
                    # 嘗試獲取更大的圖片
                    # Amazon 圖片 URL 通常包含尺寸參數，可以替換
                    src = re.sub(r'\._[A-Z]+\d+_\.', '._AC_SL1500_.', src)
                    return src
            
        except Exception:
            pass
        
        return None
    
    def _get_variant_availability(self, element) -> str:
        """從變體元素提取庫存狀態"""
        try:
            # 檢查是否有 "unavailable" 類別
            class_attr = element.get_attribute("class") or ""
            if "unavailable" in class_attr.lower() or "swatchUnavailable" in class_attr:
                return "out_of_stock"
            
            # 檢查 aria-disabled
            if element.get_attribute("aria-disabled") == "true":
                return "out_of_stock"
            
            # 檢查是否有刪除線或灰色樣式
            style = element.get_attribute("style") or ""
            if "opacity" in style.lower() or "gray" in style.lower():
                return "out_of_stock"
            
        except Exception:
            pass
        
        return "in_stock"
    
    def _normalize_variant_identifier(self, variant_name: str) -> str:
        """
        正規化變體識別符
        
        將變體名稱轉換為適合作為 ID 一部分的格式。
        
        Args:
            variant_name: 變體名稱
            
        Returns:
            正規化後的識別符
        """
        if not variant_name:
            return "default"
        
        # 轉換為小寫
        identifier = variant_name.lower()
        
        # 移除特殊字元，保留字母、數字和空格
        identifier = re.sub(r'[^a-z0-9\s]', '', identifier)
        
        # 將空格替換為底線
        identifier = re.sub(r'\s+', '_', identifier)
        
        # 移除連續的底線
        identifier = re.sub(r'_+', '_', identifier)
        
        # 移除首尾底線
        identifier = identifier.strip('_')
        
        # 限制長度
        if len(identifier) > 50:
            identifier = identifier[:50]
        
        return identifier or "default"

    
    def _is_in_addon_section(self, element) -> bool:
        """
        檢查元素是否在加購區塊中（簡化版本）
        
        用於價格提取時快速檢查。
        
        Args:
            element: 要檢查的元素
            
        Returns:
            True 如果元素在加購區塊中
        """
        try:
            # 使用 JavaScript 快速檢查
            is_in_addon = self._page.evaluate("""
                (element) => {
                    const addonIds = [
                        'similarities_feature_div',
                        'sims-fbt',
                        'sp_detail',
                        'anonCarousel',
                        'brand-snapshot-widget',
                        'HLCXComparisonWidget_feature_div',
                        'sims-consolidated-1_feature_div',
                        'sims-consolidated-2_feature_div',
                        'rhf',
                        'day0-sims-feature',
                        'p13n-asin-recommendations',
                        'sponsoredProducts2_feature_div'
                    ];
                    
                    let current = element;
                    while (current && current !== document.body) {
                        if (current.id && addonIds.includes(current.id)) {
                            return true;
                        }
                        current = current.parentElement;
                    }
                    return false;
                }
            """, element.element_handle())
            
            return is_in_addon
            
        except Exception:
            return False
    
    def _get_nearby_section_text(self, element) -> Optional[str]:
        """
        獲取元素附近的區塊標題文字
        
        用於判斷元素所在的區塊類型。
        
        Args:
            element: 要檢查的元素
            
        Returns:
            附近的標題文字，若無則返回 None
        """
        try:
            # 使用 JavaScript 查找附近的標題
            section_text = self._page.evaluate("""
                (element) => {
                    // 向上查找最近的 section 或 div 容器
                    let current = element;
                    for (let i = 0; i < 10 && current; i++) {
                        // 查找標題元素
                        const headers = current.querySelectorAll('h2, h3, .a-section-header, [class*="header"]');
                        for (const header of headers) {
                            const text = header.textContent || header.innerText;
                            if (text && text.trim().length > 0 && text.trim().length < 200) {
                                return text.trim();
                            }
                        }
                        current = current.parentElement;
                    }
                    return null;
                }
            """, element.element_handle())
            
            return section_text
            
        except Exception:
            return None
    
