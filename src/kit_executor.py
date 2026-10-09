import requests
from config.settings import KIT_API_KEY, KIT_BASE_URL, KIT_SYMBOL


def execute_trade(sig):
    """إرسال أمر إلى KiT Hub — عدّل حسب التوثيق."""
    if not KIT_API_KEY:
        print("[KIT] Not configured — skipping")
        return None

    headers = {
        "Authorization": f"Bearer {KIT_API_KEY}",
        "Content-Type": "application/json",
    }
    order = {
        "symbol": KIT_SYMBOL,
        "side": "buy" if sig["side"] == "BUY" else "sell",
        "order_type": "market",
        "quantity": 1,
        "stop_loss": sig["sl"],
        "take_profit": sig["tp1"],
    }
    try:
        r = requests.post(f"{KIT_BASE_URL}/v1/orders", json=order, headers=headers, timeout=10)
        print(f"[KIT] {r.status_code} — {r.text}")
        return r.json()
    except Exception as e:
        print(f"[KIT ERROR] {e}")
        return None