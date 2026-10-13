"""Read-only live verification. No order/customer data or secrets printed."""
from dotenv import load_dotenv


def main():
    load_dotenv()
    from jumia_client import JumiaClient
    from telegram_api import Telegram
    client, telegram = JumiaClient(), Telegram()
    try:
        bot = telegram.call("getMe")
        webhook = telegram.call("getWebhookInfo")
        if webhook.get("url"):
            raise RuntimeError("Telegram has an active webhook; remove it before using polling")
        shops = client.shops()
        orders = client.orders(status="PENDING", days=1)
        print("Telegram authentication: OK")
        print("Telegram bot: @" + str(bot.get("username", "unknown")))
        print("Jumia authentication and shops: OK")
        print("Connected shops: " + str(len(shops)))
        print("Pending orders in last 24 hours: " + str(len(orders)))
    finally:
        client.session.close()
        telegram.session.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Live verification failed: " + str(exc)[:250])
        raise SystemExit(1)
