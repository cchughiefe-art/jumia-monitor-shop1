import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://vendor-api.jumia.com"
FILE = "notified_orders.json"
TIMEOUT = 30


# ---------------- SESSION ----------------
def session():
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


# ---------------- TOKEN ----------------
def get_token(s):
    url = f"{BASE_URL}/token"

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("JUMIA_REFRESH_TOKEN"),
        "client_id": os.environ.get("JUMIA_CLIENT_ID")
    }

    r = s.post(url, data=payload, timeout=TIMEOUT)
    r.raise_for_status()

    token = r.json().get("access_token")
    if not token:
        raise Exception("Token not returned")

    return token


# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_TOKEN')}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
            "text": msg
        },
        timeout=TIMEOUT
    )


# ---------------- STORAGE ----------------
def load_seen():
    try:
        if os.path.exists(FILE):
            with open(FILE, "r") as f:
                return json.load(f)
    except:
        return []
    return []


def save_seen(data):
    with open(FILE, "w") as f:
        json.dump(data, f)


# ---------------- FETCH ITEMS (IMPORTANT FIX) ----------------
def get_order_items(s, token, order_id):
    url = f"{BASE_URL}/orders/{order_id}/items"

    r = s.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT
    )

    if r.status_code != 200:
        logger.warning(f"Could not fetch items for {order_id}")
        return []

    try:
        return r.json().get("items", [])
    except:
        return []


# ---------------- MAIN ----------------
def run():
    s = session()

    try:
        shop = os.environ.get("SHOP_NAME", "Shop")

        token = get_token(s)

        r = s.get(
            f"{BASE_URL}/orders",
            headers={"Authorization": f"Bearer {token}"},
            params={"status": "PENDING"},
            timeout=TIMEOUT
        )

        r.raise_for_status()
        data = r.json()

        orders = data.get("orders", [])
        seen = load_seen()

        new_orders = [o for o in orders if o.get("id") not in seen]

        for o in new_orders:

            order_id = o.get("id")
            order_no = o.get("number")
            status = o.get("status")

            price = o.get("totalAmountLocal", {}).get("value", 0)

            shipping = o.get("shippingAddress", {})
            customer = f"{shipping.get('firstName','')} {shipping.get('lastName','')}".strip()

            # ---------------- ITEMS FIX ----------------
            items = get_order_items(s, token, order_id)

            item_text = ""

            for item in items:
                name = (
                    item.get("name")
                    or item.get("productName")
                    or item.get("sku")
                    or "Unknown Product"
                )

                qty = item.get("quantity", 1)

                item_text += f"- {name} x{qty}\n"

            if not item_text:
                item_text = "- No item details available\n"

            message = (
                f"{shop}\n\n"
                f"NEW ORDER\n"
                f"Order No: {order_no}\n"
                f"Customer: {customer}\n\n"
                f"Amount: ₦{price}\n"
                f"Status: {status}\n\n"
                f"Items:\n{item_text}"
            )

            send_telegram(message)

            seen.append(order_id)

        save_seen(seen)

        logger.info(f"Processed {len(new_orders)} new orders")

    except Exception as e:
        logger.error(str(e))

        send_telegram(
            f"Bot Error ({os.environ.get('SHOP_NAME','Shop')}): {str(e)}"
        )


if __name__ == "__main__":
    run()
