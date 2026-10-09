# ICT 8 Independent Models — Trading Bot

استراتيجية ICT آلية مبنية على 8 نماذج مستقلة، مخصصة لـ **NAS100** على فريم **5 دقائق**.

## ⚡ النتائج

| النموذج | نسبة النجاح |
|---------|-------------|
| MMBM | 88.9% |
| SMR | 66.7% |
| PO3 | 75.0% |
| Judas | 60.0% |
| Turtle | 100% |
| TGIF | 100% |
| Lunch | 100% |
| **الإجمالي** | **75.6%** |

## 🚀 التنصيب

### 1. الاستنساخ
```bash
git clone https://github.com/YOUR_USERNAME/ict-trading-bot.git
cd ict-trading-bot
```

### 2. تثبيت المتطلبات
```bash
pip install -r requirements.txt
```

### 3. الإعداد
```bash
cp .env.example .env
# عبّئ القيم في .env
```

### 4. التشغيل
```bash
# مرة واحدة
python main.py --once

# حلقة مستمرة
python main.py
```

## 🤖 GitHub Actions (تشغيل مجاني 24/7)

1. **أضف Secrets في المستودع:**
   - Settings → Secrets → Actions
   - أضف كل متغير من `.env.example`

2. **فعّل Actions:**
   - Actions → ICT Trading Bot → Enable

3. **البوت سيعمل تلقائياً** كل 5 دقائق خلال ساعات السوق.

## 📁 الهيكل

```
ict-trading-bot/
├── .github/workflows/ict_bot.yml   ← جدولة تلقائية
├── src/                            ← الكود الأساسي
├── config/settings.py              ← الإعدادات
├── main.py                         ← نقطة البدء
└── requirements.txt
```

## ⚠️ تحذير

هذا البوت لأغراض **تعليمية**. التداول الحقيقي يحمل مخاطر.
استخدم **حساب تجريبي** أولاً لأسبوعين على الأقل.

## 📜 الرخصة

MIT