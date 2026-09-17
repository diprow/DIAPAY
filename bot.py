#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات تلگرام نرخ ارز و طلا (منبع: وب‌سرویس نوسان)
- فقط زمانی پیام می‌فرستد که قیمت نسبت به آخرین ارسال تغییر کرده باشد
- هر بار یک پیام جدید در کانال می‌فرستد (تاریخچه حفظ می‌شود)
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- تنظیمات
API_URL = "http://api.navasan.tech/latest/"
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
# فایل عمومی نرخ‌ها برای وب‌اپ (در هر اجرا نوشته می‌شود)
PUBLIC_JSON = os.environ.get("PUBLIC_JSON", "rates.json")

API_KEY = os.environ.get("NAVASAN_API_KEY", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# اگر مقادیر API ریال بود این را 10 بگذارید تا به تومان تبدیل شود
UNIT_DIVISOR = float(os.environ.get("UNIT_DIVISOR", "1"))

# حداقل درصد تغییر برای ارسال پیام (0 یعنی هر تغییری)
MIN_CHANGE_PCT = float(os.environ.get("MIN_CHANGE_PCT", "0"))

# فقط تغییر این آیتم‌ها باعث ارسال پیام می‌شود (بقیه فقط نمایش داده می‌شوند)
TRIGGER_ITEMS = [s.strip() for s in os.environ.get("TRIGGER_ITEMS", "eur,usd").split(",") if s.strip()]

DRY_RUN = os.environ.get("DRY_RUN", "") == "1"

# ---- امضای برند (از ورک‌فلو قابل تغییر است) ----
BRAND_EMOJI   = os.environ.get("BRAND_EMOJI", "💠")
BRAND_NAME    = os.environ.get("BRAND_NAME", "دیاپی")
BRAND_TAGLINE = os.environ.get("BRAND_TAGLINE", "تبدیل ارز بدون مرز")
BRAND_CONTACT = os.environ.get("BRAND_CONTACT", "@diapayadmin")
BRAND_LINK    = os.environ.get("BRAND_LINK", "@diapaychanel")

# نام‌های احتمالی هر آیتم در پاسخ API (اولین کلید موجود استفاده می‌شود)
# (شناسه, عنوان, ایموجی, [کلیدهای خرید], [کلیدهای فروش], ضریب واحد)
# ضریب ۱۰۰۰ برای آیتم‌هایی که نوسان به «هزار تومان» می‌دهد
SPEC = [
    ("eur",      "یورو",              "🇪🇺", ["eur"],       ["eur"],       1),
    ("usd",      "دلار آمریکا",       "🇺🇸", ["usd_buy"],   ["usd_sell"],  1),
    ("sekkeh",   "سکه امامی",         "🪙", ["sekkeh"],    ["sekkeh"],    1000),
    ("bahar",    "سکه بهار آزادی",    "🪙", ["bahar"],     ["bahar"],     1000),
    ("nim",      "نیم‌سکه",            "🪙", ["nim"],       ["nim"],       1000),
    ("rob",      "ربع‌سکه",            "🪙", ["rob"],       ["rob"],       1000),
    ("gerami",   "سکه گرمی",          "🪙", ["gerami"],    ["gerami"],    1000),
    ("18ayar",   "طلای ۱۸ عیار (گرم)", "🥇", ["18ayar"],    ["18ayar"],    1),
    ("abshodeh", "مثقال طلا (آبشده)", "🥇", ["abshodeh"],  ["abshodeh"],  1000),
]

GOLD_ORDER = ["sekkeh", "bahar", "nim", "rob", "gerami", "18ayar", "abshodeh"]

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# ---------------------------------------------------------------- ابزارها
def fa_num(n, decimals=0):
    """عدد را با جداکننده هزارگان و ارقام فارسی برمی‌گرداند."""
    try:
        s = f"{float(n):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"
    return s.translate(FA_DIGITS)


def to_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def pick(data, keys):
    """اولین کلید موجود از لیست را برمی‌گرداند."""
    for k in keys:
        node = data.get(k)
        if isinstance(node, dict) and to_float(node.get("value")) is not None:
            return k, node
    return None, None


def http_get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "navasan-telegram-bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- دریافت داده
def fetch_rates():
    if not API_KEY:
        sys.exit("خطا: NAVASAN_API_KEY تنظیم نشده است.")
    url = API_URL + "?" + urllib.parse.urlencode({"api_key": API_KEY})
    data = http_get_json(url)
    if not isinstance(data, dict) or not data:
        sys.exit(f"پاسخ نامعتبر از API: {data}")
    if "error" in data or "status" in data:
        sys.exit(f"خطای API نوسان: {data}")
    return data


def build_snapshot(data):
    """از پاسخ خام، دیکشنری تمیزی از آیتم‌های موجود می‌سازد."""
    snap = {}
    for item_id, title, emoji, buy_keys, sell_keys, mult in SPEC:
        bk, bnode = pick(data, buy_keys)
        sk, snode = pick(data, sell_keys)
        if bnode is None and snode is None:
            continue
        node = snode or bnode          # نرخ فروش نمایش داده می‌شود
        scale = mult / UNIT_DIVISOR
        buy = to_float(bnode["value"]) * scale if bnode else None
        sell = to_float(snode["value"]) * scale if snode else None
        snap[item_id] = {
            "title": title,
            "emoji": emoji,
            "buy": buy,
            "sell": sell,
            "single": bk == sk,
            "change": (to_float(node.get("change")) or 0.0) * scale,
            "date": node.get("date", ""),
        }
    return snap


# ---------------------------------------------------------------- وضعیت
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(snap):
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "values": {k: {"buy": v["buy"], "sell": v["sell"]} for k, v in snap.items()},
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def changed_since_last(snap, state):
    """آیا آیتم‌های موردنظر تغییر کرده‌اند؟ خروجی: (bool, دیکشنری دلتاها)"""
    old = (state or {}).get("values", {})
    if not old:
        return True, {}          # اولین اجرا → همیشه ارسال

    deltas = {}
    triggered = False
    for item_id, cur in snap.items():
        prev = old.get(item_id)
        if not prev:
            if item_id in TRIGGER_ITEMS:
                triggered = True
            continue
        for side in ("buy", "sell"):
            a, b = prev.get(side), cur.get(side)
            if a is None or b is None:
                continue
            diff = b - a
            if diff:
                deltas.setdefault(item_id, {})[side] = diff
                pct = abs(diff) / a * 100 if a else 100
                if item_id in TRIGGER_ITEMS and pct >= MIN_CHANGE_PCT:
                    triggered = True
    return triggered, deltas


# ---------------------------------------------------------------- خروجی عمومی برای سایت
def write_public_json(snap):
    """rates.json را برای وب‌اپ می‌نویسد — در هر اجرا، چه پیام برود چه نرود."""
    now_utc = datetime.now(timezone.utc)
    teh = tehran_now()
    items = []
    for item_id in ["eur", "usd"] + GOLD_ORDER:
        d = snap.get(item_id)
        if not d:
            continue
        value = d["sell"] if d["sell"] is not None else d["buy"]
        if value is None:
            continue
        items.append({
            "id": item_id,
            "title": d["title"],
            "emoji": d["emoji"],
            "group": "currency" if item_id in ("eur", "usd") else "gold",
            "value": round(value),
            "change": round(d["change"] or 0),
        })
    api_date = next((d["date"] for d in snap.values() if d.get("date")), "")
    payload = {
        "updated_iso": now_utc.replace(microsecond=0).isoformat(),
        "updated_fa": teh.strftime("%H:%M"),
        "updated_date": api_date.split(" ")[0] if api_date else "",
        "currency": "toman",
        "source": "navasan.tech",
        "items": items,
    }
    with open(PUBLIC_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"{PUBLIC_JSON} نوشته شد ({len(items)} آیتم).")


# ---------------------------------------------------------------- ساخت پیام
def arrow(change):
    if change > 0:
        return "🔺"
    if change < 0:
        return "🔻"
    return "▪️"


def fmt_change(change):
    if not change:
        return "بدون تغییر"
    sign = "+" if change > 0 else "−"
    return f"{arrow(change)} {sign}{fa_num(abs(change))}"


def tehran_now():
    return datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)


