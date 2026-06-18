import requests
import os

# Secrets
CLIENT_ID = os.environ['JUMIA_CLIENT_ID']
REFRESH_TOKEN = os.environ['JUMIA_REFRESH_TOKEN']
TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
SHOP_NAME = os.environ['SHOP_NAME']

# Use the correct Vendor Center API base URL
BASE_URL = "https://vendor-api.jumia.com"

def get_access_token():
    # This endpoint exchanges your Refresh Token for an Access Token
    url = f"{BASE_URL}/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID
    }
    response = requests.post(url, data=data).json()
    # If the request fails, this will raise an error - check your logs if it does
    return response.get('access_token')

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": f"[{SHOP_NAME}] {msg}"}
    requests.post(url, data=payload)

def check_orders():
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Vendor Center Order Endpoint
    url = f"{BASE_URL}/orders"
    params = {"status": "pending"}
    
    try:
        response = requests.get(url, headers=headers, params=params).json()
        orders = response.get('orders', [])
        
        if orders:
            send_telegram(f"Alert: You have {len(orders)} new pending order(s)!")
        else:
            print("No new orders.")
    except Exception as e:
        print(f"Error connecting to Jumia: {e}")

if __name__ == "__main__":
    check_orders()
    
