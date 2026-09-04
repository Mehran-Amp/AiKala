"""
AiKala - Keyboards, UI Layouts & Callback Mapping (keyboards.py)
===============================================================
شامل کیبوردهای تعاملی، سیستم امن جلوگیری از خطای ۶۴ بایت callback_data،
قالب‌بندی کارت مشخصات کالا و صفحه‌بندی هوشمند نتایج جستجو.
"""

import os
import json
import hashlib
from typing import List, Dict, Any, Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Update
)
from telegram.ext import ContextTypes

try:
    import config
except ImportError:
    config = None

ADMIN_IDS = getattr(config, "ADMIN_IDS", [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()] if os.getenv("ADMIN_IDS") else [])
SUPPORT_USERNAME = getattr(config, "SUPPORT_USERNAME", "@AiKala_Admin")
PRICE_NOTE = getattr(config, "PRICE_NOTE", "⚠️ به علت نوسانات ارز، استعلام قیمت قطعی و موجودی پیش از ارسال ضروری است.")

from search_engine import clean_key

# ─── سیستم کش callback_data برای جلوگیری از خطای ۶۴ بایت تلگرام ───

CALLBACK_DATA_MAP: Dict[str, str] = {}
CALLBACK_MAP_FILE = "callback_map.json"

def load_callback_map():
    global CALLBACK_DATA_MAP
    if os.path.exists(CALLBACK_MAP_FILE):
        try:
            with open(CALLBACK_MAP_FILE, "r", encoding="utf-8") as f:
                CALLBACK_DATA_MAP = json.load(f)
        except Exception:
            CALLBACK_DATA_MAP = {}

