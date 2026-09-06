"""
AiKala - Admin Panel & Photo Management Controller (admin_panel.py)
===================================================================
مدیریت و پایش کانال‌ها، تایید سفارشات و فیش‌ها، آمار فروشگاه
و دریافت هوشمند لینک‌های آلبوم عکس توسط ادمین با محافظت Debounce و وب‌پروبینگ.
"""

import os
import re
import time
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

try:
    import config
except ImportError:
    config = None

ADMIN_IDS = getattr(config, "ADMIN_IDS", [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()] if os.getenv("ADMIN_IDS") else [])
PHOTOS_CHANNEL = getattr(config, "PHOTOS_CHANNEL", getattr(config, "PHOTO_CHANNEL", getattr(config, "IMAGE_CHANNEL", getattr(config, "IMAGES_CHANNEL", os.getenv("PHOTOS_CHANNEL", "@Aikala_Image")))))

from database import Database
from keyboards import is_admin, make_safe_cb, resolve_safe_cb
from sync_prices import get_last_price_sync_str, update_live_prices
from photo_service import (
    VERIFIED_PRODUCT_PHOTOS,
    PENDING_IMAGE_REQUESTS,
    CHANNEL_POSTS_METADATA,
    CHANNEL_PHOTOS_MAP,
    CHANNEL_MEDIA_GROUPS,
    load_channel_photos_map,
    save_verified_photos,
    save_verified_product_entry,
    find_matching_verified_photos,
    parse_telegram_post_link,
    probe_telegram_channel_album,
    probe_telegram_channel_album_and_caption,
    clean_channel_caption,
    send_verified_photos_to_user
)

logger = logging.getLogger(__name__)
db = Database()

