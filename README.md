# ربات نرخ ارز و طلا — دیاپی 💠

انتشار خودکار نرخ **یورو، دلار، طلا و سکه** به تومان در کانال تلگرام `@diapaychanel`.
داده از [navasan.tech](http://navasan.tech) — **فقط وقتی قیمت تغییر کرده باشد** پیام جدید می‌رود.
بدون سرور، روی GitHub Actions رایگان.

---

## فایل‌ها

```
bot.py                          اسکریپت اصلی
state.json                      آخرین قیمت‌ها (خودکار بروز می‌شود)
.github/workflows/rates.yml     زمان‌بندی و تنظیمات
```

## Secrets لازم

Settings → Secrets and variables → Actions

| نام | مقدار |
|---|---|
| `NAVASAN_API_KEY` | کلید از @navasan_contact_bot |
| `TELEGRAM_BOT_TOKEN` | توکن از @BotFather |
| `TELEGRAM_CHAT_ID` | `@diapaychanel` |

همچنین Settings → Actions → General → **Read and write permissions**

## زمان‌بندی فعلی

چهار نوبت در روز، شنبه تا چهارشنبه، به وقت تهران:

```
۱۰:۰۰  ·  ۱۲:۳۰  ·  ۱۵:۰۰  ·  ۱۷:۳۰
```

≈ ۸۸ درخواست در ماه — داخل سهمیه‌ی رایگان نوسان (۱۲۰).

برای تغییر، خطوط `cron` در `rates.yml` را ویرایش کن (زمان‌ها UTC هستند؛ تهران = UTC + ۳:۳۰).

## تنظیمات (بخش `env` در rates.yml)

| متغیر | پیش‌فرض | کار |
|---|---|---|
| `TRIGGER_ITEMS` | `eur,usd` | تغییر کدام آیتم‌ها باعث ارسال شود |
| `MIN_CHANGE_PCT` | `0` | حداقل درصد تغییر برای ارسال |
| `UNIT_DIVISOR` | `1` | اگر قیمت‌ها ۱۰ برابر بزرگ بودند `10` کن |
| `BRAND_EMOJI` | `💠` | ایموجی امضا |
| `BRAND_NAME` | `دیاپی` | نام برند |
| `BRAND_TAGLINE` | `تبدیل ارز بدون مرز` | شعار |
| `BRAND_CONTACT` | `@diapayadmin` | آیدی پشتیبانی |
| `BRAND_LINK` | `@diapaychanel` | آیدی کانال |

هر کدام را `''` بگذاری، آن خط از پیام حذف می‌شود.

## نمونه‌ی پیام

```
📊 نرخ لحظه‌ای ارز و طلا

🇪🇺 یورو
   🔺 ۲۶۶,۰۳۰ تومان  (+۱,۲۰۰)

🇺🇸 دلار آمریکا
   ▪️ ۲۳۰,۶۰۰ تومان

━━━━━━━━━━━━━━
🥇 طلا و سکه
▪️ سکه امامی: ۲۳۴,۰۰۰,۰۰۰ تومان
▪️ نیم‌سکه: ۱۱۹,۰۰۰,۰۰۰ تومان
▪️ طلای ۱۸ عیار (گرم): ۲۳,۵۰۰,۶۲۰ تومان

━━━━━━━━━━━━━━
🕒 ساعت ۱۰:۰۰ به وقت تهران

💠 دیاپی — تبدیل ارز بدون مرز
💬 استعلام و سفارش: @diapayadmin
🔗 @diapaychanel
```

## تست محلی

```bash
DRY_RUN=1 NAVASAN_API_KEY=xxx python3 bot.py     # بدون ارسال
NAVASAN_API_KEY=xxx python3 bot.py --list-keys   # دیدن کلیدهای خام API
```

## رفع اشکال

| خطا | حل |
|---|---|
| `chat not found` | `TELEGRAM_CHAT_ID` غلط است یا یوزرنیم کانال عوض شده |
| `not enough rights` | ربات دسترسی Post Messages ندارد |
| `unauthorized` | توکن ربات اشتباه است |
| پیام تکراری هر بار | `state.json` کامیت نمی‌شود → Workflow permissions را Read and write کن |
| هیچ پیامی نمی‌آید | طبیعی است اگر قیمت تغییر نکرده — لاگ Actions را ببین |
| ورک‌فلو بعد ۶۰ روز خوابید | گیت‌هاب ریپوهای بی‌فعالیت را متوقف می‌کند؛ از تب Actions دوباره Enable کن |

## نکته

یوزرنیم کانال اگر عوض شود ربات می‌خوابد. برای مصونیت، از شناسه‌ی عددی کانال استفاده کن:
`https://api.telegram.org/bot<TOKEN>/getUpdates` → عدد `chat.id` (مثل `-100...`) را در `TELEGRAM_CHAT_ID` بگذار.
