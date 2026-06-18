import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://vendor-api.jumia.com"
NOTIFIED_ORDERS_FILE = "notified_orders.json"
TIMEOUT = 30 

def get_session():
    """Create a session with retry logic and exponential backoff."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def get_access_token(session):
    """Exchanges Refresh Token for Access Token."""
    url = f"{BASE_URL}/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("JUMIA_REFRESH_TOKEN"),
        "client_id": os.environ.get("JUMIA_CLIENT_ID")
    }
    response = session.post(url, data=payload, timeout=TIMEOUT)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise ValueError("Failed to retrieve access token.")
    return token

def send_telegram(message):
    """Sends a message to Telegram."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    requests.post(url, data=payload, timeout=TIMEOUT)

def load_notified_orders():
    """Loads notified orders with JSON corruption protection."""
    if os.path.exists(NOTIFIED_ORDERS_FILE):
        try:
            with open(NOTIFIED_ORDERS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Corruption detected in {NOTIFIED_ORDERS_FILE}: {e}. Resetting file.")
            return []
    return []

def save_notified_orders(orders):
    """Saves notified orders to JSON."""
    with open(NOTIFIED_ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=4)

def check_orders():
    session = get_session()
    shop = os.environ.get("SHOP_NAME", "Shop")
    try:
        token = get_access_token(session)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Jumia GOP API standard: Use GET with Query Parameters
        url = f"{BASE_URL}/orders"
        params = {"status": "pending"}
        
        # Changed back to GET
        response = session.get(url, headers=headers, params=params, timeout=TIMEOUT)
        
        if response.status_code != 200:
            logger.error(f"API Error Response: {response.text}")
            response.raise_for_status()
            
        data = response.json()
        orders = data.get("orders", [])
        notified = load_notified_orders()
        
        new_orders = [o for o in orders if o.get("order_id") not in notified]

        if new_orders:
            for order in new_orders:
                msg = (f"{shop}\nNew Order\nID: {order.get('order_id')}\n"
                       f"Customer: {order.get('customer_name', 'N/A')}\n"
                       f"Value: {order.get('price', 'N/A')}\nStatus: {order.get('status', 'N/A')}")
                send_telegram(msg)
                notified.append(order.get("order_id"))
            
            save_notified_orders(notified)
            logger.info(f"Processed {len(new_orders)} new orders.")
        else:
            send_telegram(f"[{shop}] No new pending orders found.")
            logger.info("No new orders found.")
            
    except Exception as e:
        logger.error(f"Critical failure: {e}")
        send_telegram(f"Bot Error: {e}")
            
if __name__ == "__main__":
    check_orders()
        
