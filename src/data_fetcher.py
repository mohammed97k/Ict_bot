import requests
import pandas as pd
from config.settings import TWELVEDATA_API_KEY


def fetch_bars(ticker="NDX", interval="5min", outputsize=5000):
    """
    جلب شموع من TwelveData بتوقيت نيويورك.
    
    Args:
        ticker: رمز الأصل (NDX, QQQ, ...)
        interval: 1min, 5min, 15min, 1h
        outputsize: عدد الشموع (حد أقصى 5000)
    
    Returns:
        DataFrame مع الأعمدة: open, high, low, close, volume
    """
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": ticker,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVEDATA_API_KEY,
        "timezone": "America/New_York",
        "order": "ASC",
    }

    r = requests.get(url, params=params, timeout=20).json()

    if r.get("status") == "error" or "values" not in r:
        raise RuntimeError(f"TwelveData error: {r.get('message', r)}")

    df = pd.DataFrame(r["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.rename(columns={"datetime": "time"})
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.set_index("time").sort_index()
    return df[["open", "high", "low", "close", "volume"]]
