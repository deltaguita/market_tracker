"""
爬蟲基礎類別模組

定義所有網站爬蟲的共用介面和行為，包括：
- 抽象方法定義 (scrape, parse_product, get_product_id)
- 瀏覽器初始化和關閉邏輯
- User-Agent 輪換
- 共用錯誤處理和重試邏輯
"""

import random
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright


class BaseScraper(ABC):
    """
    爬蟲基礎類別
    
    所有網站特定的爬蟲都應繼承此類別並實作抽象方法。
    提供共用的瀏覽器自動化功能和 User-Agent 輪換。
    """
    
    # 預設 User-Agent 列表，用於輪換以避免被封鎖
    DEFAULT_USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    # 預設重試設定
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_BASE = 5  # 秒
    
    def __init__(self, headless: bool = True, user_agents: Optional[List[str]] = None):
        """
        初始化爬蟲
        
        Args:
            headless: 是否以無頭模式運行瀏覽器
            user_agents: 自訂 User-Agent 列表，若為 None 則使用預設列表
        """
        self.headless = headless
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS.copy()
        
        # 瀏覽器相關實例（延遲初始化）
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # 當前使用的 User-Agent
        self._current_user_agent: Optional[str] = None
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        返回來源名稱
        
        子類別必須實作此屬性，返回唯一的來源識別符。
        例如: 'amazon_us', 'mercari_jp'
        
        Returns:
            來源名稱字串
        """
        pass
    
    @abstractmethod
    def scrape(self, url: str) -> List[Dict]:
        """
        爬取指定 URL 的商品資訊
        
        子類別必須實作此方法，處理特定網站的爬取邏輯。
        
        Args:
            url: 要爬取的網頁 URL
            
        Returns:
            商品資訊字典列表，每個字典至少包含:
            - id: 商品唯一識別符
            - title: 商品標題
            - product_url: 商品頁面 URL
            - 其他網站特定欄位（如價格、圖片等）
        """
        pass
    
    @abstractmethod
    def parse_product(self, element) -> Optional[Dict]:
        """
        解析單一商品元素
        
        子類別必須實作此方法，從頁面元素中提取商品資訊。
        
        Args:
            element: 頁面上的商品元素（Playwright Locator 或其他）
            
        Returns:
            商品資訊字典，若解析失敗則返回 None
        """
        pass
    
    @abstractmethod
    def get_product_id(self, url: str) -> Optional[str]:
        """
        從 URL 提取商品 ID
        
        子類別必須實作此方法，從商品 URL 中提取唯一識別符。
        
        Args:
            url: 商品頁面 URL
            
        Returns:
            商品 ID 字串，若無法提取則返回 None
        """
        pass
    
    @property
    def page(self) -> Optional[Page]:
        """取得當前頁面實例"""
        return self._page
    
    @property
    def browser(self) -> Optional[Browser]:
        """取得當前瀏覽器實例"""
        return self._browser
    
    def _get_user_agent(self) -> str:
        """
        隨機選擇一個 User-Agent
        
        從 user_agents 列表中隨機選擇一個，並記錄當前使用的 UA。
        
        Returns:
            隨機選擇的 User-Agent 字串
        """
        self._current_user_agent = random.choice(self.user_agents)
        return self._current_user_agent
    
    def _rotate_user_agent(self) -> str:
        """
        輪換到新的 User-Agent
        
        選擇一個與當前不同的 User-Agent（如果可能）。
        
        Returns:
            新的 User-Agent 字串
        """
        if len(self.user_agents) <= 1:
            return self._get_user_agent()
        
        available = [ua for ua in self.user_agents if ua != self._current_user_agent]
        self._current_user_agent = random.choice(available)
        return self._current_user_agent
    
    def _init_browser(self) -> None:
        """
        初始化瀏覽器
        
        啟動 Playwright 和 Chromium 瀏覽器，建立新的瀏覽器上下文和頁面。
        使用隨機 User-Agent 以避免被偵測。
        """
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=self._get_user_agent()
        )
        self._page = self._context.new_page()
    
    def _close_browser(self) -> None:
        """
        關閉瀏覽器
        
        依序關閉頁面、上下文、瀏覽器和 Playwright 實例。
        安全處理可能的 None 值。
        """
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
            
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
    
    def _reinit_browser_with_new_ua(self) -> None:
        """
        使用新的 User-Agent 重新初始化瀏覽器
        
        關閉現有瀏覽器並使用輪換後的 User-Agent 重新啟動。
        用於重試時避免被封鎖。
        """
        self._close_browser()
        self._rotate_user_agent()
        self._init_browser()
    
    def _wait_random(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """
        隨機等待一段時間
        
        用於模擬人類行為，避免被偵測為機器人。
        
        Args:
            min_seconds: 最小等待秒數
            max_seconds: 最大等待秒數
        """
        time.sleep(random.uniform(min_seconds, max_seconds))
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """
        計算重試延遲時間（指數退避）
        
        Args:
            attempt: 當前重試次數（從 0 開始）
            
        Returns:
            延遲秒數
        """
        base_delay = self.DEFAULT_RETRY_DELAY_BASE * (attempt + 1)
        jitter = random.uniform(0, base_delay * 0.5)
        return base_delay + jitter
    
    def __enter__(self):
        """支援 context manager 用法"""
        self._init_browser()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """支援 context manager 用法"""
        self._close_browser()
        return False
