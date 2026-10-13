"""Minimal Telegram Bot API client for alerts and authorized commands."""
import os

import requests


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token=None, session=None):
        token = token or os.getenv("TELEGRAM_TOKEN")
        if not token:
            raise TelegramError("Missing TELEGRAM_TOKEN")
        self.url = "https://api.telegram.org/bot" + token + "/"
        self.session = session or requests.Session()

    def call(self, method, payload=None, timeout=30):
        try:
            res = self.session.post(self.url + method, json=payload or {}, timeout=timeout)
            res.raise_for_status()
            data = res.json()
            if not data.get("ok"):
                raise TelegramError("Telegram rejected " + method)
            return data.get("result")
        except (requests.RequestException, ValueError) as exc:
            raise TelegramError("Telegram " + method + " delivery failed") from exc

    def send(self, chat_id, message, reply_markup=None):
        text = str(message)
        if not text:
            return
        # Telegram text limit is 4096; split long reports safely.
        for start in range(0, len(text), 3800):
            payload = {"chat_id": str(chat_id), "text": text[start:start + 3800]}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            self.call("sendMessage", payload)

    def updates(self, offset=None, timeout=25):
        return self.call("getUpdates", {"offset": offset, "timeout": timeout,
                                        "allowed_updates": ["message"]}, timeout=timeout + 10)
