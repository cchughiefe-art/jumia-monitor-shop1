"""KataBump entry point. Environment variables override the private .env file."""
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    data = Path(os.getenv("DATA_DIR", "data"))
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TELEGRAM_OFFSET_FILE", str(data / "telegram_offset.json"))
    os.environ.setdefault("JUMIA_MONITOR_STATE", str(data / "notified_orders.json"))
    # A second local worker must not consume the same Telegram updates.
    import fcntl
    lock = (data / "worker.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another worker is running in this data directory")
    from telegram_bot import Assistant
    assistant = Assistant()
    signal.signal(signal.SIGTERM, lambda *_: assistant.stop.set())
    signal.signal(signal.SIGINT, lambda *_: assistant.stop.set())
    try:
        assistant.startup()
        assistant.loop()
    finally:
        assistant.client.session.close()
        assistant.telegram.session.close()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print request tracebacks containing token-bearing Telegram URLs.
        logging.error("Startup failed (%s): %s", type(exc).__name__, str(exc)[:250])
        sys.exit(1)
