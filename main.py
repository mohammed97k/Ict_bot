"""
ICT 8 Independent Models — Live Trader
========================================
- NAS100 / NDX
- فريم 5 دقائق
- 8 نماذج مستقلة
"""

import time
import sys
from datetime import datetime

from config.settings import TWELVEDATA_TICKER, TIMEFRAME
from src.data_fetcher import fetch_bars
from src.strategy import ICTStrategy
from src.telegram_notifier import (
    send_telegram, format_trade_alert, format_close_alert
)
from src.kit_executor import execute_trade
from src.state import load_state, save_state


def run_once():
    """دورة واحدة — تفتح صفقات جديدة فقط."""
    print("=" * 50)
    print(f"🕐 Run at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. تحميل الحالة السابقة
    state = load_state()
    last_processed_time = state.get("last_processed_time")
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

    # ═══════════════════════════════════════════════════════
    #  ⚠️ الإصلاح الجوهري: معالجة الشموع الجديدة فقط
    # ═══════════════════════════════════════════════════════
    df_closed = df.iloc[:-1]  # بدون الشمعة الجارية

    if last_processed_time:
        last_dt = datetime.fromisoformat(last_processed_time)
        new_bars = df_closed[df_closed.index > last_dt]
        if len(new_bars) == 0:
            print("[INFO] No new bars since last run")
            save_state({**strategy.to_state(), "last_processed_time": last_processed_time})
            return
        print(f"🆕 New bars: {len(new_bars)}")
    else:
        # أول تشغيل: آخر 20 شمعة فقط (لا نفتح صفقات تاريخية)
        new_bars = df_closed.iloc[-20:]
        print(f"[FIRST RUN] Processing last {len(new_bars)} bars only")

    # 4. نجمع السياق الكامل + نعالج الشموع الجديدة
    #    (لاستخراج Pivots و FVG بشكل صحيح، نحتاج التاريخ)
    combined = df_closed.iloc[-200:] if len(df_closed) > 200 else df_closed

    # 5. حذف إشارات التاريخ: نعالج فقط الشموع الجديدة
    signals = strategy.process_new(combined, new_bars.index[0])

    # 6. إرسال الإشارات الجديدة
    for sig in signals:
        msg = format_trade_alert(sig)
        send_telegram(msg)
        execute_trade(sig)
        print(msg)

    if not signals:
        print("[INFO] No new signals")

    # 7. حفظ الحالة + آخر وقت معالج
    new_state = strategy.to_state()
    new_state["last_processed_time"] = str(df_closed.index[-1])
    save_state(new_state)

    print(f"✅ Done | Daily trades: {strategy.daily_trades}")


def run_loop(interval_sec=30):
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