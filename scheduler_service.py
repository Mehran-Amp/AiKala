# -*- coding: utf-8 -*-
"""
scheduler_service.py
سرویس زمان‌بندی خودکار:
1. به‌روزرسانی ۲ ساعته قیمت‌های زنده (سبک، سریع و امن)
2. به‌روزرسانی هفتگی کاتالوگ پایه و بازسازی درخت دسته‌بندی
"""

import time
import threading
import sync_prices
import sync_catalog
import db_bridge

def start_background_scheduler():
    def worker():
        print("🚀 سرویس زمان‌بندی خودکار فعال شد.")
        # بررسی اولیه قیمت‌ها
        sync_prices.update_live_prices()
        
        last_weekly_check = time.time()
        
        while True:
            try:
                # هر 2 ساعت (7200 ثانیه)
                time.sleep(7200)
                print("⏰ اجرای نوبت همگام‌سازی ۲ ساعته قیمت‌ها...")
                sync_prices.update_live_prices()

                # هر 7 روز یک‌بار بازسازی درخت کاتالوگ
                if time.time() - last_weekly_check >= 7 * 86400:
                    print("📅 اجرای نوبت هفتگی بازسازی کاتالوگ و دسته‌بندی‌ها...")
                    sync_catalog.extract_products()
                    db_bridge.load_catalog_into_db()
                    last_weekly_check = time.time()

            except Exception as e:
                print("خطا در زمان‌بند خودکار:", e)
                time.sleep(60)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    start_background_scheduler()
    while True:
        time.sleep(1)
