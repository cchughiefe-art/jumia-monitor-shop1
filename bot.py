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
        raise Exception("No access token returned")

    return token


# ---------------- TELEGRAM ----------------
def send_telegram(text):
    url = f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_TOKEN')}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": os.environ.get("TELEGRAM_CHAT_ID"),
            "text": text
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


# ---------------- ORDER PARSER ----------------
def parse_items(order):
    items = (
        order.get("items")
        or order.get("orderItems")
        or order.get("orderLines")
        or []
    )

    result = ""

    for item in items:

        name = (
            item.get("name")
            or item.get("productName")
            or item.get("title")
            or item.get("sku")
        )

        qty = item.get("quantity") or item.get("qty") or 1

        # nested product support
        if not name and isinstance(item.get("product"), dict):
            name = item["product"].get("name")

        if not name:
            name = "Unknown Product"

        result += f"- {name} x{qty}\n"

    return result if result else "- No item details available\n"


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

            customer_name = f"{shipping.get('firstName','')} {shipping.get('lastName','')}".strip()
            address = shipping.get("address", "")
            city = shipping.get("city", "")
            region = shipping.get("region", "")
            country = shipping.get("countryName", "")

            items_text = parse_items(o)

            message = (
                f"{shop}\n\n"
                f"NEW ORDER\n"
                f"Order No: {order_no}\n"
                f"Order ID: {order_id}\n\n"
                f"Customer:\n{customer_name}\n\n"
                f"Address:\n{address}\n"
                f"{city}, {region}\n"
                f"{country}\n\n"
                f"Items:\n{items_text}\n"
                f"Amount: ₦{price}\n"
                f"Status: {status}"
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