def save_callback_map():
    try:
        with open(CALLBACK_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(CALLBACK_DATA_MAP, f, ensure_ascii=False)
    except Exception:
        pass

load_callback_map()

def make_safe_cb(prefix: str, payload: Any) -> str:
    """تولید callback_data تضمین‌شده زیر ۶۴ بایت برای تلگرام"""
    s_payload = str(payload if payload is not None else "").strip()
    full = f"{prefix}|{s_payload}"
    if len(full.encode("utf-8")) <= 64:
        return full
    h = hashlib.md5(s_payload.encode("utf-8")).hexdigest()[:16]
    short_cb = f"{prefix}|h_{h}"
    CALLBACK_DATA_MAP[short_cb] = s_payload
    save_callback_map()
    return short_cb

def resolve_safe_cb(cb_data: str) -> str:
    """بازیابی مقدار اصلی از callback_data"""
    if not cb_data:
        return ""
    if cb_data in CALLBACK_DATA_MAP:
        return CALLBACK_DATA_MAP[cb_data]
    if "|" in cb_data:
        prefix, rest = cb_data.split("|", 1)
        if rest.startswith("h_") and cb_data in CALLBACK_DATA_MAP:
            return CALLBACK_DATA_MAP[cb_data]
        return rest
    return cb_data

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ─── کیبوردهای منوی اصلی ───

def main_menu_keyboard(is_adm: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("🔍 جستجوی کالا"), KeyboardButton("📂 دسته‌بندی‌ها")],
        [KeyboardButton("📋 پیگیری سفارش"), KeyboardButton("ℹ️ راهنمای خرید و ضمانت")],
        [KeyboardButton("📞 پشتیبانی و مشاوره")]
    ]
    if is_adm:
        buttons.append([KeyboardButton("⚙️ پنل مدیریت ادمین")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# توابع کیبورد راهنمای خرید جهت سازگاری و تفکیک به guidbuy.py منتقل شده‌اند
from guidbuy import help_menu_keyboard, guide_section_keyboard

# ─── قالب‌بندی پیام مشخصات کالا ───

def build_boxed_product_message(p: Dict[str, Any]) -> str:
    name = p.get("name", "محصول بدون نام")
    brand = p.get("brand", "نامشخص")
    category = p.get("category") or p.get("category_name") or "لوازم خانگی"
    raw_price = p.get("price", 0)

    if isinstance(raw_price, (int, float)) and raw_price > 0:
        price_str = f"{int(raw_price):,} تومان"
    elif p.get("price_formatted"):
        price_str = p["price_formatted"]
    else:
        price_str = str(raw_price) if raw_price else "تماس بگیرید"

    status_raw = p.get("status", "b")
    if status_raw == "b" and (isinstance(raw_price, (int, float)) and raw_price > 0):
        status_text = "✅ موجود در انبار"
    elif status_raw == "i":
        status_text = "📞 استعلام تلفنی"
    else:
        status_text = "❌ ناموجود"

    specs = p.get("specs", {})
    if isinstance(specs, str):
        try:
            specs = json.loads(specs)
        except Exception:
            specs = {}

    specs_lines = []
    if isinstance(specs, dict):
        for k, v in specs.items():
            if v:
                specs_lines.append(f"▫️ <b>{k}:</b> {v}")

    specs_str = "\n".join(specs_lines) if specs_lines else "▫️ دارای ضمانت اصالت کتبی و گارانتی معتبر شرکتی"

    msg = (
        f"🌟 <b>{name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷 <b>برند:</b> {brand} | 📂 <b>دسته:</b> {category}\n"
        f"💰 <b>قیمت روز:</b> {price_str}\n"
        f"📦 <b>وضعیت موجودی:</b> {status_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>مشخصات فنی کالا:</b>\n"
        f"{specs_str}\n\n"
        f"{PRICE_NOTE}"
    )
    return msg

# ─── کیبورد زیر هر کارت کالا ───

def product_inline_keyboard(pid: str, context: Optional[ContextTypes.DEFAULT_TYPE] = None) -> InlineKeyboardMarkup:
    """دکمه‌های اقدام زیر کارت کالا: استعلام قیمت و کرایه، تصاویر محصول، تماس با پشتیبانی"""
    pid_str = str(pid if pid is not None else "").strip()
    buttons = [
        [
            InlineKeyboardButton("💰 استعلام قیمت تمام‌شده و کرایه", callback_data=make_safe_cb("inq", pid_str))
        ],
        [
            InlineKeyboardButton("📸 تصاویر محصول", callback_data=make_safe_cb("req_img", pid_str)),
            InlineKeyboardButton("📞 پشتیبانی و مشاوره", callback_data="show_support")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def inquiry_quote_keyboard(pid: str, req_id: Any = None) -> InlineKeyboardMarkup:
    """کیبورد ارسالی به مشتری همراه با قیمت اعلامی ادمین شامل ثبت سفارش و صدور پیش‌فاکتور"""
    pid_str = str(pid if pid is not None else "").strip()
    payload = f"{pid_str}:{req_id}" if req_id is not None else pid_str
    buttons = [
        [
            InlineKeyboardButton("🛒 ثبت سفارش و صدور پیش‌فاکتور رسمی", callback_data=make_safe_cb("buy", payload))
        ],
        [
            InlineKeyboardButton("📞 پشتیبانی و مشاوره", callback_data="show_support")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

# ─── صفحه‌بندی نتایج جستجو ───

async def show_search_page(update: Update, context: ContextTypes.DEFAULT_TYPE, products: List[Dict[str, Any]], page: int = 0):
    page_size = 5
    total = len(products)
    start = page * page_size
    end = start + page_size
    current_batch = products[start:end]

    buttons = []
    for p in current_batch:
        pid = str(p.get("product_id", "")).strip()
        if not pid:
            pid = str(clean_key(p.get("name", "")))[:20]
        name = str(p.get("name", "")).strip()[:38]
        cb = make_safe_cb("sel", pid)
        buttons.append([InlineKeyboardButton(f"🔹 {name}", callback_data=cb)])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"spage|{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"spage|{page+1}"))
    if nav:
        buttons.append(nav)

    kb = InlineKeyboardMarkup(buttons)
    text = f"🔍 <b>تعداد {total} محصول منطبق یافت شد:</b> (صفحه {page+1} از {((total-1)//page_size)+1})"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
