import os
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf
import requests

# =========================================================
# إعدادات عامة
# =========================================================

SYMBOLS = {
    "EURUSD": {"ticker": "EURUSD=X", "digits": 5, "pip": 0.0001},
    "XAUUSD": {"ticker": "GC=F",     "digits": 2, "pip": 0.1},
    "NASDAQ": {"ticker": "NQ=F",     "digits": 1, "pip": 1.0},
    "DOWJONES": {"ticker": "YM=F",   "digits": 1, "pip": 1.0},
}

MIN_RR = 2.0                # أقل نسبة عائد/مخاطرة مقبولة (من اختيارك)
SWING_WINDOW = 3            # عدد الشموع يمين ويسار لتأكيد القمة/القاع (Fractal)
DISPLACEMENT_MULT = 1.4     # حجم شمعة الإزاحة يجب يكون أكبر من متوسط آخر 20 شمعة بهذا المعامل
LOOKBACK_SWEEP = 15         # كم شمعة نرجع نبحث عن اصطياد سيولة حديث
LOOKAHEAD_MSS = 12          # كم شمعة بعد الاصطياد نسمح فيها لظهور MSS
STATE_FILE = "state.json"

KILLZONES_GMT = [
    (7, 10),   # لندن
    (12, 15),  # نيويورك
]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# =========================================================
# أدوات مساعدة عامة
# =========================================================

def in_killzone(now_utc: datetime) -> bool:
    h = now_utc.hour
    return any(start <= h < end for start, end in KILLZONES_GMT)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token/chat id missing — skipping send.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code != 200:
            print("Telegram error:", r.text)
    except Exception as e:
        print("Telegram send failed:", e)


# =========================================================
# جلب البيانات
# =========================================================

def fetch(ticker: str, interval: str, period: str) -> pd.DataFrame:
    df = yf.download(ticker, interval=interval, period=period,
                      progress=False, auto_adjust=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["open", "high", "low", "close"]].dropna()


# =========================================================
# اكتشاف القمم والقواع (Swing Points) — أساس البنية والسيولة
# =========================================================

def find_swings(df: pd.DataFrame, window: int = SWING_WINDOW):
    highs, lows = [], []
    h = df["high"].values
    l = df["low"].values
    n = len(df)
    for i in range(window, n - window):
        if h[i] == max(h[i - window:i + window + 1]):
            highs.append(i)
        if l[i] == min(l[i - window:i + window + 1]):
            lows.append(i)
    return highs, lows


# =========================================================
# تحديد الانحياز العام (Bias) من الفريم الأعلى
# آخر MSS مؤكد = كسر بإغلاق لآخر قمة/قاع بنيوي بارز
# =========================================================

def detect_bias(df_htf: pd.DataFrame):
    highs, lows = find_swings(df_htf, window=SWING_WINDOW)
    if not highs or not lows:
        return None

    closes = df_htf["close"].values
    n = len(df_htf)
    last_bias = None

    swing_points = sorted([(i, "H") for i in highs] + [(i, "L") for i in lows])

    for idx in range(SWING_WINDOW * 2, n):
        recent_highs = [i for i, t in swing_points if t == "H" and i < idx]
        recent_lows = [i for i, t in swing_points if t == "L" and i < idx]
        if not recent_highs or not recent_lows:
            continue
        last_high_idx = recent_highs[-1]
        last_low_idx = recent_lows[-1]

        if closes[idx] > df_htf["high"].values[last_high_idx]:
            last_bias = "up"
        elif closes[idx] < df_htf["low"].values[last_low_idx]:
            last_bias = "down"

    return last_bias


def find_dol(df_htf: pd.DataFrame, bias: str, current_price: float):
    highs, lows = find_swings(df_htf, window=SWING_WINDOW)
    if bias == "up":
        candidates = [df_htf["high"].values[i] for i in highs
                      if df_htf["high"].values[i] > current_price]
        return min(candidates) if candidates else None
    elif bias == "down":
        candidates = [df_htf["low"].values[i] for i in lows
                      if df_htf["low"].values[i] < current_price]
        return max(candidates) if candidates else None
    return None


# =========================================================
# اصطياد السيولة + تأكيد MSS + الإزاحة على الفريم الأدنى (15 دقيقة)
# =========================================================

