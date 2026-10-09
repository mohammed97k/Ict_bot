import numpy as np
import pandas as pd
from datetime import datetime
from config.settings import (
    PIVOT_LEN, DISPLACE_MULT, COOLDOWN_BARS, MAX_PER_DAY, USE_HTF_BIAS,
    SL_MIN_PTS, SL_MAX_PTS, SL_SAFETY, TP1_PTS, RR_TP2, RR_TP3,
    ENABLED_MODELS,
)


def atr_rma(high, low, close, length=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False).mean()


def pivothigh(high, left, right):
    arr = high.values
    n = len(arr)
    out = np.full(n, np.nan)
    for i in range(left, n - right):
        window = arr[i-left : i+right+1]
        if arr[i] == window.max() and (window == arr[i]).sum() == 1:
            out[i + right] = arr[i]
    return out


def pivotlow(low, left, right):
    arr = low.values
    n = len(arr)
    out = np.full(n, np.nan)
    for i in range(left, n - right):
        window = arr[i-left : i+right+1]
        if arr[i] == window.min() and (window == arr[i]).sum() == 1:
            out[i + right] = arr[i]
    return out


class ICTStrategy:
    def __init__(self, state=None):
        self.daily_trades = 0
        self.cur_day = None
        self.trades = {k: {"alive": False, "last_bar": -9999} for k in ENABLED_MODELS}
        self.stats = {k: {"tr": 0, "w": 0} for k in ENABLED_MODELS}

        self.last_hi = np.nan
        self.last_lo = np.nan
        self.last_ssl = -9999
        self.last_bsl = -9999
        self.last_mssb = -9999
        self.last_msss = -9999
        self.b_fvg_hi = np.nan; self.b_fvg_lo = np.nan; self.b_fvg_bar = -9999
        self.s_fvg_hi = np.nan; self.s_fvg_lo = np.nan; self.s_fvg_bar = -9999
        self.ob_b_hi = np.nan; self.ob_b_lo = np.nan
        self.ob_s_hi = np.nan; self.ob_s_lo = np.nan
        self.midnight_open = np.nan

        if state:
            self._load_state(state)

    def _load_state(self, state):
        self.daily_trades = state.get("daily_trades", 0)
        cur_day = state.get("cur_day")
        if cur_day:
            try:
                self.cur_day = datetime.fromisoformat(cur_day).date()
            except Exception:
                pass
        for k, v in state.get("trades", {}).items():
            if k in self.trades:
                self.trades[k].update(v)
        for k, v in state.get("stats", {}).items():
            if k in self.stats:
                self.stats[k] = v

    def to_state(self):
        return {
            "daily_trades": self.daily_trades,
            "cur_day": str(self.cur_day) if self.cur_day else None,
            "trades": self.trades,
            "stats": self.stats,
        }

    @staticmethod
    def _in_window(t, start, end):
        s = datetime.strptime(start, "%H:%M").time()
        e = datetime.strptime(end, "%H:%M").time()
        return s <= t.time() <= e

    # ═══════════════════════════════════════════════════════
    #  الدالة الجديدة: تعالج التاريخ لبناء الحالة،
    #  لكن تفتح الصفقات فقط بعد cutoff_time
    # ═══════════════════════════════════════════════════════
    def process_new(self, df_full, cutoff_time):
        signals = []
        df = df_full.copy()
        df["atr"] = atr_rma(df["high"], df["low"], df["close"], 14)
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
        df["piv_hi"] = pivothigh(df["high"], PIVOT_LEN, PIVOT_LEN)
        df["piv_lo"] = pivotlow(df["low"], PIVOT_LEN, PIVOT_LEN)

        for i in range(PIVOT_LEN + 2, len(df)):
            row = df.iloc[i]
            t = row.name
            c = row["close"]; h = row["high"]; l = row["low"]; o = row["open"]
            atr = row["atr"]; ema200 = row["ema200"]

            day = t.date()
            if day != self.cur_day:
                self.cur_day = day
                self.daily_trades = 0

            if t.hour == 0 and t.minute == 0:
                self.midnight_open = o

            if not np.isnan(row["piv_hi"]):
                self.last_hi = row["piv_hi"]
            if not np.isnan(row["piv_lo"]):
                self.last_lo = row["piv_lo"]

            sweep_ssl = (not np.isnan(self.last_lo)) and (l < self.last_lo) and (c > self.last_lo)
            sweep_bsl = (not np.isnan(self.last_hi)) and (h > self.last_hi) and (c < self.last_hi)
            if sweep_ssl: self.last_ssl = i
            if sweep_bsl: self.last_bsl = i

            displace = (h - l) > DISPLACE_MULT * atr
            mss_bull = (not np.isnan(self.last_hi)) and (c > self.last_hi) and displace
            mss_bear = (not np.isnan(self.last_lo)) and (c < self.last_lo) and displace
            if mss_bull: self.last_mssb = i
            if mss_bear: self.last_msss = i

            if i >= 2:
                if l > df["high"].iloc[i-2]:
                    self.b_fvg_hi = l
                    self.b_fvg_lo = df["high"].iloc[i-2]
                    self.b_fvg_bar = i
                if h < df["low"].iloc[i-2]:
                    self.s_fvg_hi = df["low"].iloc[i-2]
                    self.s_fvg_lo = h
                    self.s_fvg_bar = i

            if mss_bull:
                for k in range(1, 11):
                    if df["close"].iloc[i-k] < df["open"].iloc[i-k]:
                        self.ob_b_hi = df["high"].iloc[i-k]
                        self.ob_b_lo = df["low"].iloc[i-k]
                        break
            if mss_bear:
                for k in range(1, 11):
                    if df["close"].iloc[i-k] > df["open"].iloc[i-k]:
                        self.ob_s_hi = df["high"].iloc[i-k]
                        self.ob_s_lo = df["low"].iloc[i-k]
                        break

            sweep_fresh_l = (i - self.last_ssl) <= 25
            sweep_fresh_s = (i - self.last_bsl) <= 25
            mss_fresh_l = (i - self.last_mssb) <= 25
            mss_fresh_s = (i - self.last_msss) <= 25
            chain_l = sweep_fresh_l and mss_fresh_l and self.last_mssb > self.last_ssl
            chain_s = sweep_fresh_s and mss_fresh_s and self.last_msss > self.last_bsl

            htf_bull = (not USE_HTF_BIAS) or (c > ema200)
            htf_bear = (not USE_HTF_BIAS) or (c < ema200)
            daily_ok = self.daily_trades < MAX_PER_DAY

            # ⚠️ فقط نفتح صفقات بعد cutoff_time
            if t < cutoff_time:
                continue

            # MMBM
            if ENABLED_MODELS["MMBM"] and daily_ok and not self.trades["MMBM"]["alive"]:
                if (i - self.trades["MMBM"]["last_bar"]) > COOLDOWN_BARS:
                    if chain_l and htf_bull and self._in_window(t, "09:30", "11:30"):
                        if not np.isnan(self.midnight_open) and c > self.midnight_open:
                            if not np.isnan(self.ob_b_lo) and l <= self.ob_b_hi and c > self.ob_b_lo:
                                signals.append(self._open("MMBM", True, self.ob_b_lo, i, t, c))
                                self.daily_trades += 1

            # MMSM
            if ENABLED_MODELS["MMSM"] and daily_ok and not self.trades["MMSM"]["alive"]:
                if (i - self.trades["MMSM"]["last_bar"]) > COOLDOWN_BARS:
                    if chain_s and htf_bear and self._in_window(t, "09:30", "11:30"):
                        if not np.isnan(self.midnight_open) and c < self.midnight_open:
                            if not np.isnan(self.ob_s_hi) and h >= self.ob_s_lo and c < self.ob_s_hi:
                                signals.append(self._open("MMSM", False, self.ob_s_hi, i, t, c))
                                self.daily_trades += 1

            # PO3
            if ENABLED_MODELS["PO3"] and daily_ok and not self.trades["PO3"]["alive"]:
                if (i - self.trades["PO3"]["last_bar"]) > COOLDOWN_BARS:
                    if self._in_window(t, "09:30", "11:30") and not np.isnan(self.midnight_open):
                        if chain_l and htf_bull and l < self.midnight_open and c > self.midnight_open and mss_bull:
                            signals.append(self._open("PO3", True, l, i, t, c))
                            self.daily_trades += 1
                        elif chain_s and htf_bear and h > self.midnight_open and c < self.midnight_open and mss_bear:
                            signals.append(self._open("PO3", False, h, i, t, c))
                            self.daily_trades += 1

            # Judas
            if ENABLED_MODELS["Judas"] and daily_ok and not self.trades["Judas"]["alive"]:
                if (i - self.trades["Judas"]["last_bar"]) > COOLDOWN_BARS:
                    if self._in_window(t, "09:30", "09:45"):
                        if sweep_ssl and htf_bull and c > o and c > df["high"].iloc[i-1]:
                            signals.append(self._open("Judas", True, l, i, t, c))
                            self.daily_trades += 1
                        elif sweep_bsl and htf_bear and c < o and c < df["low"].iloc[i-1]:
                            signals.append(self._open("Judas", False, h, i, t, c))
                            self.daily_trades += 1

            # Turtle
            if ENABLED_MODELS["Turtle"] and daily_ok and not self.trades["Turtle"]["alive"]:
                if (i - self.trades["Turtle"]["last_bar"]) > COOLDOWN_BARS:
                    if self._in_window(t, "09:30", "11:30"):
                        if sweep_ssl and mss_fresh_l and htf_bull and (i - self.last_mssb) <= 5:
                            signals.append(self._open("Turtle", True, l, i, t, c))
                            self.daily_trades += 1
                        elif sweep_bsl and mss_fresh_s and htf_bear and (i - self.last_msss) <= 5:
                            signals.append(self._open("Turtle", False, h, i, t, c))
                            self.daily_trades += 1

            # SMR
            if ENABLED_MODELS["SMR"] and daily_ok and not self.trades["SMR"]["alive"]:
                if (i - self.trades["SMR"]["last_bar"]) > COOLDOWN_BARS:
                    if self._in_window(t, "09:30", "11:30"):
                        if chain_l and htf_bull and not np.isnan(self.ob_b_lo) and l <= self.ob_b_hi and c > self.ob_b_lo:
                            signals.append(self._open("SMR", True, self.ob_b_lo, i, t, c))
                            self.daily_trades += 1
                        elif chain_s and htf_bear and not np.isnan(self.ob_s_hi) and h >= self.ob_s_lo and c < self.ob_s_hi:
                            signals.append(self._open("SMR", False, self.ob_s_hi, i, t, c))
                            self.daily_trades += 1

            # TGIF
            if ENABLED_MODELS["TGIF"] and daily_ok and not self.trades["TGIF"]["alive"]:
                if (i - self.trades["TGIF"]["last_bar"]) > COOLDOWN_BARS:
                    if t.weekday() == 4 and self._in_window(t, "13:30", "15:00"):
                        if chain_l and htf_bull and displace and mss_bull:
                            signals.append(self._open("TGIF", True, l, i, t, c))
                            self.daily_trades += 1
                        elif chain_s and htf_bear and displace and mss_bear:
                            signals.append(self._open("TGIF", False, h, i, t, c))
                            self.daily_trades += 1

            # Lunch
            if ENABLED_MODELS["Lunch"] and daily_ok and not self.trades["Lunch"]["alive"]:
                if (i - self.trades["Lunch"]["last_bar"]) > COOLDOWN_BARS:
                    if self._in_window(t, "12:00", "13:30"):
                        if chain_l and htf_bull and not np.isnan(self.ob_b_hi) and c > self.ob_b_hi:
                            signals.append(self._open("Lunch", True, self.ob_b_lo, i, t, c))
                            self.daily_trades += 1
                        elif chain_s and htf_bear and not np.isnan(self.ob_s_hi) and c < self.ob_s_lo:
                            signals.append(self._open("Lunch", False, self.ob_s_hi, i, t, c))
                            self.daily_trades += 1

        return signals

    # ═══════════════════════════════════════════════════════
    #  الدالة القديمة (نحتفظ بها للتوافق)
    # ═══════════════════════════════════════════════════════
    def process(self, df):
        return self.process_new(df, df.index[0])

    def _open(self, name, is_long, sl_base, bar_idx, t, price):
        raw_sl = abs(price - sl_base)
        clamped = max(SL_MIN_PTS, min(SL_MAX_PTS, raw_sl))
        final_sl_dist = clamped + SL_SAFETY

        slv = price - final_sl_dist if is_long else price + final_sl_dist
        p1 = max(TP1_PTS, final_sl_dist)
        p2 = max(TP1_PTS * 1.5, RR_TP2 * final_sl_dist)
        p3 = max(TP1_PTS * 2.0, RR_TP3 * final_sl_dist)

        tp1 = price + p1 if is_long else price - p1
        tp2 = price + p2 if is_long else price - p2
        tp3 = price + p3 if is_long else price - p3

        self.trades[name] = {
            "alive": True, "is_long": is_long,
            "entry": float(price), "sl": float(slv),
            "tp1": float(tp1), "tp2": float(tp2), "tp3": float(tp3),
            "hits": 0, "last_bar": bar_idx, "time": str(t),
        }
        self.stats[name]["tr"] += 1

        return {
            "model": name,
            "side": "BUY" if is_long else "SELL",
            "entry": float(price),
            "sl": float(slv),
            "tp1": float(tp1),
            "tp2": float(tp2),
            "tp3": float(tp3),
            "time": str(t),
        }

    def update(self, df):
        if len(df) < 2:
            return []
        last = df.iloc[-1]
        h, l = last["high"], last["low"]
        closed = []

        for name, tr in self.trades.items():
            if not tr["alive"]:
                continue

            hits = tr["hits"]
            if tr["is_long"]:
                if h >= tr["tp1"] and hits < 1: hits = 1
                if h >= tr["tp2"] and hits < 2: hits = 2
                if h >= tr["tp3"] and hits < 3: hits = 3
            else:
                if l <= tr["tp1"] and hits < 1: hits = 1
                if l <= tr["tp2"] and hits < 2: hits = 2
                if l <= tr["tp3"] and hits < 3: hits = 3
            tr["hits"] = hits

            sl_hit = (l <= tr["sl"]) if tr["is_long"] else (h >= tr["sl"])
            ended = sl_hit or (hits >= 3)

            if ended:
                tr["alive"] = False
                if hits >= 1:
                    self.stats[name]["w"] += 1
                closed.append({
                    "model": name,
                    "hits": hits,
                    "sl_hit": sl_hit,
                    "entry": tr["entry"],
                    "time": tr["time"],
                })
        return closed
    