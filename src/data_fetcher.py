import yfinance as yf
import pandas as pd


def fetch_bars(ticker="^NDX", interval="5m", outputsize=5000):
    """
    جلب شموع من Yahoo Finance.
    
    Ticker:
        ^NDX = Nasdaq 100 Index
        ^DJI = Dow Jones
    Interval:
        1m, 5m, 15m, 30m, 1h
    """
    # yfinance يقبل الفترات المحددة فقط
    period = "60d" if interval == "5m" else "30d"
    
    df = yf.download(
        tickers=ticker,
        interval=interval,
        period=period,
        auto_adjust=False,
        progress=False,
    )
    
    if df is None or len(df) == 0:
        raise RuntimeError(f"No data for {ticker}")
    
    # تنظيف الأعمدة
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"adj close": "adjclose"})
    
    # احتفظ بالأعمدة المطلوبة فقط
    keep = ["open", "high", "low", "close", "volume"]
    df = df[[c for c in keep if c in df.columns]]
    
    # المنطقة الزمنية
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("America/New_York")
    
    df = df.dropna()
    return df.tail(outputsize)