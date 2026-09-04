# -*- coding: utf-8 -*-
"""
sync_prices.py
همگام‌سازی سبک، امن و ۲ ساعته قیمت‌ها و وضعیت موجودی کالاها (زیر ۱ ثانیه).
بدون نیاز به اسکرپ HTML و کاملاً مستقیم از منبع زنده JSON.
"""

import urllib.request
import ssl
import json
import os
import sqlite3
import time

LIVE_JSON_URL = "https://momtazkalla.com/wp-content/uploads/procache-live/live-data.json"
CATALOG_FILE = "catalog_products.json"
DB_FILE = "bot_data.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def update_live_prices():
    """
    دریافت فایل کم‌حجم JSON زنده و به‌روزرسانی آنی قیمت و وضعیت در:
    1. فایل کاتالوگ پایه (catalog_products.json)
    2. دیتابیس SQLite ربات
    """
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] شروع بررسی قیمت‌های زنده...")
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        req = urllib.request.Request(LIVE_JSON_URL, headers=HEADERS)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            live_data = json.loads(resp.read().decode('utf-8', errors='ignore'))
    except Exception as e:
        print("خطا در دریافت فایل قیمت زنده:", e)
        return False

    items = live_data.get("i", {})
    if not items:
        print("هیچ آیتمی در فایل قیمت لایو یافت نشد.")
        return False

    # 1. به‌روزرسانی فایل کاتالوگ در صورت وجود
    catalog = {}
    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except Exception as e:
            print("خطا در خواندن فایل کاتالوگ:", e)

    updated_count = 0
    for pid, live_info in items.items():
        # d: قیمت به تومان
        # s: وضعیت (b: موجود، o: ناموجود، i: استعلام تلفنی)
        new_price = live_info.get("d", 0)
        new_status = live_info.get("s", "b")

        if pid in catalog:
            if catalog[pid].get("price") != new_price or catalog[pid].get("status") != new_status:
                catalog[pid]["price"] = new_price
                catalog[pid]["status"] = new_status
                updated_count += 1

    if updated_count > 0 and catalog:
        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)
        print(f"✅ قیمت و وضعیت {updated_count} محصول در کاتالوگ به‌روزرسانی شد.")
    else:
        print("اطلاعات کاتالوگ از قبل به‌روز بود.")

    # 2. همگام‌سازی با دیتابیس ربات (در صورت وجود جدول products)
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # بررسی وجود جدول
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products';")
        if cursor.fetchone():
            db_updates = 0
            for pid, live_info in items.items():
                p = live_info.get("d", 0)
                s = live_info.get("s", "b")
                cursor.execute(
                    "UPDATE products SET price = ?, status = ? WHERE product_id = ? OR data_id = ?",
                    (p, s, pid, pid)
                )
                if cursor.rowcount > 0:
                    db_updates += cursor.rowcount
            conn.commit()
            if db_updates > 0:
                print(f"✅ قیمت‌های دیتابیس ربات نیز برای {db_updates} ردیف آپدیت شدند.")
        conn.close()
    except Exception as e:
        print("اطلاع دیتابیس:", e)

    return True

if __name__ == "__main__":
    update_live_prices()
