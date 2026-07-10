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
OFFSET_PATH = "data/commands_offset.txt"
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


# ---------------------------------------------------------------------------
# 指令去重 marker：記錄「已處理到哪個 Telegram update_id」
#
# 重要：這裡「不」推進 Telegram 全域 offset（getUpdates 不帶 offset），
# 因為 offset 是 bot 全域共享，一旦確認會連帶消費掉 scraper 要處理的 /ignore。
# 改用本地（且會被 commit）的 marker，只在應用層過濾已處理的指令，
# 確保 /list、/remove、/add 每則只執行一次，避免每 10 分鐘重工/洗版。
# ---------------------------------------------------------------------------


def _load_marker(offset_path):
    if not os.path.exists(offset_path):
        return None
    try:
        with open(offset_path, "r") as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def _save_marker(offset_path, value):
    os.makedirs(os.path.dirname(offset_path) or ".", exist_ok=True)
    with open(offset_path, "w") as f:
        f.write(str(value))


def _format_list(tracking_urls):
    """組出 /list 回覆內容。"""
    if not tracking_urls:
        return "📋 <b>追蹤清單</b>\n\n目前沒有追蹤任何商品。"
    lines = ["📋 <b>追蹤清單</b>"]
    for i, entry in enumerate(tracking_urls, start=1):
        name = entry.get("name", "Unknown")
        budget = (
            f"（≤ {entry['max_ntd']} NTD）" if entry.get("max_ntd") is not None else ""
        )
        lines.append(f"\n{i}. <b>{name}</b>{budget}\n{entry.get('url', '')}")
    lines.append("\n\n移除：<code>/remove &lt;名稱&gt;</code>")
    return "".join(lines)


def _find_remove_targets(target, tracking_urls):
    """
    找出要移除的項目索引。先以名稱精確比對，找不到再以正規化 URL 比對。
    回傳索引列表（可能 0、1 或多筆）。
    """
    matches = [i for i, e in enumerate(tracking_urls) if e.get("name") == target]
    if matches:
        return matches
    tnorm = _normalize_url(target)
    return [
        i
        for i, e in enumerate(tracking_urls)
        if e.get("url") and _normalize_url(e["url"]) == tnorm
    ]


def process_commands(
    bot_token,
    chat_id,
    config_path=CONFIG_PATH,
    offset_path=OFFSET_PATH,
):
    """
    統一處理 Telegram 設定層指令：/add、/remove、/list。

    使用本地 marker（offset_path）記住已處理的 update_id，確保每則指令只執行一次
    （避免每 10 分鐘排程重工）。回傳摘要 dict。

    回傳：
        {
          "added": [...],       # 本次新增的項目
          "removed": [...],     # 本次移除的項目
          "listed": int,        # 本次回覆 /list 的次數
          "config_changed": bool,
          "marker": int | None, # 更新後的 marker
        }
    """
    summary = {
        "added": [],
        "removed": [],
        "listed": 0,
        "config_changed": False,
        "marker": None,
    }

    try:
        data = _telegram_get_updates(bot_token)
    except Exception as e:  # noqa: BLE001
        print(f"Failed to fetch Telegram updates: {e}")
        return summary

    marker = _load_marker(offset_path)
    summary["marker"] = marker
    if not data.get("ok") or not data.get("result"):
        return summary

    config = _load_config(config_path)
    tracking_urls = config.get("tracking_urls", [])
    existing_norms = {
        _normalize_url(u["url"]) for u in tracking_urls if u.get("url")
    }

    new_marker = marker
    handled = False  # 是否處理過「我們的」指令（決定是否需要更新/commit marker）

    for update in sorted(data["result"], key=lambda u: u.get("update_id", 0)):
        uid = update.get("update_id")
        if uid is None:
            continue
        if marker is not None and uid <= marker:
            continue  # 已處理過，跳過（記住哪個指令執行過了）

        message = update.get("message") or update.get("edited_message")
        if not message:
            continue
        if str(message.get("chat", {}).get("id")) != str(chat_id):
            continue

        text = (message.get("text") or "").strip()
        lower = text.lower()

        # 只有「我們的」指令才推進 marker；其餘（如 /ignore、閒聊）不碰，
        # 交由各自的獨立讀取處理，避免影響 scraper 的 /ignore。
        if lower.startswith("/add"):
            handled = True
            new_marker = uid if new_marker is None else max(new_marker, uid)
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
                _telegram_send_message(
                    bot_token, chat_id, f"ℹ️ <b>已在追蹤清單</b>\n{name}"
                )
                continue
            entry = {"name": name, "url": url}
            if max_ntd is not None:
                entry["max_ntd"] = max_ntd
            tracking_urls.append(entry)
            existing_norms.add(norm)
            summary["added"].append(entry)
            summary["config_changed"] = True
            budget = f"\n預算上限：{max_ntd} NTD" if max_ntd is not None else ""
            _telegram_send_message(
                bot_token, chat_id, f"✅ <b>已加入追蹤</b>\n{name}{budget}"
            )

        elif lower.startswith("/remove"):
            handled = True
            new_marker = uid if new_marker is None else max(new_marker, uid)
            parts = text.split(maxsplit=1)
            target = parts[1].strip() if len(parts) > 1 else ""
            if not target:
                _telegram_send_message(
                    bot_token,
                    chat_id,
                    "⚠️ <b>移除失敗</b>\n請指定名稱或 URL：<code>/remove &lt;名稱&gt;</code>",
                )
                continue
            idxs = _find_remove_targets(target, tracking_urls)
            if not idxs:
                _telegram_send_message(
                    bot_token, chat_id, f"❓ <b>找不到</b>\n清單中沒有「{target}」"
                )
                continue
            if len(idxs) > 1:
                _telegram_send_message(
                    bot_token,
                    chat_id,
                    (
                        f"⚠️ <b>名稱重複</b>\n有 {len(idxs)} 筆叫「{target}」，"
                        "請改用完整 URL 移除：<code>/remove &lt;url&gt;</code>"
                    ),
                )
                continue
            removed = tracking_urls.pop(idxs[0])
            if removed.get("url"):
                existing_norms.discard(_normalize_url(removed["url"]))
            summary["removed"].append(removed)
            summary["config_changed"] = True
            _telegram_send_message(
                bot_token,
                chat_id,
                f"🗑️ <b>已移除</b>\n{removed.get('name', 'Unknown')}",
            )

        elif lower.startswith("/list"):
            handled = True
            new_marker = uid if new_marker is None else max(new_marker, uid)
            _telegram_send_message(bot_token, chat_id, _format_list(tracking_urls))
            summary["listed"] += 1

        else:
            # 非設定層指令（例如 /ignore）：不處理、不推進 marker
            continue

    if summary["config_changed"]:
        config["tracking_urls"] = tracking_urls
        _save_config(config_path, config)

    if handled and new_marker is not None and new_marker != marker:
        _save_marker(offset_path, new_marker)
        summary["marker"] = new_marker

    print(
        "process_commands: "
        f"added={len(summary['added'])} removed={len(summary['removed'])} "
        f"listed={summary['listed']} marker={summary['marker']}"
    )
    return summary
