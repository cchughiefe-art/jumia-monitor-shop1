import os
import requests
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://vendor-api.jumia.com"

def get_access_token():
    """Fetches the access token and logs potential issues."""
    url = f"{BASE_URL}/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("JUMIA_REFRESH_TOKEN"),
        "client_id": os.environ.get("JUMIA_CLIENT_ID")
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            logger.error(f"Token Error: {response.status_code} - {response.text}")
            return None
        return response.json().get("access_token")
    except Exception as e:
        logger.error(f"Token Request Failed: {e}")
        return None

def list_drop_off_stations():
    token = get_access_token()
    if not token:
        logger.error("No access token available. Cannot proceed.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    logger.info("Attempting to fetch shipment providers...")
    
    try:
        response = requests.get(f"{BASE_URL}/orders/shipment-providers", headers=headers)
        
        if response.status_code == 200:
            providers = response.json().get("shipment_providers", [])
            logger.info("--- DISCOVERED DROP-OFF STATIONS ---")
            for p in providers:
                logger.info(f"Name: {p.get('name')} | ID: {p.get('id')}")
        else:
            logger.error(f"Failed to fetch stations.")
            logger.error(f"Status Code: {response.status_code}")
            logger.error(f"Response Content: {response.text}")
            
    except Exception as e:
        logger.error(f"Request Exception: {e}")

if __name__ == "__main__":
    list_drop_off_stations()
    
