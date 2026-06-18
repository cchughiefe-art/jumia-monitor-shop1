import os
import requests
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://vendor-api.jumia.com"

def get_access_token():
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("JUMIA_REFRESH_TOKEN"),
        "client_id": os.environ.get("JUMIA_CLIENT_ID")
    }
    response = requests.post(f"{BASE_URL}/token", data=payload)
    return response.json().get("access_token")

def list_drop_off_stations():
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(f"{BASE_URL}/orders/shipment-providers", headers=headers)
    
    if response.status_code == 200:
        providers = response.json().get("shipment_providers", [])
        logger.info("--- DISCOVERED DROP-OFF STATIONS ---")
        for p in providers:
            logger.info(f"Station Name: {p.get('name')} | Station ID: {p.get('id')}")
    else:
        logger.error(f"Could not fetch stations. Status: {response.status_code}")

if __name__ == "__main__":
    list_drop_off_stations()
