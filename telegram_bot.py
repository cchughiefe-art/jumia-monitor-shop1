"""Interactive Telegram control plane. Run as one long-lived worker.

Read commands are enabled for allowlisted chats. Shipment write commands additionally
require an allowlisted admin user, an environment flag and a short confirmation code.
"""
import json
import logging
import os
import secrets
import time
import threading
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path

from bot import order_text, run as check_orders
from jumia_client import JumiaClient, JumiaError, valid_uuid
from telegram_api import Telegram, TelegramError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
OFFSET_PATH = Path(os.getenv("TELEGRAM_OFFSET_FILE", "telegram_offset.json"))
HELP = ("JUMIA SELLER ASSISTANT\n"
        "/shops - connected Jumia stores\n"
        "/orders [status|ALL] [page] - recent orders (default PENDING)\n"
        "/order <order_uuid> - items and item IDs\n"
        "/stats - recent status counts\n"
        "/stock [product_sid] - stock API preview\n"
        "/providers <item_uuid> - shipping methods for an item\n"
        "/check - run new-order monitor now\n"
        "/whoami - show your Telegram user ID\n"
        "/status - worker health and last order check\n"
        "/ready <item_uuid> - propose ready-to-ship (admin only)\n"
        "/pack <item_uuid> <provider_uuid> - propose packing (admin only)\n"
        "/confirm <code> - confirm proposed action (2 minutes)\n"
        "/cancel - discard pending action\n"
        "No automatic order cancellation or price changes are enabled.")
MENU = {"keyboard": [["/orders", "/stats"], ["/shops", "/stock"],
                     ["/check", "/status"], ["/help", "/whoami"]],
        "resize_keyboard": True, "is_persistent": True}
COMMANDS = [("start", "Open the command menu"), ("orders", "Recent orders"),
            ("shops", "Connected stores"), ("stats", "Order status summary"),
            ("stock", "Stock preview"), ("order", "Order item details"),
            ("providers", "Shipping providers"), ("check", "Check new orders"),
            ("status", "Worker health"), ("whoami", "Your Telegram ID"),
            ("pack", "Propose packing"), ("ready", "Propose ready-to-ship"),
            ("confirm", "Confirm a proposed shipment"), ("cancel", "Clear a proposal"),
            ("help", "Command instructions")]


def csv_ids(name):
    return set(s.strip() for s in os.getenv(name, "").split(",") if s.strip())


