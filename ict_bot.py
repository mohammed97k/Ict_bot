import os, json, asyncio
from datetime import datetime
import pytz
import pandas as pd
import numpy as np
from mt5linux import MetaTrader5 as mt5
from telegram import Bot as TGBot

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT  = os.environ["TELEGRAM_CHAT_ID"]
LOGIN = int(os.environ["MT5_LOGIN"])
PWD   = os.environ["MT5_PASSWORD"]
SRV   = os.environ["MT5_SERVER"]
SYM   = os.environ.get("MT5_SYMBOL", "NDXUSD#")

MOSUL = pytz.timezone("Asia/Baghdad")
NY    = pytz.timezone("America/New_York")
STATE = "config.json"

def load():
    if os.path.exists(STATE):
        with open(STATE) as f: return json.load(f)
    return {}

def save(s):
    with open(STATE, "w") as f: json.dump(s, f, indent=2, default=str)

def init_mt5():
    ok = mt5.initialize(login=LOGIN, password=PWD, server=SRV, timeout=300000)
    if not ok:
        raise Exception(f"MT5 init failed: {mt5.last_error()}")
    info = mt5.account_info()
    if info is None:
        raise Exception("MT5 connected but no account info")
    print(f"[MT5 OK] {info.login} @ {info.server}")

def fetch():
    r = mt5.copy_rates_from_pos(SYM, mt5.TIMEFRAME_M5, 0, 600)
    if r is None or len(r) == 0:
        raise Exception(f"No data for {SYM}")
    df = pd.DataFrame(r)
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(NY)
    return df[["dt", "open", "high", "low", "close"]]

def ind(df):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1/14, adjust=False).mean()
    df["ema"] = c.ewm(span=200, adjust=False).mean()
    df["disp"] = (h - l) > 1.3 * df["atr"]
    df["ph"] = np.nan
    df["pl"] = np.nan
    for i in range(4, len(df)-4):
        if h.iloc[i] == h.iloc[i-4:i+5].max(): df.at[i, "ph"] = h.iloc[i]
        if l.iloc[i] == l.iloc[i-4:i+5].min(): df.at[i, "pl"] = l.iloc[i]
    return df

