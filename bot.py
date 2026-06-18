import requests
import os

# Secrets
CLIENT_ID = os.environ['JUMIA_CLIENT_ID']
REFRESH_TOKEN = os.environ['JUMIA_REFRESH_TOKEN']
TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
SHOP_NAME = os.environ['SHOP_NAME']

BASE_URL = "https://vendor-api.jumia.com"

def get_access_token():
    url = f"{BASE_URL}/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID
    }
    response = requests.post(url, data=data).json()
    return response.get('access_token')

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": f"[{SHOP_NAME}] {msg}"}
    requests.post(url, data=payload)

def check_orders():
    try:
        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"{BASE_URL}/orders"
        params = {"status": "pending"}
        
        response = requests.get(url, headers=headers, params=params).json()
        orders = response.get('orders', [])
        
        if orders:
            send_telegram(f"Alert: You have {len(orders)} new pending order(s)!")
        else:
            # THIS IS THE NEW PART: Now it tells you even if it's empty
            send_telegram("No new pending orders found.")
            
    except Exception as e:
        send_telegram(f"Bot Error: {str(e)}")

if __name__ == "__main__":
    check_orders()
    
