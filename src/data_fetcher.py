import requests
import pandas as pd
from datetime import datetime, timedelta
from config.settings import TWELVEDATA_API_KEY, LOOKBACK_DAYS, NY_TZ


def fetch_bars(ticker="NDX", interval="5min", lookback_days=None):
    """جلب شموع من TwelveData بتوقيت نيويورك."""
    if lookback_days is None:
        lookback_days = LOOKBACK_DAYS

    # TwelveData يقبل outputsize بحد أقصى 5000
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": ticker,
        "interval": interval,
        "outputsize": 5000,
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
