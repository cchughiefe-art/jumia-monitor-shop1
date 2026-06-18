import requests
import os

# Your secret keys are pulled automatically from your GitHub Secrets
CLIENT_ID = os.environ['JUMIA_CLIENT_ID']
REFRESH_TOKEN = os.environ['JUMIA_REFRESH_TOKEN']
TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
SHOP_NAME = os.environ['SHOP_NAME']

def get_access_token():
    url = "https://api.sellercenter.jumia.com.ng/oauth/token"
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
    access_token = get_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}
    url = "https://api.sellercenter.jumia.com.ng/orders"
    
    # We only want pending orders
    params = {"Status": "pending", "Format": "JSON"}
    
    try:
        response = requests.get(url, headers=headers, params=params).json()
        orders = response.get('SuccessResponse', {}).get('Body', {}).get('Orders', {}).get('Order', [])
        
        if orders:
            count = len(orders)
            send_telegram(f"Alert: You have {count} new pending order(s)!")
        else:
            print("No new orders.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_orders()
  
