#!/usr/bin/env python3
"""
測試 telegram_commands 模組
"""

import os
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

from src.storage import ProductStorage
from src.telegram_commands import process_ignore_commands


class TestProcessIgnoreCommands(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_products.db")
        self.storage = ProductStorage(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("src.telegram_commands.requests.get")
    def test_process_ignore_commands_adds_to_storage(self, mock_get):
        """測試處理 /ignore 指令會加入忽略清單"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 12345},
                        "text": "/ignore m12345678",
                    },
                }
            ],
        }
        mock_get.return_value.raise_for_status = MagicMock()

        process_ignore_commands(
            self.storage,
            bot_token="test_token",
            chat_id="12345",
        )

        self.assertEqual(self.storage.get_ignored_ids(), {"m12345678"})

    @patch("src.telegram_commands.requests.get")
    def test_process_ignore_commands_ignores_wrong_chat(self, mock_get):
        """測試只處理設定 chat 的訊息"""
        mock_get.return_value.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 99999},
                        "text": "/ignore m12345678",
                    },
                }
            ],
        }
        mock_get.return_value.raise_for_status = MagicMock()

        process_ignore_commands(
            self.storage,
            bot_token="test_token",
            chat_id="12345",
        )

        self.assertEqual(self.storage.get_ignored_ids(), set())

    @patch("src.telegram_commands.requests.get")
    def test_process_ignore_commands_empty_result(self, mock_get):
        """測試空結果不影響 storage"""
        mock_get.return_value.json.return_value = {"ok": True, "result": []}
        mock_get.return_value.raise_for_status = MagicMock()

        process_ignore_commands(
            self.storage,
            bot_token="test_token",
            chat_id="12345",
        )

        self.assertEqual(self.storage.get_ignored_ids(), set())


if __name__ == "__main__":
    unittest.main()
