"""Scheduled order monitor for GitHub Actions or a cron server."""
import json
import logging
import os
from pathlib import Path

from jumia_client import JumiaClient
from telegram_api import Telegram

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
STATE_FILE = Path(os.getenv("JUMIA_MONITOR_STATE", "notified_orders.json"))


def load_seen(path=STATE_FILE):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise ValueError("Invalid notification state file")
    return data


def save_seen(data, path=STATE_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data[-2000:], indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def order_text(order, items=None, shop="Jumia Shop"):
    amount = order.get("totalAmountLocal") or order.get("totalAmount") or {}
    if not isinstance(amount, dict):
        amount = {}
    country = order.get("country") or {}
    currency = amount.get("currency") or country.get("currencyCode", "")
    total = amount.get("value", "?")
    lines = [shop, "NEW JUMIA ORDER", "Order: " + str(order.get("number", "?")),
             "Status: " + str(order.get("status", "?")),
             "Amount: " + str(total) + " " + str(currency)]
    if items:
        lines.append("Items:")
        for item in items[:25]:
            product = item.get("product") or {}
            name = product.get("name") or product.get("sellerSku") or "Unknown product"
            lines.append("- " + str(name)[:120] + " (" + str(item.get("status", "?")) + ")")
    # Customer shipping address and phone are intentionally omitted from chats.
    return "\n".join(lines)


def run(client=None, telegram=None, state_path=STATE_FILE):
    client = client or JumiaClient()
    telegram = telegram or Telegram()
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("Missing TELEGRAM_CHAT_ID")
    status = os.getenv("JUMIA_ORDER_STATUS", "PENDING")
    days = int(os.getenv("JUMIA_LOOKBACK_DAYS", "14"))
    orders = client.orders(status=status, days=days)
    seen = load_seen(state_path)
    already_seen = set(seen)
    count = 0
    for order in reversed(orders):
        order_id = str(order.get("id") or "")
        if not order_id or order_id in already_seen:
            continue
        try:
            items = client.items(order_id)
        except Exception as exc:
            logger.warning("Items unavailable for order %s: %s", order_id, type(exc).__name__)
            items = []
        telegram.send(chat_id, order_text(order, items, os.getenv("SHOP_NAME", "Jumia Shop")))
        seen.append(order_id)
        already_seen.add(order_id)
        save_seen(seen, state_path)
        count += 1
    logger.info("Delivered %s new order alerts", count)
    return count


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("Jumia monitor failed")
        raise
