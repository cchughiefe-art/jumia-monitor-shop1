import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://vendor-api.jumia.com"
NOTIFIED_ORDERS_FILE = "notified_orders.json"
TRANSPORT_COST = 700
PRINTING_COST = 100
TIMEOUT = 30 

def get_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def get_access_token(session):
    url = f"{BASE_URL}/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("JUMIA_REFRESH_TOKEN"),
        "client_id": os.environ.get("JUMIA_CLIENT_ID")
    }
    response = session.post(url, data=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json().get("access_token")

def send_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    requests.post(url, data=payload, timeout=TIMEOUT)

def load_notified_orders():
    if os.path.exists(NOTIFIED_ORDERS_FILE):
        try:
            with open(NOTIFIED_ORDERS_FILE, "r") as f:
                return json.load(f)
        except: return []
    return []

def save_notified_orders(orders):
    with open(NOTIFIED_ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=4)

def check_orders():
    session = get_session()
    shop = os.environ.get("SHOP_NAME", "Shop")
    try:
        token = get_access_token(session)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Using your confirmed endpoint
        url = f"{BASE_URL}/orders"
        
        # Some Jumia APIs require a pagination or limit parameter for GET
        response = session.get(url, headers=headers, params={"limit": 50}, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            orders = data.get("orders", [])
            
            # Filter locally using status values confirmed by your documentation/logs
            new_orders = [o for o in orders if o.get("status") == "pending" and o.get("order_id") not in load_notified_orders()]
            
            if new_orders:
                for order in new_orders:
                    total_fees = TRANSPORT_COST + PRINTING_COST
                    msg = (f"{shop}\nNew Order Detected!\nID: {order.get('order_id')}\n"
                           f"Price: {order.get('price')}\n"
                           f"Internal Fees: {total_fees}")
                    send_telegram(msg)
                    
                    notified = load_notified_orders()
                    notified.append(order.get("order_id"))
                    save_notified_orders(notified)
            else:
                logger.info("No new pending orders.")
        else:
            logger.error(f"API Error {response.status_code}: {response.text}")

    except Exception as e:
        logger.error(f"Failure: {str(e)}")

if __name__ == "__main__":
    check_orders()
    
