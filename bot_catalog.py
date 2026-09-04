# -*- coding: utf-8 -*-
"""
bot_catalog.py
ناوبری داینامیک تلگرام و قالب‌بندی متنی کارت‌های محصولات.
بدون تصویر، بدون کوچک‌ترین ردپا از سایت مبدأ (کاملاً White-Label)
و بدون نمایش تاریخ یا ساعت به‌روزرسانی قیمت.
"""

import os
import json
import sqlite3
from typing import Dict, List, Optional, Tuple, Any

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ImportError:
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None

from keyboards import make_safe_cb, resolve_safe_cb

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


# ─── سیستم ناوبری تعاملی و پویای دسته‌بندی‌ها ───

def load_categories_tree() -> dict:
    if os.path.exists(CATEGORIES_FILE):
        try:
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def get_main_categories_markup():
    tree = load_categories_tree()
    buttons = []
    order = ["tv", "conditioner", "refrigerator", "washing_machine", "dishwasher", "small_appliances"]
    row = []
    for cat_key in order:
        cat_data = tree.get(cat_key, {})
        title = cat_data.get("title", cat_key)
        pids = set()
        for subk, subv in cat_data.items():
            if isinstance(subv, dict):
                for itemv in subv.values():
                    if isinstance(itemv, list):
                        pids.update(itemv)
        count_str = f" ({len(pids)})" if pids else ""
        cb = make_safe_cb("cat_m", cat_key)
        row.append(InlineKeyboardButton(f"{title}{count_str}", callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def get_category_sub_markup(cat_key: str) -> Tuple[str, Any]:
    tree = load_categories_tree()
    cat_data = tree.get(cat_key, {})
    title = cat_data.get("title", cat_key)
    buttons = []

    if cat_key == "small_appliances":
        subcats = cat_data.get("subcategories", {})
        row = []
        for sub_name, pids in subcats.items():
            count = len(pids) if isinstance(pids, list) else 0
            btn_text = f"{sub_name} ({count})"
            cb = make_safe_cb("cat_sub", f"{cat_key}:{sub_name}")
            row.append(InlineKeyboardButton(btn_text, callback_data=cb))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([
            InlineKeyboardButton("📋 مشاهده همه کالاهای این دسته", callback_data=make_safe_cb("cat_all", cat_key)),
            InlineKeyboardButton("🔙 بازگشت به دسته‌ها", callback_data="cat_back")
        ])
        msg_text = f"☕️ <b>زیرشاخه‌های {title}:</b>\nلطفاً گروه کالای مورد نظر را انتخاب نمایید:"
        return msg_text, InlineKeyboardMarkup(buttons)

    filter_labels = {
        "brands": "🏷 بر اساس برند",
        "sizes": "📏 بر اساس سایز",
        "capacities": "⚡️ بر اساس ظرفیت",
        "plans": "🚪 بر اساس نوع و طرح بدنه",
        "types": "💨 بر اساس نوع دستگاه",
        "baskets": "🍽 بر اساس تعداد سبدها"
    }

    for subk, subv in cat_data.items():
        if subk != "title" and isinstance(subv, dict) and subv:
            lbl = filter_labels.get(subk, f"بر اساس {subk}")
            cb = make_safe_cb("cat_f", f"{cat_key}:{subk}")
            buttons.append([InlineKeyboardButton(lbl, callback_data=cb)])

    buttons.append([
        InlineKeyboardButton("📋 مشاهده همه کالاهای این دسته", callback_data=make_safe_cb("cat_all", cat_key)),
        InlineKeyboardButton("🔙 بازگشت به دسته‌ها", callback_data="cat_back")
    ])

    all_pids = set()
    for subk, subv in cat_data.items():
        if isinstance(subv, dict):
            for itemv in subv.values():
                if isinstance(itemv, list):
                    all_pids.update(itemv)

    msg_text = (
        f"📂 <b>دسته‌بندی: {title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 تعداد کل مدل‌های موجود: <b>{len(all_pids)} مدل</b>\n\n"
        f"🔍 نحوه انتخاب و فیلتر را مشخص فرمایید:"
    )
    return msg_text, InlineKeyboardMarkup(buttons)

def get_filter_options_markup(cat_key: str, filter_type: str) -> Tuple[str, Any]:
    tree = load_categories_tree()
    cat_data = tree.get(cat_key, {})
    title = cat_data.get("title", cat_key)
    options_dict = cat_data.get(filter_type, {})

    buttons = []
    row = []
    for opt_name, pids in options_dict.items():
        count = len(pids) if isinstance(pids, list) else 0
        btn_text = f"{opt_name} ({count})"
        cb = make_safe_cb("cat_opt", f"{cat_key}:{filter_type}:{opt_name}")
        row.append(InlineKeyboardButton(btn_text, callback_data=cb))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton("🔙 بازگشت به این دسته", callback_data=make_safe_cb("cat_m", cat_key)),
        InlineKeyboardButton("📂 همه دسته‌ها", callback_data="cat_back")
    ])

    filter_names = {
        "brands": "برندها",
        "sizes": "سایزها",
        "capacities": "ظرفیت‌ها",
        "plans": "طرح‌ها و مدل‌های بدنه",
        "types": "انواع مدل‌ها",
        "baskets": "تعداد سبدها"
    }
    f_title = filter_names.get(filter_type, filter_type)
    msg_text = f"🔍 <b>{title} - انتخاب بر اساس {f_title}:</b>\nلطفاً گزینه مورد نظر را انتخاب فرمایید:"
    return msg_text, InlineKeyboardMarkup(buttons)

def get_products_for_category_selection(cat_key: str, filter_type: Optional[str] = None, opt_name: Optional[str] = None) -> List[dict]:
    tree = load_categories_tree()
    cat_data = tree.get(cat_key, {})
    target_pids = set()

    if filter_type and opt_name:
        sub_dict = cat_data.get(filter_type, {})
        pids = sub_dict.get(opt_name, [])
        target_pids.update(str(p) for p in pids)
    else:
        for subk, subv in cat_data.items():
            if isinstance(subv, dict):
                for itemv in subv.values():
                    if isinstance(itemv, list):
                        target_pids.update(str(p) for p in itemv)

    from search_engine import JSON_PRODUCTS
    matched = []
    for p in JSON_PRODUCTS:
        pid = str(p.get("product_id", "")).strip()
        if pid in target_pids:
            matched.append(p)

    return matched

