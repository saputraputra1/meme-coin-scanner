import os

TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN", "8280898654:AAE7-w2OiGk8vUh47gD5J7HJQnbu2P_EOLM")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID", "")
TELEGRAM_PROXY = os.environ.get("TELEGRAM_PROXY", "")
HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "4ffecd7b-a4be-48bd-b689-4ee8bde100a3")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "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")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", "8000"))
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(16).hex())

SCAN_INTERVAL_SECONDS = 60
MIN_LIQUIDITY_USD = 5000
MAX_MARKET_CAP_USD = 1000000
MAX_TOKEN_AGE_MINUTES = 60
MIN_HOLDER_COUNT = 50
MIN_SCORE_FOR_ALERT = 70

SCORE_SAFETY_WEIGHT = 40
SCORE_LIQUIDITY_WEIGHT = 25
SCORE_HOLDER_WEIGHT = 20
SCORE_SOCIAL_WEIGHT = 15

MAX_TOP10_HOLDER_PCT = 30
MIN_LP_BURNED_PCT = 80

FILTER_PRESETS = {
    "aggressive": {"name": "Aggressive (high risk)", "liq_min": 1000, "mcap_max": 500000, "age_max": 120, "holders_min": 10, "score_min": 40},
    "balanced":  {"name": "Balanced", "liq_min": 5000, "mcap_max": 1000000, "age_max": 60, "holders_min": 50, "score_min": 60},
    "conservative": {"name": "Conservative (safe)", "liq_min": 20000, "mcap_max": 500000, "age_max": 30, "holders_min": 100, "score_min": 75},
}

MEME_SEARCH_TERMS = ["meme", "pepe", "doge", "cat", "ai", "bot", "moon", "sol", "wif", "bonk"]

# Auto Trade Configuration
AUTO_TRADE_ENABLED = os.environ.get("AUTO_TRADE_ENABLED", "true").lower() == "true"
AUTO_TRADE_DEFAULT_MODE = "full-auto"
AUTO_TRADE_DEFAULT_BUY_SOL = 0.1
AUTO_TRADE_MAX_POSITIONS = 10
AUTO_TRADE_MIN_CONFIDENCE = 7
AUTO_TRADE_STOP_LOSS_PCT = -40
AUTO_TRADE_TAKE_PROFIT_PCT = 100
AUTO_TRADE_SLIPPAGE_BPS = 500
POSITION_MONITOR_INTERVAL = 180
