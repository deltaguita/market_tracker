"""
設定檔載入模組

支援各來源獨立的設定檔，並提供預設值填充功能。
"""

import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


# 預設值定義
DEFAULT_CONFIG = {
    "amazon_us": {
        "source": "amazon_us",
        "schedule_interval_hours": 8,
        "price_tracking_mode": "full_history",
        "tracking_urls": []
    },
    "mercari_jp": {
        "source": "mercari_jp",
        "schedule_interval_hours": 4,
        "price_tracking_mode": "latest_only",
        "tracking_urls": []
    }
}

# 來源名稱到設定檔名稱的映射
SOURCE_TO_CONFIG_FILE = {
    "amazon_us": "amazon.json",
    "mercari_jp": "mercari.json"
}


@dataclass
class TrackingUrl:
    """追蹤 URL 設定"""
    name: str
    url: str
    max_usd: Optional[float] = None
    max_ntd: Optional[int] = None


@dataclass
class SourceConfig:
    """來源設定"""
    source: str
    schedule_interval_hours: int
    price_tracking_mode: str
    tracking_urls: List[TrackingUrl] = field(default_factory=list)
    
    def __post_init__(self):
        # 將 dict 轉換為 TrackingUrl 物件
        if self.tracking_urls and isinstance(self.tracking_urls[0], dict):
            self.tracking_urls = [
                TrackingUrl(**url) for url in self.tracking_urls
            ]


def load_source_config(
    source: str,
    config_dir: str = "config"
) -> SourceConfig:
    """
    載入指定來源的設定檔
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        config_dir: 設定檔目錄路徑
    
    Returns:
        SourceConfig: 來源設定物件
    
    Raises:
        ValueError: 當來源名稱無效時
        FileNotFoundError: 當設定檔不存在時
    """
    if source not in SOURCE_TO_CONFIG_FILE:
        raise ValueError(f"Unknown source: {source}. Valid sources: {list(SOURCE_TO_CONFIG_FILE.keys())}")
    
    config_file = SOURCE_TO_CONFIG_FILE[source]
    config_path = os.path.join(config_dir, config_file)
    
    # 載入設定檔
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    else:
        config_data = {}
    
    # 合併預設值
    defaults = DEFAULT_CONFIG.get(source, {})
    merged_config = {**defaults, **config_data}
    
    # 確保 source 欄位正確
    merged_config["source"] = source
    
    return SourceConfig(**merged_config)


def load_all_configs(config_dir: str = "config") -> Dict[str, SourceConfig]:
    """
    載入所有來源的設定檔
    
    Args:
        config_dir: 設定檔目錄路徑
    
    Returns:
        Dict[str, SourceConfig]: 來源名稱到設定的映射
    """
    configs = {}
    for source in SOURCE_TO_CONFIG_FILE.keys():
        try:
            configs[source] = load_source_config(source, config_dir)
        except FileNotFoundError:
            # 使用預設設定
            configs[source] = SourceConfig(**DEFAULT_CONFIG[source])
    return configs


def get_config_path(source: str, config_dir: str = "config") -> str:
    """
    取得指定來源的設定檔路徑
    
    Args:
        source: 來源名稱
        config_dir: 設定檔目錄路徑
    
    Returns:
        str: 設定檔完整路徑
    """
    if source not in SOURCE_TO_CONFIG_FILE:
        raise ValueError(f"Unknown source: {source}")
    return os.path.join(config_dir, SOURCE_TO_CONFIG_FILE[source])


def get_scraper_for_source(source: str, headless: bool = True, notifier=None):
    """
    根據來源名稱取得對應的爬蟲實例
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        headless: 是否以無頭模式運行瀏覽器
        notifier: TelegramNotifier 實例（可選，用於 timeout 通知）
    
    Returns:
        對應的爬蟲實例
    
    Raises:
        ValueError: 當來源名稱無效時
    """
    if source == "amazon_us":
        from scrapers.amazon.scraper import AmazonScraper
        return AmazonScraper(headless=headless, notifier=notifier)
    elif source == "mercari_jp":
        from scrapers.mercari.scraper import MercariScraper
        return MercariScraper(headless=headless, fetch_product_names=True)
    else:
        raise ValueError(f"Unknown source: {source}")


def get_max_threshold(url_config: TrackingUrl, source: str) -> Optional[float]:
    """
    取得價格上限門檻
    
    Args:
        url_config: URL 設定物件 (TrackingUrl)
        source: 來源名稱
    
    Returns:
        價格上限（USD for amazon_us, NTD for mercari_jp）
    """
    if source == "amazon_us":
        return url_config.max_usd
    else:
        return url_config.max_ntd
