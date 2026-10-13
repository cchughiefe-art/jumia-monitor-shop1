# Run the Jumia command bot on KataBump

The worker uses Python and Telegram long polling. It needs no public port or
webhook and runs independently of your phone. Only one worker may use your bot token.

## Server setup

1. Sign in at https://dashboard.katabump.com and create a **free Python server**.
2. Open its control panel. In **Startup**, use Python 3.11 and set **PY FILE** to `main.py`.
3. Upload the repository ZIP and extract it. `main.py` and `requirements.txt` must be at the server root, not inside another folder.
4. Copy `.env.example` to `.env` in the server file manager. Enter your Jumia client ID, refresh token, Telegram token and allowed chat ID there. GitHub Actions secrets are encrypted and cannot be copied out of GitHub.
5. Leave `ENABLE_JUMIA_WRITES=0` initially. Use **Console → Start**. The host installs `requirements.txt` dependencies.
6. Look for `Telegram connected; command menu installed`. In your allowed Telegram chat, send `/start`, `/status`, `/shops`, `/orders`, `/stock` and `/check`.
7. Before enabling the server monitor, disable the old GitHub Actions **Jumia Order Monitor** workflow, or set repository variable `JUMIA_SERVER_ACTIVE` to `1`. Otherwise both processes may notify the same orders.

Before switching, copy the existing `notified_orders.json` to the server's
`data/notified_orders.json` so previously notified orders stay deduplicated.
Keep the `data/` folder across upgrades. Do not upload a `.env` file to GitHub.

## Shipment commands

Use `/whoami` to obtain your numeric Telegram user ID. Set
`TELEGRAM_ADMIN_USER_IDS` to that ID and `ENABLE_JUMIA_WRITES=1`, then restart.
Use `/order <order_uuid>` to find order-item IDs and `/providers <item_uuid>`
to discover valid providers. `/pack` and `/ready` each require `/confirm <code>`
within two minutes, from the same account in the same chat. A restart cancels
all unconfirmed proposals. Queued shipment commands older than two minutes
are rejected. Tracking-code providers are not supported by this version.

## Live verification

Run `python healthcheck.py` on the server, or run **Actions → Live API Health
Check → Run workflow** using your existing GitHub secrets. This verifies
Telegram authentication, absence of a conflicting webhook, and Jumia shop/order
read access without sending customer data or modifying orders.

## Free-plan renewal

KataBump advertises 308 MB RAM, 716 MB storage and renewal every **four days**.
Renew through the dashboard before expiry. This is a renewable free server,
not an unattended lifetime hosting guarantee. Back up `.env` privately and
`data/` before expiry or deleting the server.

Official instructions:
- https://docs.katabump.com/guides/python
- https://docs.katabump.com/hosting/renew-your-server/

## Troubleshooting

- `Missing ...`: fill the named variable in `.env`, then restart.
- OAuth failed: refresh the authorized Jumia Vendor Center integration credentials.
- HTTP 403: verify assigned Jumia API permissions for the account.
- Active webhook: remove the old webhook through the bot's authorized setup before using polling.
- Another worker / Telegram polling conflict: stop other processes using the same token.
- No response: verify your numeric chat ID is allowlisted and the server is running.
- Startup fails: inspect logs, check Python version, `requirements.txt`, and write permissions on `data/`.

Telegram is the implemented command channel. WhatsApp, bulk catalog feeds,
stock/price writes and a web dashboard are separate unfinished features.