def build_message(snap, deltas):
    now = tehran_now()
    lines = ["📊 <b>نرخ لحظه‌ای ارز و طلا</b>", ""]

    def price_line(item_id, d, indent=True):
        val = d["sell"] if d["sell"] is not None else d["buy"]
        step = (deltas.get(item_id) or {}).get("sell") or (deltas.get(item_id) or {}).get("buy")
        mark = arrow(step) if step else arrow(d["change"])
        tail = ""
        if step:
            sign = "+" if step > 0 else "−"
            tail = f"  <i>({sign}{fa_num(abs(step))})</i>"
        pad = "   " if indent else ""
        return f"{pad}{mark} <code>{fa_num(val)}</code> تومان{tail}"

    # ارزها
    for item_id in ("eur", "usd"):
        d = snap.get(item_id)
        if not d:
            continue
        lines.append(f"{d['emoji']} <b>{d['title']}</b>")
        lines.append(price_line(item_id, d))
        lines.append("")

    # طلا و سکه
    gold = [i for i in GOLD_ORDER if i in snap]
    if gold:
        lines.append("━━━━━━━━━━━━━━")
        lines.append("🥇 <b>طلا و سکه</b>")
        for item_id in gold:
            d = snap[item_id]
            val = d["sell"] if d["sell"] is not None else d["buy"]
            step = (deltas.get(item_id) or {}).get("sell") or (deltas.get(item_id) or {}).get("buy")
            mark = arrow(step) if step else arrow(d["change"])
            lines.append(f"{mark} {d['title']}: <code>{fa_num(val)}</code> تومان")
        lines.append("")

    clock = f"{now.hour:02d}:{now.minute:02d}".translate(FA_DIGITS)
    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"🕒 ساعت {clock} به وقت تهران")

    # امضای برند
    if BRAND_NAME:
        lines.append("")
        sig = f"{BRAND_EMOJI} <b>{BRAND_NAME}</b>"
        if BRAND_TAGLINE:
            sig += f" — <i>{BRAND_TAGLINE}</i>"
        lines.append(sig)
        if BRAND_CONTACT:
            lines.append(f"💬 استعلام و سفارش: {BRAND_CONTACT}")
        if BRAND_LINK:
            lines.append(f"🔗 {BRAND_LINK}")

    return "\n".join(lines)


