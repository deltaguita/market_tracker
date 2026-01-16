"""
Mercari JP 爬蟲模組

繼承 BaseScraper，實作 Mercari 日本網站的商品爬取邏輯。
支援搜尋結果頁面的商品提取，包括：
- API 響應攔截方式（優先）
- DOM 解析方式（備用）
- 多頁翻頁支援
"""

import time
import random
import re
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from typing import List, Dict, Optional, Tuple
from playwright.sync_api import sync_playwright, Page

from core.base_scraper import BaseScraper
from src.exchange_rate import ExchangeRate


class MercariScraper(BaseScraper):
    """
    Mercari JP 爬蟲
    
    繼承 BaseScraper，實作 Mercari 日本網站特定的爬取邏輯。
    支援 API 攔截和 DOM 解析兩種方式提取商品資訊。
    """
    
    def __init__(self, headless: bool = True, fetch_product_names: bool = True):
        """
        初始化 Mercari 爬蟲
        
        Args:
            headless: 是否以無頭模式運行瀏覽器
            fetch_product_names: 是否訪問詳情頁獲取商品名稱
        """
        super().__init__(headless=headless)
        self.fetch_product_names = fetch_product_names
        
        # 初始化匯率模組
        self.exchange_rate = ExchangeRate()
        self.exchange_rate.fetch_jpy_to_twd_rate()
    
    @property
    def source_name(self) -> str:
        """返回來源名稱"""
        return "mercari_jp"
    
    def get_product_id(self, url: str) -> Optional[str]:
        """
        從商品 URL 提取商品 ID
        
        支援的 URL 格式：
        - https://jp.mercari.com/products/m1234567890
        - https://jp.mercari.com/item/m1234567890
        - https://item.mercari.com/jp/m1234567890
        
        Args:
            url: 商品頁面 URL
            
        Returns:
            商品 ID 字串，若無法提取則返回 None
        """
        patterns = [
            r"/products/([a-zA-Z0-9]+)",
            r"/item/([a-zA-Z0-9]+)",
            r"/jp/([a-zA-Z0-9]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def parse_product(self, element) -> Optional[Dict]:
        """
        解析單一商品元素
        
        此方法主要用於 DOM 解析方式，從頁面元素中提取商品資訊。
        
        Args:
            element: Playwright Locator 元素
            
        Returns:
            商品資訊字典，若解析失敗則返回 None
        """
        # 此方法的實作在 _extract_products_from_page 中
        # 這裡提供一個簡化版本供外部調用
        return None
    
    def scrape(self, url: str, max_retries: int = 3) -> List[Dict]:
        """
        爬取指定 URL 的所有商品（支援多頁）
        
        優先使用 API 攔截方式，若失敗則回退到 DOM 解析方式。
        
        Args:
            url: 搜尋結果頁面 URL
            max_retries: 最大重試次數
            
        Returns:
            商品資訊字典列表
        """
        url_with_status = self._add_status_parameter(url)
        all_products = []

        for attempt in range(max_retries):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(
                        user_agent=self._get_user_agent()
                    )
                    page = context.new_page()

                    # 設置 API 響應攔截器（必須在 goto 之前）
                    api_response_data = None

                    def handle_response(response):
                        nonlocal api_response_data
                        if (
                            "api.mercari.jp/v2/entities:search" in response.url
                            and response.status == 200
                        ):
                            try:
                                api_response_data = response.json()
                                print(
                                    f"成功攔截到 API 響應，包含 {len(api_response_data.get('items', []))} 個商品"
                                )
                            except:
                                pass

                    page.on("response", handle_response)

                    # 載入第一頁
                    print(f"Loading URL: {url_with_status}")
                    page.goto(
                        url_with_status, wait_until="domcontentloaded", timeout=60000
                    )

                    # 滾動頁面以觸發動態載入
                    self._scroll_page_to_load_all(page)

                    # 檢查頁面標題確認載入成功
                    title = page.title()
                    print(f"Page title: {title[:100]}")

                    # 等待 API 響應
                    time.sleep(10)

                    # 如果攔截到 API 響應，使用它
                    if api_response_data:
                        all_products = self._parse_api_response(api_response_data)

                    # 如果 API 方式失敗，回退到 DOM 方式
                    if not all_products:
                        print("API 方式失敗，回退到 DOM 方式...")
                        page_products = self._extract_products_from_page(page)
                        all_products.extend(page_products)
                        print(f"Page 1: Found {len(page_products)} products")

                    # 翻頁並解析
                    page_num = 2
                    while self._has_next_page(page):
                        if self._go_to_next_page(page):
                            page_products = self._extract_products_from_page(page)
                            all_products.extend(page_products)
                            print(
                                f"Page {page_num}: Found {len(page_products)} products"
                            )
                            page_num += 1
                        else:
                            break

                    browser.close()
                    break  # 成功則跳出重試循環

            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = self._calculate_retry_delay(attempt)
                    print(f"Retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
                else:
                    print("Max retries reached, giving up")
                    raise

        # 去重（以 ID 為準）
        unique_products = self._deduplicate_products(all_products)
        print(f"Total unique products: {len(unique_products)}")
        return unique_products
    
    def _add_status_parameter(self, url: str) -> str:
        """自動在網址上補充 &status=on_sale 參數"""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        query_params["status"] = ["on_sale"]
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)
    
    def _scroll_page_to_load_all(self, page: Page) -> None:
        """滾動頁面以載入所有商品"""
        print("開始滾動頁面以載入所有商品...")
        last_count = 0
        stable_count = 0

        for scroll_attempt in range(20):  # 最多滾動20次
            # 滾動到底部
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # 檢查當前商品數量
            current_count = page.locator("a[href*='/item/']").count()
            if scroll_attempt % 5 == 0:
                print(f"滾動中... 當前找到 {current_count} 個商品")

            if current_count == last_count:
                stable_count += 1
                if stable_count >= 3:  # 連續3次沒有新商品，停止
                    break
            else:
                stable_count = 0
                last_count = current_count

            # 也嘗試滾動到中間位置
            if scroll_attempt % 3 == 0:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(1)

        # 最終等待讓所有內容載入
        time.sleep(5)
    
    def _parse_api_response(self, api_response_data: Dict) -> List[Dict]:
        """解析 API 響應資料"""
        products = []
        items = api_response_data.get("items", [])
        print(f"從攔截的 API 響應中提取 {len(items)} 個商品")

        for item in items:
            product_id = item.get("id", "")
            if not product_id:
                continue

            # 提取價格（日圓）
            price_jpy = int(item.get("price", 0))

            # 提取商品名稱
            name = item.get("name", "")

            # 提取圖片
            thumbnails = item.get("thumbnails", [])
            photos = item.get("photos", [])
            image_url = ""
            if thumbnails:
                image_url = thumbnails[0]
            elif photos:
                image_url = photos[0].get("uri", "")

            # 構建商品 URL（根據 ID 格式）
            if product_id.startswith("m"):
                product_url = f"https://jp.mercari.com/item/{product_id}"
            else:
                product_url = f"https://jp.mercari.com/products/{product_id}"

            # 使用匯率計算台幣價格
            price_twd = self.exchange_rate.convert_jpy_to_twd(price_jpy)

            products.append({
                "id": product_id,
                "title": name,
                "price_jpy": price_jpy,
                "price_twd": price_twd,
                "image_url": image_url,
                "product_url": product_url,
            })
        
        return products
    
    def _parse_price(self, price_text: str) -> Tuple[int, int]:
        """
        解析價格文字，返回 (日圓, 台幣)
        
        支援多種格式：
        - "29,737日圓 NT$6,296"
        - "NT$4,869"
        - "¥19,050 NT$4,023"
        """
        if not price_text:
            return 0, 0

        jpy = 0
        twd = 0

        # 提取日圓價格
        jpy_patterns = [
            r"([\d,]+)\s*日圓",
            r"¥\s*([\d,]+)",
            r"JPY\s*([\d,]+)",
        ]
        for pattern in jpy_patterns:
            match = re.search(pattern, price_text)
            if match:
                jpy = int(match.group(1).replace(",", ""))
                break

        # 提取台幣價格
        twd_patterns = [
            r"NT\$\s*([\d,]+)",
            r"TWD\s*([\d,]+)",
            r"NT\s*([\d,]+)",
        ]
        for pattern in twd_patterns:
            match = re.search(pattern, price_text)
            if match:
                twd = int(match.group(1).replace(",", ""))
                break

        # 如果只找到一個數字且沒有貨幣標記，假設是台幣
        if jpy == 0 and twd == 0:
            numbers = re.findall(r"([\d,]+)", price_text)
            if numbers:
                candidates = [int(n.replace(",", "")) for n in numbers if int(n.replace(",", "")) > 100]
                if candidates:
                    twd = max(candidates)

        return jpy, twd
    
    def _fetch_product_name(self, page: Page, product_url: str) -> str:
        """訪問商品詳情頁獲取商品名稱"""
        if not self.fetch_product_names:
            return ""

        try:
            detail_page = page.context.new_page()
            detail_page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(1, 2))

            name = detail_page.evaluate("""
                () => {
                    const selectors = [
                        'h1',
                        '[data-testid*="title"]',
                        '[class*="title"]',
                        '[class*="name"]',
                        '.item-name',
                        'h1.item-name'
                    ];
                    
                    for (const selector of selectors) {
                        const elem = document.querySelector(selector);
                        if (elem && elem.textContent && elem.textContent.trim().length > 5) {
                            return elem.textContent.trim();
                        }
                    }
                    return null;
                }
            """)

            detail_page.close()
            return name or ""
        except Exception as e:
            print(f"Warning: Failed to fetch product name from {product_url}: {e}")
            return ""

    
    def _extract_products_from_page(self, page: Page) -> List[Dict]:
        """從當前頁面提取商品資訊（DOM 解析方式）"""
        products = []
        time.sleep(3)

        # 嘗試多種方式查找商品連結
        selectors_to_try = [
            "a[href*='/products/']",
            "a[href*='/item/']",
            "li[role='listitem'] a",
            "[data-testid*='item'] a",
            "[data-testid*='product'] a",
        ]

        items = []
        for selector in selectors_to_try:
            try:
                found = page.locator(selector).all()
                if found:
                    for link in found:
                        href = link.get_attribute("href") or ""
                        if "/products/" in href or "/item/" in href or "item.mercari.com" in href:
                            items.append(link)
                    if items:
                        print(f"Found {len(items)} product links using: {selector}")
                        break
            except Exception:
                continue

        if not items:
            # 最後嘗試：從頁面 HTML 中提取
            try:
                html = page.content()
                product_urls = re.findall(r'href=["\']([^"\']*\/products\/[^"\']*)["\']', html)
                if product_urls:
                    print(f"Found {len(set(product_urls))} product URLs in HTML")
                    if product_urls:
                        items = page.locator(
                            f"a[href*='{product_urls[0].split('/products/')[1].split('/')[0]}']"
                        ).all()
            except:
                pass

        if not items:
            print("Warning: No products found")
            return []
        
        print(f"Processing {len(items)} product items")
        
        for idx, item in enumerate(items):
            try:
                product = self._extract_single_product(page, item, idx)
                if product:
                    products.append(product)
            except Exception as e:
                if idx < 2:
                    print(f"  Item {idx}: Error extracting product: {e}")
                continue

        return products
    
    def _extract_single_product(self, page: Page, item, idx: int) -> Optional[Dict]:
        """從單一商品元素提取資訊"""
        # 獲取商品 URL
        product_url = item.get_attribute("href")
        if not product_url:
            return None

        if "/products/" not in product_url and "/item/" not in product_url:
            return None

        # 補全完整 URL
        if product_url.startswith("/"):
            product_url = f"https://jp.mercari.com{product_url}"
        elif not product_url.startswith("http"):
            product_url = f"https://jp.mercari.com/{product_url}"

        # 提取商品 ID
        product_id = self.get_product_id(product_url)
        if not product_id:
            return None

        # 嘗試使用 CDP Accessibility API 獲取資訊
        accessible_name = self._get_accessible_name(page, item, product_id)
        
        # 獲取圖片和文字資訊
        img_name, image_url, link_text = self._get_element_info(page, item)
        
        # 如果從 CDP 獲取到名稱，優先使用
        if accessible_name and len(accessible_name) > 10:
            img_name = accessible_name

        # 提取價格
        all_text = f"{img_name} {link_text}".strip()
        price_jpy, price_twd = self._parse_price(all_text)

        # 如果沒有價格，嘗試其他方式
        if price_jpy == 0 and price_twd == 0:
            price_jpy, price_twd = self._find_price_in_area(page, product_id)

        if price_jpy == 0 and price_twd == 0:
            return None

        # 提取標題
        title = self._extract_title(img_name, link_text, product_id)
        
        # 如果標題太短，嘗試從詳情頁獲取
        if (not title or len(title) < 5 or title == product_id) and self.fetch_product_names:
            detail_name = self._fetch_product_name(page, product_url)
            if detail_name:
                title = detail_name

        if not title or title == "未知商品":
            title = f"商品 {product_id}"

        return {
            "id": product_id,
            "title": title,
            "price_jpy": price_jpy,
            "price_twd": price_twd,
            "image_url": image_url,
            "product_url": product_url,
        }
    
    def _get_accessible_name(self, page: Page, item, product_id: str) -> str:
        """使用 CDP Accessibility API 獲取無障礙名稱"""
        accessible_name = ""
        try:
            item.wait_for(state="visible", timeout=5000)
            box = item.bounding_box()
            if box and box.get("x") is not None:
                cdp = page.context.new_cdp_session(page)
                cdp.send("Accessibility.enable")
                cdp.send("DOM.enable")

                center_x = int(box["x"] + box["width"] / 2)
                center_y = int(box["y"] + box["height"] / 2)

                try:
                    location_result = cdp.send("DOM.getNodeForLocation", {"x": center_x, "y": center_y})
                    if "nodeId" in location_result:
                        ax_result = cdp.send("Accessibility.getPartialAXTree", {
                            "nodeId": location_result["nodeId"],
                            "fetchRelatives": True,
                        })
                        accessible_name = self._extract_name_from_ax_tree(ax_result, accessible_name)
                except Exception:
                    # 回退到 DOM.querySelector
                    try:
                        dom_doc = cdp.send("DOM.getDocument", {"depth": -1})
                        query_result = cdp.send("DOM.querySelector", {
                            "nodeId": dom_doc["root"]["nodeId"],
                            "selector": f'a[href*="{product_id}"]',
                        })
                        if "nodeId" in query_result:
                            ax_result = cdp.send("Accessibility.getPartialAXTree", {
                                "nodeId": query_result["nodeId"],
                                "fetchRelatives": True,
                            })
                            accessible_name = self._extract_name_from_ax_tree(ax_result, accessible_name)
                    except:
                        pass
        except Exception:
            pass
        return accessible_name
    
    def _extract_name_from_ax_tree(self, ax_result: Dict, current_name: str) -> str:
        """從無障礙樹中提取名稱"""
        if "nodes" not in ax_result:
            return current_name
            
        for ax_node in ax_result["nodes"]:
            role = ax_node.get("role", {})
            if isinstance(role, dict):
                role_type = role.get("type", "")
                role_value = role.get("value", "")
            else:
                role_type = str(role)
                role_value = ""

            name_obj = ax_node.get("name", {})
            name_value = name_obj.get("value", "") if isinstance(name_obj, dict) else str(name_obj)

            if (("link" in role_value.lower() or "link" in role_type.lower()) 
                and name_value and len(name_value) > len(current_name)):
                current_name = name_value
        
        return current_name
    
    def _get_element_info(self, page: Page, item) -> Tuple[str, str, str]:
        """獲取元素的圖片名稱、圖片 URL 和連結文字"""
        img_name = ""
        image_url = ""
        link_text = ""
        
        try:
            link_text = item.inner_text() or ""
        except:
            pass

        try:
            img = item.locator("img").first
            if img.count() == 0:
                parent = item.locator("xpath=..").first
                if parent.count() > 0:
                    img = parent.locator("img").first
            
            if img and img.count() > 0:
                try:
                    img_element = img.element_handle()
                    if img_element:
                        img_name = page.evaluate("""
                            (img) => {
                                return img.getAttribute('name') || 
                                       img.getAttribute('alt') || 
                                       img.getAttribute('title') || '';
                            }
                        """, img_element) or ""
                except:
                    img_name = img.get_attribute("name") or img.get_attribute("alt") or img.get_attribute("title") or ""
                
                image_url = img.get_attribute("src") or ""
        except:
            pass
        
        return img_name, image_url, link_text
    
    def _find_price_in_area(self, page: Page, product_id: str) -> Tuple[int, int]:
        """在商品區域附近查找價格"""
        try:
            product_area = page.locator(f"a[href*='{product_id}']").locator("xpath=ancestor::*[1]").first
            if product_area.count() > 0:
                area_text = product_area.inner_text() or ""
                return self._parse_price(area_text)
        except:
            pass
        return 0, 0
    
    def _extract_title(self, img_name: str, link_text: str, product_id: str) -> str:
        """從圖片名稱和連結文字中提取標題"""
        if img_name:
            # 移除 "的圖片" 後面的內容
            if "的圖片" in img_name:
                title = img_name.split("的圖片")[0].strip()
            else:
                title = re.sub(r"\s*[\d,]+\s*日圓.*$", "", img_name).strip()
                title = re.sub(r"\s*NT\$\s*[\d,]+.*$", "", title).strip()
                title = re.sub(r"\s*¥\s*[\d,]+.*$", "", title).strip()

            # 清理標題
            title = re.sub(r"\s*NT\$\s*[\d,]+", "", title).strip()
            title = re.sub(r"\s*¥\s*[\d,]+", "", title).strip()
            title = re.sub(r"\s*[\d,]+\s*日圓", "", title).strip()

            if len(title) < 3 or title.isdigit():
                if link_text and len(link_text) > len(title):
                    title = link_text[:100]
                    title = re.sub(r"\s*NT\$\s*[\d,]+", "", title).strip()
                    title = re.sub(r"\s*¥\s*[\d,]+", "", title).strip()
        else:
            title = link_text[:100] if link_text else "未知商品"
            title = re.sub(r"\s*NT\$\s*[\d,]+", "", title).strip()
            title = re.sub(r"\s*¥\s*[\d,]+", "", title).strip()

        return re.sub(r"\s+", " ", title).strip()
    
    def _has_next_page(self, page: Page) -> bool:
        """檢查是否有下一頁"""
        try:
            next_link = page.locator("a:has-text('下一頁')").first
            if next_link.count() > 0:
                return next_link.is_visible()
        except Exception:
            pass
        return False

    def _go_to_next_page(self, page: Page) -> bool:
        """翻到下一頁"""
        try:
            next_link = page.locator("a:has-text('下一頁')").first
            if next_link.count() > 0 and next_link.is_visible():
                next_link.click()
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(random.uniform(2, 4))
                return True
        except Exception as e:
            print(f"Error going to next page: {e}")
        return False
    
    def _deduplicate_products(self, products: List[Dict]) -> List[Dict]:
        """去重商品列表"""
        seen_ids = set()
        unique_products = []
        for product in products:
            if product["id"] not in seen_ids:
                seen_ids.add(product["id"])
                unique_products.append(product)
        return unique_products