# ─── دستورات پنل مدیریت ───

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """داشبورد اصلی و بهینه‌سازی‌شده مدیریت فروشگاه هوشمند آاگ کالا"""
    user = update.effective_user
    if not is_admin(user.id):
        if update.message:
            await update.message.reply_text(
                f"⛔️ <b>دسترسی محدود به مدیریت فروشگاه</b>\n\n"
                f"شناسه کاربری شما: <code>{user.id}</code>\n"
                f"جهت دسترسی به پنل مدیریت، این شناسه را در متغیر <code>ADMIN_IDS</code> در سرور اضافه فرمایید.",
                parse_mode="HTML"
            )
        return

    # پاکسازی وضعیت‌های موقت احتمالی ادمین
    context.user_data.pop("awaiting_broadcast_msg", None)

    stats = await db.get_stats()
    total_prods = stats.get('total_products', 0)
    try:
        from search_engine import JSON_PRODUCTS
        if len(JSON_PRODUCTS) > total_prods:
            total_prods = len(JSON_PRODUCTS)
    except Exception:
        pass

    pending_receipts = stats.get('pending_receipts', 0)
    badge_pending = f" ({pending_receipts} فیش جدید 🔴)" if pending_receipts > 0 else ""

    last_sync_time = get_last_price_sync_str()

    text = (
        f"⚙️ <b>داشبورد مدیریت بازرگانی آاگ کالا</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ <b>آخرین بروزرسانی لیست قیمت محصولات:</b>\n"
        f"📅 <code>{last_sync_time}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>خلاصه وضعیت فروشگاه:</b>\n"
        f"▫️ کل کالاهای فعال کاتالوگ: <b>{total_prods:,} کالا</b>\n"
        f"▫️ کل سفارشات ثبت‌شده: <b>{stats.get('total_orders', 0)} سفارش</b>\n"
        f"▫️ سفارشات امروز: <b>{stats.get('today_orders', 0)}</b>\n"
        f"▫️ فیش‌های منتظر بررسی ادمین: <b>{pending_receipts} عدد</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 لطفاً بخش مورد نظر خود را انتخاب فرمایید:"
    )

    kb = InlineKeyboardMarkup([
        # ۱. سفارشات و فیش‌های بانکی
        [InlineKeyboardButton(f"📋 مدیریت سفارشات و فیش‌ها{badge_pending}", callback_data="adm_manage_orders")],
        
        # ۲. کاتالوگ و قیمت‌ها
        [
            InlineKeyboardButton("📊 ارسال فایل اکسل لپ‌تاپ (.xlsx)", callback_data="adm_upload_laptop_excel"),
            InlineKeyboardButton("💻 مدیریت کاتالوگ لپ‌تاپ", callback_data="adm_laptop_hub")
        ],
        [
            InlineKeyboardButton("🔄 بروزرسانی دستی قیمتها", callback_data="adm_sync_live_prices")
        ],
        
        # ۳. پشتیبانی و پیام همگانی
        [
            InlineKeyboardButton("👥 کارشناسان پشتیبانی", callback_data="adm_manage_support"),
            InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast_ask")
        ],
        
        # ۴. تنظیمات مالی و گزارش کاتالوگ
        [
            InlineKeyboardButton("💳 مشخصات بانکی و بیعانه", callback_data="adm_bank_settings"),
            InlineKeyboardButton("📊 گزارش وضعیت کاتالوگ", callback_data="adm_catalog_report")
        ],
        
        # بازگشت به منوی اصلی ربات
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی فروشگاه", callback_data="back_to_main")]
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
            return
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

# ─── ساب‌منوهای اختصاصی و ماژولار پنل ادمین ───

async def admin_laptop_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مرکز مدیریت و استخراج قیمت و مشخصات لپ‌تاپ"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    # شمارش تعداد لپ‌تاپ‌های ذخیره شده
    laptop_count = 0
    try:
        from search_engine import JSON_PRODUCTS
        laptop_count = sum(1 for p in JSON_PRODUCTS if p.get("category_key") == "laptop" or p.get("category_name") == "لپ‌تاپ")
    except Exception:
        pass

    text = (
        f"💻 <b>مرکز استخراج هوشمند و ثبت کاتالوگ لپ‌تاپ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"▫️ تعداد لپ‌تاپ‌های فعال در فروشگاه: <b>{laptop_count} مدل</b>\n"
        f"▫️ موتور استخراج: <b>تحلیل‌گر پیشرفته اکسل + هوش مصنوعی بینایی ماشین</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"روش ورود اطلاعات مورد نظر خود را انتخاب فرمایید:\n"
        f"📊 <b>ارسال فایل اکسل:</b> آپلود فایل جدول (.xlsx / .csv) به صورت مستقیم\n"
        f"📸 <b>ارسال عکس:</b> اسکرین‌شات یا عکس جدول چاپی/دیجیتال\n"
        f"📋 <b>کپی متن:</b> پیست کردن مستقیم متن جدول اکسل یا پیام تلگرامی"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 ارسال فایل اکسل (.xlsx / .csv)", callback_data="adm_upload_laptop_excel")],
        [InlineKeyboardButton("📸 ارسال عکس یا اسکرین‌شات جدول", callback_data="adm_upload_laptop_photo")],
        [InlineKeyboardButton("📋 کپی و ارسال مستقیم متن جدول", callback_data="adm_text_laptop_prompt")],
        [InlineKeyboardButton("🗑 پاکسازی لیست لپ‌تاپ‌ها", callback_data="adm_clear_laptops_ask")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_upload_laptop_excel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راهنمای آپلود مستقیم فایل اکسل کاتالوگ لپ‌تاپ"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    context.user_data["awaiting_laptop_photo"] = True
    context.user_data["awaiting_laptop_excel"] = True
    context.user_data.pop("pending_extracted_laptops", None)

    text = (
        "📊 <b>آپلود فایل اکسل لیست قیمت و موجودی لپ‌تاپ:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "لطفاً فایل اکسل خود با پسوند <b>.xlsx</b> یا <b>.csv</b> را به صورت فایل در همین چت ارسال (Upload) فرمایید.\n\n"
        "✨ <b>قابلیت‌های هوشمند سیستم استخراج اکسل:</b>\n"
        "▫️ پشتیبانی از تمام نسخه‌ها و شیت‌های اکسل (.xlsx و .csv)\n"
        "▫️ تشخیص خودکار ستون‌ها (کد، برند، مدل، پردازنده، رم، هارد، گرافیک، صفحه نمایش، گرید، قیمت)\n"
        "🚫 <b>فیلتر قطعی قیمت همکار</b> (ستون‌های همکاری و عمده به هیچ عنوان ثبت یا نمایش داده نمی‌شوند)\n"
        "🚫 <b>فیلتر خودکار اطلاعات تماس و تبلیغات</b>\n"
        "▫️ پیش‌نمایش سطرهای استخراج‌شده قبل از تایید نهایی و ثبت در فروشگاه\n\n"
        "👇 <i>همین حالا فایل اکسل را ارسال فرمایید (یا برای انصراف کلمه لغو را بفرستید):</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="adm_laptop_hub")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_text_laptop_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راهنمای پیست متن جدول قیمت لپ‌تاپ"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    context.user_data["awaiting_laptop_photo"] = True
    context.user_data.pop("pending_extracted_laptops", None)

    text = (
        "📋 <b>استخراج سریع از جدول اکسل یا پیام تلگرام:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>شما می‌توانید مستقیماً خود فایل اکسل (.xlsx / .csv) را در همین چت بفرستید</b> یا متن جدول را کپی و پیست فرمایید.\n\n"
        "✨ <b>قابلیت‌های هوشمند سیستم:</b>\n"
        "▫️ خواندن خودکار فایل‌های اکسل (.xlsx و .csv)\n"
        "▫️ پردازش آنی بدون معطلی\n"
        "🚫 حذف اتوماتیک ستون همکار و تبلیغات متفرقه\n"
        "▫️ دسته‌بندی بر اساس برند (Dell, HP, Lenovo, Asus, Apple و...)\n"
        "▫️ استخراج CPU، RAM، Storage، Graphic و گرید\n\n"
        "❌ <i>جهت انصراف، کلمه <code>لغو</code> را بفرستید.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 ارسال فایل اکسل (.xlsx / .csv)", callback_data="adm_upload_laptop_excel")],
        [InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="adm_laptop_hub")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_clear_laptops_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تاییدیه پاکسازی لیست لپ‌تاپ‌ها"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    text = (
        "⚠️ <b>هشدار پاکسازی کاتالوگ لپ‌تاپ‌ها:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "آیا اطمینان دارید که می‌خواهید <b>کلیه مدل‌های لپ‌تاپ ثبت‌شده</b> را حذف نمایید؟\n\n"
        "💡 <i>کالاهای لوازم خانگی بدون تغییر باقی خواهند ماند.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 بله، کلیه لپ‌تاپ‌ها حذف شوند", callback_data="adm_clear_laptops_do")],
        [InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="adm_laptop_hub")]
    ])
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_clear_laptops_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای پاکسازی فایل لپ‌تاپ‌ها و بارگذاری مجدد کاتالوگ"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    l_file = "laptops_catalog.json"
    if os.path.exists(l_file):
        try:
            with open(l_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error clearing laptops: {e}")

    try:
        from bot import load_json_products
        load_json_products()
    except Exception:
        pass

    text = "✅ <b>لیست لپ‌تاپ‌ها با موفقیت پاکسازی شد.</b>"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به منوی لپ‌تاپ", callback_data="adm_laptop_hub")],
        [InlineKeyboardButton("🔙 پنل مدیریت", callback_data="adm_back_panel")]
    ])
    if update.callback_query:
        await update.callback_query.answer("لیست لپ‌تاپ‌ها پاکسازی شد", show_alert=True)
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_sync_live_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای دستی و آنی بروزرسانی قیمت‌ها از ممتازکالا"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    query = update.callback_query
    if query:
        await query.answer("در حال دریافت قیمت‌های زنده...", show_alert=False)
        try:
            await query.edit_message_text(
                "⏳ <b>در حال برقراری ارتباط با سرور ممتازکالا و دریافت آخرین قیمت‌ها...</b>\n"
                "<i>لطفاً چند لحظه شکیبا باشید...</i>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    success = False
    try:
        success = update_live_prices()
    except Exception as e:
        logger.error(f"Error during live sync: {e}")

    new_sync_time = get_last_price_sync_str()

    if success:
        result_text = (
            f"✅ <b>قیمت‌ها و وضعیت موجودی با موفقیت بروزرسانی شد!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱ <b>آخرین بروزرسانی لیست قیمت محصولات:</b>\n"
            f"📅 <code>{new_sync_time}</code>\n"
            f"🌐 منبع: <b>داده‌های زنده ممتازکالا</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ تمامی قیمت‌ها، تغییرات موجودی و تخفیفات کالاها در دیتابیس و کاتالوگ ربات اعمال گردید."
        )
    else:
        result_text = (
            f"⚠️ <b>بروزرسانی زنده با خطا مواجه شد.</b>\n"
            f"احتمالاً ارتباط موقت با سرور منبع با تاخیر مواجه شده است.\n"
            f"آخرین زمان معتبر ثبت‌شده: <code>{new_sync_time}</code>"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="adm_sync_live_prices")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
    ])

    if query:
        try:
            await query.edit_message_text(result_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(result_text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(result_text, reply_markup=kb, parse_mode="HTML")

async def admin_bank_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش و مدیریت مشخصات حساب بانکی، کارت، شبا و درصد بیعانه"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    # پاکسازی حالت‌های انتظار ویرایش قبلی
    context.user_data.pop("awaiting_bank_edit_field", None)

    card_num = getattr(config, "CARD_NUMBER", "6104-3386-4929-6106")
    card_holder = getattr(config, "CARD_HOLDER", "فروشگاه آاگ کالا مهران امین پور")
    shaba_html = getattr(config, "SHABA_HTML", "IR <code>620120020000005786685564</code>")
    deposit_pct = getattr(config, "DEPOSIT_PERCENT", 8)

    text = (
        f"💳 <b>مدیریت حساب بانکی و بیعانه فروشگاه:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"▫️ شماره کارت: <code>{card_num}</code>\n"
        f"▫️ شماره شبا: {shaba_html}\n"
        f"▫️ به نام: <b>{card_holder}</b>\n"
        f"▫️ درصد بیعانه: <b>{deposit_pct}٪ کل مبلغ کالا</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 جهت تغییر هر کدام از موارد، روی دکمه مربوطه کلیک فرمایید:\n"
        f"<i>(تغییرات به صورت آنی در پیش‌فاکتورها، محاسبات مالی و فاکتورهای رسمی ذخیره و اعمال می‌شود)</i>"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ تغییر شماره کارت", callback_data="adm_edit_bank_card"),
            InlineKeyboardButton("✏️ تغییر شماره شبا", callback_data="adm_edit_bank_shaba")
        ],
        [
            InlineKeyboardButton("✏️ تغییر نام دارنده حساب", callback_data="adm_edit_bank_holder"),
            InlineKeyboardButton("✏️ تغییر درصد بیعانه", callback_data="adm_edit_bank_deposit")
        ],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_prompt_bank_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, field_key: str):
    """درخواست ورودی متنی از ادمین برای ویرایش یک مشخصه بانکی"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    context.user_data["awaiting_bank_edit_field"] = field_key

    prompts = {
        "card": (
            "💳 <b>تغییر شماره کارت واریز بیعانه:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"شماره کارت فعلی: <code>{getattr(config, 'CARD_NUMBER', '')}</code>\n\n"
            "لطفاً شماره کارت جدید ۱۶ رقمی را در همین چت ارسال فرمایید:\n"
            "<i>(می‌توانید به صورت پیوسته یا خط تیره ۴ رقم ۴ رقم بفرستید)</i>"
        ),
        "shaba": (
            "🏦 <b>تغییر شماره شبا بانکی:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"شماره شبا فعلی: {getattr(config, 'SHABA_HTML', '')}\n\n"
            "لطفاً شماره شبا ۲۴ رقمی جدید را ارسال فرمایید:\n"
            "<i>(نیازی به نوشتن کلمه IR نیست، سیستم خودکار تنظیم می‌کند)</i>"
        ),
        "holder": (
            "👤 <b>تغییر نام دارنده حساب / کارت:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"نام فعلی: <b>{getattr(config, 'CARD_HOLDER', '')}</b>\n\n"
            "لطفاً نام و نام خانوادگی کامل یا نام تجاری حساب را ارسال فرمایید:"
        ),
        "deposit": (
            "📊 <b>تغییر درصد محاسبه بیعانه سفارشات:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"درصد فعلی: <b>{getattr(config, 'DEPOSIT_PERCENT', 8)}٪</b>\n\n"
            "لطفاً درصد جدید را به صورت یک عدد بین <b>۱ تا ۱۰۰</b> ارسال فرمایید:\n"
            "<i>(مثال: عدد 10 برای ۱۰٪، یا 5 برای ۵٪)</i>"
        )
    }

    prompt_text = prompts.get(field_key, "لطفاً مقدار جدید را ارسال فرمایید:")
    prompt_text += "\n\n❌ <i>جهت انصراف، کلمه <code>لغو</code> را ارسال نمایید.</i>"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="adm_bank_settings")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(prompt_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(prompt_text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(prompt_text, reply_markup=kb, parse_mode="HTML")

async def handle_admin_bank_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """دریافت مقدار جدید ارسالی ادمین برای فیلدهای بانکی و ذخیره قطعی آن"""
    field = context.user_data.get("awaiting_bank_edit_field")
    if not field:
        return False

    user = update.effective_user
    if not is_admin(user.id):
        return False

    val = update.message.text.strip() if update.message.text else ""
    if val in ["لغو", "/cancel", "انصراف", "بازگشت"]:
        context.user_data.pop("awaiting_bank_edit_field", None)
        await update.message.reply_text("❌ ویرایش مشخصات بانکی لغو گردید.")
        await admin_bank_settings(update, context)
        return True

    # نرمال‌سازی اعداد فارسی
    from search_engine import _normalize_digits
    val_norm = _normalize_digits(val)

    if field == "card":
        digits = "".join(re.findall(r'\d+', val_norm))
        if len(digits) != 16:
            await update.message.reply_text("⚠️ شماره کارت باید دقیقاً ۱۶ رقم باشد. لطفاً مجدداً شماره معتبر بفرستید یا کلمه «لغو» را ارسال فرمایید:")
            return True
        # قالب‌بندی با خط تیره
        formatted_card = f"{digits[0:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:16]}"
        config.update_bank_settings(card_number=formatted_card)
        success_msg = f"✅ شماره کارت با موفقیت به <code>{formatted_card}</code> تغییر یافت."

    elif field == "shaba":
        digits = "".join(re.findall(r'\d+', val_norm))
        if len(digits) != 24:
            await update.message.reply_text("⚠️ شماره شبا باید دقیقاً ۲۴ رقم (بدون IR) باشد. لطفاً مجدداً با دقت بفرستید یا کلمه «لغو» را ارسال فرمایید:")
            return True
        new_shaba = f"IR {digits}"
        config.update_bank_settings(card_shaba=new_shaba)
        success_msg = f"✅ شماره شبا با موفقیت به IR <code>{digits}</code> تغییر یافت."

    elif field == "holder":
        if len(val) < 3:
            await update.message.reply_text("⚠️ نام وارد شده بیش از حد کوتاه است. لطفاً نام کامل دارنده حساب را وارد نمایید:")
            return True
        config.update_bank_settings(card_holder=val)
        success_msg = f"✅ نام دارنده حساب با موفقیت به <b>{val}</b> تغییر یافت."

    elif field == "deposit":
        digits = "".join(re.findall(r'\d+', val_norm))
        if not digits or int(digits) < 1 or int(digits) > 100:
            await update.message.reply_text("⚠️ درصد بیعانه باید عددی بین ۱ تا ۱۰۰ باشد (مثلاً 8 یا 10). لطفاً مجدداً ارسال فرمایید:")
            return True
        pct = int(digits)
        config.update_bank_settings(deposit_percent=pct)
        success_msg = f"✅ درصد محاسبه بیعانه با موفقیت به <b>{pct}٪</b> کل فاکتور تغییر یافت."

    else:
        context.user_data.pop("awaiting_bank_edit_field", None)
        return False

    context.user_data.pop("awaiting_bank_edit_field", None)
    await update.message.reply_text(success_msg, parse_mode="HTML")
    await admin_bank_settings(update, context)
    return True

async def admin_catalog_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش تفکیک‌شده کاتالوگ محصولات"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    home_count = 0
    laptop_count = 0
    brands = set()
    try:
        from search_engine import JSON_PRODUCTS
        for p in JSON_PRODUCTS:
            if p.get("category_key") == "laptop" or p.get("category_name") == "لپ‌تاپ":
                laptop_count += 1
            else:
                home_count += 1
            if p.get("brand"):
                brands.add(p.get("brand"))
    except Exception:
        pass

    total = home_count + laptop_count
    last_sync = get_last_price_sync_str()

    text = (
        f"📊 <b>گزارش و آمار جامع کاتالوگ فروشگاه:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 کل کالاهای موجود در کاتالوگ: <b>{total:,} کالا</b>\n"
        f"🏠 لوازم خانگی و آشپزخانه: <b>{home_count:,} کالا</b>\n"
        f"💻 دسته‌بندی لپ‌تاپ: <b>{laptop_count} مدل</b>\n"
        f"🏷 تعداد برندهای پوشش‌داده‌شده: <b>{len(brands)} برند</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ <b>آخرین بروزرسانی لیست قیمت محصولات:</b>\n"
        f"📅 <code>{last_sync}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ تمام محصولات قابلیت جستجوی هوشمند متنی و فیلتر بر اساس برند و دسته را دارند."
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی زنده قیمت‌ها", callback_data="adm_sync_live_prices")],
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def admin_broadcast_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """درخواست متن پیام همگانی از ادمین"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    context.user_data["awaiting_broadcast_msg"] = True

    active_users = await db.get_all_active_user_ids()
    count_users = len(active_users)

    text = (
        f"📢 <b>ارسال پیام همگانی به کاربران ربات:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 تعداد کاربران ثبت‌شده در سیستم: <b>{count_users} کاربر</b>\n\n"
        f"لطفاً متن اطلاعیه، تخفیف یا پیام مورد نظر خود را در همین چت ارسال فرمایید.\n"
        f"<i>(قبل از ارسال قطعی، یک پیش‌نمایش به همراه دکمه تایید نهایی به شما نمایش داده خواهد شد)</i>\n\n"
        f"❌ <i>جهت انصراف، کلمه <code>لغو</code> را ارسال فرمایید.</i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 انصراف و بازگشت به پنل", callback_data="adm_back_panel")]
    ])

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def handle_admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """دریافت متن ارسالی ادمین جهت برودکست و نمایش پیش‌نمایش"""
    if not context.user_data.get("awaiting_broadcast_msg"):
        return False

    user = update.effective_user
    if not is_admin(user.id):
        return False

    text = update.message.text.strip() if update.message.text else ""
    if text.startswith("/cancel") or text.lower() == "لغو":
        context.user_data.pop("awaiting_broadcast_msg", None)
        await update.message.reply_text("❌ ارسال پیام همگانی لغو گردید.")
        await admin_panel_command(update, context)
        return True

    context.user_data.pop("awaiting_broadcast_msg", None)
    context.user_data["pending_broadcast_text"] = text

    active_users = await db.get_all_active_user_ids()

    preview = (
        f"📢 <b>پیش‌نمایش پیام همگانی:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 این پیام برای <b>{len(active_users)} کاربر</b> ارسال خواهد شد.\n"
        f"آیا برای ارسال به کلیه کاربران اطمینان دارید؟"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله، همین الان ارسال شود", callback_data="adm_broadcast_do"),
            InlineKeyboardButton("❌ لغو", callback_data="adm_back_panel")
        ]
    ])
    await update.message.reply_text(preview, reply_markup=kb, parse_mode="HTML")
    return True