# ---------------------------------------------------------------- تلگرام
def _tg_call(text, parse_mode="HTML"):
    """یک درخواست به تلگرام. خروجی: (ok, پاسخ یا متن خطا)"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    fields = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        fields["parse_mode"] = parse_mode
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode())
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return True, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            desc = body.get("description", "")
        except Exception:
            desc = f"HTTP {e.code}"
        return False, desc
    except Exception as e:
        return False, str(e)


def strip_tags(text):
    return re.sub(r"</?(b|i|u|s|code|pre|a)[^>]*>", "", text)


def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        sys.exit("خطا: TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID تنظیم نشده است.")

    ok, res = _tg_call(text, "HTML")
    if ok:
        return res

    print(f"⚠️ تلگرام پیام را با HTML نپذیرفت: {res}")

    # اگر ایراد از قالب‌بندی بود، بدون HTML دوباره امتحان کن
    if "entit" in str(res).lower() or "parse" in str(res).lower() or "tag" in str(res).lower():
        print("↩️ تلاش دوباره بدون قالب‌بندی HTML...")
        ok2, res2 = _tg_call(strip_tags(text), None)
        if ok2:
            print("✅ پیام بدون قالب‌بندی ارسال شد.")
            return res2
        res = res2

    # راهنمای خطاهای رایج
    hints = {
        "chat not found":   "شناسه‌ی کانال (TELEGRAM_CHAT_ID) اشتباه است یا ربات ادمین کانال نیست.",
        "bot was blocked":  "ربات از کانال حذف یا بلاک شده است.",
        "not enough rights":"ربات دسترسی Post Messages در کانال ندارد.",
        "unauthorized":     "توکن ربات (TELEGRAM_BOT_TOKEN) اشتباه است.",
        "chat_id is empty": "TELEGRAM_CHAT_ID خالی است.",
    }
    low = str(res).lower()
    for k, v in hints.items():
        if k in low:
            sys.exit(f"ارسال ناموفق: {res}\n👈 {v}")

    sys.exit(f"ارسال به تلگرام ناموفق بود: {res}")


# ---------------------------------------------------------------- ارسال دستی
def run_manual(path):
    """
    نرخ‌های دستی (از manual.json) را در کانال می‌فرستد و روی سایت می‌گذارد.
    مبنای بقیه‌ی آیتم‌ها آخرین rates.json است؛ به API نوسان درخواستی نمی‌زند.
    state.json تغییر نمی‌کند تا ربات ساعتی مثل قبل با آخرین نرخ خودکار مقایسه کند.
    """
    with open(path, encoding="utf-8") as f:
        manual = json.load(f)
    try:
        with open(PUBLIC_JSON, encoding="utf-8") as f:
            base = json.load(f)
    except (OSError, ValueError):
        sys.exit(f"{PUBLIC_JSON} پیدا نشد؛ اول یک بار ربات خودکار را اجرا کنید.")

    snap, deltas = {}, {}
    for it in base.get("items", []):
        snap[it["id"]] = {"title": it["title"], "emoji": it["emoji"], "buy": it["value"],
                          "sell": it["value"], "single": True, "change": it.get("change", 0), "date": ""}
    rates = manual.get("rates", manual)
    applied = {}
    for k, v in rates.items():
        if k not in snap:
            continue
        new = to_float(v)
        if new is None:
            continue
        diff = new - snap[k]["sell"]
        snap[k]["buy"] = snap[k]["sell"] = new
        snap[k]["change"] = diff
        if diff:
            deltas[k] = {"sell": diff}
        applied[k] = new
    if not applied:
        sys.exit(f"هیچ نرخ معتبری در {path} نبود.")

    write_public_json(snap)
    with open(PUBLIC_JSON, encoding="utf-8") as f:
        pub = json.load(f)
    pub["manual"] = True
    with open(PUBLIC_JSON, "w", encoding="utf-8") as f:
        json.dump(pub, f, ensure_ascii=False, indent=2)

    if manual.get("post", True):
        msg = build_message(snap, deltas)
        if DRY_RUN:
            print("--- DRY RUN ---")
            print(msg)
        else:
            send_telegram(msg)
            print("پیام دستی با موفقیت ارسال شد.")
    print("نرخ‌های دستی اعمال شد:", applied)


# ---------------------------------------------------------------- اجرا
def main():
    if "--manual" in sys.argv:
        run_manual(sys.argv[sys.argv.index("--manual") + 1])
        return

    if "--list-keys" in sys.argv:
        print(json.dumps(fetch_rates(), ensure_ascii=False, indent=2))
        return

    if "--sample" in sys.argv:          # تست آفلاین با داده نمونه
        with open(sys.argv[sys.argv.index("--sample") + 1], encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = fetch_rates()

    snap = build_snapshot(data)
    if not snap:
        sys.exit("هیچ آیتم شناخته‌شده‌ای در پاسخ API پیدا نشد. با --list-keys کلیدها را ببینید.")

    write_public_json(snap)

    state = load_state()
    triggered, deltas = changed_since_last(snap, state)

    if not triggered:
        print("قیمت تغییری نکرده — پیامی ارسال نشد.")
        return

    msg = build_message(snap, deltas)

    if DRY_RUN:
        print("--- DRY RUN ---")
        print(msg)
    else:
        send_telegram(msg)
        print("پیام با موفقیت ارسال شد.")

    save_state(snap)


if __name__ == "__main__":
    main()
