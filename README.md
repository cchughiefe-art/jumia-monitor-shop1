# Jumia Monitor Shop1: Vendor Center Seller Assistant

A Python-based assistant for managing an authorized Jumia Vendor Center seller account.
It provides reliable scheduled order notifications and a persistent Telegram command
interface. The existing GitHub Actions monitor is preserved and repaired.

## What is implemented

For a persistent server, start with [KataBump deployment instructions](DEPLOY-KATABUMP.md).
Run `python main.py`; it loads a private `.env`, stores state under `data/`,
installs Telegram's command menu and prevents a second local worker. `/status`
shows uptime and the latest monitor result. `/orders ALL 2` opens page two.
Run `python healthcheck.py` or the **Live API Health Check** workflow to verify
read access before relying on the bot. Live credentials and server login are
required to complete deployment.

- Jumia OAuth refresh-token authentication with access-token caching, safe error messages and HTTP timeouts.
- Paginated Jumia orders with a configurable lookback window and optional status filters.
- Correct Jumia **GET /orders/items?orderId=...** endpoint and item names/SKUs.
- Shipping-provider discovery by **order-item ID**, not order ID.
- Telegram order notifications with deduplication and no customer address/phone in alerts.
- Interactive Telegram commands: `/shops`, `/orders`, `/order`, `/stats`, `/stock`, `/providers`, `/check`, `/whoami`.
- Optional `/pack` and `/ready` commands with administrator allowlisting, opt-in write flag, provider validation for packing, and a two-minute confirmation step.
- Unit tests and scheduled GitHub Actions monitor with fixed YAML/commit logic.

**Not implemented yet:** WhatsApp inbound/outbound integration, catalog creation, stock/price write feeds, automated cancellation, sales accounting, AI natural-language agent, dashboard. None of these are claimed as operational. Jumia supports catalog feeds, but their shapes and privileges need to be tested against your approved Vendor Center account before enabling writes. Cancel actions remain deliberately disabled due to the effect on seller metrics.

## 1. Credentials

Get your **Jumia Vendor Center** client ID and refresh token from the authorized API integration workflow. The account needs appropriate Viewer roles for read commands and Order Manager permissions for shipping actions. You also need a Telegram bot token from BotFather.

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**, set:

| Secret | Purpose |
|---|---|
| `JUMIA_CLIENT_ID` | Your Vendor Center API client ID |
| `JUMIA_REFRESH_TOKEN` | Your API refresh token |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Private Telegram chat ID allowed to receive alerts |

Optional `SHOP_NAME` is a GitHub Actions *variable*. Do not commit actual credentials, passwords, chats, or customer data.

## 2. Scheduled order notifications (GitHub Actions)

The `Jumia Order Monitor` workflow runs approximately every 30 minutes (GitHub may delay schedules). Run it manually once from **Actions → Jumia Order Monitor → Run workflow** to verify authorization and Telegram delivery. It tracks *only order UUIDs* in `notified_orders.json`, committing them after successfully sending Telegram alerts. Failed delivery does not mark an order as notified. The lookback window is 14 days; use `JUMIA_LOOKBACK_DAYS` locally for a different period (1 to 89 days).

## 3. Interactive Telegram assistant (Termux or a persistent server)

Telegram chat replies require a **continuously running process**. GitHub Actions scheduling alone cannot offer real-time interactive chat. On Android/Termux:

```sh
pkg install python -y
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
set -a
. ./.env
set +a
python main.py
```

Fill the `.env` values yourself. Restrict the bot using `TELEGRAM_CHAT_ID`, and optionally `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated).
Use `/whoami` in the already-allowed chat to get your Telegram numeric user ID.

To **enable writes intentionally**: set `TELEGRAM_ADMIN_USER_IDS=<your numeric Telegram ID>` and `ENABLE_JUMIA_WRITES=1`, then restart the worker. `/ready <item_uuid>` or `/pack <item_uuid> <provider_uuid>` only proposes the operation. You must reply with `/confirm <code>` within two minutes in the same chat and from the same Telegram account. Jumia still enforces role permissions and validates requests. Packing may require provider-specific tracking codes: the starter command only works with providers not requiring a tracking code.

**Important:** operate only one Telegram polling worker for each Telegram bot token. Running both this worker and the GitHub scheduled monitor may duplicate alerts if their notification-state files are not synchronized. For a permanent server, disable the scheduled monitor and use the server's persisted `notified_orders.json`. Use a persistent disk/volume for local state; otherwise restarts may send duplicate alerts. Long polling will not work when that bot has an active webhook.

## 4. Verify shipment providers

Obtain an item UUID with `/order <order_uuid>` and run:

```sh
python discovery.py <item_uuid>
```

You can also use **Actions → Discover Shipment Providers** and enter the item UUID.

## 5. Tests

```sh
python -m unittest discover -s tests -v
```

Tests use fake API responses and do not touch live Jumia or Telegram accounts. Production API permissions, token validity and live fulfillment are **not tested** by these unit tests.

## Security and scope

- Credentials stay in secret environment variables. Never paste tokens in public GitHub issues or Telegram chats.
- Bot commands are processed only for allowlisted chat IDs. Write commands also require explicit admin user ID and opt-in flag.
- Sensitive actions use explicit confirmation and do not retry non-idempotent POST requests.
- Do not enable automated cancellations. Protect shipping and fulfillment from accidental changes.
- The bot does not expose a public web dashboard or an unauthenticated webhook.

## Verified API routes and documentation

[Jumia Vendor API Postman collection](https://www.postman.com/jumiagandalf/jumia-vendor-api/collection/ggwctko/vendor-api-collection) and [Vendor Center API docs](https://vendorcenter.jumia.com/api-docs/):

- `POST /token`
- `GET /shops`
- `GET /orders` (paginated)
- `GET /orders/items?orderId=...`
- `GET /orders/shipment-providers?orderItemId=...`
- `GET /catalog/stock`
- `POST /orders/pack`
- `POST /orders/ready-to-ship`

### Future WhatsApp channel

A real WhatsApp integration should use **Meta WhatsApp Cloud API** with your authorized WhatsApp Business account, a HTTPS webhook, verification token, access token and approved recipient/templates as applicable. Route its authenticated messages through the same command permission layer after webhook signature validation. It is **not** safe to connect it by sharing personal WhatsApp session cookies or pairing session files.
