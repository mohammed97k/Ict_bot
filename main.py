"""
ICT 8 Independent Models — Live Trader
========================================
- NAS100 فقط
- فريم 5 دقائق
- 8 نماذج مستقلة
- إشعارات تيليجرام
"""

import time
import sys
from config.settings import POLYGON_TICKER, TIMEFRAME
from src.data_fetcher import fetch_bars
from src.strategy import ICTStrategy
from src.telegram_notifier import send_telegram, format_trade_alert, format_close_alert
from src.kit_executor import execute_trade
from src.state import load_state, save_state


def run_once():
    """دورة واحدة — تُستخدم من GitHub Actions أو Cron."""
    state = load_state()
    strategy = ICTStrategy(state=state)

    df = fetch_bars(POLYGON_TICKER, TIMEFRAME)
    if len(df) < 50:
        print("[INFO] Not enough bars")
        return

    # تحديث الصفقات المفتوحة
    closed = strategy.update(df)
    for tr in closed:
        msg = format_close_alert(tr)
        send_telegram(msg)
        print(msg)

    # معالجة آخر شمعة مكتملة
    signals = strategy.process(df.iloc[:-1])
    for sig in signals:
        msg = format_trade_alert(sig)
        send_telegram(msg)
        execute_trade(sig)
        print(msg)

    # حفظ الحالة
    save_state(strategy.to_state())


def run_loop(interval_sec=30):
    """حلقة مستمرة — تُستخدم عند تشغيل السكربت محلياً."""
    print("🚀 ICT 8 Models — Live Trader Started")
    while True:
        try:
            run_once()
            time.sleep(interval_sec)
        except KeyboardInterrupt:
            print("\n⛔ Stopped")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(60)


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        run_loop()