async def admin_broadcast_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ارسال قطعی پیام همگانی به کلیه کاربران"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    text = context.user_data.pop("pending_broadcast_text", None)
    if not text:
        await update.callback_query.answer("پیامی برای ارسال یافت نشد.", show_alert=True)
        await admin_panel_command(update, context)
        return

    query = update.callback_query
    await query.answer("در حال ارسال همگانی...", show_alert=False)
    status_msg = await query.message.reply_text("⏳ <b>در حال ارسال پیام همگانی به کاربران...</b>", parse_mode="HTML")

    active_users = await db.get_all_active_user_ids()
    sent = 0
    failed = 0

    for uid in active_users:
        if uid == user.id:
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # رعایت محدودیت نرخ تلگرام
        except Exception:
            failed += 1

    report = (
        f"🎉 <b>نتیجه ارسال پیام همگانی:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ ارسال موفق: <b>{sent} کاربر</b>\n"
        f"❌ ناموفق (مسدود یا غیرفعال): <b>{failed} کاربر</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
    ])
    try:
        await status_msg.edit_text(report, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await query.message.reply_text(report, reply_markup=kb, parse_mode="HTML")

async def sync_photos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    load_channel_photos_map()
    total_posts = len(CHANNEL_POSTS_METADATA)
    total_keys = len(CHANNEL_PHOTOS_MAP)
    colors_detected = sum(1 for p in CHANNEL_POSTS_METADATA if p.get("color"))
    
    msg = (
        f"📸 <b>وضعیت گالری تصاویر محصولات:</b>\n\n"
        f"📦 تعداد کل پست‌های ایندکس‌شده: <b>{total_posts}</b>\n"
        f"🎨 پست‌های دارای رنگ تفکیک‌شده: <b>{colors_detected}</b>\n"
        f"🏷 کلیدهای مدل فعال: <b>{total_keys}</b>\n"
        f"📸 تصاویر تایید شده دستی: <b>{len(VERIFIED_PRODUCT_PHOTOS)}</b>\n\n"
        f"✨ سیستم تفکیک رنگ و تنزل هوشمند فعال است."
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")

async def setphoto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور مدیریت برای اتصال مستقیم و تایید عکس یا آلبوم برای هر کالا"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📸 <b>راهنمای ثبت دستی تصویر کالا:</b>\n\n"
            "جهت ثبت تصویر یا آلبوم برای هر کالا، دستور را به صورت زیر وارد فرمایید:\n"
            "<code>/setphoto [کد_محصول]</code>\n\n"
            "مثال:\n"
            "<code>/setphoto 68798</code>\n\n"
            "سپس ربات منتظر دریافت عکس، فوروارد از کانال یا ارسال شماره پست می‌ماند.",
            parse_mode="HTML"
        )
        return

    pid = str(args[0]).strip()
    from photo_service import VERIFIED_PRODUCT_PHOTOS

    # بررسی نام محصول از کاتالوگ در صورت امکان
    pname = f"کالای {pid}"
    try:
        from bot import JSON_PRODUCTS
        prod = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == pid), None)
        if prod and prod.get("name"):
            pname = prod["name"]
    except Exception:
        pass

    context.user_data["awaiting_product_image_link"] = {
        "pid": pid,
        "target_uid": 0,
        "product_name": pname
    }

    await update.message.reply_text(
        f"📸 <b>ثبت تصاویر تایید شده برای محصول:</b>\n"
        f"🌟 <b>{pname}</b> (کد: <code>{pid}</code>)\n\n"
        f"لطفاً همین الان <b>عکس‌ها را ارسال فرمایید</b> یا <b>پست کانال را فوروارد کنید</b> یا <b>شماره پست کانال</b> (مانند <code>452</code>) را بفرستید.\n\n"
        f"❌ جهت انصراف: /cancel",
        parse_mode="HTML"
    )

