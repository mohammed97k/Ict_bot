"""
ICT 8 Independent Models — Live Trader
========================================
- NAS100 فقط
- فريم 5 دقائق
- 8 نماذج مستقلة
- إشعارات تيليجرام + تنفيذ KiT Hub

التشغيل:
    python main.py --once      # دورة واحدة (لـ GitHub Actions)
    python main.py             # حلقة مستمرة (محلياً)
"""

import time
import sys

from config.settings import TWELVEDATA_TICKER, TIMEFRAME
from src.data_fetcher import fetch_bars
from src.strategy import ICTStrategy
from src.telegram_notifier import (
    send_telegram, format_trade_alert, format_close_alert
)
from src.kit_executor import execute_trade
from src.state import load_state, save_state


def run_once():
    """دورة واحدة — تُستخدم من GitHub Actions أو Cron."""
    print("=" * 50)
    print(f"🕐 Run started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. تحميل الحالة
    state = load_state()
    strategy = ICTStrategy(state=state)

    # 2. جلب البيانات
    try:
        df = fetch_bars(TWELVEDATA_TICKER, TIMEFRAME)
    except Exception as e:
        print(f"[FETCH ERROR] {e}")
        return

    print(f"📊 Loaded {len(df)} bars | Last: {df.index[-1]}")

    if len(df) < 50:
        print("[INFO] Not enough bars")
        return

    # 3. تحديث الصفقات المفتوحة أولاً
    closed = strategy.update(df)
    for tr in closed:
        msg = format_close_alert(tr)
        send_telegram(msg)
        print(msg)

    # 4. معالجة الشموع المكتملة (بدون الأخيرة الجارية)
    df_closed = df.iloc[:-1]
    signals = strategy.process(df_closed)

    # 5. إرسال الإشارات الجديدة
    for sig in signals:
        msg = format_trade_alert(sig)
        send_telegram(msg)
        execute_trade(sig)
        print(msg)

    if not signals and not closed:
        print("[INFO] No new signals")

    # 6. حفظ الحالة
    save_state(strategy.to_state())
    print(f"✅ Run completed | Daily trades: {strategy.daily_trades}")


def run_loop(interval_sec=30):
    """حلقة مستمرة — للتشغيل المحلي."""
    print("🚀 ICT 8 Models — Live Trader Started")
    while True:
        try:
            run_once()
            print(f"💤 Sleeping {interval_sec}s...\n")
            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n⛔ Stopped by user")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(60)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()
