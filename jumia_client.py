"""Jumia Vendor Center API wrapper. No credentials or customer data are logged."""
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class JumiaError(RuntimeError):
    pass


def valid_uuid(value):
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


class JumiaClient:
    def __init__(self, session=None, client_id=None, refresh_token=None):
        self.client_id = client_id or os.getenv("JUMIA_CLIENT_ID")
        self.refresh_token = refresh_token or os.getenv("JUMIA_REFRESH_TOKEN")
        if not self.client_id or not self.refresh_token:
            raise JumiaError("Missing JUMIA_CLIENT_ID or JUMIA_REFRESH_TOKEN")
        self.base = "https://vendor-api.jumia.com"
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(total=3, backoff_factor=1,
                          status_forcelist=(429, 500, 502, 503, 504),
                          allowed_methods=frozenset(("GET",)),
                          respect_retry_after_header=True)
            self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self._token = None
        self._expires = 0

    def _access_token(self):
        if self._token and time.monotonic() < self._expires:
            return self._token
        try:
            response = self.session.post(
                self.base + "/token",
                data={"grant_type": "refresh_token", "refresh_token": self.refresh_token,
                      "client_id": self.client_id}, timeout=(5, 25))
            response.raise_for_status()
            body = response.json()
            token = body.get("access_token")
            if not token:
                raise JumiaError("Jumia token response has no access_token")
            self._token = token
            self._expires = time.monotonic() + max(30, int(body.get("expires_in", 3600)) - 120)
            return token
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise JumiaError("Jumia OAuth token request failed") from exc

    def request(self, method, path, *, params=None, data=None):
        if method not in ("GET", "POST") or not path.startswith("/") or "//" in path:
            raise ValueError("Unsupported request")
        for attempt in range(2):
            headers = {"Authorization": "Bearer " + self._access_token(),
                       "Accept": "application/json"}
            try:
                response = self.session.request(
                    method, self.base + path, headers=headers,
                    params=params, json=data, timeout=(5, 25))
                if response.status_code == 401 and attempt == 0:
                    self._token = None
                    continue
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, (dict, list)):
                    raise JumiaError("Unexpected API response format")
                return result
            except (requests.RequestException, ValueError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                suffix = " (HTTP " + str(status) + ")" if status else ""
                raise JumiaError("Jumia " + method + " " + path + " failed" + suffix) from exc
        raise JumiaError("Jumia authorization failed (HTTP 401)")

    def shops(self):
        response = self.request("GET", "/shops")
        return response.get("shops", [])

    def orders(self, status=None, shop_id=None, days=14, max_pages=10):
        if not 1 <= days <= 89 or not 1 <= max_pages <= 20:
            raise ValueError("days or max_pages out of range")
        since = datetime.now(timezone.utc) - timedelta(days=days)
        params = {"sort": "DESC", "createdAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if status:
            params["status"] = status.upper()
        if shop_id:
            if not valid_uuid(shop_id):
                raise ValueError("Invalid shop UUID")
            params["shopId"] = shop_id
        result, seen_tokens = [], set()
        for _ in range(max_pages):
            data = self.request("GET", "/orders", params=params)
            if not isinstance(data, dict) or not isinstance(data.get("orders", []), list):
                raise JumiaError("Unexpected orders response")
            result.extend(data.get("orders", []))
            token = data.get("nextToken")
            if data.get("isLastPage") is True or not token:
                return result
            if token in seen_tokens:
                raise JumiaError("Repeated pagination token")
            seen_tokens.add(token)
            params["token"] = token
        raise JumiaError("Order pagination limit reached; narrow the query")

    def items(self, order_id):
        if not valid_uuid(order_id):
            raise ValueError("Order ID must be a UUID")
        data = self.request("GET", "/orders/items", params={"orderId": order_id})
        return data.get("items", []) if isinstance(data, dict) else []

    def shipment_providers(self, item_id):
        if not valid_uuid(item_id):
            raise ValueError("Item ID must be a UUID")
        data = self.request("GET", "/orders/shipment-providers",
                            params={"orderItemId": item_id})
        return data.get("orderItems", [])

    def stock(self, size=20, product_sid=None):
        if not 1 <= size <= 100:
            raise ValueError("Invalid page size")
        params = {"size": size}
        if product_sid:
            params["productSids"] = product_sid
        return self.request("GET", "/catalog/stock", params=params)

    def ready_to_ship(self, item_ids):
        if not item_ids or len(item_ids) > 20 or not all(valid_uuid(x) for x in item_ids):
            raise ValueError("Expected 1-20 order-item UUIDs")
        return self.request("POST", "/orders/ready-to-ship",
                            data={"orderItemIds": item_ids})

    def pack(self, item_id, provider_id):
        if not valid_uuid(item_id) or not valid_uuid(provider_id):
            raise ValueError("Invalid order-item or provider UUID")
        return self.request("POST", "/orders/pack",
                            data={"orderItems": [{"id": item_id,
                                                  "shipmentProviderId": provider_id}]})
