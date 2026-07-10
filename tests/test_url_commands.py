#!/usr/bin/env python3
"""
測試 url_commands 模組（Telegram /add 指令處理）
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src import url_commands
from src.url_commands import parse_add_command, process_add_commands


def _updates(*messages):
    """建構 getUpdates 回傳格式。messages: list of (chat_id, text)。"""
    result = []
    for i, (chat_id, text) in enumerate(messages, start=1):
        result.append(
            {
                "update_id": i,
                "message": {"chat": {"id": chat_id}, "text": text},
            }
        )
    return {"ok": True, "result": result}


class TestParseAddCommand(unittest.TestCase):
    def test_url_only_derives_name_from_keyword(self):
        url = "https://jp.mercari.com/search?keyword=%E3%83%AC%E3%82%AD%20FX"
        parsed_url, name, max_ntd = parse_add_command(f"/add {url}")
        self.assertEqual(parsed_url, url)
        self.assertEqual(name, "レキ FX")  # percent-decoded
        self.assertIsNone(max_ntd)

    def test_pipe_form_with_name_and_budget(self):
        url = "https://jp.mercari.com/search?keyword=abc"
        parsed_url, name, max_ntd = parse_add_command(f"/add {url} | 我的名稱 | 3500")
        self.assertEqual(parsed_url, url)
        self.assertEqual(name, "我的名稱")
        self.assertEqual(max_ntd, 3500)

    def test_missing_url_raises(self):
        with self.assertRaises(ValueError):
            parse_add_command("/add")

    def test_non_http_raises(self):
        with self.assertRaises(ValueError):
            parse_add_command("/add ftp://example.com")

    def test_invalid_max_ntd_raises(self):
        url = "https://jp.mercari.com/search?keyword=abc"
        with self.assertRaises(ValueError):
            parse_add_command(f"/add {url} | name | abc")
        with self.assertRaises(ValueError):
            parse_add_command(f"/add {url} | name | -5")


class TestProcessAddCommands(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "urls.json")
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "tracking_urls": [
                        {
                            "name": "既有",
                            "url": "https://jp.mercari.com/search?keyword=exist",
                        }
                    ]
                },
                f,
                ensure_ascii=False,
            )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _read_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_adds_new_url(self, mock_updates, mock_send):
        url = "https://jp.mercari.com/search?keyword=%E3%83%AC%E3%82%AD"
        mock_updates.return_value = _updates((12345, f"/add {url}"))

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["url"], url)
        self.assertEqual(added[0]["name"], "レキ")
        config = self._read_config()
        self.assertEqual(len(config["tracking_urls"]), 2)
        mock_send.assert_called_once()

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_dedup_existing_url_not_added(self, mock_updates, mock_send):
        """重入載入：同一 URL 再次被讀到不應重複加入，也不通知。"""
        mock_updates.return_value = _updates(
            (12345, "/add https://jp.mercari.com/search?keyword=exist")
        )

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added, [])
        self.assertEqual(len(self._read_config()["tracking_urls"]), 1)
        mock_send.assert_not_called()

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_dedup_same_url_different_query_order(self, mock_updates, mock_send):
        """正規化去重：參數順序不同但實質相同的 URL 視為重複。"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "tracking_urls": [
                        {
                            "name": "既有",
                            "url": "https://jp.mercari.com/search?keyword=abc&status=on_sale",
                        }
                    ]
                },
                f,
            )
        mock_updates.return_value = _updates(
            (12345, "/add https://jp.mercari.com/search?status=on_sale&keyword=abc")
        )

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added, [])
        self.assertEqual(len(self._read_config()["tracking_urls"]), 1)

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_dedup_within_same_batch(self, mock_updates, mock_send):
        """同一批訊息中的重複 /add 只加入一次。"""
        url = "https://jp.mercari.com/search?keyword=dup"
        mock_updates.return_value = _updates(
            (12345, f"/add {url}"),
            (12345, f"/add {url}"),
        )

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(len(added), 1)
        self.assertEqual(len(self._read_config()["tracking_urls"]), 2)

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_ignores_wrong_chat(self, mock_updates, mock_send):
        mock_updates.return_value = _updates(
            (99999, "/add https://jp.mercari.com/search?keyword=other")
        )

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added, [])
        self.assertEqual(len(self._read_config()["tracking_urls"]), 1)
        mock_send.assert_not_called()

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_malformed_command_notifies_error(self, mock_updates, mock_send):
        mock_updates.return_value = _updates((12345, "/add not-a-url"))

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added, [])
        self.assertEqual(len(self._read_config()["tracking_urls"]), 1)
        mock_send.assert_called_once()

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_parses_max_ntd_into_entry(self, mock_updates, mock_send):
        url = "https://jp.mercari.com/search?keyword=budget"
        mock_updates.return_value = _updates((12345, f"/add {url} | 名稱 | 4000"))

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added[0]["max_ntd"], 4000)

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_empty_result_no_change(self, mock_updates, mock_send):
        mock_updates.return_value = {"ok": True, "result": []}

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added, [])
        self.assertEqual(len(self._read_config()["tracking_urls"]), 1)

    @patch("src.url_commands._telegram_send_message")
    @patch("src.url_commands._telegram_get_updates")
    def test_ignores_non_add_messages(self, mock_updates, mock_send):
        mock_updates.return_value = _updates((12345, "/ignore m12345678"))

        added = process_add_commands("token", "12345", config_path=self.config_path)

        self.assertEqual(added, [])
        self.assertEqual(len(self._read_config()["tracking_urls"]), 1)


if __name__ == "__main__":
    unittest.main()