def detect_setup(df_ltf: pd.DataFrame, bias: str):
    """
    يفصل بين أمرين مختلفين عمداً:
    - "المستوى البنيوي" الذي قد يكون قديماً نسبياً (آخر قاع/قمة بارزة معروفة).
    - "شمعة الاصطياد" اللي لازم تكون حديثة (ضمن آخر LOOKBACK_SWEEP شمعة).
    """
    highs, lows = find_swings(df_ltf, window=SWING_WINDOW)
    n = len(df_ltf)
    if n < 30:
        return None

    high = df_ltf["high"].values
    low = df_ltf["low"].values
    close = df_ltf["close"].values
    open_ = df_ltf["open"].values
    body = np.abs(close - open_)
    avg_body = pd.Series(body).rolling(20).mean().values

    recent_start = max(0, n - LOOKBACK_SWEEP)

    if bias == "up":
        low_levels = [(i, low[i]) for i in lows]
        for j in range(recent_start, n):
            prior = [lvl for i, lvl in low_levels if i < j]
            if not prior:
                continue
            level = prior[-1]
            if low[j] < level and close[j] > level:
                sweep_candle = j
                prior_highs = [i for i in highs if i < sweep_candle]
                if not prior_highs:
                    continue
                structure_level = high[prior_highs[-1]]
                for k in range(sweep_candle, min(sweep_candle + LOOKAHEAD_MSS, n)):
                    if close[k] > structure_level and not math.isnan(avg_body[k]) \
                            and body[k] > DISPLACEMENT_MULT * avg_body[k]:
                        return build_setup(df_ltf, "up", sweep_candle, k, highs, lows)
    else:
        high_levels = [(i, high[i]) for i in highs]
        for j in range(recent_start, n):
            prior = [lvl for i, lvl in high_levels if i < j]
            if not prior:
                continue
            level = prior[-1]
            if high[j] > level and close[j] < level:
                sweep_candle = j
                prior_lows = [i for i in lows if i < sweep_candle]
                if not prior_lows:
                    continue
                structure_level = low[prior_lows[-1]]
                for k in range(sweep_candle, min(sweep_candle + LOOKAHEAD_MSS, n)):
                    if close[k] < structure_level and not math.isnan(avg_body[k]) \
                            and body[k] > DISPLACEMENT_MULT * avg_body[k]:
                        return build_setup(df_ltf, "down", sweep_candle, k, highs, lows)
    return None


def build_setup(df_ltf, direction, sweep_idx, mss_idx, highs, lows):
    high = df_ltf["high"].values
    low = df_ltf["low"].values
    open_ = df_ltf["open"].values
    close = df_ltf["close"].values
    n = len(df_ltf)

    end_search = min(mss_idx + 10, n - 1)
    if direction == "up":
        disp_low = low[sweep_idx]
        disp_high = max(high[mss_idx:end_search + 1])
    else:
        disp_high = high[sweep_idx]
        disp_low = min(low[mss_idx:end_search + 1])

    rng = disp_high - disp_low
    if rng <= 0:
        return None

    if direction == "up":
        ote_top = disp_high - rng * 0.62
        ote_bottom = disp_high - rng * 0.79
    else:
        ote_bottom = disp_low + rng * 0.62
        ote_top = disp_low + rng * 0.79

    ob_zone = None
    for i in range(mss_idx, sweep_idx, -1):
        is_bear = close[i] < open_[i]
        is_bull = close[i] > open_[i]
        if direction == "up" and is_bear:
            ob_zone = (low[i], high[i])
            break
        if direction == "down" and is_bull:
            ob_zone = (low[i], high[i])
            break

    fvg_zone = None
    for i in range(sweep_idx + 1, min(mss_idx + 3, n - 1)):
        if direction == "up" and high[i - 1] < low[i + 1]:
            fvg_zone = (high[i - 1], low[i + 1])
        elif direction == "down" and low[i - 1] > high[i + 1]:
            fvg_zone = (high[i + 1], low[i - 1])

    return {
        "direction": direction,
        "sweep_idx": sweep_idx,
        "mss_idx": mss_idx,
        "sweep_level": low[sweep_idx] if direction == "up" else high[sweep_idx],
        "ote_zone": (ote_bottom, ote_top),
        "ob_zone": ob_zone,
        "fvg_zone": fvg_zone,
        "sweep_time": df_ltf.index[sweep_idx],
    }


