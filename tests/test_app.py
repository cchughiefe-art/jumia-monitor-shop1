import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bot import load_seen, order_text, run, save_seen
from jumia_client import JumiaClient, JumiaError
from telegram_bot import Assistant

ORDER = "41ea7c3b-20f0-466d-a095-e6e909298180"
ITEM = "b94e5592-a34c-40ff-964c-e0c80e571cd2"
PROVIDER = "00000000-0000-4000-8000-000000000001"


class TestJumiaClient(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        auth = self.session.post.return_value
        auth.status_code = 200
        auth.json.return_value = {"access_token": "test", "expires_in": 3600}
        self.client = JumiaClient(session=self.session, client_id="example", refresh_token="secret")

    def test_correct_order_items_path(self):
        res = self.session.request.return_value
        res.status_code = 200
        res.json.return_value = {"orderId": ORDER, "items": [{"id": ITEM}]}
        result = self.client.items(ORDER)
        self.assertEqual(result[0]["id"], ITEM)
        _, kwargs = self.session.request.call_args
        self.assertEqual(self.session.request.call_args.args[:2],
                         ("GET", "https://vendor-api.jumia.com/orders/items"))
        self.assertEqual(kwargs["params"], {"orderId": ORDER})

    def test_pagination_uses_next_token(self):
        res = self.session.request.return_value
        res.status_code = 200
        res.json.side_effect = [
            {"orders": [{"id": "a"}], "nextToken": "next", "isLastPage": False},
            {"orders": [{"id": "b"}], "isLastPage": True},
        ]
        self.assertEqual(len(self.client.orders(status="PENDING")), 2)
        self.assertEqual(self.session.request.call_args.kwargs["params"]["token"], "next")

    def test_write_uses_expected_payload(self):
        res = self.session.request.return_value
        res.status_code = 201
        res.json.return_value = {"success": {"total": 1}}
        self.client.pack(ITEM, PROVIDER)
        self.assertEqual(self.session.request.call_args.kwargs["json"],
                         {"orderItems": [{"id": ITEM, "shipmentProviderId": PROVIDER}]})

    def test_bad_uuid_rejected_without_request(self):
        with self.assertRaises(ValueError):
            self.client.ready_to_ship(["bad-id"])
        self.session.request.assert_not_called()

    def test_oauth_error_does_not_leak(self):
        self.session.post.return_value.raise_for_status.side_effect = ValueError("secret")
        with self.assertRaises(JumiaError) as cm:
            self.client.shops()
        self.assertNotIn("secret", str(cm.exception))


class TestMonitor(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "100", "SHOP_NAME": "Shop1"})
    def test_only_marks_seen_after_successful_alert(self):
        client = MagicMock()
        client.orders.return_value = [{"id": ORDER, "number": "123", "status": "PENDING",
                                       "totalAmountLocal": {"currency": "NGN", "value": 2500}}]
        client.items.return_value = [{"product": {"name": "Charger"}, "status": "PENDING"}]
        telegram = MagicMock()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            telegram.send.side_effect = RuntimeError("send failed")
            with self.assertRaises(RuntimeError):
                run(client, telegram, path)
            self.assertFalse(path.exists())
            telegram.send.side_effect = None
            self.assertEqual(run(client, telegram, path), 1)
            self.assertEqual(run(client, telegram, path), 0)
            self.assertEqual(load_seen(path), [ORDER])

    def test_no_address_in_notification(self):
        msg = order_text({"number": "1", "shippingAddress": {"address": "Sensitive Address"},
                          "totalAmountLocal": {"value": 10, "currency": "NGN"}}, [])
        self.assertNotIn("Sensitive Address", msg)


class TestTelegram(unittest.TestCase):
    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "100", "TELEGRAM_ADMIN_USER_IDS": "200",
                             "ENABLE_JUMIA_WRITES": "0"}, clear=True)
    def test_writes_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            assistant = Assistant(MagicMock(), MagicMock(), Path(td) / "offset.json")
            self.assertIn("disabled", assistant.command("100", "200", "/ready " + ITEM))
            assistant.client.ready_to_ship.assert_not_called()
            assistant.handle({"message": {"chat": {"id": 101},
                                          "from": {"id": 200}, "text": "/shops"}})
            assistant.telegram.send.assert_not_called()

    @patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "100", "TELEGRAM_ADMIN_USER_IDS": "200",
                             "ENABLE_JUMIA_WRITES": "1"}, clear=True)
    def test_confirm_requires_same_user(self):
        with tempfile.TemporaryDirectory() as td:
            client, telegram = MagicMock(), MagicMock()
            client.ready_to_ship.return_value = {"success": {"total": 1}}
            assistant = Assistant(client, telegram, Path(td) / "offset.json")
            proposal = assistant.command("100", "200", "/ready " + ITEM)
            code = proposal.split("/confirm ")[1].split()[0]
            self.assertIn("No pending", assistant.command("100", "201", "/confirm " + code))
            self.assertIn("Jumia response", assistant.command("100", "200", "/confirm " + code))
            self.assertIn("No pending", assistant.command("100", "200", "/confirm " + code))
            client.ready_to_ship.assert_called_once_with([ITEM])


if __name__ == "__main__":
    unittest.main()
