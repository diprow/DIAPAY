#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ارسال نوتیف وب‌اپ دیاپی به همه‌ی مشترک‌ها
ورودی: notify.json  →  {"title": "...", "body": "...", "url": "./#rates", "tag": "diapay"}
"""
import json, os, sys, urllib.request, urllib.error
from pywebpush import webpush, WebPushException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SENDER_SECRET = os.environ.get("PUSH_SENDER_SECRET", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUB = os.environ.get("VAPID_SUBJECT", "mailto:dyko.moradi@gmail.com")
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"


def rpc(name, payload):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{name}", method="POST",
        data=json.dumps(payload).encode(),
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        sys.exit(f"خطای پایگاه داده ({name}): {e.code} {e.read().decode()[:300]}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "notify.json"
    with open(path, encoding="utf-8") as f:
        msg = json.load(f)
    if not msg.get("body"):
        sys.exit("متن نوتیف (body) خالی است.")
    for k, v in {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY,
                 "PUSH_SENDER_SECRET": SENDER_SECRET, "VAPID_PRIVATE_KEY": VAPID_PRIVATE}.items():
        if not v:
            sys.exit(f"تنظیم نشده: {k}")

    payload = json.dumps({
        "title": msg.get("title") or "دیاپی",
        "body": msg["body"],
        "url": msg.get("url") or "./",
        "tag": msg.get("tag") or "diapay",
    }, ensure_ascii=False)

    subs = rpc("diapay_list_subscriptions", {"p_secret": SENDER_SECRET}) or []
    print(f"تعداد مشترک‌ها: {len(subs)}")
    sent, dead, failed = 0, [], 0
    for s in subs:
        info = {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
        if DRY_RUN:
            sent += 1
            continue
        try:
            webpush(info, payload, vapid_private_key=VAPID_PRIVATE,
                    vapid_claims={"sub": VAPID_SUB}, ttl=6 * 3600, timeout=20)
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):
                dead.append(s["endpoint"])       # اشتراک منقضی/لغوشده
            else:
                failed += 1
                print(f"خطا ({code}): {str(e)[:200]}")
        except Exception as e:                    # خطای شبکه و…
            failed += 1
            print(f"خطا: {str(e)[:200]}")

    if dead:
        n = rpc("diapay_remove_subscriptions", {"p_secret": SENDER_SECRET, "p_endpoints": dead})
        print(f"اشتراک‌های منقضی حذف شد: {n}")
    print(f"ارسال موفق: {sent} · ناموفق: {failed} · منقضی: {len(dead)}")


if __name__ == "__main__":
    main()
