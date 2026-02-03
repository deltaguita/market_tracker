import os
import requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import ProductStorage

OFFSET_FILE = "data/telegram_offset.txt"


def _load_offset() -> int | None:
    if not os.path.exists(OFFSET_FILE):
        return None
    try:
        with open(OFFSET_FILE, "r") as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def _save_offset(offset: int) -> None:
    os.makedirs(os.path.dirname(OFFSET_FILE), exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def process_ignore_commands(
    storage: "ProductStorage",
    bot_token: str,
    chat_id: str,
) -> None:
    """
    啟動時處理 Telegram 未讀訊息中的 /ignore 指令。
    只處理來自設定 chat 的訊息。
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"timeout": 0}
    offset = _load_offset()
    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Failed to fetch Telegram updates: {e}")
        return

    if not data.get("ok") or not data.get("result"):
        return

    result = data["result"]
    last_update_id = None

    for update in result:
        last_update_id = update["update_id"]
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        msg_chat_id = str(message["chat"]["id"])
        if msg_chat_id != str(chat_id):
            continue

        text = message.get("text") or ""
        if not text.strip().lower().startswith("/ignore"):
            continue

        parts = text.split(maxsplit=1)
        product_id = parts[1].strip() if len(parts) > 1 else ""
        if not product_id:
            continue

        storage.add_ignored(product_id)
        print(f"Ignored product: {product_id}")

    if last_update_id is not None:
        _save_offset(last_update_id + 1)
