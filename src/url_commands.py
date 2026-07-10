"""
處理 Telegram /add 指令，將新的追蹤商品寫入 config/urls.json。

此模組刻意只使用 Python 標準庫（urllib），不依賴 requests，
以便在 CI 的 prepare job（無 pip install）中用系統 python3 直接執行。

冪等性設計：
- prepare job 呼叫 getUpdates 時「不」推進 Telegram offset（避免吃掉 track job
  要處理的 /ignore 訊息），因此同一則 /add 在 Telegram 保留期（約 24h）內會被
  重複讀到。故以「URL 正規化去重」確保不會重複加入同一商品。
- 只有實際新增才發送 Telegram 通知；已存在則靜默，避免每次排程洗版。
"""

import json
import os
import urllib.parse
import urllib.request

CONFIG_PATH = "config/urls.json"
_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _telegram_get_updates(bot_token, timeout=5):
    """呼叫 getUpdates（不帶 offset，不會確認/消費訊息）。"""
    url = _API_BASE.format(token=bot_token, method="getUpdates") + "?timeout=0"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _telegram_send_message(bot_token, chat_id, text):
    """發送 Telegram 訊息（失敗只記錄，不中斷流程）。"""
    url = _API_BASE.format(token=bot_token, method="sendMessage")
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:  # noqa: BLE001 - 通知失敗不應中斷主流程
        print(f"Failed to send Telegram message: {e}")


def _normalize_url(url):
    """
    正規化 URL 以供去重比對：
    - scheme / host 轉小寫
    - path 去除尾端斜線
    - query 參數排序（避免順序不同被視為不同）
    - 移除 fragment
    使用者貼進來的 URL 通常已是 percent-encoded，這裡不改變其編碼內容，
    僅做結構性正規化。
    """
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query.sort()
        normalized_query = urllib.parse.urlencode(query)
        return urllib.parse.urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path.rstrip("/"),
                normalized_query,
                "",
            )
        )
    except Exception:  # noqa: BLE001
        return url.strip()


def _derive_name(url):
    """從 URL 的 keyword 參數推導可讀名稱（percent-decode）。"""
    try:
        parsed = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        keyword = params.get("keyword")
        if keyword:
            return urllib.parse.unquote(keyword).strip() or "Unknown"
    except Exception:  # noqa: BLE001
        pass
    return "Unknown"


def parse_add_command(text):
    """
    解析 /add 指令，回傳 (url, name, max_ntd)。格式錯誤時拋 ValueError。

    支援格式：
        /add <url>
        /add <url> | <名稱>
        /add <url> | <名稱> | <max_ntd>
    """
    body = text.split(maxsplit=1)
    if len(body) < 2 or not body[1].strip():
        raise ValueError("缺少 URL")

    parts = [p.strip() for p in body[1].split("|")]
    url = parts[0]
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("URL 需以 http:// 或 https:// 開頭")

    name = parts[1] if len(parts) > 1 and parts[1] else _derive_name(url)

    max_ntd = None
    if len(parts) > 2 and parts[2]:
        if not parts[2].isdigit() or int(parts[2]) <= 0:
            raise ValueError("max_ntd 需為正整數")
        max_ntd = int(parts[2])

    return url, name, max_ntd


def _load_config(config_path):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_config(config_path, config):
    os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def process_add_commands(bot_token, chat_id, config_path=CONFIG_PATH):
    """
    讀取 Telegram 未讀訊息中的 /add 指令，去重後寫入 config。

    回傳實際新增的項目列表（dict）。若無變更則回傳空清單且不改動檔案。
    """
    try:
        data = _telegram_get_updates(bot_token)
    except Exception as e:  # noqa: BLE001
        print(f"Failed to fetch Telegram updates: {e}")
        return []

    if not data.get("ok") or not data.get("result"):
        return []

    config = _load_config(config_path)
    tracking_urls = config.get("tracking_urls", [])

    # 既有 URL 的正規化集合，用於跨執行去重（避免重入載入產生重複商品）
    existing_norms = {
        _normalize_url(u.get("url", "")) for u in tracking_urls if u.get("url")
    }
    added = []

    for update in data["result"]:
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        if str(message.get("chat", {}).get("id")) != str(chat_id):
            continue

        text = (message.get("text") or "").strip()
        if not text.lower().startswith("/add"):
            continue

        try:
            url, name, max_ntd = parse_add_command(text)
        except ValueError as e:
            _telegram_send_message(
                bot_token,
                chat_id,
                (
                    f"⚠️ <b>新增失敗</b>\n{e}\n\n"
                    "格式：<code>/add &lt;url&gt; | &lt;名稱&gt; | &lt;max_ntd&gt;</code>"
                ),
            )
            continue

        norm = _normalize_url(url)
        if norm in existing_norms:
            # 已在追蹤清單：靜默略過，避免每次排程重複讀到而洗版
            print(f"Skip duplicate URL: {name}")
            continue

        entry = {"name": name, "url": url}
        if max_ntd is not None:
            entry["max_ntd"] = max_ntd
        tracking_urls.append(entry)
        existing_norms.add(norm)
        added.append(entry)

        budget = f"\n預算上限：{max_ntd} NTD" if max_ntd is not None else ""
        _telegram_send_message(
            bot_token,
            chat_id,
            f"✅ <b>已加入追蹤</b>\n{name}{budget}",
        )
        print(f"Added tracking URL: {name}")

    if added:
        config["tracking_urls"] = tracking_urls
        _save_config(config_path, config)
        print(f"Added {len(added)} new tracking URL(s)")

    return added
