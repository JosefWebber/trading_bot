import os

# ================================================================
#  TRADING BOT — CONFIGURATION
#  Keys are read from environment variables (set in Railway)
#  For local testing, you can set them in your terminal with:
#  export COINBASE_API_KEY_NAME="your key here"
# ================================================================

# --- API KEYS (loaded from environment variables) ---
COINBASE_API_KEY_NAME = os.environ.get("COINBASE_API_KEY_NAME", "")
COINBASE_PRIVATE_KEY  = os.environ.get("COINBASE_PRIVATE_KEY", "")
TELEGRAM_BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID      = os.environ.get("TELEGRAM_CHAT_ID", "")

# ----------------------------------------------------------------
#  TRADING SETTINGS
# ----------------------------------------------------------------
MAX_POSITION_SIZE_PCT        = 0.10
TRAILING_STOP_PCT            = 0.10
HARD_STOP_LOSS_PCT           = 0.15
TIME_LIMIT_HOURS             = 2
DAILY_LOSS_LIMIT_PCT         = 0.20
COOLDOWN_MINUTES             = 30
SENTIMENT_THRESHOLD          = 0.30
TAKE_PROFIT_LEVELS           = [0.20, 0.35]
TAKE_PROFIT_PORTIONS         = [0.33, 0.33]
MODE                         = "auto"
CHECK_INTERVAL_SECONDS       = 120
PRICE_CHECK_INTERVAL_SECONDS = 30
MORNING_SUMMARY_HOUR         = 8
