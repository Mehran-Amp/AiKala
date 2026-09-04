# -*- coding: utf-8 -*-
"""
bot_catalog.py
ناوبری داینامیک تلگرام و قالب‌بندی متنی کارت‌های محصولات.
بدون تصویر، بدون کوچک‌ترین ردپا از سایت مبدأ (کاملاً White-Label)
و بدون نمایش تاریخ یا ساعت به‌روزرسانی قیمت.
"""

import json
import sqlite3
from typing import Dict, List, Optional

DB_PATH = "bot_data.db"
CATEGORIES_FILE = "categories_tree.json"

def format_price(amount: int) -> str:
    if not amount or amount <= 0:
        return "تماس بگیرید"
    return f"{amount:,} تومان"

def get_product_card(prod: dict) -> str:
    """تولید کارت متنی شیک و استاندارد محصول برای ارسال در تلگرام"""
    name = prod.get("name", "")
    price = prod.get("price", 0)
    status_raw = prod.get("status", "b")

    if status_raw == "b" and price > 0:
        status_text = "✅ موجود در انبار"
    elif status_raw == "i":
        status_text = "📞 استعلام تلفنی"
    else:
        status_text = "❌ ناموجود"

    cat = prod.get("category_key", "")
    lines = [
        f"🏷 **{name}**",
        "",
        f"▫️ **قیمت روز:** `{format_price(price)}`",
        f"▫️ **وضعیت موجودی:** {status_text}",
    ]

    # مشخصات مو به مو بر اساس نوع کالا
    if cat == "tv":
        if prod.get("assembly"):
            lines.append(f"▫️ **کشور مونتاژ:** {prod['assembly']}")
        if prod.get("year"):
            lines.append(f"▫️ **سال ساخت:** {prod['year']}")
        if prod.get("resolution"):
            lines.append(f"▫️ **کیفیت تصویر:** {prod['resolution']}")
        if prod.get("panel"):
            lines.append(f"▫️ **نوع پنل:** {prod['panel']}")
        if prod.get("refresh_rate"):
            lines.append(f"▫️ **رفرش ریت:** {prod['refresh_rate']}")
        if prod.get("backlight"):
            lines.append(f"▫️ **بکلایت:** {prod['backlight']}")
        if prod.get("os"):
            lines.append(f"▫️ **سیستم‌عامل:** {prod['os']}")
        if prod.get("score"):
            lines.append(f"▫️ **امتیاز کیفی کارشناسی:** ⭐️ {prod['score']} از ۱۰")

    elif cat == "conditioner":
        if prod.get("temp_range"):
            lines.append(f"▫️ **شرایط آب و هوایی:** {prod['temp_range']}")
        if prod.get("room_size"):
            lines.append(f"▫️ **پوشش فضا:** {prod['room_size']}")
        if prod.get("energy_consumption"):
            lines.append(f"▫️ **نوع موتور و مصرف:** {prod['energy_consumption']}")
        if prod.get("performance"):
            lines.append(f"▫️ **عملکرد:** {prod['performance']}")
        if prod.get("key_features"):
            lines.append(f"▫️ **ویژگی‌های کلیدی:** {prod['key_features']}")
        if prod.get("score"):
            lines.append(f"▫️ **امتیاز کیفی:** ⭐️ {prod['score']} از ۱۰")

    elif cat == "refrigerator":
        if prod.get("plan"):
            lines.append(f"▫️ **طرح و نوع:** {prod['plan']}")
        if prod.get("capacity_foot"):
            lines.append(f"▫️ **ظرفیت به فوت:** {prod['capacity_foot']}")
        if prod.get("num_doors"):
            lines.append(f"▫️ **تعداد درب:** {prod['num_doors']}")
        if prod.get("assembly"):
            lines.append(f"▫️ **کشور مونتاژ:** {prod['assembly']}")
        if prod.get("score"):
            lines.append(f"▫️ **امتیاز کیفی:** ⭐️ {prod['score']} از ۱۰")

    elif cat == "washing_machine":
        if prod.get("capacity_kg"):
            lines.append(f"▫️ **ظرفیت شستشو:** {prod['capacity_kg']} کیلوگرم")
        if prod.get("plan"):
            lines.append(f"▫️ **نوع طراحی:** {prod['plan']}")
        if prod.get("assembly"):
            lines.append(f"▫️ **کشور مونتاژ:** {prod['assembly']}")
        if prod.get("score"):
            lines.append(f"▫️ **امتیاز کیفی:** ⭐️ {prod['score']} از ۱۰")

    elif cat == "dishwasher":
        if prod.get("baskets"):
            lines.append(f"▫️ **تعداد سبدها:** {prod['baskets']}")
        if prod.get("assembly"):
            lines.append(f"▫️ **کشور مونتاژ:** {prod['assembly']}")
        if prod.get("score"):
            lines.append(f"▫️ **امتیاز کیفی:** ⭐️ {prod['score']} از ۱۰")

    elif cat == "small_appliances":
        if prod.get("subcategory"):
            lines.append(f"▫️ **دسته‌بندی:** {prod['subcategory']}")
        if prod.get("score"):
            lines.append(f"▫️ **امتیاز کیفی:** ⭐️ {prod['score']} از ۱۰")
        if prod.get("more_details"):
            lines.append(f"\n📝 **توضیحات:**\n{prod['more_details']}")

    return "\n".join(lines)

def search_products(query: str, limit: int = 10) -> List[dict]:
    """جستجوی فوق‌سریع کمتر از ۲ میلی‌ثانیه بر اساس مدل و نام"""
    if not query:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    q_words = query.strip().split()
    conditions = []
    params = []
    for w in q_words:
        conditions.append("(name LIKE ? OR model_number LIKE ? OR brand LIKE ?)")
        param = f"%{w}%"
        params.extend([param, param, param])
    
    where_sql = " AND ".join(conditions)
    cursor.execute(f"""
        SELECT * FROM products
        WHERE {where_sql}
        ORDER BY CASE WHEN price > 0 THEN 0 ELSE 1 END, price DESC
        LIMIT ?
    """, (*params, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_product_by_id(pid: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = ?", (pid,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
