import time
import random
import re
import json
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
from typing import List, Dict, Optional, Tuple
from playwright.sync_api import sync_playwright, Page, Browser
from src.exchange_rate import ExchangeRate


class MercariScraper:
    def __init__(self, headless: bool = True, fetch_product_names: bool = True):
        self.headless = headless
        self.fetch_product_names = fetch_product_names  # 是否訪問詳情頁獲取名稱
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        ]
        # 初始化匯率模組
        self.exchange_rate = ExchangeRate()
        self.exchange_rate.fetch_jpy_to_twd_rate()

    def _add_status_parameter(self, url: str) -> str:
        """自動在網址上補充 &status=on_sale 參數"""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        query_params["status"] = ["on_sale"]
        new_query = urlencode(query_params, doseq=True)
        new_parsed = parsed._replace(query=new_query)
        return urlunparse(new_parsed)

    def _fetch_product_name(self, page: Page, product_url: str) -> str:
        """訪問商品詳情頁獲取商品名稱"""
        if not self.fetch_product_names:
            return ""

        try:
            # 在新分頁中打開商品詳情頁
            detail_page = page.context.new_page()
            detail_page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(random.uniform(1, 2))

            # 獲取商品名稱
            name = detail_page.evaluate("""
                () => {
                    // 嘗試多種選擇器
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

    def _extract_product_id(self, product_url: str) -> Optional[str]:
        """從商品 URL 提取商品 ID"""
        # Mercari 商品 URL 格式可能是:
        # - https://jp.mercari.com/products/m1234567890
        # - https://jp.mercari.com/item/m1234567890
        # - https://item.mercari.com/jp/m1234567890
        patterns = [
            r"/products/([a-zA-Z0-9]+)",
            r"/item/([a-zA-Z0-9]+)",
            r"/jp/([a-zA-Z0-9]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, product_url)
            if match:
                return match.group(1)
        return None

    def _parse_price(self, price_text: str) -> Tuple[int, int]:
        """解析價格文字，返回 (日圓, 台幣)"""
        if not price_text:
            return 0, 0

        # 從文字中提取數字，支援多種格式：
        # - "29,737日圓 NT$6,296"
        # - "NT$4,869"
        # - "¥19,050 NT$4,023"
        # - "4,869" (只有台幣)

        jpy = 0
        twd = 0

        # 提取日圓價格（多種格式）
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

        # 提取台幣價格（多種格式）
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

        # 如果只找到一個數字且沒有貨幣標記，假設是台幣（Mercari 台灣站）
        if jpy == 0 and twd == 0:
            # 查找所有數字
            numbers = re.findall(r"([\d,]+)", price_text)
            if numbers:
                # 取最大的數字作為價格（通常是價格）
                max_num = max(
                    [
                        int(n.replace(",", ""))
                        for n in numbers
                        if int(n.replace(",", "")) > 100
                    ]
                )
                if max_num > 100:  # 價格通常大於 100
                    twd = max_num
                    # 不進行換算，只保留實際提取的價格

        return jpy, twd

    def _extract_products_from_page(self, page: Page) -> List[Dict]:
        """從當前頁面提取商品資訊"""
        products = []
        # 等待頁面載入
        time.sleep(3)  # 給頁面更多時間載入

        # 直接查找所有包含 /products/ 的連結
        try:
            # 等待頁面完全載入
            time.sleep(2)

            # 嘗試多種方式查找商品連結
            selectors_to_try = [
                "a[href*='/products/']",  # 直接找商品連結
                "a[href*='/item/']",  # 可能的替代格式
                "li[role='listitem'] a",  # 列表項中的連結
                "[data-testid*='item'] a",
                "[data-testid*='product'] a",
            ]

            items = []
            for selector in selectors_to_try:
                try:
                    found = page.locator(selector).all()
                    if found:
                        # 過濾出商品連結
                        for link in found:
                            href = link.get_attribute("href") or ""
                            if (
                                "/products/" in href
                                or "/item/" in href
                                or "item.mercari.com" in href
                            ):
                                items.append(link)
                        if items:
                            print(f"Found {len(items)} product links using: {selector}")
                            break
                except Exception as e:
                    continue

            if not items:
                # 最後嘗試：從頁面 HTML 中提取
                try:
                    html = page.content()
                    product_urls = re.findall(
                        r'href=["\']([^"\']*\/products\/[^"\']*)["\']', html
                    )
                    if product_urls:
                        print(f"Found {len(set(product_urls))} product URLs in HTML")
                        # 使用第一個找到的 URL 來定位元素
                        if product_urls:
                            items = page.locator(
                                f"a[href*='{product_urls[0].split('/products/')[1].split('/')[0]}']"
                            ).all()
                except:
                    pass

        except Exception as e:
            print(f"Error finding products: {e}")
            items = []

        if not items:
            print("Warning: No products found")
            return []
        print(f"Processing {len(items)} product items")
        for idx, item in enumerate(items):
            try:
                # 直接從連結獲取 URL（item 現在就是 a 標籤）
                product_url = item.get_attribute("href")
                if not product_url:
                    if idx < 2:  # 只對前2個輸出調試
                        print(f"  Item {idx}: No href attribute")
                    continue

                # 確保是商品連結（支援多種格式）
                if "/products/" not in product_url and "/item/" not in product_url:
                    if idx < 2:
                        print(f"  Item {idx}: Not a product URL: {product_url[:50]}")
                    continue

                # 補全完整 URL
                if product_url.startswith("/"):
                    product_url = f"https://jp.mercari.com{product_url}"
                elif not product_url.startswith("http"):
                    product_url = f"https://jp.mercari.com/{product_url}"

                # 提取商品 ID
                product_id = self._extract_product_id(product_url)
                if not product_id:
                    if idx < 2:
                        print(
                            f"  Item {idx}: Could not extract product ID from: {product_url}"
                        )
                    continue

                if idx < 2:
                    print(f"  Item {idx}: Found product ID: {product_id}")

                # 提取商品名稱和價格
                # 優先使用 CDP Accessibility API 獲取無障礙名稱（參考 Selenium issue #16135）
                # 無障礙樹包含完整的商品資訊，即使 DOM 中沒有
                accessible_name = ""
                img_name = ""
                image_url = ""
                link_text = ""
                img = None  # 初始化 img 變數

                try:
                    # 獲取連結的位置（等待元素可見）
                    item.wait_for(state="visible", timeout=5000)
                    box = item.bounding_box()
                    if box and box.get("x") is not None:
                        # 使用 CDP 獲取無障礙資訊
                        cdp = page.context.new_cdp_session(page)
                        cdp.send("Accessibility.enable")
                        cdp.send("DOM.enable")

                        # 計算元素中心點（考慮滾動位置）
                        center_x = int(box["x"] + box["width"] / 2)
                        center_y = int(box["y"] + box["height"] / 2)

                        # 使用位置獲取 node ID
                        try:
                            location_result = cdp.send(
                                "DOM.getNodeForLocation", {"x": center_x, "y": center_y}
                            )

                            if "nodeId" in location_result:
                                # 獲取該節點的無障礙資訊
                                ax_result = cdp.send(
                                    "Accessibility.getPartialAXTree",
                                    {
                                        "nodeId": location_result["nodeId"],
                                        "fetchRelatives": True,
                                    },
                                )

                                # 從無障礙樹中提取名稱
                                if "nodes" in ax_result:
                                    for ax_node in ax_result["nodes"]:
                                        role = ax_node.get("role", {})
                                        # role 對象有 "type" 和 "value" 屬性
                                        if isinstance(role, dict):
                                            role_type = role.get("type", "")
                                            role_value = role.get("value", "")
                                        else:
                                            role_type = str(role)
                                            role_value = ""

                                        name_obj = ax_node.get("name", {})
                                        name_value = (
                                            name_obj.get("value", "")
                                            if isinstance(name_obj, dict)
                                            else str(name_obj)
                                        )

                                        # 檢查是否為連結且有名稱（檢查 role_value 或 role_type）
                                        if (
                                            (
                                                "link" in role_value.lower()
                                                or "link" in role_type.lower()
                                            )
                                            and name_value
                                            and len(name_value) > len(accessible_name)
                                        ):
                                            accessible_name = name_value
                        except Exception as inner_e:
                            # 如果 getNodeForLocation 失敗，嘗試使用 DOM.querySelector
                            try:
                                # 使用 DOM 查詢獲取 node ID
                                dom_doc = cdp.send("DOM.getDocument", {"depth": -1})
                                query_result = cdp.send(
                                    "DOM.querySelector",
                                    {
                                        "nodeId": dom_doc["root"]["nodeId"],
                                        "selector": f'a[href*="{product_id}"]',
                                    },
                                )

                                if "nodeId" in query_result:
                                    ax_result = cdp.send(
                                        "Accessibility.getPartialAXTree",
                                        {
                                            "nodeId": query_result["nodeId"],
                                            "fetchRelatives": True,
                                        },
                                    )

                                    if "nodes" in ax_result:
                                        for ax_node in ax_result["nodes"]:
                                            role = ax_node.get("role", {})
                                            # role 對象有 "type" 和 "value" 屬性
                                            if isinstance(role, dict):
                                                role_type = role.get("type", "")
                                                role_value = role.get("value", "")
                                            else:
                                                role_type = str(role)
                                                role_value = ""

                                            name_obj = ax_node.get("name", {})
                                            name_value = (
                                                name_obj.get("value", "")
                                                if isinstance(name_obj, dict)
                                                else str(name_obj)
                                            )

                                            # 檢查是否為連結且有名稱（檢查 role_value 或 role_type）
                                            if (
                                                (
                                                    "link" in role_value.lower()
                                                    or "link" in role_type.lower()
                                                )
                                                and name_value
                                                and len(name_value)
                                                > len(accessible_name)
                                            ):
                                                accessible_name = name_value
                            except:
                                pass
                except Exception as e:
                    # CDP 失敗時靜默處理，回退到其他方法
                    pass

                # 如果從無障礙樹獲取到名稱，優先使用
                if accessible_name and len(accessible_name) > 10:
                    img_name = accessible_name
                    if idx < 2:
                        print(
                            f"  Item {idx}: Got accessible name from CDP: {accessible_name[:100]}"
                        )
                else:
                    # 回退到原有方法：嘗試從父元素或附近找圖片和價格資訊
                    img = None
                    parent = None
                    grandparent = None

                    try:
                        # 先嘗試在連結內部找圖片（最常見的情況）
                        img = item.locator("img").first
                        if img.count() == 0:
                            # 如果連結內部沒有，找父元素
                            parent = item.locator("xpath=..").first
                            if parent.count() > 0:
                                img = parent.locator("img").first
                                if img.count() == 0:
                                    # 嘗試找父元素的父元素
                                    grandparent = parent.locator("xpath=..").first
                                    if grandparent.count() > 0:
                                        img = grandparent.locator("img").first
                    except:
                        pass

                    # 先獲取連結文字
                    try:
                        link_text = item.inner_text() or ""
                    except:
                        pass

                    # 嘗試從圖片獲取名稱（優先順序：name > alt > title）
                    if img and img.count() > 0:
                        try:
                            # 使用 evaluate 直接從 DOM 讀取屬性
                            img_element = img.element_handle()
                            if img_element:
                                img_name = (
                                    page.evaluate(
                                        """
                                    (img) => {
                                        return img.getAttribute('name') || 
                                               img.getAttribute('alt') || 
                                               img.getAttribute('title') || '';
                                    }
                                """,
                                        img_element,
                                    )
                                    or ""
                                )
                        except:
                            # 如果 JavaScript 失敗，回退到標準方法
                            img_name = img.get_attribute("name") or ""
                            if not img_name:
                                img_name = img.get_attribute("alt") or ""
                            if not img_name:
                                img_name = img.get_attribute("title") or ""

                        image_url = img.get_attribute("src") or ""

                # 如果圖片沒有 name/alt/title，嘗試從父元素找所有圖片
                # 只有在沒有從 CDP 獲取到名稱時才需要查找圖片
                if (
                    not img_name or len(img_name) < 10
                ) and not accessible_name:  # 如果名稱太短，可能是價格不是商品名
                    try:
                        # 在父元素或祖父元素中找所有圖片
                        search_containers = []
                        if parent and hasattr(parent, "count") and parent.count() > 0:
                            search_containers.append(parent)
                        if (
                            grandparent
                            and hasattr(grandparent, "count")
                            and grandparent.count() > 0
                        ):
                            search_containers.append(grandparent)

                        for container in search_containers:
                            all_imgs = container.locator("img").all()
                            for img_elem in all_imgs:
                                try:
                                    # 使用 JavaScript 直接讀取
                                    img_handle = img_elem.element_handle()
                                    if img_handle:
                                        candidate_name = (
                                            page.evaluate(
                                                """
                                            (img) => {
                                                return img.getAttribute('name') || 
                                                       img.getAttribute('alt') || 
                                                       img.getAttribute('title') || '';
                                            }
                                        """,
                                                img_handle,
                                            )
                                            or ""
                                        )
                                        if candidate_name and len(candidate_name) > len(
                                            img_name
                                        ):
                                            img_name = candidate_name
                                            if not image_url:
                                                image_url = (
                                                    img_elem.get_attribute("src") or ""
                                                )
                                            break
                                except:
                                    # 回退到標準方法
                                    candidate_name = (
                                        img_elem.get_attribute("name") or ""
                                    )
                                    if candidate_name and len(candidate_name) > len(
                                        img_name
                                    ):
                                        img_name = candidate_name
                                        if not image_url:
                                            image_url = (
                                                img_elem.get_attribute("src") or ""
                                            )
                                        break
                    except:
                        pass

                # 如果還是沒有，嘗試從連結文字獲取
                if not img_name and link_text:
                    img_name = link_text[:200]  # 限制長度

                # 調試輸出（僅前2個商品）
                if idx < 2:
                    print(
                        f"  Item {idx}: img_name length: {len(img_name)}, preview: {img_name[:100]}"
                    )

                # 從父元素或附近元素提取價格資訊
                price_text = ""
                try:
                    # 如果已經從 CDP 獲取到名稱（包含價格），直接使用
                    if accessible_name and len(accessible_name) > 10:
                        price_text = accessible_name
                    else:
                        # 嘗試從父元素獲取所有文字（包含價格）
                        if parent and hasattr(parent, "count") and parent.count() > 0:
                            parent_text = parent.inner_text() or ""
                            if parent_text:
                                price_text = parent_text
                            else:
                                # 嘗試從祖父元素
                                if (
                                    grandparent
                                    and hasattr(grandparent, "count")
                                    and grandparent.count() > 0
                                ):
                                    grandparent_text = grandparent.inner_text() or ""
                                    if grandparent_text:
                                        price_text = grandparent_text

                    # 如果還是沒有，嘗試從整個商品卡片區域找價格
                    if not price_text:
                        # 查找包含價格的元素
                        price_elements = (
                            page.locator(f"a[href*='{product_id}']")
                            .locator(
                                "xpath=ancestor::*[contains(@class, 'item') or contains(@class, 'product') or contains(@class, 'card')]"
                            )
                            .first
                        )
                        if price_elements.count() > 0:
                            price_text = price_elements.inner_text() or ""
                except:
                    pass

                # 合併所有文字來源來提取價格
                all_text = f"{img_name} {link_text} {price_text}".strip()

                # 調試：輸出提取的文字（僅前2個商品）
                if idx < 2:
                    print(f"  Item {idx}: Extracted text preview: {all_text[:150]}")

                # 從所有文字來源提取標題和價格
                # 格式可能是: "商品名稱 29,737日圓 NT$6,296" 或 "NT$4,869"

                # 提取價格（優先從 all_text）
                price_jpy, price_twd = self._parse_price(all_text)

                # 如果沒有從 all_text 提取到價格，嘗試其他方式
                if price_jpy == 0 and price_twd == 0:
                    # 嘗試直接從頁面查找價格元素
                    try:
                        # 查找包含商品 ID 的區域附近的價格
                        product_area = (
                            page.locator(f"a[href*='{product_id}']")
                            .locator("xpath=ancestor::*[1]")
                            .first
                        )
                        if product_area.count() > 0:
                            area_text = product_area.inner_text() or ""
                            if idx < 2:
                                print(
                                    f"  Item {idx}: Product area text: {area_text[:200]}"
                                )
                            price_jpy, price_twd = self._parse_price(area_text)

                        # 如果還是沒有，嘗試查找附近的價格元素
                        if price_jpy == 0 and price_twd == 0:
                            # 查找包含 NT$ 或日圓的元素
                            price_selectors = [
                                f"a[href*='{product_id}'] ~ *",
                                f"a[href*='{product_id}'] xpath=following-sibling::*",
                                f"a[href*='{product_id}'] xpath=ancestor::*//*[contains(text(), 'NT$') or contains(text(), '日圓')]",
                            ]
                            for selector in price_selectors:
                                try:
                                    price_elem = page.locator(selector).first
                                    if price_elem.count() > 0:
                                        price_elem_text = price_elem.inner_text() or ""
                                        if (
                                            "NT$" in price_elem_text
                                            or "日圓" in price_elem_text
                                        ):
                                            price_jpy, price_twd = self._parse_price(
                                                price_elem_text
                                            )
                                            if price_jpy > 0 or price_twd > 0:
                                                break
                                except:
                                    continue
                    except Exception as e:
                        if idx < 2:
                            print(f"  Item {idx}: Error finding price: {e}")
                        pass

                if idx < 2:
                    print(
                        f"  Item {idx}: Parsed price - JPY: ¥{price_jpy:,}, TWD: NT${price_twd:,}"
                    )

                # 提取標題
                # 商品名稱通常在圖片的 name/alt 屬性中，格式為：
                # "商品名稱的圖片 29,737日圓 NT$6,296" 或
                # "【新着商品】グレー 1300481 カーボン FX クレシダ...的圖片 29,737日圓 NT$6,296"
                if img_name:
                    # 先移除 "的圖片" 後面的所有內容（包含價格）
                    if "的圖片" in img_name:
                        title = img_name.split("的圖片")[0].strip()
                    else:
                        # 如果沒有 "的圖片"，嘗試移除價格部分
                        # 移除日圓價格
                        title = re.sub(r"\s*[\d,]+\s*日圓.*$", "", img_name).strip()
                        # 移除台幣價格
                        title = re.sub(r"\s*NT\$\s*[\d,]+.*$", "", title).strip()
                        # 移除其他價格格式
                        title = re.sub(r"\s*¥\s*[\d,]+.*$", "", title).strip()

                    # 清理標題（移除可能的價格殘留）
                    title = re.sub(r"\s*NT\$\s*[\d,]+", "", title).strip()
                    title = re.sub(r"\s*¥\s*[\d,]+", "", title).strip()
                    title = re.sub(r"\s*[\d,]+\s*日圓", "", title).strip()

                    # 如果標題太短或只有數字，嘗試從其他來源獲取
                    if len(title) < 3 or title.isdigit():
                        if link_text and len(link_text) > len(title):
                            title = link_text[:100]
                            title = re.sub(r"\s*NT\$\s*[\d,]+", "", title).strip()
                            title = re.sub(r"\s*¥\s*[\d,]+", "", title).strip()
                else:
                    # 如果沒有圖片資訊，從連結文字提取
                    title = link_text[:100] if link_text else "未知商品"
                    # 清理標題
                    title = re.sub(r"\s*NT\$\s*[\d,]+", "", title).strip()
                    title = re.sub(r"\s*¥\s*[\d,]+", "", title).strip()

                # 最終清理：移除多餘空格
                title = re.sub(r"\s+", " ", title).strip()

                # 如果標題還是太短或只有商品 ID，嘗試從詳情頁獲取
                if (
                    not title
                    or len(title) < 5
                    or title == f"商品 {product_id}"
                    or title == product_id
                ) and self.fetch_product_names:
                    detail_name = self._fetch_product_name(page, product_url)
                    if detail_name:
                        title = detail_name
                        if idx < 2:
                            print(
                                f"  Item {idx}: Fetched name from detail page: {title[:50]}"
                            )

                # 提取圖片 URL
                image_url = (
                    img.get_attribute("src")
                    if (img and hasattr(img, "count") and img.count())
                    else ""
                )

                if product_id:
                    if not title or title == "未知商品":
                        title = f"商品 {product_id}"
                    # 不進行換算，只保留實際提取的價格
                    # 如果兩個都沒有價格，設為 0（會被過濾掉）
                    if price_jpy == 0 and price_twd == 0:
                        if idx < 2:
                            print(f"  Item {idx}: Warning - No price found, skipping")
                        continue

                    products.append(
                        {
                            "id": product_id,
                            "title": title,
                            "price_jpy": price_jpy,
                            "price_twd": price_twd,
                            "image_url": image_url,
                            "product_url": product_url,
                        }
                    )
                    if idx < 2:
                        print(
                            f"  Item {idx}: Successfully extracted - {title[:50]} (¥{price_jpy})"
                        )
            except Exception as e:
                if idx < 2:
                    print(f"  Item {idx}: Error extracting product: {e}")
                continue

        return products

    def _has_next_page(self, page: Page) -> bool:
        """檢查是否有下一頁"""
        try:
            # 尋找「下一頁」連結
            next_link = page.locator("a:has-text('下一頁')").first
            if next_link.count() > 0:
                # 檢查連結是否可點擊（不是 disabled）
                is_visible = next_link.is_visible()
                return is_visible
        except Exception:
            pass
        return False

    def _go_to_next_page(self, page: Page) -> bool:
        """翻到下一頁"""
        try:
            next_link = page.locator("a:has-text('下一頁')").first
            if next_link.count() > 0 and next_link.is_visible():
                next_link.click()
                # 等待頁面載入（使用更寬鬆的條件）
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(random.uniform(2, 4))  # 增加頁面間延遲
                return True
        except Exception as e:
            print(f"Error going to next page: {e}")
        return False

    def _call_search_api(self, page: Page, keyword: str) -> List[Dict]:
        """攔截瀏覽器發送的 API 請求來獲取商品"""
        products = []
        api_response_data = None

        try:
            # 設置響應攔截器
            def handle_response(response):
                nonlocal api_response_data
                if (
                    "api.mercari.jp/v2/entities:search" in response.url
                    and response.status == 200
                ):
                    try:
                        api_response_data = response.json()
                    except:
                        pass

            page.on("response", handle_response)

            # 等待頁面載入並觸發 API 請求
            time.sleep(10)

            # 如果還沒有收到響應，嘗試滾動頁面觸發
            if api_response_data is None:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(5)

            if api_response_data:
                items = api_response_data.get("items", [])
                print(f"攔截到 API 響應，返回 {len(items)} 個商品")

                # 轉換 API 響應為標準格式
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

                    # 台幣價格需要從其他地方獲取或計算（API 只返回日圓）
                    # 暫時設為 0，後續可以通過匯率轉換
                    price_twd = 0

                    products.append(
                        {
                            "id": product_id,
                            "title": name,
                            "price_jpy": price_jpy,
                            "price_twd": price_twd,
                            "image_url": image_url,
                            "product_url": product_url,
                        }
                    )
            else:
                print("未能攔截到 API 響應")

        except Exception as e:
            print(f"攔截 API 失敗: {e}")
            import traceback

            traceback.print_exc()

        return products

    def scrape(self, url: str, max_retries: int = 3) -> List[Dict]:
        """爬取指定 URL 的所有商品（支援多頁）"""
        url_with_status = self._add_status_parameter(url)
        all_products = []

        for attempt in range(max_retries):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(
                        user_agent=random.choice(self.user_agents)
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

                    # 載入第一頁（使用更寬鬆的等待條件）
                    print(f"Loading URL: {url_with_status}")
                    page.goto(
                        url_with_status, wait_until="domcontentloaded", timeout=60000
                    )

                    # 滾動頁面以觸發動態載入（更積極的策略）
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
                            page.evaluate(
                                "window.scrollTo(0, document.body.scrollHeight / 2)"
                            )
                            time.sleep(1)

                    # 最終等待讓所有內容載入
                    time.sleep(5)

                    # 檢查頁面標題確認載入成功
                    title = page.title()
                    print(f"Page title: {title[:100]}")

                    # 等待 API 響應（頁面載入時會自動觸發）
                    time.sleep(10)

                    # 如果攔截到 API 響應，使用它
                    if api_response_data:
                        items = api_response_data.get("items", [])
                        print(f"從攔截的 API 響應中提取 {len(items)} 個商品")

                        # 轉換 API 響應為標準格式
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
                                product_url = (
                                    f"https://jp.mercari.com/item/{product_id}"
                                )
                            else:
                                product_url = (
                                    f"https://jp.mercari.com/products/{product_id}"
                                )

                            # 使用匯率計算台幣價格
                            price_twd = self.exchange_rate.convert_jpy_to_twd(price_jpy)

                            all_products.append(
                                {
                                    "id": product_id,
                                    "title": name,
                                    "price_jpy": price_jpy,
                                    "price_twd": price_twd,
                                    "image_url": image_url,
                                    "product_url": product_url,
                                }
                            )

                    # 如果 API 方式失敗，回退到 DOM 方式
                    if not all_products:
                        print("API 方式失敗，回退到 DOM 方式...")
                        # 檢查頁面內容
                        try:
                            # 嘗試查找任何包含價格的元素
                            price_elements = page.locator(
                                "[class*='price'], [class*='Price'], [data-testid*='price']"
                            ).count()
                            print(f"Found {price_elements} potential price elements")
                        except:
                            pass

                        # 解析第一頁
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
                    wait_time = random.uniform(5, 10) * (attempt + 1)
                    print(f"Retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
                else:
                    print("Max retries reached, giving up")
                    raise

        # 去重（以 ID 為準）
        seen_ids = set()
        unique_products = []
        for product in all_products:
            if product["id"] not in seen_ids:
                seen_ids.add(product["id"])
                unique_products.append(product)

        print(f"Total unique products: {len(unique_products)}")
        return unique_products
