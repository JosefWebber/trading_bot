# Crypto Sentiment Trading Bot — Setup Guide

## What this bot does
- Monitors **Trump**, **Elon Musk**, **Michael Saylor**, and **Cathie Wood** 24/7
- Detects positive crypto mentions using AI sentiment analysis
- Automatically buys on Coinbase when a strong positive signal is detected
- Protects every trade with a **trailing stop loss**, **hard stop loss**, and **time limit**
- Sells in chunks at **take profit levels** to lock in gains
- Sends you a **Telegram notification** for every action
- Sends a **morning summary** every day at 8am

---

## Requirements
- Python 3.10 or newer
- A Coinbase Advanced account with funds
- A Telegram account
- A computer or server that stays on (or a free cloud host — see Step 5)

---

## Step 1 — Install Python dependencies

Open a terminal in the `trading_bot` folder and run:

```bash
pip install -r requirements.txt
```

---

## Step 2 — Fill in your API keys (config.py)

Open `config.py` and fill in:

```python
COINBASE_API_KEY_NAME = "organizations/xxx/apiKeys/xxx"   # from Coinbase
COINBASE_PRIVATE_KEY  = """-----BEGIN EC PRIVATE KEY-----
...your key here...
-----END EC PRIVATE KEY-----"""

TELEGRAM_BOT_TOKEN = "1234567890:ABCdef..."    # from @BotFather
TELEGRAM_CHAT_ID   = "987654321"               # see Step 3 below
```

**Your private key is multi-line** — paste it exactly as Coinbase showed it,
including the `-----BEGIN` and `-----END` lines, inside triple quotes.

---

## Step 3 — Get your Telegram Chat ID

1. Open Telegram and search for your bot (the one you created with @BotFather)
2. Send it the message: `/start`
3. In your browser, open this URL (replace TOKEN with your bot token):
   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```
4. Look for `"chat":{"id":` — that number is your Chat ID
5. Paste it into `config.py` as `TELEGRAM_CHAT_ID`

---

## Step 4 — Run the bot

```bash
python main.py
```

You should see log messages in the terminal and receive a startup
message on Telegram within a few seconds.

---

## Step 5 — Keep it running 24/7 (free cloud hosting)

Instead of leaving your computer on, deploy to **Railway** (free tier):

1. Go to https://railway.app and sign up (free)
2. Click **New Project → Deploy from GitHub**
3. Upload this folder to a GitHub repo first (also free)
4. Set your environment variables in Railway's dashboard
   (same keys as in config.py — safer than hardcoding them)
5. Railway will run the bot continuously for free

---

## Telegram Commands

Once the bot is running, send these to your Telegram bot:

| Command   | What it does                              |
|-----------|-------------------------------------------|
| `/status` | Current balance, open positions, today's P&L |
| `/mode`   | Toggle between AUTO and APPROVAL mode     |
| `/resume` | Restart trading after daily loss limit    |
| `/stats`  | All-time trade statistics                 |
| `/help`   | Show command list                         |

---

## Adjusting your settings (config.py)

| Setting                  | Default | What it controls                              |
|--------------------------|---------|-----------------------------------------------|
| `MAX_POSITION_SIZE_PCT`  | 10%     | Max % of balance per trade                    |
| `TRAILING_STOP_PCT`      | 10%     | Sell if price falls 10% from its peak         |
| `HARD_STOP_LOSS_PCT`     | 15%     | Never lose more than 15% from entry           |
| `TIME_LIMIT_HOURS`       | 2       | Auto-sell after 2 hours regardless            |
| `DAILY_LOSS_LIMIT_PCT`   | 20%     | Pause bot if 20% of balance lost today        |
| `COOLDOWN_MINUTES`       | 30      | Wait 30 min before re-trading same coin       |
| `SENTIMENT_THRESHOLD`    | 0.30    | Minimum confidence score to trigger a buy     |
| `TAKE_PROFIT_LEVELS`     | 20%, 35%| Sell 33% of position at each level            |
| `MODE`                   | "auto"  | "auto" or "approval"                          |

You can change any of these at any time — just restart the bot.

---

## Trade log

Every trade is saved to `trades.csv` in the same folder.
Open it in Excel or Google Sheets to review performance.

---

## Upgrading to paid X API later

When you're ready to upgrade from free Nitter RSS to the real X API:

1. Subscribe at https://developer.twitter.com (~£63/month)
2. Get your API Key, Secret, and Bearer Token
3. Open `social_monitor.py` and replace the Nitter section with
   the official Twitter API calls (I can help with this when you're ready)

---

## Important notes

- The bot only has **trade** permission on Coinbase — it cannot withdraw funds
- Your bank details are never involved — withdrawals are done manually via Coinbase
- Past performance cannot predict future results — crypto is volatile
- Only invest money you're comfortable losing entirely
