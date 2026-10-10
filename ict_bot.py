# ict_bot.py
# ═══════════════════════════════════════════════════════════════
# ICT 7-Model Signal Bot for NAS100 (5M)
# Data Source: MetaTrader 5 (read-only, no trading)
# Notifications: Telegram
# Deploy: Windows VPS or local machine with MT5 installed
# ═══════════════════════════════════════════════════════════════

import os
import json
import time
import asyncio
from datetime import datetime, timedelta
import pytz

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

# ═══════════ CONFIG ═══════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
MT5_SYMBOL         = os.getenv("MT5_SYMBOL", "NAS100")
MT5_LOGIN          = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD       = os.getenv("MT5_PASSWORD", "")
MT5_SERVER         = os.getenv("MT5_SERVER", "")

BARS               = 600
INTERVAL_SECONDS   = 60   # يفحص كل دقيقة (يتخطى الشموع المكررة)

MOSUL_TZ = pytz.timezone("Asia/Baghdad")
NY_TZ    = pytz.timezone("America/New_York")
STATE_FILE = "config.json"

# ═══════════ MT5 SETUP ═══════════
def init_mt5():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        raise Exception(f"MT5 init failed: {mt5.last_error()}")
    print(f"[MT5] Connected. Terminal: {mt5.terminal_info().name}")
    print(f"[MT5] Account: {mt5.account_info().login} @ {mt5.account_info().server}")

def shutdown_mt5():
    mt5.shutdown()

def fetch_ohlc():
    """يقرأ آخر BARS شمعة 5 دقائق من MT5."""
    rates = mt5.copy_rates_from_pos(MT5_SYMBOL, mt5.TIMEFRAME_M5, 0, BARS)
    if rates is None or len(rates) == 0:
        raise Exception(f"MT5 returned no data for {MT5_SYMBOL}")

    df = pd.DataFrame(rates)
    df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(NY_TZ)
    df = df.rename(columns={"tick_volume": "volume"})
    return df[["datetime", "open", "high", "low", "close", "volume"]]

# ═══════════ INDICATORS ═══════════
def compute_indicators(df):
    high, low, close = df["high"], df["low"], df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    df["ema200"] = close.ewm(span=200, adjust=False).mean()
    df["disp"] = (high - low) > 1.3 * df["atr14"]

    # Pivots (4,4) — with lookahead confirmation
    df["piv_hi"] = np.nan
    df["piv_lo"] = np.nan
    for i in range(4, len(df) - 4):
        window_hi = high.iloc[i-4:i+5]
        window_lo = low.iloc[i-4:i+5]
        if high.iloc[i] == window_hi.max():
            df.at[i, "piv_hi"] = high.iloc[i]
        if low.iloc[i] == window_lo.min():
            df.at[i, "piv_lo"] = low.iloc[i]

    return df

# ═══════════ STATE ═══════════
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
 f    return {}

def save_state(state,):
    with open(STATE_FILE, " indentw") as f:
        json.dump(state=2,, default=str)

