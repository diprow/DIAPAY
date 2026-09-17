#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ربات تلگرام نرخ ارز و طلا (منبع: وب‌سرویس نوسان)
- فقط زمانی پیام می‌فرستد که قیمت نسبت به آخرین ارسال تغییر کرده باشد
- هر بار یک پیام جدید در کانال می‌فرستد (تاریخچه حفظ می‌شود)
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- تنظیمات
API_URL = "http://api.navasan.tech/latest/"
STATE_FILE = os.environ.get("STATE_FILE", "state.json")

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
BRAND_LINK    = os.environ.get("BRAND_LINK", "@diapayit")

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
        node = bnode or snode
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
def send_telegram(text):
    if not BOT_TOKEN or not CHAT_ID:
        sys.exit("خطا: TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID تنظیم نشده است.")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(req, timeout=25) as r:
        res = json.loads(r.read().decode("utf-8"))
    if not res.get("ok"):
        sys.exit(f"ارسال به تلگرام ناموفق بود: {res}")
    return res


# ---------------------------------------------------------------- اجرا
def main():
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