class Bot:
    def __init__(self):
        self.s = load()
        for k, v in {"lb": None, "lPH": None, "lPL": None,
                     "obBHi": None, "obBLo": None, "obSHi": None, "obSLo": None,
                     "mo": None, "day": None, "dt": 0, "act": {}, "mli": {}}.items():
            self.s.setdefault(k, v)
        self.tg = TGBot(token=TOKEN)

    def send(self, m):
        try:
            asyncio.run(self.tg.send_message(chat_id=CHAT, text=m))
            print(f"[TG] {m[:50]}")
        except Exception as e:
            print(f"[TG ERR] {e}")

    def now(self):
        return datetime.now(MOSUL).strftime("%I:%M %p").lstrip("0")

    def sig(self, s):
        ic = "🟢 BUY" if s["is_long"] else "🔴 SELL"
        return (f"{ic} [{s['model']}]\n"
                f"Entry: {s['entry']:.2f}\n"
                f"SL: {s['sl']:.2f}\n"
                f"🎯 TP1: {s['tp1']:.2f}\n"
                f"🎯 🎯 TP2: {s['tp2']:.2f}\n"
                f"🎯 🎯 🎯 TP3: {s['tp3']:.2f}\n"
                f"Points: {s['pts']:.2f}\n"
                f"🕐 {self.now()}")

    def hit(self, a):
        if a["type"] == "SL":
            return f"🛑 SL HIT [{a['model']}]\nPrice: {a['price']:.2f}\n🕐 {self.now()}"
        e = {"TP1": "🎯", "TP2": "🎯 🎯", "TP3": "🎯 🎯 🎯"}[a["type"]]
        return (f"✅ {a['type']} HIT [{a['model']}] {e}\n"
                f"Price: {a['price']:.2f}\n"
                f"Points: {a['pts']:.2f}\n"
                f"🕐 {self.now()}")

    def check_hits(self, bar):
        for m, t in list(self.s["act"].items()):
            il = t["is_long"]
            if il:
                slh = bar["low"]  <= t["sl"];  t1 = bar["high"] >= t["tp1"]
                t2  = bar["high"] >= t["tp2"]; t3 = bar["high"] >= t["tp3"]
            else:
                slh = bar["high"] >= t["sl"];  t1 = bar["low"]  <= t["tp1"]
                t2  = bar["low"]  <= t["tp2"]; t3 = bar["low"]  <= t["tp3"]
            if slh and not t["tp1_hit"]:
                self.send(self.hit({"model": m, "type": "SL", "price": t["sl"]}))
                del self.s["act"][m]; continue
            if t1 and not t["tp1_hit"]:
                t["tp1_hit"] = True
                self.send(self.hit({"model": m, "type": "TP1", "price": t["tp1"], "pts": abs(t["tp1"]-t["entry"])}))
            if t2 and not t["tp2_hit"]:
                t["tp2_hit"] = True
                self.send(self.hit({"model": m, "type": "TP2", "price": t["tp2"], "pts": abs(t["tp2"]-t["entry"])}))
            if t3 and not t["tp3_hit"]:
                t["tp3_hit"] = True
                self.send(self.hit({"model": m, "type": "TP3", "price": t["tp3"], "pts": abs(t["tp3"]-t["entry"])}))
                del self.s["act"][m]

    def fire(self, model, il, e, slb, idx):
        if self.s["dt"] >= 3: return None
        last = self.s["mli"].get(model)
        if last and (idx - last) < 20: return None
        if model in self.s["act"]: return None
        raw = abs(e - slb)
        cl = max(50.0, min(180.0, raw))
        fsl = cl + 20.0
        slv = e - fsl if il else e + fsl
        tp1 = e + max(80.0, fsl) if il else e - max(80.0, fsl)
        tp2 = e + max(120.0, 2.0*fsl) if il else e - max(120.0, 2.0*fsl)
        tp3 = e + max(160.0, 3.0*fsl) if il else e - max(160.0, 3.0*fsl)
        pts = abs(tp1 - e)
        self.s["act"][model] = {"entry": e, "sl": slv, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                                "is_long": il, "pts": pts,
                                "tp1_hit": False, "tp2_hit": False, "tp3_hit": False}
        self.s["mli"][model] = idx
        self.s["dt"] += 1
        return {"model": model, "entry": e, "sl": slv, "tp1": tp1,
                "tp2": tp2, "tp3": tp3, "is_long": il, "pts": pts}

    def run(self, df):
        df = ind(df)
        bar = df.iloc[-2]
        key = str(bar["dt"])
        if self.s["lb"] == key:
            print("[SKIP]"); return
        self.s["lb"] = key
        t = bar["dt"]
        hm = t.hour*100 + t.minute
        am    = 930 <= hm < 1130
        judas = 930 <= hm < 945
        lunch = 1200 <= hm < 1330
        pm    = 1330 <= hm < 1500
        fri   = t.weekday() == 4
        if 0 <= hm < 5: self.s["mo"] = float(bar["open"])
        today = str(t.date())
        if self.s["day"] != today:
            self.s["day"] = today; self.s["dt"] = 0; self.s["act"] = {}
        ph = df["ph"].dropna(); pl = df["pl"].dropna()
        if len(ph): self.s["lPH"] = float(ph.iloc[-1])
        if len(pl): self.s["lPL"] = float(pl.iloc[-1])
        lPH = self.s["lPH"]; lPL = self.s["lPL"]
        if lPH and bar["close"] > lPH and bar["disp"]:
            for i in range(2, 12):
                r = df.iloc[-i]
                if r["close"] < r["open"]:
                    self.s["obBHi"] = float(r["high"]); self.s["obBLo"] = float(r["low"]); break
        if lPL and bar["close"] < lPL and bar["disp"]:
            for i in range(2, 12):
                r = df.iloc[-i]
                if r["close"] > r["open"]:
                    self.s["obSHi"] = float(r["high"]); self.s["obSLo"] = float(r["low"]); break
        self.check_hits(bar)
        mid = self.s["mo"]
        bbh = self.s["obBHi"]; bbl = self.s["obBLo"]
        bsh = self.s["obSHi"]; bsl = self.s["obSLo"]
        ix = len(df)
        sg = []
        if mid and bar["close"] > bar["ema"] and am and bar["close"] > mid and bbh and bar["low"] <= bbh and bar["close"] > bbl:
            r = self.fire("MMBM", True, float(bar["close"]), bbl or lPL, ix)
            if r: sg.append(r)
        if mid and bar["close"] < bar["ema"] and am and bar["close"] < mid and bsl and bar["high"] >= bsl and bar["close"] < bsh:
            r = self.fire("MMSM", False, float(bar["close"]), bsh or lPH, ix)
            if r: sg.append(r)
        if am and mid and bar["low"] < mid and bar["close"] > mid:
            r = self.fire("PO3", True, float(bar["close"]), bbl or lPL, ix)
            if r: sg.append(r)
        if am and mid and bar["high"] > mid and bar["close"] < mid:
            r = self.fire("PO3", False, float(bar["close"]), bsh or lPH, ix)
            if r: sg.append(r)
        if judas:
            rg = bar["high"] - bar["low"]
            su = rg > 0 and (bar["close"] - bar["low"])/rg >= 0.70
            sd = rg > 0 and (bar["high"] - bar["close"])/rg >= 0.70
            if bar["disp"] and bar["close"] > bar["ema"] and mid and bar["close"] > mid and su:
                r = self.fire("Judas", True, float(bar["close"]), bbl or lPL, ix)
                if r: sg.append(r)
            if bar["disp"] and bar["close"] < bar["ema"] and mid and bar["close"] < mid and sd:
                r = self.fire("Judas", False, float(bar["close"]), bsh or lPH, ix)
                if r: sg.append(r)
        if am and bbh and bar["low"] <= bbh and bar["close"] > bbl:
            r = self.fire("SMR", True, float(bar["close"]), bbl or lPL, ix)
            if r: sg.append(r)
        if am and bsl and bar["high"] >= bsl and bar["close"] < bsh:
            r = self.fire("SMR", False, float(bar["close"]), bsh or lPH, ix)
            if r: sg.append(r)
        if fri and pm and bar["disp"]:
            if mid and bar["close"] > mid:
                r = self.fire("TGIF", True, float(bar["close"]), bbl or lPL, ix)
                if r: sg.append(r)
            if mid and bar["close"] < mid:
                r = self.fire("TGIF", False, float(bar["close"]), bsh or lPH, ix)
                if r: sg.append(r)
        if lunch and bbh and bar["close"] > bbh:
            r = self.fire("Lunch", True, float(bar["close"]), bbl or lPL, ix)
            if r: sg.append(r)
        if lunch and bsl and bar["close"] < bsl:
            r = self.fire("Lunch", False, float(bar["close"]), bsh or lPH, ix)
            if r: sg.append(r)
        for s in sg:
            self.send(self.sig(s))
        save(self.s)

def main():
    print(f"[START] {datetime.now(MOSUL)}")
    init_mt5()
    df = fetch()
    b = Bot()
    b.run(df)
    mt5.shutdown()
    print("[DONE]")

if __name__ == "__main__":
    main()