# ═══════════ MAIN LOGIC ═══════════
class ICTBot:
    def __init__(self):
        self.state = load_state()
        self.state.setdefault("last_processed_bar", None)
        self.state.setdefault("lastPH", None)
        self.state.setdefault("lastPL", None)
        self.state.setdefault("bSSL", None)
        self.state.setdefault("bBSL", None)
        self.state.setdefault("bMssB", None)
        self.state.setdefault("bMssS", None)
        self.state.setdefault("ob_b_hi", None)
        self.state.setdefault("ob_b_lo", None)
        self.state.setdefault("ob_s_hi", None)
        self.state.setdefault("ob_s_lo", None)
        self.state.setdefault("midnight_open", None)
        self.state.setdefault("day", None)
        self.state.setdefault("daily_trades", 0)
        self.state.setdefault("active_trades", {})
        self.state.setdefault("model_last_bar_idx", {})
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)

    # ─── Telegram ───
    async def _send(self, msg):
        try:
            await self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
        except Exception as e:
            print(f"[TG ERROR] {e}")

    def send(self, msg):
        asyncio.run(self._send(msg))

    def fmt_time(self):
        now = datetime.now(MOSUL_TZ)
        return now.strftime("%I:%M %p")

    def fmt_signal(self, s):
        icon = "🟢 BUY" if s["is_long"] else "🔴 SELL"
        return (
            f"{icon} [{s['model']}]\n"
            f"Entry: {s['entry']:.2f}\n"
            f"SL: {s['sl']:.2f}\n"
            f"🎯 TP1: {s['tp1']:.2f}\n"
            f"🎯 🎯 TP2: {s['tp2']:.2f}\n"
            f"🎯 🎯 🎯 TP3: {s['tp3']:.2f}\n"
            f"Points: {s['pts']:.2f}\n"
            f"🕐 {self.fmt_time()}"
        )

    def fmt_hit(self, a):
        if a["type"] == "SL":
            return (
                f"🛑 SL HIT [{a['model']}]\n"
                f"Price: {a['price']:.2f}\n"
                f"🕐 {self.fmt_time()}"
            )
        emoji = {"TP1": "🎯", "TP2": "🎯 🎯", "TP3": "🎯 🎯 🎯"}[a["type"]]
        return (
            f"✅ {a['type']} HIT [{a['model']}] {emoji}\n"
            f"Price: {a['price']:.2f}\n"
            f"Points: {a['pts']:.2f}\n"
            f"🕐 {self.fmt_time()}"
        )

    # ─── Core processing ───
    def process(self, df):
        df = compute_indicators(df)
        last_bar = df.iloc[-2]   # آخر شمعة مغلقة
        bar_time = last_bar["datetime"]
        bar_key  = str(bar_time)

        # منع تكرار نفس الشمعة
        if self.state["last_processed_bar"] == bar_key:
            return
        self.state["last_processed_bar"] = bar_key

        now_ny = bar_time
        hour_min = now_ny.hour * 100 + now_ny.minute
        in_am     = 930 <= hour_min < 1130
        in_judas  = 930 <= hour_min < 945
        in_lunch  = 1200 <= hour_min < 1330
        in_pm     = 1330 <= hour_min < 1500
        is_fri    = now_ny.weekday() == 4

        # Midnight Open
        if 0 <= hour_min < 5:
            self.state["midnight_open"] = float(last_bar["open"])

        # Daily reset
        today = str(now_ny.date())
        if self.state["day"] != today:
            self.state["day"] = today
            self.state["daily_trades"] = 0
            self.state["active_trades"] = {}

        # ═══════════ Update pivots / sweeps / MSS ═══════════
        # آخر pivot مكتشف
        piv_his = df["piv_hi"].dropna()
        piv_los = df["piv_lo"].dropna()
        if len(piv_his) > 0:
            self.state["lastPH"] = float(piv_his.iloc[-1])
        if len(piv_los) > 0:
            self.state["lastPL"] = float(piv_los.iloc[-1])

        lastPH = self.state["lastPH"]
        lastPL = self.state["lastPL"]

        # Sweep
        sweepSSL = lastPL is not None and last_bar["low"]  < lastPL and last_bar["close"] > lastPL
        sweepBSL = lastPH is not None and last_bar["high"] > lastPH and last_bar["close"] < lastPH

        if sweepSSL:
            self.state["bSSL"] = bar_key
        if sweepBSL:
            self.state["bBSL"] = bar_key

        # MSS
        mssBull = lastPH is not None and last_bar["close"] > lastPH and last_bar["disp"]
        mssBear = lastPL is not None and last_bar["close"] < lastPL and last_bar["disp"]

        if mssBull:
            self.state["bMssB"] = bar_key
            # OB = آخر شمعة هابطة قبل MSS خلال 10 شموع
            for i in range(2, 12):
                if df.iloc[-i]["close"] < df.iloc[-i]["open"]:
                    self.state["ob_b_hi"] = float(df.iloc[-i]["high"])
                    self.state["ob_b_lo"] = float(df.iloc[-i]["low"])
                    break
        if mssBear:
            self.state["bMssS"] = bar_key
            for i in range(2, 12):
                if df.iloc[-i]["close"] > df.iloc[-i]["open"]:
                    self.state["ob_s_hi"] = float(df.iloc[-i]["high"])
                    self.state["ob_s_lo"] = float(df.iloc[-i]["low"])
                    break

        # ═══════════ Check TP/SL on active trades ═══════════
        self.check_active_trades(last_bar)

        # ═══════════ Signal detection ═══════════
        signals = []
        midnight = self.state["midnight_open"]
        ob_b_hi  = self.state["ob_b_hi"]
        ob_b_lo  = self.state["ob_b_lo"]
        ob_s_hi  = self.state["ob_s_hi"]
        ob_s_lo  = self.state["ob_s_lo"]
        total_bar_idx = len(df)

        # MMBM
        if (midnight and last_bar["close"] > last_bar["ema200"] and in_am
            and last_bar["close"] > midnight
            and ob_b_hi and last_bar["low"] <= ob_b_hi and last_bar["close"] > ob_b_lo):
            s = self._prep("MMBM", True, float(last_bar["close"]), ob_b_lo or lastPL, total_bar_idx)
            if s: signals.append(s)

        # MMSM
        if (midnight and last_bar["close"] < last_bar["ema200"] and in_am
            and last_bar["close"] < midnight
            and ob_s_lo and last_bar["high"] >= ob_s_lo and last_bar["close"] < ob_s_hi):
            s = self._prep("MMSM", False, float(last_bar["close"]), ob_s_hi or lastPH, total_bar_idx)
            if s: signals.append(s)

        # PO3
        if in_am and midnight and last_bar["low"] < midnight and last_bar["close"] > midnight:
            s = self._prep("PO3", True, float(last_bar["close"]), ob_b_lo or lastPL, total_bar_idx)
            if s: signals.append(s)
        if in_am and midnight and last_bar["high"] > midnight and last_bar["close"] < midnight:
            s = self._prep("PO3", False, float(last_bar["close"]), ob_s_hi or lastPH, total_bar_idx)
            if s: signals.append(s)

        # Judas
        if in_judas:
            rng = last_bar["high"] - last_bar["low"]
            strong_up = rng > 0 and (last_bar["close"] - last_bar["low"]) / rng >= 0.70
            strong_dn = rng > 0 and (last_bar["high"] - last_bar["close"]) / rng >= 0.70
            if (last_bar["disp"] and last_bar["close"] > last_bar["ema200"]
                and midnight and last_bar["close"] > midnight and strong_up):
                s = self._prep("Judas", True, float(last_bar["close"]), ob_b_lo or lastPL, total_bar_idx)
                if s: signals.append(s)
            if (last_bar["disp"] and last_bar["close"] < last_bar["ema200"]
                and midnight and last_bar["close"] < midnight and strong_dn):
                s = self._prep("Judas", False, float(last_bar["close"]), ob_s_hi or lastPH, total_bar_idx)
                if s: signals.append(s)

        # SMR
        if in_am and ob_b_hi and last_bar["low"] <= ob_b_hi and last_bar["close"] > ob_b_lo:
            s = self._prep("SMR", True, float(last_bar["close"]), ob_b_lo or lastPL, total_bar_idx)
            if s: signals.append(s)
        if in_am and ob_s_lo and last_bar["high"] >= ob_s_lo and last_bar["close"] < ob_s_hi:
            s = self._prep("SMR", False, float(last_bar["close"]), ob_s_hi or lastPH, total_bar_idx)
            if s: signals.append(s)

        # TGIF
        if is_fri and in_pm and last_bar["disp"]:
            if midnight and last_bar["close"] > midnight:
                s = self._prep("TGIF", True, float(last_bar["close"]), ob_b_lo or lastPL, total_bar_idx)
                if s: signals.append(s)
            if midnight and last_bar["close"] < midnight:
                s = self._prep("TGIF", False, float(last_bar["close"]), ob_s_hi or lastPH, total_bar_idx)
                if s: signals.append(s)

        # Lunch
        if in_lunch and ob_b_hi and last_bar["close"] > ob_b_hi:
            s = self._prep("Lunch", True, float(last_bar["close"]), ob_b_lo or lastPL, total_bar_idx)
            if s: signals.append(s)
        if in_lunch and ob_s_lo and last_bar["close"] < ob_s_lo:
            s = self._prep("Lunch", False, float(last_bar["close"]), ob_s_hi or lastPH, total_bar_idx)
            if s: signals.append(s)

        # ═══════════ Send signals ═══════════
        for s in signals:
            self.send(self.fmt_signal(s))
            print(f"[SIGNAL] {s['model']} {'BUY' if s['is_long'] else 'SELL'} @ {s['entry']}")

        save_state(self.state)

    def _prep(self, model, is_long, entry, sl_base, bar_idx):
        if self.state["daily_trades"] >= 3:
            return None

        # Cooldown 20 شمعة
        last_idx = self.state["model_last_bar_idx"].get(model)
        if last_idx is not None and (bar_idx - last_idx) < 20:
            return None

        # صفقة نشطة؟
        if model in self.state["active_trades"]:
            return None

        raw = abs(entry - sl_base)
        clamped = max(50.0, min(180.0, raw))
        final_sl = clamped + 20.0
        slv = entry - final_sl if is_long else entry + final_sl
        tp1 = entry + max(80.0, final_sl) if is_long else entry - max(80.0, final_sl)
        tp2d = max(80.0 * 1.5, 2.0 * final_sl)
        tp3d = max(80.0 * 2.0, 3.0 * final_sl)
        tp2 = entry + tp2d if is_long else entry - tp2d
        tp3 = entry + tp3d if is_long else entry - tp3d
        pts = abs(tp1 - entry)

        self.state["active_trades"][model] = {
            "entry": entry, "sl": slv, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "is_long": is_long, "pts": pts,
            "tp1_hit": False, "tp2_hit": False, "tp3_hit": False,
            "bar_idx": bar_idx,
        }
        self.state["model_last_bar_idx"][model] = bar_idx
        self.state["daily_trades"] += 1

        return {"model": model, "entry": entry, "sl": slv,
                "tp1": tp1, "tp2": tp2, "tp3": tp3,
                "is_long": is_long, "pts": pts}

    def check_active_trades(self, bar):
        for model, t in list(self.state["active_trades"].items()):
            is_long = t["is_long"]
            if is_long:
                sl_hit  = bar["low"]  <= t["sl"]
                tp1_hit = bar["high"] >= t["tp1"]
                tp2_hit = bar["high"] >= t["tp2"]
                tp3_hit = bar["high"] >= t["tp3"]
            else:
                sl_hit  = bar["high"] >= t["sl"]
                tp1_hit = bar["low"]  <= t["tp1"]
                tp2_hit = bar["low"]  <= t["tp2"]
                tp3_hit = bar["low"]  <= t["tp3"]

            # SL قبل TP1 = خسارة
            if sl_hit and not t["tp1_hit"]:
                self.send(self.fmt_hit({"model": model, "type": "SL", "price": t["sl"]}))
                del self.state["active_trades"][model]
                print(f"[HIT] {model} SL @ {t['sl']}")
                continue

            if tp1_hit and not t["tp1_hit"]:
                t["tp1_hit"] = True
                self.send(self.fmt_hit({"model": model, "type": "TP1", "price": t["tp1"],
                                        "pts": abs(t["tp1"]-t["entry"])}))
                print(f"[HIT] {model} TP1")

            if tp2_hit and not t["tp2_hit"]:
                t["tp2_hit"] = True
                self.send(self.fmt_hit({"model": model, "type": "TP2", "price": t["tp2"],
                                        "pts": abs(t["tp2"]-t["entry"])}))
                print(f"[HIT] {model} TP2")

            if tp3_hit and not t["tp3_hit"]:
                t["tp3_hit"] = True
                self.send(self.fmt_hit({"model": model, "type": "TP3", "price": t["tp3"],
                                        "pts": abs(t["tp3"]-t["entry"])}))
                print(f"[HIT] {model} TP3")
                del self.state["active_trades"][model]
                continue

# ═══════════ MAIN LOOP ═══════════
def main():
    print("═" * 60)
    print(" ICT 7-Model Signal Bot — NAS100 (5M)")
    print("═" * 60)
    init_mt5()

    bot = ICTBot()
    print("[BOT] Started. Checking every minute...")
    bot.send("🤖 ICT Bot started.\nMonitoring NAS100 (5M).")

    try:
        while True:
            try:
                df = fetch_ohlc()
                bot.process(df)
            except Exception as e:
                print(f"[ERROR] {e}")
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n[BOT] Stopped by user.")
    finally:
        shutdown_mt5()
        bot.send("🔌 ICT Bot stopped.")

if __name__ == "__main__":
    main()