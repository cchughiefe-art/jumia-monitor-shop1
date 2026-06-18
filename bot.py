import os
import json
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://vendor-api.jumia.com"
TIMEOUT = 30


def session():
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


def get_token(s):
    url = f"{BASE_URL}/token"

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": os.environ.get("JUMIA_REFRESH_TOKEN"),
        "client_id": os.environ.get("JUMIA_CLIENT_ID")
    }

    r = s.post(url, data=payload, timeout=TIMEOUT)

    logger.info(f"TOKEN STATUS: {r.status_code}")
    logger.info(f"TOKEN RESPONSE: {r.text}")

    r.raise_for_status()

    token = r.json().get("access_token")
    if not token:
        raise Exception("No access token returned")

    return token


def run():
    s = session()

    try:
        token = get_token(s)

        headers = {"Authorization": f"Bearer {token}"}

        # IMPORTANT: no filters for debugging
        url = f"{BASE_URL}/orders"

        r = s.get(url, headers=headers, timeout=TIMEOUT)

        logger.info(f"ORDERS STATUS: {r.status_code}")
        logger.info(f"RAW ORDERS RESPONSE: {r.text}")

        r.raise_for_status()

        try:
            data = r.json()
        except Exception:
            logger.error("Response is not valid JSON")
            return

        logger.info(f"PARSED JSON: {json.dumps(data, indent=2)}")

        # Try multiple possible keys (we don't assume structure yet)
        orders = (
            data.get("orders")
            or data.get("data", {}).get("orders")
            or data.get("results")
            or data.get("items")
            or []
        )

        logger.info(f"FOUND ORDERS COUNT: {len(orders)}")

        for o in orders:
            logger.info(f"SAMPLE ORDER: {o}")

    except Exception as e:
        logger.error(f"DEBUG ERROR: {e}")


if __name__ == "__main__":
    run()