async def clearphotos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور ادمین برای تایید و پاکسازی کامل لیست عکس‌های تستی"""
    user = update.effective_user
    if not is_admin(user.id):
        return

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ بله، تمامی عکس‌ها پاک شوند", callback_data="adm_clear_photos_do")
        ],
        [
            InlineKeyboardButton("🔙 انصراف و بازگشت به پنل", callback_data="adm_back_panel")
        ]
    ])
    msg = (
        "⚠️ <b>هشدار پاکسازی کل تصاویر و کش محصولات:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "آیا مایلید <b>تمامی عکس‌های تستی و آرشیو موجود</b> برای محصولات را حذف نمایید؟\n\n"
        "این عمل موارد زیر را پاکسازی می‌کند:\n"
        "▫️ کلیه تصاویر تایید شده دستی پیشین\n"
        "▫️ کش تصاویر و ارتباطات تستی قبلی\n\n"
        "🎯 <i>پس از پاکسازی، تنها تصاویری که از این به بعد در کانال رسمی عکس قرار دهید یا با دستور <code>/setphoto</code> اضافه کنید، برای محصولات نمایش داده می‌شوند.</i>"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(msg, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await update.callback_query.message.reply_text(msg, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, reply_markup=kb, parse_mode="HTML")

# ─── پردازش ثبت لینک و عکس توسط ادمین ───

async def handle_admin_photo_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    req_data = context.user_data.get("awaiting_product_image_link")
    if not req_data:
        return

    pid = str(req_data.get("pid", "")).strip()
    pname = req_data.get("product_name", pid)
    target_uid = req_data.get("target_uid")

    text = update.message.text.strip() if update.message.text else ""
    if text.startswith("/cancel"):
        context.user_data.pop("awaiting_product_image_link", None)
        await update.message.reply_text("❌ فرآیند ثبت لینک تصویر لغو گردید.")
        return

    if "collected_msg_ids" not in req_data:
        req_data["collected_msg_ids"] = []
    if "collected_file_ids" not in req_data:
        req_data["collected_file_ids"] = []

    channel = PHOTOS_CHANNEL
    msg_ids = []
    file_ids = []
    post_link = ""
    detected_caption = (update.message.caption or "").strip()

    # ۱. آیا پیام از کانال عکس فوروارد شده است؟
    if getattr(update.message, 'forward_origin', None):
        origin = update.message.forward_origin
        if hasattr(origin, 'chat') and origin.chat:
            ch_uname = origin.chat.username or str(origin.chat.id)
            channel = f"@{ch_uname}" if not ch_uname.startswith("@") and not ch_uname.startswith("-") else ch_uname
        if hasattr(origin, 'message_id'):
            msg_ids.append(origin.message_id)
    elif getattr(update.message, 'forward_from_chat', None):
        f_chat = update.message.forward_from_chat
        ch_uname = f_chat.username or str(f_chat.id)
        channel = f"@{ch_uname}" if not ch_uname.startswith("@") and not ch_uname.startswith("-") else ch_uname
        if getattr(update.message, 'forward_from_message_id', None):
            msg_ids.append(update.message.forward_from_message_id)

    # ۲. آیا عکس مستقیماً در چت ارسال شده است؟
    if update.message.photo:
        file_ids.append(update.message.photo[-1].file_id)

    # ۳. آیا متن ارسال شده حاوی لینک یا شماره پیام است؟
    if text:
        parsed = parse_telegram_post_link(text)
        if parsed:
            ch_parsed, m_ids = parsed
            channel = ch_parsed
            msg_ids.extend(m_ids)
            if "t.me" in text:
                post_link = text
        elif "t.me" in text:
            post_link = text

    req_data["collected_msg_ids"].extend(msg_ids)
    req_data["collected_file_ids"].extend(file_ids)

    # مکانیزم هوشمند Debounce برای جلوگیری از قطعه‌قطعه شدن آلبوم فوروارد شده
    is_multi_candidate = bool(
        getattr(update.message, 'media_group_id', None) or 
        update.message.photo or 
        getattr(update.message, 'forward_origin', None) or 
        getattr(update.message, 'forward_from_chat', None)
    )

    if is_multi_candidate:
        req_data["last_update_time"] = time.time()
        await asyncio.sleep(0.8)
        if time.time() - req_data.get("last_update_time", 0) < 0.75:
            return
        if req_data.get("is_processing"):
            return
        req_data["is_processing"] = True

    final_msg_ids = sorted(list(set(req_data["collected_msg_ids"])))
    final_file_ids = list(dict.fromkeys(req_data["collected_file_ids"]))

    # ۱. تطبیق سریع با آلبوم‌های کش‌شده در CHANNEL_MEDIA_GROUPS
    matched_mg = False
    for mid in list(final_msg_ids):
        mid_str = str(mid)
        for mg_id, g_info in CHANNEL_MEDIA_GROUPS.items():
            g_mids = [str(x) for x in g_info.get("msg_ids", [])]
            if mid_str in g_mids:
                logger.info(f"🎯 [ALBUM MATCH] Found album {mg_id} in CHANNEL_MEDIA_GROUPS for msg {mid}: {g_mids}")
                final_msg_ids = sorted(list(set(final_msg_ids + [int(x) for x in g_mids if str(x).isdigit()])))
                final_file_ids = list(dict.fromkeys(final_file_ids + g_info.get("photos", [])))
                matched_mg = True
                break
        if matched_mg:
            break

    # ۲. تطبیق با متادیتای پست‌های ایندکس‌شده در CHANNEL_POSTS_METADATA
    if not matched_mg:
        for mid in list(final_msg_ids):
            mid_str = str(mid)
            for post in CHANNEL_POSTS_METADATA:
                post_mids = [str(x) for x in post.get("msg_ids", [])]
                if mid_str in post_mids or mid_str in [str(x) for x in post.get("photos", [])]:
                    logger.info(f"🎯 [METADATA MATCH] Found post in CHANNEL_POSTS_METADATA for msg {mid}: {post_mids}")
                    if post_mids:
                        final_msg_ids = sorted(list(set(final_msg_ids + [int(x) for x in post_mids if str(x).isdigit()])))
                    if post.get("photos"):
                        extra_fids = [p for p in post["photos"] if not str(p).isdigit()]
                        final_file_ids = list(dict.fromkeys(final_file_ids + extra_fids))
                    matched_mg = True
                    break
            if matched_mg:
                break

    # ۳. 🌐 پویش قطعی و همه‌جانبه وب ویجت تلگرام (Telegram Public Embed)
    if channel and final_msg_ids and (len(final_file_ids) <= 1 or len(final_msg_ids) <= 1):
        target_mid = final_msg_ids[0]
        ch_clean = str(channel).replace("@", "").strip()
        if not ch_clean.startswith("-"):
            logger.info(f"🌐 [ADMIN INPUT] Probing channel album & caption via public embed for {ch_clean}/{target_mid}...")
            scraped_photos, scraped_mids, scraped_caption = await probe_telegram_channel_album_and_caption(ch_clean, target_mid)
            if scraped_photos:
                logger.info(f"🎉 [ADMIN INPUT] Successfully extracted {len(scraped_photos)} album photos from embed!")
                for sp in scraped_photos:
                    if sp not in final_file_ids:
                        final_file_ids.append(sp)
                for sm in scraped_mids:
                    if sm not in final_msg_ids:
                        final_msg_ids.append(sm)
            if not detected_caption and scraped_caption:
                detected_caption = scraped_caption
                logger.info(f"📝 [ADMIN INPUT] Extracted caption from embed ({len(scraped_caption)} chars)")

    # ۴. پویش تکمیلی از طریق فوروارد با مدیریت ایمن خطا (جهت استخراج تمام عکس‌های آلبوم)
    if channel and final_msg_ids and len(final_file_ids) < max(len(final_msg_ids), 2):
        probed_msgs = []
        try:
            def get_msg_orig_date(msg):
                if getattr(msg, 'forward_origin', None) and hasattr(msg.forward_origin, 'date'):
                    return msg.forward_origin.date
                if getattr(msg, 'forward_date', None):
                    return msg.forward_date
                return None

            # الف) اگر چندین شماره پیام وارد شده باشد (مثلاً رنج 452-455)، عکس تک‌تک آن‌ها استخراج شود
            if len(final_msg_ids) > 1:
                logger.info(f"🔍 Fetching photos for specified message IDs {final_msg_ids} via forward...")
                for mid in final_msg_ids:
                    try:
                        fwd = await context.bot.forward_message(
                            chat_id=update.effective_chat.id,
                            from_chat_id=channel,
                            message_id=mid
                        )
                        probed_msgs.append(fwd.message_id)
                        if not detected_caption and (fwd.caption or fwd.text):
                            detected_caption = (fwd.caption or fwd.text or "").strip()
                        if fwd.photo:
                            tfid = fwd.photo[-1].file_id
                            if tfid not in final_file_ids:
                                final_file_ids.append(tfid)
                    except Exception as ex:
                        logger.debug(f"Could not forward msg {mid}: {ex}")

            # ب) اگر تک‌شماره وارد شده، پیام‌های مجاور (آلبوم چندتایی) پویش شوند
            elif len(final_msg_ids) == 1:
                target_mid = final_msg_ids[0]
                logger.info(f"🔍 Probing sequential album messages in {channel} around message {target_mid} bidirectionally...")
                fwd_target = await context.bot.forward_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=channel,
                    message_id=target_mid
                )
                probed_msgs.append(fwd_target.message_id)
                if not detected_caption and (fwd_target.caption or fwd_target.text):
                    detected_caption = (fwd_target.caption or fwd_target.text or "").strip()

                base_orig_date = get_msg_orig_date(fwd_target)
                base_mg_id = getattr(fwd_target, 'media_group_id', None)

                if fwd_target.photo:
                    tfid = fwd_target.photo[-1].file_id
                    if tfid not in final_file_ids:
                        final_file_ids.append(tfid)

                if fwd_target.photo:
                    # پویش عقب‌گرد پیام‌های قبلی آلبوم (target_mid - 1 تا target_mid - 10)
                    for prev_id in range(target_mid - 1, max(1, target_mid - 10), -1):
                        try:
                            prev_fwd = await context.bot.forward_message(
                                chat_id=update.effective_chat.id,
                                from_chat_id=channel,
                                message_id=prev_id
                            )
                            probed_msgs.append(prev_fwd.message_id)
                            prev_orig_date = get_msg_orig_date(prev_fwd)
                            prev_mg_id = getattr(prev_fwd, 'media_group_id', None)

                            is_album_match = False
                            if base_mg_id and prev_mg_id and base_mg_id == prev_mg_id:
                                is_album_match = True
                            elif prev_fwd.photo and prev_orig_date and base_orig_date and abs((prev_orig_date - base_orig_date).total_seconds()) <= 4:
                                is_album_match = True

                            if prev_fwd.photo and is_album_match:
                                logger.info(f"   ➕ Discovered album photo at previous msg_id {prev_id}")
                                if prev_id not in final_msg_ids:
                                    final_msg_ids.append(prev_id)
                                pfid = prev_fwd.photo[-1].file_id
                                if pfid not in final_file_ids:
                                    final_file_ids.append(pfid)
                            else:
                                break
                        except Exception:
                            break

                    # پویش پیش‌رو پیام‌های بعدی آلبوم (target_mid + 1 تا target_mid + 10)
                    for next_id in range(target_mid + 1, target_mid + 10):
                        try:
                            next_fwd = await context.bot.forward_message(
                                chat_id=update.effective_chat.id,
                                from_chat_id=channel,
                                message_id=next_id
                            )
                            probed_msgs.append(next_fwd.message_id)
                            next_orig_date = get_msg_orig_date(next_fwd)
                            next_mg_id = getattr(next_fwd, 'media_group_id', None)

                            is_album_match = False
                            if base_mg_id and next_mg_id and base_mg_id == next_mg_id:
                                is_album_match = True
                            elif next_fwd.photo and next_orig_date and base_orig_date and abs((next_orig_date - base_orig_date).total_seconds()) <= 4:
                                is_album_match = True

                            if next_fwd.photo and is_album_match:
                                logger.info(f"   ➕ Discovered album photo at next msg_id {next_id}")
                                if next_id not in final_msg_ids:
                                    final_msg_ids.append(next_id)
                                nfid = next_fwd.photo[-1].file_id
                                if nfid not in final_file_ids:
                                    final_file_ids.append(nfid)
                            else:
                                break
                        except Exception:
                            break

        except Exception as e:
            logger.info(f"Forward probe skipped or not supported for channel {channel}: {e}")
        finally:
            for p_mid in probed_msgs:
                try:
                    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=p_mid)
                except Exception:
                    pass

    if not final_msg_ids and not final_file_ids and not post_link:
        await update.message.reply_text(
            "⚠️ <b>ورودی نامعتبر است!</b>\n\n"
            "لطفاً شماره پیام را وارد کنید (مثال: <code>452</code> یا رنج: <code>452-455</code>) "
            "یا پست را فوروارد نموده و یا عکس‌ها را مستقیماً ارسال فرمایید.\n\n"
            "❌ جهت انصراف: /cancel",
            parse_mode="HTML"
        )
        return

    final_msg_ids = sorted(list(set(final_msg_ids)))
    if not post_link and final_msg_ids:
        ch_clean = channel.replace("@", "")
        post_link = f"https://t.me/{ch_clean}/{final_msg_ids[0]}"

    # ذخیره پایدار در کش تایید شده با اطلاعات کامل مدل
    prod_model = ""
    prod_brand = ""
    prod_cat = ""
    prod_obj = None
    try:
        from search_engine import JSON_PRODUCTS
        prod_obj = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        if prod_obj:
            prod_model = str(prod_obj.get("model_number", ""))
            prod_brand = prod_obj.get("brand", "")
            prod_cat = prod_obj.get("category_name", "") or prod_obj.get("category_key", "")
    except Exception:
        pass

    clean_caption = clean_channel_caption(detected_caption) if detected_caption else ""
    if prod_obj and clean_caption:
        prod_obj["extra_description"] = clean_caption

    save_verified_product_entry(
        pid=pid,
        product_name=pname,
        channel=channel,
        message_ids=final_msg_ids,
        file_ids=final_file_ids,
        link=post_link,
        model_number=prod_model,
        brand=prod_brand,
        category=prod_cat,
        caption=clean_caption
    )
    context.user_data.pop("awaiting_product_image_link", None)

    # ارسال آنی برای کاربری که دکمه را زده بود و سایر کاربران در انتظار این کالا
    recipients = set()
    if target_uid and target_uid != 0:
        recipients.add(target_uid)
    for uid in PENDING_IMAGE_REQUESTS.get(pid, []):
        recipients.add(uid)

    sent_count = 0
    for uid in recipients:
        try:
            await send_verified_photos_to_user(context.bot, uid, pid, pname)
            sent_count += 1
        except Exception as e:
            logger.error(f"Error sending verified photos to recipient {uid}: {e}")

    PENDING_IMAGE_REQUESTS.pop(pid, None)

    # بررسی و ارسال خودکار برای کاربرانی که منتظر مدل‌های مشابه این کالا بوده‌اند
    similar_cleared_pids = []
    try:
        from search_engine import JSON_PRODUCTS
        for pending_pid, waiting_users in list(PENDING_IMAGE_REQUESTS.items()):
            if pending_pid != pid and waiting_users:
                m_pid, m_data, m_type = find_matching_verified_photos(pending_pid)
                if m_pid == pid and m_data:
                    w_prod = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pending_pid)), None)
                    w_name = w_prod.get("name", f"کالای {pending_pid}") if w_prod else f"کالای {pending_pid}"
                    w_note = f"تصاویر مربوط به سری و مدل مشابه ({pname}) می‌باشد." if pname != w_name else None
                    for w_uid in waiting_users:
                        try:
                            await send_verified_photos_to_user(context.bot, w_uid, pending_pid, w_name, photo_data=m_data, matched_note=w_note)
                            sent_count += 1
                        except Exception as e_w:
                            logger.error(f"Error sending photos to waiting user {w_uid} for similar model {pending_pid}: {e_w}")
                    similar_cleared_pids.append(pending_pid)
    except Exception as e_sim:
        logger.error(f"Error processing similar pending requests: {e_sim}")

    for sc_pid in similar_cleared_pids:
        PENDING_IMAGE_REQUESTS.pop(sc_pid, None)

    total_photos_detected = len(final_file_ids) if final_file_ids else len(final_msg_ids)
    desc_status = f"📝 <b>توضیحات تکمیلی:</b> {len(clean_caption)} کاراکتر استخراج و به مشخصات فنی کالا پیوست شد.\n" if clean_caption else ""
    await update.message.reply_text(
        f"✅ <b>تصاویر محصول با موفقیت تایید و ثبت شد!</b>\n\n"
        f"📦 <b>محصول:</b> {pname}\n"
        f"🖼 <b>تعداد تصاویر کشف شده آلبوم:</b> {total_photos_detected} عکس\n"
        f"🔗 <b>مرجع تصاویر:</b> <code>{post_link or final_msg_ids}</code>\n"
        f"{desc_status}"
        f"👥 <b>ارسال آنی برای کاربران در انتظار:</b> {sent_count} کاربر\n\n"
        f"✨ <i>از این لحظه، هر کاربری دکمه «📸 تصاویر محصول» این کالا یا مدل‌های مشابه آن را لمس کند، کل آلبوم {total_photos_detected} تایی به صورت خودکار برای او ارسال خواهد شد.</i>",
        parse_mode="HTML"
    )
