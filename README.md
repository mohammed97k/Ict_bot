# ICT 8 Independent Models — Trading Bot

بوت تداول آلي مبني على 8 نماذج ICT مستقلة، مخصص لـ **NAS100** على فريم **5 دقائق**.

## 📊 النتائج المتوقعة

| النموذج | نسبة النجاح |
|---------|-------------|
| MMBM    | 88.9%       |
| SMR     | 66.7%       |
| PO3     | 75.0%       |
| Judas   | 60.0%       |
| Turtle  | 100%        |
| TGIF    | 100%        |
| Lunch   | 100%        |
| **الإجمالي** | **75.6%** |

## 🚀 التنصيب

### 1. الاستنساخ
```bash
git clone https://github.com/YOUR_USERNAME/ict-trading-bot.git
cd ict-trading-bot
```

### 2. المتطلبات
```bash
pip install -r requirements.txt
```

### 3. الإعداد
```bash
cp .env.example .env
# عبّئ القيم
```

### 4. التشغيل
```bash
python main.py --once   # دورة واحدة
python main.py          # حلقة مستمرة
```

## 🤖 GitHub Actions

1. **Settings → Secrets → Actions**
2. أضف:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `TWELVEDATA_API_KEY`
   - `TWELVEDATA_TICKER` (NDX)
   - `KIT_API_KEY`
   - `KIT_API_SECRET`
   - `KIT_BASE_URL`
   - `KIT_SYMBOL` (NAS100)
3. **Actions → Enable workflows**

البوت يعمل تلقائياً كل 5 دقائق خلال ساعات السوق.

## 📋 الحصول على المفاتيح

### Telegram
1. `@BotFather` → `/newbot`
2. انسخ Token
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` → Chat ID

### TwelveData
1. سجّل في [twelvedata.com](https://twelvedata.com)
2. اختر خطة **Grow** (29$/شهر) لبيانات NAS100 التاريخية
3. انسخ API Key

## ⚠️ تحذير

لأغراض **تعليمية** فقط. التداول الحقيقي يحمل مخاطر.
استخدم **حساب تجريبي** لأسبوعين أولاً.

## 📜 الرخصة

MIT
