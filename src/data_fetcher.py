import requests
import pandas as pd
from datetime import datetime, timedelta
from config.settings import POLYGON_API_KEY, LOOKBACK_DAYS, NY_TZ


def fetch_bars(ticker="NDX", interval="5min", lookback_days=None):
    """جلب شموع من Polygon.io بتوقيت نيويورك."""
    if lookback_days is None:
        lookback_days = LOOKBACK_DAYS

    end = datetime.utcnow()
    start = end - timedelta(days=lookback_days)

    mult, unit = _parse_interval(interval)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{mult}/{unit}/"
        f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
        f"?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_API_KEY}"
    )

    r = requests.get(url, timeout=15).json()
    if "results" not in r:
        raise RuntimeError(f"Polygon error: {r}")

    df = pd.DataFrame(r["results"])
    df["time"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(NY_TZ)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df = df[["time", "open", "high", "low", "close", "volume"]].set_index("time")
    return df


def _parse_interval(interval):
    """5min → (5, 'minute'), 1h → (1, 'hour')."""
    if interval.endswith("min"):
        return int(interval[:-3]), "minute"
    if interval.endswith("h"):
        return int(interval[:-1]), "hour"
    if interval.endswith("day"):
        return 1, "day"
    raise ValueError(f"Unknown interval: {interval}")