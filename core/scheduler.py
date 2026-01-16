"""
排程檢查模組

支援各來源獨立的排程設定，記錄和讀取上次執行時間，
並判斷是否到達下次執行時間。
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict


# 預設的排程狀態檔案路徑
DEFAULT_SCHEDULE_FILE = "data/schedule_state.json"


def _load_schedule_state(schedule_file: str = DEFAULT_SCHEDULE_FILE) -> Dict:
    """
    載入排程狀態檔案
    
    Args:
        schedule_file: 排程狀態檔案路徑
    
    Returns:
        Dict: 排程狀態資料，格式為 {source: {"last_run_time": ISO8601 string}}
    """
    if os.path.exists(schedule_file):
        try:
            with open(schedule_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_schedule_state(
    state: Dict, 
    schedule_file: str = DEFAULT_SCHEDULE_FILE
) -> None:
    """
    儲存排程狀態檔案
    
    Args:
        state: 排程狀態資料
        schedule_file: 排程狀態檔案路徑
    """
    # 確保目錄存在
    os.makedirs(os.path.dirname(schedule_file), exist_ok=True)
    
    with open(schedule_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_last_run_time(
    source: str,
    schedule_file: str = DEFAULT_SCHEDULE_FILE
) -> Optional[datetime]:
    """
    取得指定來源的上次執行時間
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        schedule_file: 排程狀態檔案路徑
    
    Returns:
        Optional[datetime]: 上次執行時間，若無記錄則返回 None
    """
    state = _load_schedule_state(schedule_file)
    source_state = state.get(source, {})
    last_run_str = source_state.get("last_run_time")
    
    if last_run_str:
        try:
            return datetime.fromisoformat(last_run_str)
        except ValueError:
            return None
    return None


def record_run_time(
    source: str,
    run_time: Optional[datetime] = None,
    schedule_file: str = DEFAULT_SCHEDULE_FILE
) -> None:
    """
    記錄指定來源的執行時間
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        run_time: 執行時間，預設為當前時間
        schedule_file: 排程狀態檔案路徑
    """
    if run_time is None:
        run_time = datetime.now()
    
    state = _load_schedule_state(schedule_file)
    
    if source not in state:
        state[source] = {}
    
    state[source]["last_run_time"] = run_time.isoformat()
    
    _save_schedule_state(state, schedule_file)


def is_due_for_scraping(
    source: str,
    interval_hours: int,
    schedule_file: str = DEFAULT_SCHEDULE_FILE,
    current_time: Optional[datetime] = None
) -> bool:
    """
    檢查指定來源是否到達下次執行時間
    
    根據 Property 12 的定義：
    對於任何來源，若 schedule_interval_hours = H 且 last_run_time = T，
    則當且僅當 (current_time - T) >= H 小時時，該來源應被標記為「到期需爬取」。
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        interval_hours: 排程間隔（小時）
        schedule_file: 排程狀態檔案路徑
        current_time: 當前時間，預設為 datetime.now()
    
    Returns:
        bool: 是否到達執行時間
              - 若無上次執行記錄，返回 True（首次執行）
              - 若 (current_time - last_run_time) >= interval_hours，返回 True
              - 否則返回 False
    """
    if current_time is None:
        current_time = datetime.now()
    
    last_run = get_last_run_time(source, schedule_file)
    
    # 若無上次執行記錄，視為首次執行，應該執行
    if last_run is None:
        return True
    
    # 計算時間差
    time_since_last_run = current_time - last_run
    interval_duration = timedelta(hours=interval_hours)
    
    # 當且僅當時間差 >= 間隔時間時，返回 True
    return time_since_last_run >= interval_duration


def get_next_run_time(
    source: str,
    interval_hours: int,
    schedule_file: str = DEFAULT_SCHEDULE_FILE
) -> Optional[datetime]:
    """
    取得指定來源的下次預計執行時間
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        interval_hours: 排程間隔（小時）
        schedule_file: 排程狀態檔案路徑
    
    Returns:
        Optional[datetime]: 下次預計執行時間，若無上次執行記錄則返回 None
    """
    last_run = get_last_run_time(source, schedule_file)
    
    if last_run is None:
        return None
    
    return last_run + timedelta(hours=interval_hours)


def get_time_until_next_run(
    source: str,
    interval_hours: int,
    schedule_file: str = DEFAULT_SCHEDULE_FILE,
    current_time: Optional[datetime] = None
) -> Optional[timedelta]:
    """
    取得距離下次執行的剩餘時間
    
    Args:
        source: 來源名稱 (amazon_us, mercari_jp)
        interval_hours: 排程間隔（小時）
        schedule_file: 排程狀態檔案路徑
        current_time: 當前時間，預設為 datetime.now()
    
    Returns:
        Optional[timedelta]: 剩餘時間
                            - 若無上次執行記錄，返回 None
                            - 若已到期，返回 timedelta(0) 或負值
    """
    if current_time is None:
        current_time = datetime.now()
    
    next_run = get_next_run_time(source, interval_hours, schedule_file)
    
    if next_run is None:
        return None
    
    return next_run - current_time


def clear_schedule_state(
    source: Optional[str] = None,
    schedule_file: str = DEFAULT_SCHEDULE_FILE
) -> None:
    """
    清除排程狀態
    
    Args:
        source: 來源名稱，若為 None 則清除所有來源的狀態
        schedule_file: 排程狀態檔案路徑
    """
    if source is None:
        # 清除整個檔案
        if os.path.exists(schedule_file):
            os.remove(schedule_file)
    else:
        # 只清除指定來源的狀態
        state = _load_schedule_state(schedule_file)
        if source in state:
            del state[source]
            _save_schedule_state(state, schedule_file)