class Assistant:
    def __init__(self, client=None, telegram=None, offset_path=OFFSET_PATH):
        self.client = client or JumiaClient()
        self.telegram = telegram or Telegram()
        self.offset_path = Path(offset_path)
        self.allowed_chats = csv_ids("TELEGRAM_ALLOWED_CHAT_IDS")
        if os.getenv("TELEGRAM_CHAT_ID"):
            self.allowed_chats.add(os.getenv("TELEGRAM_CHAT_ID"))
        if not self.allowed_chats:
            raise ValueError("Set TELEGRAM_CHAT_ID or TELEGRAM_ALLOWED_CHAT_IDS")
        self.admin_users = csv_ids("TELEGRAM_ADMIN_USER_IDS")
        self.pending = {}
        self.stop = threading.Event()
        self.started = time.monotonic()
        self.last_monitor = "Not checked yet"
        self.command_times = {}
        self.offset = self._load_offset()

    def _load_offset(self):
        if not self.offset_path.exists():
            return None
        data = json.loads(self.offset_path.read_text(encoding="utf-8"))
        return int(data["offset"])

    def _save_offset(self):
        self.offset_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.offset_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"offset": self.offset}) + "\n", encoding="utf-8")
        temp.replace(self.offset_path)

    def _is_admin(self, user_id):
        return bool(self.admin_users and str(user_id) in self.admin_users and
                    os.getenv("ENABLE_JUMIA_WRITES", "0") == "1")

    def _reply(self, chat, text):
        self.telegram.send(chat, text, reply_markup=MENU)

    def startup(self):
        self.telegram.call("getMe")
        if self.telegram.call("getWebhookInfo").get("url"):
            raise TelegramError("Active Telegram webhook prevents polling. Remove it before starting.")
        self.telegram.call("setMyCommands", {"commands": [
            {"command": name, "description": description} for name, description in COMMANDS]})
        logger.info("Telegram connected; command menu installed")

    def monitor(self):
        try:
            count = check_orders(self.client, self.telegram)
            self.last_monitor = datetime.now(timezone.utc).isoformat(timespec="seconds") + ": OK"
            return count
        except Exception as exc:
            self.last_monitor = datetime.now(timezone.utc).isoformat(timespec="seconds") + ": failed (" + type(exc).__name__ + ")"
            raise

    def _stage(self, chat, user_id, action, args):
        if not self._is_admin(user_id):
            return "Write commands are disabled. Set ENABLE_JUMIA_WRITES=1 and TELEGRAM_ADMIN_USER_IDS."
        code = secrets.token_hex(3).upper()
        self.pending[(str(chat), str(user_id))] = (code, time.monotonic() + 120, action, args)
        return ("PENDING ACTION: " + action + "\n" + "Arguments: " + ", ".join(args) +
                "\nTo execute, send /confirm " + code + " within 2 minutes.\n"
                "Double-check the Jumia item IDs first.")

    def command(self, chat, user_id, text):
        """Pure-ish command router; may be called from tests with mocked APIs."""
        parts = text.strip().split()
        if not parts:
            return HELP
        command = parts[0].split("@")[0].lower()
        args = parts[1:]
        if command in ("/start", "/help"):
            return HELP
        if command == "/whoami":
            return "Telegram user ID: " + str(user_id)
        if command == "/status":
            return ("JUMIA BOT ONLINE\nUptime: " + str(int(time.monotonic() - self.started)) +
                    " seconds\nLast order check: " + self.last_monitor +
                    "\nShipment writes for you: " + ("enabled" if self._is_admin(user_id) else "disabled"))
        if command == "/shops":
            shops = self.client.shops()
            if not shops:
                return "Jumia returned no shops. Check the assigned API roles."
            return "JUMIA SHOPS\n" + "\n".join(
                str(s.get("name", "Unnamed")) + " | " + str(s.get("id", ""))
                for s in shops[:50])
        if command == "/orders":
            status = args[0].upper() if args else "PENDING"
            if len(args) > 2:
                return "Usage: /orders [status|ALL] [page]"
            try:
                page = int(args[1]) if len(args) > 1 else 1
            except ValueError:
                return "Page must be a positive number."
            if page < 1:
                return "Page must be a positive number."
            orders = self.client.orders(status=None if status == "ALL" else status, days=14,
                                        max_pages=20, shop_id=os.getenv("JUMIA_SHOP_ID") or None)
            pages = max(1, (len(orders) + 14) // 15)
            if page > pages:
                return "There are only " + str(pages) + " pages."
            return ("Orders (" + status + "): " + str(len(orders)) + "\n" +
                    "Page " + str(page) + " of " + str(pages) + "\n" +
                    "\n".join(str(o.get("number", "?")) + " | " + str(o.get("status", "?")) +
                              " | " + str(o.get("id", "")) for o in orders[(page-1)*15:page*15]) +
                    ("\nNext: /orders " + status + " " + str(page+1) if page < pages else ""))
        if command == "/order":
            if len(args) != 1 or not valid_uuid(args[0]):
                return "Usage: /order <order_uuid>"
            items = self.client.items(args[0])
            if not items:
                return "No order items returned. Check order ID and permissions."
            lines = ["ORDER ITEMS " + args[0]]
            for item in items[:25]:
                product = item.get("product") or {}
                lines.append(str(product.get("name") or product.get("sellerSku") or "Unknown")[:100] +
                             " | " + str(item.get("status", "?")) +
                             "\nItem ID: " + str(item.get("id", "?")))
            return "\n".join(lines)
        if command == "/stats":
            orders = self.client.orders(days=14, shop_id=os.getenv("JUMIA_SHOP_ID") or None)
            counts = Counter(str(o.get("status", "UNKNOWN")) for o in orders)
            return "Last 14 days: " + str(len(orders)) + " orders\n" + "\n".join(
                str(k) + ": " + str(v) for k, v in sorted(counts.items()))
        if command == "/stock":
            data = self.client.stock(size=10, product_sid=args[0] if args else None)
            return "JUMIA STOCK PREVIEW\n" + json.dumps(data, ensure_ascii=False, indent=2)[:3100]
        if command == "/providers":
            if len(args) != 1 or not valid_uuid(args[0]):
                return "Usage: /providers <item_uuid>"
            data = self.client.shipment_providers(args[0])
            lines = []
            for record in data:
                for provider in record.get("shipmentProviders", []):
                    lines.append(str(provider.get("name", "?")) + " | " +
                                 str(provider.get("id", "?")) +
                                 (" | needs tracking" if provider.get("requireTrackingCode") else ""))
            return "Available providers:\n" + ("\n".join(lines) if lines else "None returned")
        if command == "/check":
            count = self.monitor()
            return "Order check finished. New alerts: " + str(count)
        if command == "/ready":
            if len(args) != 1 or not valid_uuid(args[0]):
                return "Usage: /ready <item_uuid>"
            return self._stage(chat, user_id, "ready", args)
        if command == "/pack":
            if len(args) != 2 or not all(valid_uuid(x) for x in args):
                return "Usage: /pack <item_uuid> <provider_uuid>"
            if not self._is_admin(user_id):
                return "Write commands are disabled for this user."
            providers = self.client.shipment_providers(args[0])
            matched = [p for item in providers
                       for p in item.get("shipmentProviders", [])
                       if str(p.get("id")) == args[1]]
            if not matched:
                return "Provider not returned by Jumia for this item. Run /providers first."
            if matched[0].get("requireTrackingCode"):
                return "This provider requires a tracking code. Packing through chat is not supported for it."
            return self._stage(chat, user_id, "pack", args)
        if command == "/cancel":
            self.pending.pop((str(chat), str(user_id)), None)
            return "Pending action cleared."
        if command == "/confirm":
            key = (str(chat), str(user_id))
            proposal = self.pending.get(key)
            if not proposal or len(args) != 1:
                return "No pending action."
            code, expires, action, action_args = proposal
            if time.monotonic() > expires:
                self.pending.pop(key, None)
                return "Confirmation expired. Start again."
            if not self._is_admin(user_id):
                return "Admin write access is disabled."
            if not secrets.compare_digest(args[0].upper(), code):
                return "Incorrect confirmation code."
            self.pending.pop(key, None)  # never retry POST automatically
            result = (self.client.ready_to_ship(action_args) if action == "ready" else
                      self.client.pack(*action_args))
            return "Jumia response:\n" + json.dumps(result, indent=2)[:3000]
        return HELP

    def handle(self, update):
        message = update.get("message") or {}
        chat = str((message.get("chat") or {}).get("id", ""))
        if chat not in self.allowed_chats:
            return  # do not reply to strangers, including DMs
        text = message.get("text", "")
        if not text.startswith("/"):
            return
        user_id = (message.get("from") or {}).get("id")
        if not user_id or (message.get("from") or {}).get("is_bot"):
            return
        # Discard queued shipment writes sent while the bot was offline.
        command = text.split()[0].split("@")[0].lower()
        if command in ("/pack", "/ready", "/confirm") and time.time() - message.get("date", 0) > 120:
            self._reply(chat, "This shipment command is too old. Send it again to continue.")
            return
        key = (chat, str(user_id))
        now = time.monotonic()
        if now - self.command_times.get(key, -10) < 1:
            return
        self.command_times[key] = now
        self.pending = {k: v for k, v in self.pending.items() if v[1] > now}
        try:
            reply = self.command(chat, user_id, text)
        except (JumiaError, ValueError, TelegramError) as exc:
            logger.warning("Command failed: %s", type(exc).__name__)
            reply = "Command failed: " + str(exc)[:300]
        except Exception as exc:
            logger.warning("Unexpected command failure: %s", type(exc).__name__)
            reply = "Unable to complete this command. Check the server logs and try again."
        if reply:
            self._reply(chat, reply)

    def loop(self):
        logger.info("Telegram assistant running; allowlisted chats: %s", len(self.allowed_chats))
        last_check = 0.0
        interval = max(60, int(os.getenv("JUMIA_POLL_SECONDS", "300")))
        while not self.stop.is_set():
            try:
                if time.monotonic() - last_check >= interval:
                    last_check = time.monotonic()
                    try:
                        self.monitor()
                    except Exception as exc:
                        logger.error("Monitor failed: %s", type(exc).__name__)
                for update in self.telegram.updates(offset=self.offset, timeout=25):
                    if self.stop.is_set():
                        break
                    # Persist before processing so a reply failure or restart cannot replay a shipment write.
                    # Failed read commands can be resent manually.
                    self.offset = int(update["update_id"]) + 1
                    self._save_offset()
                    self.handle(update)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.warning("Polling failure: %s", type(exc).__name__)
                self.stop.wait(10)


if __name__ == "__main__":
    from main import main
    main()
