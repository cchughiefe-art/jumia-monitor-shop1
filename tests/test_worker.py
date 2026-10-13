import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from telegram_bot import Assistant
from telegram_api import TelegramError
from jumia_client import JumiaClient

ITEM = "b94e5592-a34c-40ff-964c-e0c80e571cd2"


@patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "100", "TELEGRAM_ADMIN_USER_IDS": "200",
                         "ENABLE_JUMIA_WRITES": "1"}, clear=True)
class WorkerTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "100", "TELEGRAM_ADMIN_USER_IDS": "200",
                                      "ENABLE_JUMIA_WRITES": "1"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.client, self.telegram = MagicMock(), MagicMock()
        self.bot = Assistant(self.client, self.telegram, Path(self.directory.name) / "offset.json")

    def test_pagination_does_not_hide_orders_after_first_fifteen(self):
        self.client.orders.return_value = [{"id": str(i), "number": str(i)} for i in range(20)]
        reply = self.bot.command("100", "200", "/orders ALL 2")
        self.assertIn("Page 2 of 2", reply)
        self.assertIn("19 |", reply)
        self.assertNotIn("14 |", reply)
        self.assertIsNone(self.client.orders.call_args.kwargs["status"])

    def test_old_shipment_command_never_stages(self):
        self.bot.handle({"message": {"chat": {"id": 100}, "from": {"id": 200},
                                     "date": time.time() - 180, "text": "/ready " + ITEM}})
        self.assertFalse(self.bot.pending)
        self.client.ready_to_ship.assert_not_called()
        self.assertIn("too old", self.telegram.send.call_args.args[1])

    def test_webhook_conflict_stops_startup(self):
        self.telegram.call.side_effect = [{"username": "testbot"}, {"url": "https://example.test"}]
        with self.assertRaises(TelegramError):
            self.bot.startup()
        self.assertEqual(self.telegram.call.call_count, 2)

    def test_offset_is_saved_before_write_and_reply_failure(self):
        proposal = self.bot.command("100", "200", "/ready " + ITEM)
        code = proposal.split("/confirm ")[1].split()[0]
        self.client.ready_to_ship.return_value = {"success": True}
        self.telegram.updates.return_value = [{"update_id": 50, "message": {
            "chat": {"id": 100}, "from": {"id": 200}, "date": time.time(),
            "text": "/confirm " + code}}]
        def fail_reply(*args, **kwargs):
            self.assertIn("51", self.bot.offset_path.read_text())
            self.bot.stop.set()
            raise TelegramError("reply failed")
        self.telegram.send.side_effect = fail_reply
        with patch.object(self.bot, "monitor"):
            self.bot.loop()
        self.client.ready_to_ship.assert_called_once()
        restarted = Assistant(self.client, self.telegram, self.bot.offset_path)
        self.assertEqual(restarted.offset, 51)
        self.assertFalse(restarted.pending)

    def test_confirmation_expires_without_writing(self):
        proposal = self.bot.command("100", "200", "/ready " + ITEM)
        code = proposal.split("/confirm ")[1].split()[0]
        old = self.bot.pending[("100", "200")]
        self.bot.pending[("100", "200")] = (old[0], 0, old[2], old[3])
        self.assertIn("expired", self.bot.command("100", "200", "/confirm " + code))
        self.client.ready_to_ship.assert_not_called()

    def test_unauthorized_chat_cannot_confirm(self):
        self.bot.handle({"message": {"chat": {"id": 999}, "from": {"id": 200},
                                     "date": time.time(), "text": "/confirm ABCDEF"}})
        self.telegram.send.assert_not_called()
        self.client.ready_to_ship.assert_not_called()


class ResponseTests(unittest.TestCase):
    def test_empty_successful_write_response(self):
        session = MagicMock()
        session.post.return_value.json.return_value = {"access_token": "test", "expires_in": 5}
        session.request.return_value.status_code = 204
        client = JumiaClient(session, "example", "secret")
        self.assertEqual(client.ready_to_ship([ITEM]), {"accepted": True})
        session.request.return_value.json.assert_not_called()

    def test_short_token_lifetime_is_not_extended(self):
        session = MagicMock()
        session.post.return_value.json.return_value = {"access_token": "test", "expires_in": 5}
        client = JumiaClient(session, "example", "secret")
        client._access_token()
        client._access_token()
        self.assertEqual(session.post.call_count, 2)