def price_in_zone(price, zone, tolerance=0.0):
    if zone is None:
        return False
    lo, hi = min(zone), max(zone)
    return (lo - tolerance) <= price <= (hi + tolerance)


# =========================================================
# المعالجة الكاملة لزوج واحد
# =========================================================

def process_symbol(name: str, cfg: dict, state: dict, now_utc: datetime):
    ticker = cfg["ticker"]
    digits = cfg["digits"]

    df_htf = fetch(ticker, interval="60m", period="30d")
    df_ltf = fetch(ticker, interval="15m", period="10d")

    if df_htf.empty or df_ltf.empty or len(df_ltf) < 40:
        print(f"[{name}] بيانات غير كافية — تخطي.")
        return

    current_price = float(df_ltf["close"].iloc[-1])

    bias = detect_bias(df_htf)
    if bias is None:
        print(f"[{name}] لا يوجد تحيز واضح — لا تداول.")
        return

    dol = find_dol(df_htf, bias, current_price)
    if dol is None:
        print(f"[{name}] لا توجد نقطة سحب سيولة واضحة — لا تداول.")
        return

    setup = detect_setup(df_ltf, bias)
    if setup is None:
        print(f"[{name}] لا يوجد إعداد اصطياد + MSS حالياً — لا تداول.")
        return

    in_ote = price_in_zone(current_price, setup["ote_zone"])
    in_ob = price_in_zone(current_price, setup["ob_zone"])
    in_fvg = price_in_zone(current_price, setup["fvg_zone"])

    if not (in_ote and (in_ob or in_fvg)):
        print(f"[{name}] السعر ما زال خارج منطقة التراكب (OTE + OB/FVG) — انتظار.")
        return

    entry = current_price
    buffer = cfg["pip"] * 3

    if bias == "up":
        sl = setup["sweep_level"] - buffer
        tp = dol
        rr = (tp - entry) / (entry - sl) if (entry - sl) > 0 else 0
    else:
        sl = setup["sweep_level"] + buffer
        tp = dol
        rr = (entry - tp) / (sl - entry) if (sl - entry) > 0 else 0

    if rr < MIN_RR:
        print(f"[{name}] نسبة العائد/المخاطرة {rr:.2f} أقل من الحد الأدنى — رفض.")
        return

    if not in_killzone(now_utc):
        print(f"[{name}] إعداد صالح لكن خارج نافذة Killzone — لا إشعار الآن.")
        return

    signal_key = f"{name}_{setup['direction']}_{setup['sweep_time'].isoformat()}"
    if state.get(signal_key):
        print(f"[{name}] هذا الإعداد أُرسل مسبقاً — تجاهل التكرار.")
        return

    direction_ar = "شراء (BUY)" if bias == "up" else "بيع (SELL)"
    msg = (
        f"<b>إشارة ICT — {name}</b>\n"
        f"الاتجاه: {direction_ar}\n"
        f"الدخول: {entry:.{digits}f}\n"
        f"الستوب: {sl:.{digits}f}\n"
        f"الهدف: {tp:.{digits}f}\n"
        f"نسبة العائد/المخاطرة: 1:{rr:.2f}\n"
        f"الوقت (GMT): {now_utc.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"⚠️ هذه إشارة تحليلية آلية وليست توصية مالية. طبّقها يدوياً بعد المراجعة، وابدأ دائماً بحساب ديمو."
    )
    send_telegram(msg)
    state[signal_key] = True
    print(f"[{name}] تم إرسال إشعار: {direction_ar} | RR=1:{rr:.2f}")


# =========================================================
# نقطة التشغيل الرئيسية
# =========================================================

def main():
    now_utc = datetime.now(timezone.utc)
    state = load_state()

    for name, cfg in SYMBOLS.items():
        try:
            process_symbol(name, cfg, state, now_utc)
        except Exception as e:
            print(f"[{name}] خطأ غير متوقع: {e}")

    save_state(state)


if __name__ == "__main__":
    main()
