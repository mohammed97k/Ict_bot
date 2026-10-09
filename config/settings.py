import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ───
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# ─── TwelveData ───
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
TWELVEDATA_TICKER  = os.getenv("TWELVEDATA_TICKER", "NDX")

# ─── KiT Hub ───
KIT_API_KEY    = os.getenv("KIT_API_KEY")
KIT_API_SECRET = os.getenv("KIT_API_SECRET")
KIT_BASE_URL   = os.getenv("KIT_BASE_URL", "https://api.kithub.com")
KIT_SYMBOL     = os.getenv("KIT_SYMBOL", "NAS100")

# ─── Strategy ───
TIMEFRAME     = os.getenv("TIMEFRAME", "5min")
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "30"))

PIVOT_LEN     = 4
DISPLACE_MULT = 1.3
COOLDOWN_BARS = 20
MAX_PER_DAY   = 3
USE_HTF_BIAS  = True

SL_MIN_PTS = 50.0
SL_MAX_PTS = 180.0
SL_SAFETY  = 20.0
TP1_PTS    = 80.0
RR_TP2     = 2.0
RR_TP3     = 3.0

ENABLED_MODELS = {
    "MMBM":   True,
    "MMSM":   True,
    "PO3":    True,
    "Judas":  True,
    "Turtle": True,
    "SMR":    True,
    "TGIF":   True,
    "Lunch":  True,
}

NY_TZ = "America/New_York"
