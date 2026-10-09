import requests
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(text):
    """إرسال رسالة إلى تيليجرام."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM] Not configured — skipping")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[TELEGRAM] {r.status_code} — {r.text}")
            return False
        return True
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False


def format_trade_alert(sig):
    """تنسيق إشارة صفقة جديدة."""
    side = "🟢 BUY" if sig["side"] == "BUY" else "🔴 SELL"
    return (
        f"<b>{side} [{sig['model']}]</b>\n"
        f"Entry: {sig['entry']:.2f}\n"
        f"SL: {sig['sl']:.2f}\n"
        f"TP1: {sig['tp1']:.2f}\n"
        f"TP2: {sig['tp2']:.2f}\n"
        f"TP3: {sig['tp3']:.2f}\n"
        f"Time: {sig['time']}"
    )


def format_close_alert(tr):
    """تنسيق إغلاق صفقة."""
    result = "✅ WIN" if tr["hits"] >= 1 else "❌ LOSS"
    return (
        f"<b>{result} [{tr['model']}]</b>\n"
        f"Hits: {tr['hits']}/3\n"
        f"Entry: {tr['entry']:.2f}"
    )
