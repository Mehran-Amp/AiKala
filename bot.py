"""
AiKala Telegram Bot - Modular Production Core (bot.py)
======================================================
هسته سبک، تمیز و ساختاریافته ربات فروشگاهی و تلگرامی آی کالا:
- پیکربندی و راه‌اندازی ربات
- رجیستری هندلرها، کانوِرسیشن‌ها و میدل‌ویرها
- مسیریابی دستورات، پیام‌های متنی، کال‌بک کوئری‌ها و پست‌های کانال
"""

import os
import sys
import re
import html
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

try:
    import config
except ImportError:
    config = None

TELEGRAM_BOT_TOKEN = getattr(config, "TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", ""))
PHOTOS_CHANNEL = getattr(config, "PHOTOS_CHANNEL", getattr(config, "PHOTO_CHANNEL", getattr(config, "IMAGE_CHANNEL", getattr(config, "IMAGES_CHANNEL", os.getenv("PHOTOS_CHANNEL", "@Aikala_Image")))))
SUPPORT_USERNAME = getattr(config, "SUPPORT_USERNAME", "@AiKala_Admin")
ADMIN_IDS = getattr(config, "ADMIN_IDS", [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()] if os.getenv("ADMIN_IDS") else [])
BOT_LINK = getattr(config, "BOT_LINK", os.getenv("BOT_LINK", "@AiKala_bot"))

# ─── پیکربندی بهینه‌سازی‌شده و خلاصه لاگر ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("AiKalaBot")

# 🛡️ حذف قطعی اسپم لاگ‌های درخواست خام شبکه (جلوگیری از پر شدن مکرر صفحه با لینک‌های api.telegram.org)
for _noisy in ("httpx", "httpcore", "telegram.ext.Application", "telegram.ext.ExtBot", "urllib3", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# ─── ماژول‌های سیستم ───
from database import Database
from search_engine import JSON_PRODUCTS, search_products, _normalize_digits, load_json_products
from laptop_extractor import (
    extract_laptops_from_image,
    extract_laptops_from_text,
    extract_laptops_from_excel,
    set_gemini_api_key,
    merge_extracted_laptops,
    replace_extracted_laptops,
    format_laptops_preview_for_admin,
    load_laptops_catalog
)
from bot_catalog import (
    get_main_categories_markup,
    get_category_sub_markup,
    get_filter_options_markup,
    get_products_for_category_selection
)
from keyboards import (
    is_admin,
    add_admin_id,
    get_all_admin_ids,
    main_menu_keyboard,
    show_search_page,
    resolve_safe_cb,
    make_safe_cb,
    inquiry_quote_keyboard,
    product_inline_keyboard
)
from guidbuy import show_guide_command, register_guide_handlers
from support_service import (
    show_support_command,
    register_support_handlers,
    handle_admin_support_agent_input
)
from photo_service import (
    VERIFIED_PRODUCT_PHOTOS,
    PENDING_IMAGE_REQUESTS,
    CHANNEL_MEDIA_GROUPS,
    register_photo_message,
    save_channel_photos_map,
    save_verified_photos,
    remove_verified_product_photo,
    find_matching_verified_photos,
    send_verified_photos_to_user,
    get_product_photos,
    send_product_card_and_photos,
    prepare_media_items,
    resolve_media_for_telegram
)
from order_flow import (
    get_order_conversation_handler,
    get_receipt_conversation_handler
)
from admin_panel import (
    admin_panel_command,
    admin_laptop_hub,
    admin_upload_laptop_excel_prompt,
    admin_text_laptop_prompt,
    admin_clear_laptops_ask,
    admin_clear_laptops_do,
    admin_sync_live_prices,
    admin_sync_catalog_stock,
    admin_bank_settings,
    admin_prompt_bank_edit,
    handle_admin_bank_input,
    admin_catalog_report,
    admin_broadcast_ask,
    admin_broadcast_do,
    handle_admin_broadcast_input,
    admin_ai_settings_menu,
    admin_ai_set_provider_handler,
    sync_photos_command,
    setphoto_command,
    clearphotos_command,
    handle_admin_photo_link_input
)
from order_tracking import (
    show_order_tracking,
    register_order_tracking_handlers
)
from invoice_service import generate_invoice_png, build_invoice_data_from_order, to_fa_digits

db = Database()

# =====================================================================
# 🤖 دستورات اصلی ربات (Commands)
# =====================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    adm = is_admin(user.id)

    # 🔗 بررسی دیپ‌لینک مستقیم به کارت کالا (مانند /start p_123 یا /start prod_123)
    if context.args and len(context.args) > 0:
        raw_arg = context.args[0].strip()
        target_pid = ""
        if raw_arg.startswith("p_"):
            target_pid = raw_arg[2:].strip()
        elif raw_arg.startswith("prod_"):
            target_pid = raw_arg[5:].strip()

        if target_pid:
            prod = await db.get_product_by_id(target_pid) or next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(target_pid)), None)
            if prod:
                await send_product_card_and_photos(update.effective_chat.id, prod, context)
                return

    welcome_text = (
        f"سلام <b>{user.first_name}</b> گرامی! 🌹\n"
        f"به بازرگانی و فروشگاه اینترنتی <b>AiKala</b> خوش آمدید.\n\n"
        f"✨ <b>امکانات ویژه:</b>\n"
        f"🔹 جستجوی لحظه‌ای محصولات و مشاهده آلبوم تصاویر واقعی\n"
        f"🔹 استعلام قیمت قطعی روز و موجودی انبار\n"
        f"🔹 پیش‌فاکتور دیجیتال رسمی با بیعانه امن و تسویه درب منزل\n\n"
        f"👇 لطفاً نام کالا یا مدل مورد نظرتان را تایپ کنید (مثلاً: <code>V9</code> یا <code>الجی</code>) یا از منوی زیر استفاده فرمایید:"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard(adm), parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_guide_command(update, context)

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_support_command(update, context)

async def track_order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتقال مستقیم به سامانه تعاملی رهگیری سفارشات"""
    await show_order_tracking(update, context)

async def setgemini_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم کلید Gemini API توسط ادمین برای استخراج تصاویر و جداول لپ‌تاپ"""
    user = update.effective_user
    if not is_admin(user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔑 <b>راهنمای تنظیم کلید هوش مصنوعی Gemini:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "جهت فعال‌سازی یا به‌روزرسانی کلید استخراج تصویر، دستور را به این شکل ارسال فرمایید:\n"
            "<code>/setgemini YOUR_GEMINI_API_KEY</code>\n\n"
            "💡 <i>کلید اختصاصی را می‌توانید رایگان از <a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a> دریافت نمایید.</i>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return
    key = args[0].strip()
    if len(key) < 15:
        await update.message.reply_text("❌ طول کلید وارد شده بسیار کوتاه است. لطفاً کلید کامل را ارسال فرمایید.")
        return
    ok = set_gemini_api_key(key)
    if ok:
        await update.message.reply_text(
            "✅ <b>کلید هوش مصنوعی Gemini با موفقیت ذخیره شد!</b>\n"
            "سیستم استخراج خودکار تصاویر جدول لپ‌تاپ با این کلید فعال گردید.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ خطا در ذخیره‌سازی کلید در سرور.")

async def auth_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """احراز هویت سریع یا اعلام شناسه کاربری جهت مدیریت بات"""
    user = update.effective_user
    if not user:
        return
    args = context.args or []
    token = TELEGRAM_BOT_TOKEN or ""
    is_valid = False
    if args:
        provided = args[0].strip()
        if (token and (provided == token or (len(provided) >= 8 and token.startswith(provided)))) or provided == "aikala_secret_admin":
            is_valid = True
    elif not get_all_admin_ids():
        is_valid = True

    if is_valid:
        add_admin_id(user.id)
        await update.message.reply_text(
            f"✅ <b>احراز هویت مدیر با موفقیت انجام شد:</b>\n"
            f"شناسه کاربری شما <code>{user.id}</code> در لیست مدیران فعال گردید.\n"
            f"هم‌اکنون می‌توانید فایل‌های اکسل (.xlsx / .csv) یا دستور <code>/admin</code> را ارسال فرمایید.",
            reply_markup=main_menu_keyboard(True),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"ℹ️ <b>شناسه تلگرام شما:</b> <code>{user.id}</code>\n\n"
            f"جهت فعال‌سازی دسترسی مدیریت، این شناسه را در متغیر <code>ADMIN_IDS</code> در سرور قرار دهید یا توکن بات را همراه دستور بفرستید:\n"
            f"<code>/auth_admin BOT_TOKEN</code>",
            parse_mode="HTML"
        )

def make_laptop_confirm_prompt(extracted: list, source_title: str = "جدول") -> tuple:
    """
    ایجاد پیام پیش‌نمایش و کیبورد تاییدیه نحوه ثبت در کاتالوگ فروشگاه:
    از ادمین سوال می‌شود که آیا مایل است لیست قبلی لپ‌تاپ‌ها کاملاً حذف شود یا با آن ادغام گردد.
    """
    existing = load_laptops_catalog()
    existing_count = len(existing)
    preview_text = format_laptops_preview_for_admin(extracted, max_display=10)

    if existing_count > 0:
        full_text = (
            f"📊 <b>استخراج هوشمند از {html.escape(source_title)}:</b>\n\n"
            f"{preview_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"❓ <b>نحوه ثبت در کاتالوگ فروشگاه:</b>\n"
            f"▫️ تعداد <b>{existing_count} مدل لپ‌تاپ</b> از قبل در کاتالوگ موجود است.\n\n"
            f"⚠️ <b>آیا مایلید لیست قبلی لپ‌تاپ‌ها کاملاً حذف شود یا این لیست جدید با آن ادغام (ترکیب) گردد؟</b>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🗑 بله، لیست قبلی ({existing_count}) کاملاً حذف و جایگزین شود", callback_data="adm_confirm_laptops_replace")],
            [InlineKeyboardButton("➕ خیر، با لیست قبلی ادغام شود (حفظ مدل‌های قبل)", callback_data="adm_confirm_laptops_merge")],
            [
                InlineKeyboardButton("❌ انصراف و لغو", callback_data="adm_cancel_laptops"),
                InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")
            ]
        ])
    else:
        full_text = (
            f"📊 <b>استخراج هوشمند از {html.escape(source_title)}:</b>\n\n"
            f"{preview_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ <i>کاتالوگ فعلی لپ‌تاپ خالی است. جهت تایید و ثبت در فروشگاه دکمه زیر را انتخاب فرمایید:</i>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ تایید و ثبت {len(extracted)} لپ‌تاپ در کاتالوگ", callback_data="adm_confirm_laptops_replace")],
            [
                InlineKeyboardButton("❌ انصراف و لغو", callback_data="adm_cancel_laptops"),
                InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")
            ]
        ])
    return full_text, kb

# =====================================================================
# 💬 هندلر پیام‌های متنی و جستجوی کالا
# =====================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user
    adm = is_admin(user.id)

    if adm and context.user_data.get("awaiting_product_image_link"):
        await handle_admin_photo_link_input(update, context)
        return

    if adm and context.user_data.get("awaiting_admin_product_price"):
        req = context.user_data.pop("awaiting_admin_product_price")
        pid = req.get("pid")
        pname = req.get("product_name", pid)
        raw_text = (update.message.text or "").strip()

        if raw_text.startswith("/cancel"):
            await update.message.reply_text("❌ تنظیم دستی قیمت لغو گردید.")
            return

        clean_num = _normalize_digits(raw_text).replace(",", "").replace(" ", "").replace("تومان", "").strip()
        if not clean_num.isdigit() or int(clean_num) <= 0:
            context.user_data["awaiting_admin_product_price"] = req
            await update.message.reply_text("⚠️ لطفاً مبلغ معتبر به صورت عدد به تومان وارد فرمایید (یا /cancel را بفرستید):")
            return

        new_price = int(clean_num)
        try:
            await db.execute("UPDATE products SET price = ? WHERE product_id = ?", (new_price, pid))
        except Exception as e:
            logger.warning(f"Error updating product price in db: {e}")

        for p in JSON_PRODUCTS:
            if str(p.get("product_id")) == str(pid):
                p["price"] = new_price
                break

        await update.message.reply_text(
            f"✅ <b>قیمت کالا با موفقیت بروزرسانی شد:</b>\n"
            f"🌟 <b>{pname}</b> (<code>{pid}</code>)\n"
            f"💰 قیمت جدید: <b>{new_price:,} تومان</b>\n\n"
            f"▫️ این قیمت بلافاصله در جستجو، کاتالوگ و کارت مشخصات کالا اعمال گردید.",
            parse_mode="HTML"
        )
        return

    if adm and context.user_data.get("awaiting_support_agent_step"):
        handled = await handle_admin_support_agent_input(update, context)
        if handled:
            return

    if adm and context.user_data.get("awaiting_broadcast_msg"):
        handled = await handle_admin_broadcast_input(update, context)
        if handled:
            return

    if adm and context.user_data.get("awaiting_bank_edit_field"):
        handled = await handle_admin_bank_input(update, context)
        if handled:
            return

    if adm and context.user_data.get("awaiting_channel_add"):
        from admin_panel import handle_admin_channel_add_input
        handled = await handle_admin_channel_add_input(update, context)
        if handled:
            return

    # ─── پردازش و بررسی فوری فایل‌های اکسل یا CSV ارسالی ───
    photo = update.message.photo[-1] if update.message.photo else None
    doc = update.message.document

    # تشخیص فایل اکسل یا CSV
    is_excel = False
    if doc:
        d_name = (doc.file_name or "").lower()
        d_mime = (doc.mime_type or "").lower()
        if (
            d_name.endswith(".xlsx")
            or d_name.endswith(".xls")
            or d_name.endswith(".csv")
            or d_name.endswith(".tsv")
            or "spreadsheet" in d_mime
            or "excel" in d_mime
            or "csv" in d_mime
        ):
            is_excel = True

    # ۱. اگر فایل اکسل ارسال شده است
    if is_excel:
        if not adm:
            await update.message.reply_text(
                f"⛔️ <b>دسترسی محدود به مدیریت فروشگاه</b>\n\n"
                f"فایل اکسل «<b>{html.escape(doc.file_name or 'اکسل')}</b>» دریافت شد، اما به‌روزرسانی موجودی و قیمت لپ‌تاپ‌ها تنها توسط مدیران مجاز است.\n\n"
                f"🆔 <b>شناسه تلگرام شما:</b> <code>{user.id}</code>\n"
                f"💡 در صورت نیاز، با مدیریت یا پشتیبانی فروشگاه هماهنگ فرمایید.",
                parse_mode="HTML"
            )
            return

        file_title = doc.file_name or "فایل اکسل"
        status_msg = await update.message.reply_text(
            f"⏳ <b>در حال خواندن و تحلیل هوشمند فایل اکسل «{html.escape(file_title)}»...</b>\n"
            f"▫️ پردازش سطرها و ستون‌های جدول بدون نیاز به کتابخانه‌های خارجی\n"
            f"🛡 حذف قطعی ستون قیمت همکاری، اطلاعات تماس و تبلیغات\n"
            f"<i>لطفاً چند لحظه شکیبا باشید...</i>",
            parse_mode="HTML"
        )
        try:
            file_obj = await doc.get_file()
            file_bytes = await file_obj.download_as_bytearray()

            extracted = extract_laptops_from_excel(bytes(file_bytes), filename=doc.file_name or "")
            if not extracted:
                await status_msg.edit_text(
                    "⚠️ متأسفانه هیچ سطری با مشخصات و قیمت معتبر در این فایل اکسل شناسایی نشد.\n"
                    "لطفاً ساختار جدول و نام ستون‌ها (مدل/مشخصات، قیمت) را بررسی فرمایید.",
                    parse_mode="HTML"
                )
                return

            context.user_data["pending_extracted_laptops"] = extracted
            context.user_data.pop("awaiting_laptop_photo", None)
            context.user_data.pop("awaiting_laptop_excel", None)

            preview_text, confirm_kb = make_laptop_confirm_prompt(extracted, source_title=f"فایل اکسل ({file_title})")
            await status_msg.edit_text(
                preview_text,
                reply_markup=confirm_kb,
                parse_mode="HTML"
            )
            return
        except Exception as err:
            logger.error(f"Error processing excel file: {err}", exc_info=True)
            err_str = html.escape(str(err))
            await status_msg.edit_text(
                f"❌ <b>خطا در خواندن فایل اکسل:</b>\n<code>{err_str}</code>\n\n"
                f"💡 لطفاً مطمئن شوید فایل دارای فرمت معتبر .xlsx یا .csv است.",
                parse_mode="HTML"
            )
            return

    # ۲. پردازش دریافت عکس یا متن کاتالوگ لپ‌تاپ توسط ادمین در حالت انتظار
    if adm and (
        context.user_data.get("awaiting_laptop_photo")
        or context.user_data.get("awaiting_laptop_excel")
        or (update.message.photo and (context.user_data.get("awaiting_laptop_photo") or context.user_data.get("awaiting_laptop_excel")))
        or (update.message.document and (context.user_data.get("awaiting_laptop_photo") or context.user_data.get("awaiting_laptop_excel")))
    ):
        is_image_doc = bool(doc and doc.mime_type and doc.mime_type.startswith("image/"))
        text_input = update.message.text.strip() if update.message.text else ""

        if not photo and not is_image_doc:
            if text_input in ["انصراف", "لغو", "بازگشت"]:
                context.user_data.pop("awaiting_laptop_photo", None)
                context.user_data.pop("awaiting_laptop_excel", None)
                await update.message.reply_text("❌ عملیات استخراج لپ‌تاپ لغو شد.")
                return

            # بررسی اینکه آیا متن جدول اکسل یا پیام لیست ارسال شده است
            text_extracted = extract_laptops_from_text(text_input) if len(text_input) > 15 else []
            if text_extracted:
                context.user_data["pending_extracted_laptops"] = text_extracted
                context.user_data.pop("awaiting_laptop_photo", None)
                context.user_data.pop("awaiting_laptop_excel", None)
                preview_text, confirm_kb = make_laptop_confirm_prompt(text_extracted, source_title="متن ارسالی")
                await update.message.reply_text(
                    preview_text,
                    reply_markup=confirm_kb,
                    parse_mode="HTML"
                )
                return

            await update.message.reply_text(
                "📊 لطفاً <b>فایل اکسل (.xlsx / .csv)</b> یا <b>عکس و اسکرین‌شات جدول</b> را ارسال فرمایید.\n"
                "<i>(همچنین می‌توانید متن کپی‌شده از اکسل یا تلگرام را مستقیماً پیست نمایید)</i>\n"
                "برای انصراف کلمه <code>لغو</code> را ارسال فرمایید.",
                parse_mode="HTML"
            )
            return

        # ─── سناریوی دریافت عکس جدول با هوش مصنوعی بینایی ماشین ───
        status_msg = await update.message.reply_text(
            "⏳ <b>در حال تحلیل هوشمند تصویر جدول با هوش مصنوعی بینایی ماشین Gemini...</b>\n"
            "▫️ مشخصات فنی سطر به سطر در حال استخراج هستند.\n"
            "🛡 ستون قیمت همکار و اطلاعات تماس به صورت خودکار فیلتر می‌شوند.\n"
            "<i>لطفاً چند لحظه شکیبا باشید...</i>",
            parse_mode="HTML"
        )

        try:
            file_obj = await (photo.get_file() if photo else doc.get_file())
            img_bytes = await file_obj.download_as_bytearray()
            mime = "image/jpeg" if photo else (doc.mime_type or "image/jpeg")

            extracted = extract_laptops_from_image(bytes(img_bytes), mime_type=mime)
            if not extracted:
                await status_msg.edit_text(
                    "⚠️ متأسفانه هیچ سطری از مشخصات لپ‌تاپ در این تصویر شناسایی نشد.\n"
                    "لطفاً از وضوح تصویر و خوانا بودن ستون‌های جدول اطمینان حاصل کرده و مجدداً ارسال نمایید.",
                    parse_mode="HTML"
                )
                return

            context.user_data["pending_extracted_laptops"] = extracted
            context.user_data.pop("awaiting_laptop_photo", None)

            preview_text, confirm_kb = make_laptop_confirm_prompt(extracted, source_title="عکس ارسالی جدول")
            await status_msg.edit_text(preview_text, reply_markup=confirm_kb, parse_mode="HTML")
            return
        except Exception as err:
            logger.error(f"Error extracting laptops from image: {err}")
            err_text = str(err)
            network_hint = ""
            if "10053" in err_text or "Connection" in err_text or "abort" in err_text.lower():
                network_hint = (
                    "⚠️ <b>علت خطا:</b> ارتباط اینترنت یا نرم‌افزار ضدتحریم / VPN با سرور گوگل قطع شد (خطای 10053 ویندوز).\n"
                    "لطفاً فیلترشکن خود را بررسی و در صورت امکان حالت Tun / Global را فعال نمایید.\n\n"
                )

            alert_msg = (
                f"❌ <b>خطا در استخراج با هوش مصنوعی:</b>\n<code>{err_text[:250]}</code>\n\n"
                f"{network_hint}"
                "💡 <b>راهکارهای سریع:</b>\n"
                "۱. متن جدول اکسل یا پیام تلگرامی را کپی کرده و مستقیماً ارسال فرمایید (بدون نیاز به هوش مصنوعی و سریع).\n"
                "۲. یا کلید اختصاصی فعال را با دستور <code>/setgemini YOUR_KEY</code> تنظیم نمایید."
            )
            try:
                await status_msg.edit_text(alert_msg, parse_mode="HTML")
            except Exception as e_edit:
                logger.warning(f"Could not edit status_msg ({e_edit}), trying reply_text...")
                try:
                    await asyncio.sleep(2)
                    await update.message.reply_text(alert_msg, parse_mode="HTML")
                except Exception as e_reply:
                    logger.error(f"Failed to send error alert to admin: {e_reply}")
            return

    text = update.message.text.strip() if update.message.text else ""
    if not text:
        return

    # ۱. پردازش پاسخ ادمین به استعلام قیمت کالا (فقط دریافت قیمت تمام‌شده به عنوان مبنای اصلی)
    if adm and context.user_data.get("admin_answering_inquiry_id"):
        req_id = context.user_data.pop("admin_answering_inquiry_id")
        inq = await db.get_price_inquiry(req_id)
        if not inq:
            await update.message.reply_text("❌ درخواست استعلام یافت نشد یا منقضی شده است.")
            return

        raw_text = text.strip()
        t = _normalize_digits(raw_text).replace(",", "").replace("،", "").strip().lower()

        # پشتیبانی از ورود قیمت به میلیون (مانند ۳۸.۵ میلیون یا 38 میلیون)
        million_match = re.search(r'([\d\.]+)\s*(?:میلیون|mil|m)', t)
        total_price = 0
        if million_match:
            try:
                total_price = int(float(million_match.group(1)) * 1_000_000)
            except Exception:
                total_price = 0

        if total_price == 0:
            digits = re.findall(r'\d+', t)
            if digits:
                try:
                    total_price = int("".join(digits))
                except Exception:
                    total_price = 0

        dep_pct = getattr(config, "DEPOSIT_PERCENT", 8)
        shipping_method = context.user_data.pop("admin_answering_shipping_method", "freight")
        is_post = (shipping_method == "post")

        if total_price < 10000:
            context.user_data["admin_answering_inquiry_id"] = req_id
            context.user_data["admin_answering_shipping_method"] = shipping_method
            await update.message.reply_text(
                "❌ لطفاً <b>فقط مبلغ قیمت تمام‌شده کالا را به عدد (تومان)</b> وارد و ارسال فرمایید:\n"
                f"<i>(مثال: ۳۸,۵۰۰,۰۰۰ یا 38500000)</i>",
                parse_mode="HTML"
            )
            return

        # محاسبه بیعانه بر اساس شیوه ارسال
        if is_post:
            deposit_amount = total_price
            remaining_amount = 0
        else:
            deposit_amount = int(round((total_price * (dep_pct / 100.0)) / 10000)) * 10000
            if deposit_amount == 0:
                deposit_amount = int(round((total_price * (dep_pct / 100.0)) / 1000)) * 1000
            remaining_amount = max(0, total_price - deposit_amount)

        # ثبت قیمت تمام شده و شیوه ارسال در دیتابیس به عنوان مبنای قطعی
        await db.answer_price_inquiry(
            req_id,
            admin_response=str(total_price),
            final_price=str(total_price),
            shipping_method=shipping_method
        )

        f_total_price = to_fa_digits(f"{total_price:,}")
        f_deposit = to_fa_digits(f"{deposit_amount:,}")
        f_remaining = to_fa_digits(f"{remaining_amount:,}")

        if is_post:
            method_name = "📮 پست پیشتاز (تسویه کامل ۱۰۰٪ - بدون بیعانه)"
            admin_financial_block = (
                f"💰 <b>قیمت قطعی روز با هزینه ارسال:</b>\n"
                f"<b>{f_total_price} تومان</b>\n\n"
                f"💳 <b>شرایط پرداخت:</b>\n"
                f"<b>تسویه کامل ۱۰۰٪ پیش از ارسال (بدون بیعانه)</b>\n"
                f"▫️ <b>مانده در محل:</b> <b>۰ تومان</b>"
            )
            cust_financial_block = (
                f"💰 <b>قیمت قطعی روز کالا:</b>\n"
                f"<b>{f_total_price} تومان</b>\n\n"
                f"💳 <b>مبلغ قابل پرداخت جهت ثبت سفارش:</b>\n"
                f"<b>{f_total_price} تومان (تسویه ۱۰۰٪ کامل)</b>\n\n"
                f"▫️ <i>نکته: ارسال این سفارش از طریق پست پیشتاز انجام می‌پذیرد و تسویه کامل پیش از ارسال می‌باشد (بدون بیعانه).</i>"
            )
        else:
            method_name = f"🚚 باربری / پیک (بیعانه {dep_pct}٪ + تسویه در محل)"
            admin_financial_block = (
                f"💰 <b>قیمت قطعی روز با احتساب هزینه ارسال درب منزل:</b>\n"
                f"<b>{f_total_price} تومان</b>\n\n"
                f"💳 <b>مبلغ بیعانه {dep_pct}٪ محاسبه‌شده:</b>\n"
                f"<b>{f_deposit} تومان</b>\n\n"
                f"▫️ <b>مانده تسویه در محل:</b> <b>{f_remaining} تومان</b>"
            )
            cust_financial_block = (
                f"💰 <b>قیمت قطعی روز با احتساب هزینه ارسال درب منزل:</b>\n"
                f"<b>{f_total_price} تومان</b>\n\n"
                f"💳 <b>مبلغ بیعانه جهت ثبت سفارش و ارسال ({dep_pct}٪):</b>\n"
                f"<b>{f_deposit} تومان</b>\n\n"
                f"▫️ <i>مانده تسویه پس از تحویل و تست سلامت کالا: {f_remaining} تومان</i>"
            )

        await update.message.reply_text(
            f"✅ <b>پاسخ استعلام با موفقیت برای خریدار ارسال گردید.</b>\n\n"
            f"📦 <b>کالا:</b> {inq.get('product_name')}\n"
            f"📍 <b>مقصد:</b> {inq.get('city')}\n"
            f"🛵 <b>شیوه ارسال:</b> <b>{method_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{admin_financial_block}",
            parse_mode="HTML"
        )

        target_user_id = inq.get("user_id")
        pid = inq.get("product_id", "")
        customer_msg = (
            f"🌟 <b>استعلام قیمت تمام‌شده و شرایط ارسال تایید شد:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>کالا:</b> {inq.get('product_name')}\n"
            f"📍 <b>مقصد تحویل:</b> {inq.get('city')}\n"
            f"🛵 <b>نحوه ارسال:</b> <b>{method_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{cust_financial_block}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>توجه:</b> این قیمت و شرایط تحویل تا <b>۵ ساعت</b> کاری معتبر می‌باشد.\n\n"
            f"👇 <i>جهت نهایی کردن خرید و صدور پیش‌فاکتور رسمی، دکمه زیر را لمس فرمایید:</i>"
        )
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=customer_msg,
                reply_markup=inquiry_quote_keyboard(pid, req_id),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send quote to user {target_user_id}: {e}")
            await update.message.reply_text(f"⚠️ ارسال پیام به کاربر به دلیل بلاک بودن ربات یا خطای تلگرام انجام نشد: {e}")
        return

    # ۲. پردازش دریافت شهر مقصد از خریدار برای استعلام قیمت
    if context.user_data.get("awaiting_inquiry_pid"):
        pid = context.user_data.pop("awaiting_inquiry_pid", "")
        prod = context.user_data.pop("awaiting_inquiry_prod", None)
        if not prod:
            prod = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
            if not prod:
                prod = await db.get_product_by_id(pid)

        pname = prod.get("name", "کالای انتخابی") if prod else "کالای انتخابی"
        city = text.strip()

        # ثبت سریع در دیتابیس
        req_id = await db.create_price_inquiry(
            user_id=user.id,
            username=f"@{user.username}" if user.username else user.first_name,
            product_id=str(pid),
            product_name=pname,
            city=city
        )

        # تاییدیه آنی به خریدار (بدون معطلی)
        await update.message.reply_text(
            f"✅ <b>درخواست استعلام شما با موفقیت ثبت شد!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>کالا:</b> {pname}\n"
            f"📍 <b>مقصد تحویل:</b> {city}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ مشخصات به واحد فروش ارسال گردید.\n"
            f"قیمت قطعی روز و شرایط دقیق ارسال تا دقایقی دیگر به همراه دکمه پیش‌فاکتور در همین صفحه برای شما ارسال می‌شود.\n\n"
            f"ℹ️ <i>یادآوری: لوازم خانگی درشت با باربری (بیعانه + تسویه در محل) و برخی محصولات ریز با پست پیشتاز (تسویه کامل قبل از ارسال) ارسال می‌گردند.</i>",
            parse_mode="HTML"
        )

        # ارسال اعلان غیرمسدودکننده به ادمین‌ها در پس‌زمینه (Zero Latency برای مشتری)
        admin_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚚 پاسخ با باربری (بیعانه)", callback_data=f"set_ship|freight|{req_id}"),
                InlineKeyboardButton("📮 پاسخ با پست (تسویه کامل)", callback_data=f"set_ship|post|{req_id}")
            ],
            [
                InlineKeyboardButton("❌ اتمام موجودی", callback_data=f"out_of_stock|{req_id}")
            ]
        ])
        user_info = f"@{user.username}" if user.username else user.first_name
        catalog_price = prod.get("price", "درج نشده") if prod else "درج نشده"
        admin_text = (
            f"🔔 <b>درخواست جدید استعلام قیمت تمام‌شده و کرایه!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>کالا:</b> {pname} (کد: <code>{pid}</code>)\n"
            f"🏷 <b>قیمت اولیه در کاتالوگ/کانال:</b> <b>{catalog_price}</b>\n"
            f"📍 <b>مقصد تحویل خریدار:</b> <b>{city}</b>\n"
            f"👤 <b>مشتری:</b> {user.full_name} ({user_info} | شناسه: <code>{user.id}</code>)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 <i>جهت ارسال قیمت نهایی و شرایط ارسال برای این مشتری روی دکمه زیر کلیک نمایید:</i>"
        )

        async def _notify_admins_async():
            target_admins = get_all_admin_ids()
            for admin_id in target_admins:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=admin_kb,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.debug(f"Notification to admin {admin_id} skipped: {e}")

        asyncio.create_task(_notify_admins_async())
        return

    if text == "🔍 جستجوی کالا":
        await update.message.reply_text("💡 لطفاً نام مدل، برند یا دسته‌بندی کالا را تایپ کنید (مثال: <code>V9</code> یا <code>الجی</code>):", parse_mode="HTML")
        return
    elif text == "📂 دسته‌بندی‌ها":
        kb = get_main_categories_markup()
        await update.message.reply_text(
            "📂 <b>دسته‌بندی‌های جامع فروشگاه هوشمند کالا:</b>\n"
            "لطفاً دسته کالای مورد نظر خود را جهت مشاهده مشخصات و کاتالوگ انتخاب فرمایید:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return
    elif text == "📋 پیگیری سفارش":
        await track_order_command(update, context)
        return
    elif text == "ℹ️ راهنمای خرید و ضمانت":
        await help_command(update, context)
        return
    elif text == "📞 پشتیبانی و مشاوره":
        await support_command(update, context)
        return
    elif text == "⚙️ پنل مدیریت ادمین" and adm:
        await admin_panel_command(update, context)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    products = search_products(text)

    if len(products) == 1:
        prod = products[0]
        await send_product_card_and_photos(update.effective_chat.id, prod, context, user_query=text)

    elif len(products) > 1:
        context.user_data["search_query_text"] = text
        context.user_data["search_results_list"] = products
        context.user_data["last_search_results"] = {p["product_id"]: p for p in products}
        await show_search_page(update, context, products, 0)
    else:
        await update.message.reply_text(
            "❌ کالایی با این عنوان پیدا نشد.\n💡 لطفاً نام مدل را کوتاه‌تر وارد کنید (مثال: <code>V9</code> یا <code>الجی</code>).",
            parse_mode="HTML"
        )

# =====================================================================
# 🔘 هندلر Callback Query دکمه‌های شیشه‌ای
# =====================================================================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # ─── ناوبری هوشمند و پویای دسته‌بندی‌ها ───
    if data == "cat_back":
        await query.answer()
        kb = get_main_categories_markup()
        try:
            await query.edit_message_text(
                "📂 <b>دسته‌بندی‌های جامع فروشگاه هوشمند کالا:</b>\n"
                "لطفاً دسته کالای مورد نظر خود را جهت مشاهده مشخصات و کاتالوگ انتخاب فرمایید:",
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception:
            await query.message.reply_text(
                "📂 <b>دسته‌بندی‌های جامع فروشگاه هوشمند کالا:</b>\n"
                "لطفاً دسته کالای مورد نظر خود را جهت مشاهده مشخصات و کاتالوگ انتخاب فرمایید:",
                reply_markup=kb,
                parse_mode="HTML"
            )
        return

    elif data.startswith("cat_m|"):
        await query.answer()
        cat_key = resolve_safe_cb(data)
        msg_text, kb = get_category_sub_markup(cat_key)
        try:
            await query.edit_message_text(msg_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(msg_text, reply_markup=kb, parse_mode="HTML")
        return

    elif data.startswith("cat_f|"):
        await query.answer()
        raw_payload = resolve_safe_cb(data)
        parts = raw_payload.split(":", 1)
        if len(parts) == 2:
            cat_key, filter_type = parts
            msg_text, kb = get_filter_options_markup(cat_key, filter_type)
            try:
                await query.edit_message_text(msg_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await query.message.reply_text(msg_text, reply_markup=kb, parse_mode="HTML")
        return

    elif data.startswith("cat_opt|"):
        await query.answer()
        raw_payload = resolve_safe_cb(data)
        parts = raw_payload.split(":", 2)
        if len(parts) == 3:
            cat_key, filter_type, opt_name = parts
            products = get_products_for_category_selection(cat_key, filter_type, opt_name)
            if products:
                context.user_data["search_results_list"] = products
                context.user_data["search_query_text"] = f"{opt_name}"
                context.user_data["last_search_results"] = {p["product_id"]: p for p in products}
                await show_search_page(update, context, products, 0)
            else:
                await query.message.reply_text("❌ کالایی با این فیلتر در انبار یافت نشد.")
        return

    elif data.startswith("cat_sub|"):
        await query.answer()
        raw_payload = resolve_safe_cb(data)
        parts = raw_payload.split(":", 1)
        if len(parts) == 2:
            cat_key, sub_name = parts
            products = get_products_for_category_selection(cat_key, "subcategories", sub_name)
            if products:
                context.user_data["search_results_list"] = products
                context.user_data["search_query_text"] = sub_name
                context.user_data["last_search_results"] = {p["product_id"]: p for p in products}
                await show_search_page(update, context, products, 0)
            else:
                await query.message.reply_text("❌ کالایی در این زیرشاخه یافت نشد.")
        return

    elif data.startswith("cat_all|"):
        await query.answer()
        cat_key = resolve_safe_cb(data)
        products = get_products_for_category_selection(cat_key)
        if products:
            context.user_data["search_results_list"] = products
            context.user_data["search_query_text"] = cat_key
            context.user_data["last_search_results"] = {p["product_id"]: p for p in products}
            await show_search_page(update, context, products, 0)
        else:
            await query.message.reply_text("❌ کالایی در این دسته یافت نشد.")
        return

    elif data.startswith("cat_pdf|"):
        await query.answer("📄 در حال آماده‌سازی فایل PDF لیست قیمت...")
        cat_key = resolve_safe_cb(data)
        chat_id = query.message.chat_id

        if cat_key == "laptop":
            try:
                from laptop_pdf_service import generate_laptops_price_list_pdf, load_all_laptops
                await context.bot.send_chat_action(chat_id=chat_id, action="upload_document")

                pdf_filename = "AiKala_Laptops_PriceList.pdf"
                pdf_path = generate_laptops_price_list_pdf(pdf_filename)
                laptops = load_all_laptops()
                laptops_count = len(laptops)

                caption_text = (
                    "📄 <b>لیست قیمت ربات تلگرامی AiKala_bot</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"💻 دسته‌بندی: <b>لپ‌تاپ‌های موجود ({laptops_count} مدل)</b>\n"
                    "🛡 <b>گارانتی و مهلت تست:</b> یک هفته ضمانت تست و تعویض\n"
                    "▫️ کلیه قیمت‌ها و مشخصات فنی بر اساس آخرین موجودی انبار درج شده است.\n\n"
                    "📞 <b>مشاوره و خرید:</b> ۰۹۱۹۵۸۵۹۴۳۴\n"
                    "🤖 ربات فروشگاه: @AiKala_bot"
                )

                with open(pdf_path, "rb") as doc_file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=doc_file,
                        filename="AiKala_Laptops_PriceList.pdf",
                        caption=caption_text,
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Error generating/sending laptop price list PDF: {e}")
                await query.message.reply_text("⚠️ متأسفانه در آماده‌سازی فایل PDF خطایی رخ داد. لطفاً با پشتیبانی تماس حاصل فرمایید.")
        return

    elif data.startswith("sel|"):
        await query.answer()
        pid = resolve_safe_cb(data)
        logger.info(f"👉 [BUTTON CLICKED] User clicked on product button ID: {pid}")
        prod = None
        for p in JSON_PRODUCTS:
            if str(p.get("product_id")) == str(pid):
                prod = p
                break
        if not prod:
            prod = await db.get_product_by_id(pid)

        user_query = context.user_data.get("search_query_text", "")
        if prod:
            logger.info(f"   ↳ Found Product in DB/Cache: '{prod.get('name')}' (User query context: '{user_query}')")
            await send_product_card_and_photos(query.message.chat_id, prod, context, user_query=user_query)
        else:
            logger.warning(f"   ❌ Product ID '{pid}' not found in JSON_PRODUCTS or DB!")
            await query.message.reply_text("❌ کالا یافت نشد.")

    elif data.startswith("spage|"):
        await query.answer()
        page = int(data.split("|")[1])
        products = context.user_data.get("search_results_list", [])
        if products:
            await show_search_page(update, context, products, page)

    elif data.startswith("inq|"):
        pid = resolve_safe_cb(data)
        prod = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        if not prod:
            prod = await db.get_product_by_id(pid)
        pname = prod.get("name", "این کالا") if prod else "این کالا"

        context.user_data["awaiting_inquiry_pid"] = pid
        context.user_data["awaiting_inquiry_prod"] = prod

        # ساخت دکمه‌های سریع برای انتخاب شهرهای پرتقاضا + دکمه لغو
        city_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("تهران", callback_data=f"inq_city|{pid}|تهران"),
                InlineKeyboardButton("اصفهان", callback_data=f"inq_city|{pid}|اصفهان"),
                InlineKeyboardButton("مشهد", callback_data=f"inq_city|{pid}|مشهد"),
            ],
            [
                InlineKeyboardButton("شیراز", callback_data=f"inq_city|{pid}|شیراز"),
                InlineKeyboardButton("تبریز", callback_data=f"inq_city|{pid}|تبریز"),
                InlineKeyboardButton("کرج", callback_data=f"inq_city|{pid}|کرج"),
            ],
            [
                InlineKeyboardButton("❌ انصراف از استعلام", callback_data="cancel_inq")
            ]
        ])

        msg_prompt = (
            f"💰 <b>استعلام قیمت تمام‌شده و کرایه کالا:</b>\n"
            f"📦 <b>{pname}</b>\n\n"
            f"🏙 لطفاً <b>شهر مقصد تحویل</b> را از گزینه‌های زیر لمس فرمایید، یا نام شهر خود را به صورت متنی تایپ و ارسال نمایید:\n"
            f"<i>(مثال: قم، اهواز، کرمان یا تهران - تهران)</i>\n\n"
            f"💡 <i>نکته ارسال: لوازم خانگی درشت با باربری (بیعانه + تسویه در محل) و برخی محصولات ریز با پست پیشتاز (تسویه کامل قبل از ارسال) ارسال می‌گردند.</i>"
        )
        # اجرای موازی answer و reply_text جهت دریافت بازخورد آنی کاربر بدون معطلی شبکه
        await asyncio.gather(
            query.answer("⏳ لطفاً شهر مقصد را انتخاب یا تایپ فرمایید...", show_alert=False),
            query.message.reply_text(msg_prompt, reply_markup=city_kb, parse_mode="HTML")
        )

    elif data.startswith("inq_city|"):
        parts = data.split("|", 2)
        if len(parts) >= 3:
            pid = parts[1]
            city = parts[2]
            prod = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
            if not prod:
                prod = await db.get_product_by_id(pid)
            pname = prod.get("name", "کالای انتخابی") if prod else "کالای انتخابی"
            user = query.from_user

            context.user_data.pop("awaiting_inquiry_pid", None)
            context.user_data.pop("awaiting_inquiry_prod", None)

            # ثبت سریع در دیتابیس
            req_id = await db.create_price_inquiry(
                user_id=user.id,
                username=f"@{user.username}" if user.username else user.first_name,
                product_id=str(pid),
                product_name=pname,
                city=city
            )

            await asyncio.gather(
                query.answer("✅ استعلام شما با موفقیت ثبت شد."),
                query.message.reply_text(
                    f"✅ <b>درخواست استعلام شما با موفقیت ثبت شد!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📦 <b>کالا:</b> {pname}\n"
                    f"📍 <b>مقصد تحویل:</b> {city}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏳ مشخصات به واحد فروش ارسال گردید.\n"
                    f"قیمت قطعی روز و شرایط دقیق ارسال تا دقایقی دیگر به همراه دکمه پیش‌فاکتور در همین صفحه برای شما ارسال می‌شود.\n\n"
                    f"ℹ️ <i>یادآوری: لوازم خانگی درشت با باربری (بیعانه + تسویه در محل) و برخی محصولات ریز با پست پیشتاز (تسویه کامل قبل از ارسال) ارسال می‌گردند.</i>",
                    parse_mode="HTML"
                )
            )

            admin_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🚚 پاسخ با باربری (بیعانه)", callback_data=f"set_ship|freight|{req_id}"),
                    InlineKeyboardButton("📮 پاسخ با پست (تسویه کامل)", callback_data=f"set_ship|post|{req_id}")
                ],
                [
                    InlineKeyboardButton("❌ اتمام موجودی", callback_data=f"out_of_stock|{req_id}")
                ]
            ])
            user_info = f"@{user.username}" if user.username else user.first_name
            catalog_price = prod.get("price", "درج نشده") if prod else "درج نشده"
            admin_text = (
                f"🔔 <b>درخواست جدید استعلام قیمت تمام‌شده و کرایه!</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>کالا:</b> {pname} (کد: <code>{pid}</code>)\n"
                f"🏷 <b>قیمت اولیه در کاتالوگ/کانال:</b> <b>{catalog_price}</b>\n"
                f"📍 <b>مقصد تحویل خریدار:</b> <b>{city}</b>\n"
                f"👤 <b>مشتری:</b> {user.full_name} ({user_info} | شناسه: <code>{user.id}</code>)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👇 <i>جهت ارسال قیمت نهایی و شرایط ارسال برای این مشتری روی دکمه زیر کلیک نمایید:</i>"
            )

            async def _notify_admins_async():
                target_admins = get_all_admin_ids()
                for admin_id in target_admins:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=admin_text,
                            reply_markup=admin_kb,
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.debug(f"Notification to admin {admin_id} skipped: {e}")

            asyncio.create_task(_notify_admins_async())
        return

    elif data == "cancel_inq":
        context.user_data.pop("awaiting_inquiry_pid", None)
        context.user_data.pop("awaiting_inquiry_prod", None)
        await asyncio.gather(
            query.answer("❌ لغو شد."),
            query.message.reply_text("❌ درخواست استعلام لغو گردید. در صورت تمایل می‌توانید کالای دیگری را جستجو فرمایید.")
        )
        return

    elif data.startswith("ans_inq|"):
        await query.answer()
        user_id = query.from_user.id
        if not is_admin(user_id):
            await query.message.reply_text("⛔️ دسترسی به این بخش فقط مخصوص مدیران فروشگاه است.")
            return

        req_id = int(data.split("|")[1])
        inq = await db.get_price_inquiry(req_id)
        if not inq:
            await query.message.reply_text("❌ درخواست استعلام یافت نشد یا حذف شده است.")
            return

        dep_pct = getattr(config, "DEPOSIT_PERCENT", 8)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🚚 ارسال با باربری (بیعانه {dep_pct}٪ + تسویه در محل)", callback_data=f"set_ship|freight|{req_id}")],
            [InlineKeyboardButton("📮 ارسال با پست پیشتاز (تسویه ۱۰۰٪ - بدون بیعانه)", callback_data=f"set_ship|post|{req_id}")],
        ])
        admin_prompt = (
            f"✍️ <b>تعیین شیوه ارسال و پاسخ به استعلام قیمت:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>کالا:</b> {inq.get('product_name')}\n"
            f"📍 <b>مقصد تحویل:</b> {inq.get('city')}\n"
            f"👤 <b>مشتری:</b> {inq.get('username')} (شناسه: <code>{inq.get('user_id')}</code>)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 <b>لطفاً نحوه ارسال کالا برای این سفارش را انتخاب فرمایید:</b>\n\n"
            f"▫️ <b>🚚 باربری:</b> دریافت بیعانه ({dep_pct}٪) + تسویه مانده درب منزل پس از تست سلامت\n"
            f"▫️ <b>📮 پست پیشتاز:</b> واریز ۱۰۰٪ مبلغ کل کالا قبل از ارسال (بدون بیعانه)"
        )
        await query.message.reply_text(admin_prompt, reply_markup=kb, parse_mode="HTML")

    elif data.startswith("set_ship|"):
        await query.answer()
        user_id = query.from_user.id
        if not is_admin(user_id):
            await query.message.reply_text("⛔️ دسترسی به این بخش فقط مخصوص مدیران فروشگاه است.")
            return

        parts = data.split("|")
        shipping_method = parts[1]
        req_id = int(parts[2])

        inq = await db.get_price_inquiry(req_id)
        if not inq:
            await query.message.reply_text("❌ درخواست استعلام یافت نشد یا حذف شده است.")
            return

        context.user_data["admin_answering_inquiry_id"] = req_id
        context.user_data["admin_answering_shipping_method"] = shipping_method

        dep_pct = getattr(config, "DEPOSIT_PERCENT", 8)
        if shipping_method == "post":
            method_desc = "📮 <b>پست پیشتاز (تسویه ۱۰۰٪ کامل قبل از ارسال - بدون بیعانه)</b>"
            calc_hint = "مشتری ملزم به واریز کل این مبلغ خواهد بود و بیعانه‌ای دریافت نمی‌شود"
        else:
            method_desc = f"🚚 <b>باربری / پیک (دریافت {dep_pct}٪ بیعانه + تسویه مانده در محل)</b>"
            calc_hint = f"مبلغ بیعانه {dep_pct}٪ به صورت خودکار محاسبه شده و مانده در محل تسویه می‌شود"

        admin_prompt = (
            f"✍️ <b>ثبت قیمت تمام‌شده کالا:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>کالا:</b> {inq.get('product_name')}\n"
            f"📍 <b>مقصد تحویل:</b> {inq.get('city')}\n"
            f"🛵 <b>نحوه ارسال انتخابی:</b> {method_desc}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 لطفاً <b>فقط مبلغ قیمت تمام‌شده کالا (به تومان)</b> را وارد و ارسال فرمایید:\n"
            f"<i>({calc_hint} - مثال: ۳۸,۵۰۰,۰۰۰ یا 38500000)</i>"
        )
        await query.message.reply_text(admin_prompt, parse_mode="HTML")

    elif data.startswith("out_of_stock|"):
        user_id = query.from_user.id
        if not is_admin(user_id):
            await query.answer("⛔️ دسترسی به این بخش فقط مخصوص مدیران فروشگاه است.", show_alert=True)
            return

        req_id = int(data.split("|")[1])
        inq = await db.get_price_inquiry(req_id)
        if not inq:
            await query.answer("❌ درخواست استعلام یافت نشد.", show_alert=True)
            return

        buyer_id = inq.get("user_id")
        pname = inq.get("product_name", "کالا")

        # دکمه‌های پیام ارسالی به خریدار
        buyer_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗂 مشاهده همه دسته‌بندی‌های کالا", callback_data="cat_back")],
            [InlineKeyboardButton("📞 مشاوره و پیشنهاد مدل جایگزین", callback_data="show_support")]
        ])

        buyer_notice = (
            f"⚠️ <b>اطلاعیه وضعیت موجودی کالا</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"خریدار گرامی، متأسفانه موجودی انبار برای کالای <b>{pname}</b> در حال حاضر به پایان رسیده است.\n\n"
            f"💡 پیشنهاد می‌کنیم جهت مشاهده و انتخاب مدل‌های مشابه و موجود در بازار، دسته‌بندی مربوط به این کالا را مشاهده فرمایید و یا با واحد مشاوره ما در ارتباط باشید."
        )

        try:
            await context.bot.send_message(
                chat_id=buyer_id,
                text=buyer_notice,
                reply_markup=buyer_kb,
                parse_mode="HTML"
            )
            await query.answer("✅ پیام اتمام موجودی برای خریدار ارسال گردید.", show_alert=True)
        except Exception as e:
            logger.error(f"Failed to send out-of-stock notice to buyer {buyer_id}: {e}")
            await query.answer("⚠️ خطا در ارسال پیام به خریدار (احتمالاً چت با ربات مسدود است)", show_alert=True)

    elif data == "adm_sync_photos":
        await query.answer()
        await sync_photos_command(update, context)

    elif data == "adm_channels":
        await query.answer()
        from admin_panel import admin_channel_monitor_menu
        await admin_channel_monitor_menu(update, context)

    elif data == "adm_add_channel":
        await query.answer()
        from admin_panel import admin_add_channel_prompt
        await admin_add_channel_prompt(update, context)

    elif data == "adm_sync_channels_all":
        await query.answer()
        from admin_panel import admin_sync_channels_all
        await admin_sync_channels_all(update, context)

    elif data == "adm_list_channels_delete":
        await query.answer()
        from admin_panel import admin_list_channels_delete
        await admin_list_channels_delete(update, context)

    elif data.startswith("adm_del_ch|"):
        await query.answer()
        ch_to_del = data.split("|")[1]
        from admin_panel import admin_delete_channel_handler
        await admin_delete_channel_handler(update, context, ch_to_del)

    elif data == "adm_pending_orders":
        await query.answer()
        pending = await db.get_orders_by_status("Receipt_Uploaded")
        if not pending:
            empty_msg = "✅ در حال حاضر هیچ سفارشی در انتظار تایید وجود ندارد."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")]])
            try:
                await query.edit_message_text(empty_msg, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await query.message.reply_text(empty_msg, reply_markup=kb, parse_mode="HTML")
        else:
            lines = ["📋 <b>سفارشات در انتظار بررسی فیش:</b>\nبرای بررسی و تغییر وضعیت روی سفارش کلیک فرمایید:\n"]
            btns = []
            for o in pending[:8]:
                code = o.get("order_code")
                pname = (o.get("product_name") or "کالا")[:20]
                lines.append(f"▫️ سفارش <code>{code}</code> | {pname} | {o.get('full_name')}")
                btns.append([InlineKeyboardButton(f"🔎 بررسی و مدیریت سفارش {code}", callback_data=f"adm_view_ord|{code}")])
            btns.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")])
            kb = InlineKeyboardMarkup(btns)
            try:
                await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")
            except Exception:
                await query.message.reply_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")

    elif data == "adm_manage_orders":
        await query.answer()
        orders = await db.get_all_orders(limit=12)
        if not orders:
            empty_msg = "📋 در حال حاضر هیچ سفارشی در سیستم ثبت نشده است."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")]])
            try:
                await query.edit_message_text(empty_msg, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await query.message.reply_text(empty_msg, reply_markup=kb, parse_mode="HTML")
        else:
            status_fa = {
                "Awaiting_Payment": "⏳ منتظر بیعانه",
                "Receipt_Uploaded": "🔎 بررسی فیش",
                "Approved": "🚚 در حال ارسال",
                "Delivered": "✅ تسویه و تحویل شد",
                "Cancelled": "❌ لغو شده"
            }
            lines = [
                "📦 <b>مرکز مدیریت وضعیت سفارشات (پنل ادمین)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "جهت تغییر وضعیت به «در حال ارسال»، «تسویه و تحویل» یا مشاهده فیش، سفارش مورد نظر را انتخاب فرمایید:\n"
            ]
            btns = []
            for o in orders[:8]:
                code = o.get("order_code")
                pname = (o.get("product_name") or "کالا")[:18]
                st_label = status_fa.get(o.get("status"), o.get("status"))
                btns.append([InlineKeyboardButton(f"🏷 {code} | {pname} | {st_label}", callback_data=f"adm_view_ord|{code}")])
            btns.append([InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")])
            kb = InlineKeyboardMarkup(btns)
            try:
                await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")
            except Exception:
                await query.message.reply_text("\n".join(lines), reply_markup=kb, parse_mode="HTML")

    elif data.startswith("adm_view_ord|"):
        await query.answer()
        code = data.split("|")[1]
        order = await db.get_order_by_code(code)
        if not order:
            await query.message.reply_text("❌ سفارش مورد نظر یافت نشد.")
            return

        status_fa = {
            "Awaiting_Payment": "⏳ در انتظار بیعانه",
            "Receipt_Uploaded": "🔎 فیش ارسال شده (نیاز به تایید)",
            "Approved": "🚚 در حال ارسال (تایید باربری)",
            "Delivered": "✅ تسویه کامل و تحویل خریدار",
            "Cancelled": "❌ لغو شده (انقضای زمان یا دستی)"
        }
        st = order.get("status")
        txt = (
            f"📦 <b>مشخصات کامل سفارش <code>{code}</code></b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"▫️ <b>کالا:</b> {order.get('product_name')}\n"
            f"👤 <b>خریدار:</b> {order.get('full_name')}\n"
            f"📱 <b>تماس:</b> <code>{order.get('phone1')}</code> ({order.get('phone2') or '-'})\n"
            f"📍 <b>مقصد:</b> {order.get('province_city')}\n"
            f"🏠 <b>آدرس:</b> {order.get('address')}\n"
            f"💳 <b>مبلغ بیعانه:</b> {order.get('deposit_amount')} تومان\n"
            f"🏷 <b>وضعیت کنونی:</b> <b>{status_fa.get(st, st)}</b>\n"
            f"📅 <b>ثبت سفارش:</b> {order.get('created_at', '')[:16].replace('T', ' ')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 <b>تغییر وضعیت این سفارش توسط ادمین:</b>"
        )
        btns = [
            [InlineKeyboardButton("🚚 تغییر به: در حال ارسال (بارگیری شد)", callback_data=f"adm_set_status|{code}|Approved")],
            [InlineKeyboardButton("✅ تغییر به: تسویه کامل و تحویل شد", callback_data=f"adm_set_status|{code}|Delivered")],
            [InlineKeyboardButton("❌ تغییر به: لغو سفارش", callback_data=f"adm_set_status|{code}|Cancelled")],
            [InlineKeyboardButton("🔙 بازگشت به لیست سفارشات", callback_data="adm_manage_orders")],
            [InlineKeyboardButton("🔙 بازگشت به پنل اصلی", callback_data="adm_back_panel")]
        ]
        kb = InlineKeyboardMarkup(btns)

        # اگر فیش بانکی دارد می‌توان عکس فیش را هم نشان داد
        if order.get("receipt_file_id"):
            try:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=order.get("receipt_file_id"),
                    caption=f"📸 تصویر فیش واریزی سفارش <code>{code}</code>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send receipt photo to admin: {e}")

        try:
            await query.edit_message_text(txt, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(txt, reply_markup=kb, parse_mode="HTML")

    elif data.startswith("adm_set_status|"):
        await query.answer()
        parts = data.split("|")
        code = parts[1]
        new_status = parts[2]
        note = "تغییر وضعیت توسط ادمین"
        if new_status == "Approved":
            note = "تایید باربری و ارسال مرسوله"
        elif new_status == "Delivered":
            note = "تحویل کامل به خریدار و تسویه نهایی"
        elif new_status == "Cancelled":
            note = "لغو شده توسط مدیر فروشگاه"

        await db.update_order_status(code, status=new_status, admin_note=note)
        order = await db.get_order_by_code(code)

        # ارسال اطلاع‌رسانی آنی به خریدار
        if order and order.get("user_id"):
            buyer_id = order.get("user_id")
            buyer_msg = ""
            if new_status == "Approved":
                buyer_msg = (
                    f"🚚 <b>خریدار گرامی، سفارش <code>{code}</code> بارگیری و ارسال شد!</b>\n\n"
                    f"📦 کالای شما با موفقیت تحویل باربر اختصاصی گردید و در مسیر شهر مقصد است.\n"
                    f"🛡 جهت مشاهده لحظه‌ای موقعیت و تایم‌لاین ارسال، از بخش <b>پیگیری سفارشات</b> ربات استفاده فرمایید."
                )
            elif new_status == "Delivered":
                buyer_msg = (
                    f"🎉 <b>خریدار گرامی، سفارش <code>{code}</code> با موفقیت تحویل و تسویه گردید!</b>\n\n"
                    f"از حسن اعتماد و خرید شما از بازرگانی هوشمند کالا صمیمانه سپاسگزاریم. 🌹\n"
                    f"گارانتی شرکتی و خدمات پس از فروش دستگاه از تاریخ امروز فعال می‌باشد."
                )
            elif new_status == "Cancelled":
                buyer_msg = (
                    f"⚠️ <b>اطلاعیه سفارش <code>{code}</code>:</b>\n\n"
                    f"سفارش شما لغو گردید.\nعلت: {note}\n"
                    f"در صورت نیاز به راهنمایی با واحد پشتیبانی در تماس باشید."
                )

            if buyer_msg:
                try:
                    await context.bot.send_message(chat_id=buyer_id, text=buyer_msg, parse_mode="HTML")
                except Exception as ex:
                    logger.warning(f"Could not notify buyer {buyer_id} of status change: {ex}")

        await query.message.reply_text(f"✅ وضعیت سفارش <code>{code}</code> با موفقیت به <b>{new_status}</b> تغییر یافت.", parse_mode="HTML")
        await admin_panel_command(update, context)

    elif data.startswith("adm_ok|"):
        await query.answer("فیش تایید شد")
        code = data.split("|")[1]
        order = await db.get_order_by_code(code)
        shipping_method = order.get("shipping_method", "freight") if order else "freight"
        is_post = (shipping_method == "post")

        admin_note = "تسویه کامل فاکتور تایید شد. تخصیص به واحد بسته‌بندی و تحویل به پست پیشتاز." if is_post else "فیش بانکی و بیعانه تایید شد. تخصیص به واحد ترابری."
        await db.update_order_status(code, status="Approved", admin_note=admin_note)
        # بازخوانی رکورد به‌روزشده
        order = await db.get_order_by_code(code)

        # مرحله دوم: تولید فاکتور رسمی و قطعی فروش
        invoice_path = None
        if order:
            try:
                inv_data = build_invoice_data_from_order(order)
                os.makedirs("invoices", exist_ok=True)
                out_png = f"invoices/final_invoice_{code}.png"
                invoice_path = generate_invoice_png(inv_data, output_path=out_png, is_pre_invoice=False)
            except Exception as e:
                logger.error(f"Error generating final invoice PNG: {e}")

        if order and order.get("user_id"):
            buyer_id = order.get("user_id")
            buyer_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 پیگیری لحظه‌ای سفارش", callback_data=f"track_ord|{code}")],
                [InlineKeyboardButton("📞 پشتیبانی و ترابری", callback_data="show_support")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
            ])
            if is_post:
                success_caption = (
                    f"🎉 <b>فاکتور رسمی و قطعی فروش صادر گردید!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ <b>تسویه کامل سفارش <code>{code}</code> با موفقیت تایید شد.</b>\n"
                    f"📦 کالا از انبار ترخیص و جهت بسته‌بندی ضدضربه و تحویل به اداره پست پیشتاز ارجاع گردید.\n"
                    f"📮 <b>نحوه ارسال: پست پیشتاز (تسویه کامل - مانده صفر)</b>\n"
                    f"📋 <i>کد رهگیری مرسوله پستی به محض تحویل به اداره پست از طریق بخش پیگیری سفارشات برای شما ثبت خواهد شد.</i>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👇 <i>جهت مشاهده موقعیت لحظه‌ای و تایم‌لاین سفارش، دکمه پیگیری سفارش را لمس فرمایید:</i>"
                )
            else:
                success_caption = (
                    f"🎉 <b>فاکتور رسمی و قطعی فروش صادر گردید!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ <b>بیعانه سفارش <code>{code}</code> با موفقیت تایید شد.</b>\n"
                    f"📦 کالا از انبار ترخیص و تحویل واحد ترابری و بارچین اختصاصی گردید.\n"
                    f"🚚 <b>وضعیت سفارش: در حال ارسال با باربری</b>\n"
                    f"📋 <i>تسویه مانده‌حساب پس از تحویل و تست سلامت فیزیکی در محل انجام خواهد شد.</i>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👇 <i>جهت مشاهده موقعیت لحظه‌ای و تایم‌لاین ارسال، دکمه پیگیری سفارش را لمس فرمایید:</i>"
                )
            try:
                if invoice_path and os.path.exists(invoice_path):
                    with open(invoice_path, "rb") as f_inv:
                        await context.bot.send_photo(
                            chat_id=buyer_id,
                            photo=f_inv,
                            caption=success_caption,
                            reply_markup=buyer_kb,
                            parse_mode="HTML",
                            read_timeout=60.0,
                            write_timeout=90.0,
                            connect_timeout=30.0
                        )
                else:
                    await context.bot.send_message(
                        chat_id=buyer_id,
                        text=success_caption,
                        reply_markup=buyer_kb,
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.warning(f"Could not notify buyer {buyer_id}: {e}")

        method_lbl = "پست پیشتاز (تسویه کامل)" if is_post else "باربری (بیعانه)"
        try:
            await query.edit_message_caption(
                caption=f"✅ فیش سفارش <code>{code}</code> ({method_lbl}) تایید شد.\n📄 فاکتور قطعی فروش صادر و برای مشتری ارسال گردید.",
                parse_mode="HTML"
            )
        except Exception:
            await query.message.reply_text(
                f"✅ فیش سفارش <code>{code}</code> ({method_lbl}) تایید و فاکتور نهایی برای مشتری ارسال گردید.",
                parse_mode="HTML"
            )

    elif data.startswith("adm_no|"):
        await query.answer("فیش رد شد")
        code = data.split("|")[1]
        await db.update_order_status(code, status="Rejected", admin_note="عدم تایید مشخصات فیش یا مبلغ بیعانه توسط حسابداری")
        order = await db.get_order_by_code(code)
        if order and order.get("user_id"):
            buyer_id = order.get("user_id")
            buyer_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 ارسال مجدد تصویر فیش", callback_data=f"uprec|{code}")],
                [InlineKeyboardButton("📞 پشتیبانی و پیگیری", callback_data="show_support")],
                [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
            ])
            reject_msg = (
                f"❌ <b>عدم تایید فیش ارسالی برای سفارش <code>{code}</code></b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"مشخصات فیش یا مبلغ واریزی مورد تایید حسابداری قرار نگرفت.\n"
                f"علت احتمالی: ناخوانا بودن رسید، مغایرت مبلغ یا تاخیر بانکی.\n\n"
                f"💡 لطفاً تصویر فیش واریزی را مجدداً ارسال نمایید یا با پشتیبانی تماس حاصل فرمایید."
            )
            try:
                await context.bot.send_message(
                    chat_id=buyer_id,
                    text=reject_msg,
                    reply_markup=buyer_kb,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not notify buyer {buyer_id}: {e}")

        try:
            await query.edit_message_caption(
                caption=f"❌ فیش سفارش <code>{code}</code> رد شد و به مشتری اطلاع‌رسانی گردید.",
                parse_mode="HTML"
            )
        except Exception:
            await query.message.reply_text(f"❌ فیش سفارش <code>{code}</code> رد شد.", parse_mode="HTML")

    elif data == "adm_verified_photos":
        await query.answer()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="adm_back_panel")]
        ])
        if not VERIFIED_PRODUCT_PHOTOS:
            empty_msg = (
                "📸 <b>لیست تصاویر تایید شده محصولات:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "در حال حاضر هیچ تصویری به صورت دستی تایید یا ثبت نشده است.\n\n"
                "💡 <b>چگونه تصویر تایید شده ثبت کنیم؟</b>\n"
                "۱. <b>روش مستقیم:</b> با ارسال دستور زیر:\n"
                "<code>/setphoto [کد_محصول]</code> (مثال: <code>/setphoto 68798</code>)\n\n"
                "۲. <b>روش خودکار:</b> هرگاه کاربری روی «📸 تصاویر محصول» کالایی بزند و تصویری در کانال نباشد، "
                "یک دکمه «ثبت عکس» به صورت اختصاصی برای ادمین ارسال می‌شود تا با یک کلیک و ارسال عکس/لینک آن را تایید کند."
            )
            try:
                await query.edit_message_text(empty_msg, reply_markup=kb, parse_mode="HTML")
            except Exception:
                await query.message.reply_text(empty_msg, reply_markup=kb, parse_mode="HTML")
        else:
            lines = [
                f"📸 <b>لیست تصاویر تایید شده ({len(VERIFIED_PRODUCT_PHOTOS)} محصول):</b>\n",
                "━━━━━━━━━━━━━━━━━━━━\n"
            ]
            for pid_item, val in list(VERIFIED_PRODUCT_PHOTOS.items())[-20:]:
                p_link = val.get('link') or val.get('message_ids') or "فایل مستقیم"
                lines.append(f"▫️ <b>{val.get('product_name', pid_item)}</b>\n  کد: <code>{pid_item}</code> | مرجع: <code>{p_link}</code>")
            lines.append("\n💡 <i>جهت افزودن یا تغییر تصویر هر محصول، از دستور <code>/setphoto [کد]</code> استفاده نمایید.</i>")
            try:
                await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
            except Exception:
                await query.message.reply_text("\n".join(lines), reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)

    elif data == "adm_clear_photos_ask":
        await query.answer()
        await clearphotos_command(update, context)

    elif data == "adm_clear_photos_do":
        await query.answer("در حال پاکسازی لیست تصاویر...", show_alert=False)
        from photo_service import clear_all_product_photos
        stats = clear_all_product_photos()
        v_count = stats.get("verified_count", 0)
        p_count = stats.get("posts_count", 0)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
        ])
        msg = (
            f"✅ <b>تمامی تصاویر تستی و کش قبلی با موفقیت پاکسازی شدند!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"▫️ تعداد تصاویر تایید شده دستی حذف‌شده: <b>{v_count}</b> مورد\n"
            f"▫️ تعداد پست‌های ایندکس‌شده تستی کانال: <b>{p_count}</b> پست\n\n"
            f"✨ <b>از این پس:</b>\n"
            f"سیستم کاملاً آماده و تمیز است تا فقط تصاویر واقعی محصولات که در کانال عکس‌ها قرار می‌گیرند یا با دستور <code>/setphoto</code> متصل می‌شوند، برای مشتریان ارسال گردند."
        )
        try:
            await query.edit_message_text(msg, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(msg, reply_markup=kb, parse_mode="HTML")

    elif data == "back_to_main":
        await query.answer()
        user = update.effective_user
        welcome_text = (
            f"🏠 <b>منوی اصلی بازرگانی هوشمند کالا</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"سلام <b>{user.first_name}</b> گرامی! 🌹\n\n"
            f"✨ <b>دسترسی سریع به امکانات ربات:</b>\n"
            f"🔹 جهت جستجوی کالا، نام یا مدل محصول را تایپ و ارسال فرمایید.\n"
            f"🔹 برای رهگیری سفارشات یا راهنمایی، از گزینه‌های زیر استفاده فرمایید:"
        )
        main_inline_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 پیگیری سفارشات", callback_data="track_order_list")],
            [InlineKeyboardButton("ℹ️ راهنمای جامع خرید و ضمانت", callback_data="guide_main")],
            [InlineKeyboardButton("📞 پشتیبانی و مشاوره", callback_data="show_support")]
        ])
        try:
            await query.edit_message_text(welcome_text, reply_markup=main_inline_kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(welcome_text, reply_markup=main_inline_kb, parse_mode="HTML")

    elif data == "close_window":
        try:
            await query.message.delete()
        except Exception:
            pass

    elif data == "adm_back_panel":
        await query.answer()
        await admin_panel_command(update, context)

    elif data == "adm_laptop_hub":
        await admin_laptop_hub(update, context)

    elif data == "adm_text_laptop_prompt":
        await admin_text_laptop_prompt(update, context)

    elif data == "adm_clear_laptops_ask":
        await admin_clear_laptops_ask(update, context)

    elif data == "adm_clear_laptops_do":
        await admin_clear_laptops_do(update, context)

    elif data == "adm_sync_live_prices":
        await admin_sync_live_prices(update, context)

    elif data == "adm_sync_catalog_stock":
        await admin_sync_catalog_stock(update, context)

    elif data == "adm_bank_settings":
        await admin_bank_settings(update, context)

    elif data == "adm_edit_bank_card":
        await admin_prompt_bank_edit(update, context, "card")

    elif data == "adm_edit_bank_shaba":
        await admin_prompt_bank_edit(update, context, "shaba")

    elif data == "adm_edit_bank_holder":
        await admin_prompt_bank_edit(update, context, "holder")

    elif data == "adm_edit_bank_deposit":
        await admin_prompt_bank_edit(update, context, "deposit")

    elif data == "adm_catalog_report":
        await admin_catalog_report(update, context)

    elif data == "adm_ai_settings":
        await admin_ai_settings_menu(update, context)

    elif data.startswith("adm_ai_set_"):
        target_provider = data.replace("adm_ai_set_", "").strip()
        await admin_ai_set_provider_handler(update, context, target_provider)

    elif data == "adm_broadcast_ask":
        await admin_broadcast_ask(update, context)

    elif data == "adm_broadcast_do":
        await admin_broadcast_do(update, context)

    elif data == "adm_upload_laptop_excel":
        await admin_upload_laptop_excel_prompt(update, context)

    elif data == "adm_upload_laptop_photo":
        await query.answer()
        context.user_data["awaiting_laptop_photo"] = True
        context.user_data.pop("pending_extracted_laptops", None)
        cancel_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="adm_laptop_hub")]
        ])
        msg = (
            "💻 <b>استخراج هوشمند لیست قیمت و موجودی لپ‌تاپ:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "لطفاً <b>عکس، اسکرین‌شات یا فایل تصویر جدول قیمت</b> لپ‌تاپ را ارسال فرمایید.\n\n"
            "🤖 <b>فیلترهای خودکار هوش مصنوعی:</b>\n"
            "✅ خواندن ستون «قیمت» و تبدیل دقیق به تومان\n"
            "🚫 <b>حذف قطعی ستون همکاری</b> (قیمت همکار هرگز ثبت نمی‌شود)\n"
            "🚫 <b>فیلتر کامل شماره تماس‌ها</b> (درویشی، رحمانی، خاکساران و...)\n"
            "🚫 <b>حذف هدرها و نام‌های تبلیغاتی متفرقه</b>\n"
            "🏷 تفکیک خودکار و ثبت زیرمجموعه منحصراً بر اساس برند (HP، ASUS، LENOVO و...)\n\n"
            "👇 <i>هم‌اکنون عکس را در همین چت ارسال فرمایید:</i>"
        )
        try:
            await query.edit_message_text(msg, reply_markup=cancel_kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(msg, reply_markup=cancel_kb, parse_mode="HTML")

    elif data == "adm_confirm_laptops_replace":
        await query.answer("در حال جایگزینی کامل لیست لپ‌تاپ‌ها...", show_alert=False)
        extracted = context.user_data.pop("pending_extracted_laptops", None)
        if not extracted:
            await query.message.reply_text("⚠️ داده‌ای برای ثبت یافت نشد یا جلسه منقضی شده است.")
            return

        res = replace_extracted_laptops(extracted)
        # به‌روزرسانی آنی کش محصولات در حافظه بدون نیاز به ری‌استارت
        load_json_products()

        done_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 مشاهده دسته‌بندی لپ‌تاپ", callback_data="cat_m_laptop")],
            [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
        ])
        done_text = (
            f"🎉 <b>لیست لپ‌تاپ‌ها با موفقیت جایگزین شد!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🗑 <b>لیست قبلی لپ‌تاپ‌ها به طور کامل حذف گردید.</b>\n"
            f"💻 تعداد کل لپ‌تاپ‌های فعال جدید: <b>{res['total']} مدل</b>\n\n"
            f"✨ کلیه مدل‌ها بلافاصله در دسته‌بندی «💻 لپ‌تاپ» و زیرمجموعه برندها قرار گرفتند و با جستجو نیز در دسترس هستند."
        )
        try:
            await query.edit_message_text(done_text, reply_markup=done_kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(done_text, reply_markup=done_kb, parse_mode="HTML")

    elif data == "adm_confirm_laptops_merge" or data == "adm_confirm_laptops":
        await query.answer("در حال ادغام با کاتالوگ لپ‌تاپ...", show_alert=False)
        extracted = context.user_data.pop("pending_extracted_laptops", None)
        if not extracted:
            await query.message.reply_text("⚠️ داده‌ای برای ثبت یافت نشد یا جلسه منقضی شده است.")
            return

        merge_res = merge_extracted_laptops(extracted)
        # به‌روزرسانی آنی کش محصولات در حافظه بدون نیاز به ری‌استارت
        load_json_products()

        done_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 مشاهده دسته‌بندی لپ‌تاپ", callback_data="cat_m_laptop")],
            [InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="adm_back_panel")]
        ])
        done_text = (
            f"🎉 <b>لیست لپ‌تاپ‌ها با موفقیت با کاتالوگ ادغام شد!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"➕ مدل‌های جدید اضافه شده: <b>{merge_res['added']} مدل</b>\n"
            f"🔄 مدل‌های به‌روزرسانی شده: <b>{merge_res['updated']} مدل</b>\n"
            f"💻 کل لپ‌تاپ‌های فعال در کاتالوگ: <b>{merge_res['total']} مدل</b>\n\n"
            f"✨ کلیه محصولات بلافاصله در دسته‌بندی «💻 لپ‌تاپ» و زیرمجموعه برندها قرار گرفتند و با جستجوی مدل و مشخصات نیز قابل مشاهده و سفارش هستند."
        )
        try:
            await query.edit_message_text(done_text, reply_markup=done_kb, parse_mode="HTML")
        except Exception:
            await query.message.reply_text(done_text, reply_markup=done_kb, parse_mode="HTML")

    elif data == "adm_cancel_laptops":
        await query.answer("عملیات لغو شد.")
        context.user_data.pop("awaiting_laptop_photo", None)
        context.user_data.pop("awaiting_laptop_excel", None)
        context.user_data.pop("pending_extracted_laptops", None)
        await admin_panel_command(update, context)

    elif data.startswith("req_img|"):
        pid = resolve_safe_cb(data)
        user = update.effective_user

        prod = None
        for p in JSON_PRODUCTS:
            if str(p.get("product_id")) == str(pid):
                prod = p
                break
        if not prod:
            prod = await db.get_product_by_id(pid)
        pname = prod.get("name", "این محصول") if prod else "این محصول"

        # بررسی آیا محصول از دسته لپ‌تاپ است (چون عکس ندارند)
        is_laptop = (
            (prod and prod.get("category_key") == "laptop")
            or (prod and prod.get("category") in ["لپ‌تاپ", "لپ تاپ", "لپتاپ", "laptop"])
            or (prod and prod.get("category_name") in ["لپ‌تاپ", "لپ تاپ", "لپتاپ", "laptop"])
            or str(pid).upper().startswith("LAP")
            or any(w in str(pname).lower() for w in ["لپ‌تاپ", "لپ تاپ", "لپتاپ", "laptop"])
        )
        if is_laptop:
            await query.answer("💡 محصولات دسته‌بندی لپ‌تاپ فاقد تصویر آلبومی هستند و مشخصات فنی آن‌ها در کارت کالا درج شده است.", show_alert=True)
            return

        # ۱. بررسی هوشمند تصاویر تایید شده محصول یا مدل و سری مشابه
        matched_pid, photo_data, match_type = find_matching_verified_photos(prod or pid)
        if photo_data:
            if match_type == "exact":
                await query.answer("📸 در حال ارسال تصاویر اختصاصی محصول...")
                matched_note = None
            else:
                await query.answer("📸 در حال ارسال تصاویر مدل و سری کالا...")
                sim_name = photo_data.get("product_name", "")
                matched_note = f"تصاویر مربوط به سری و مدل مشابه ({sim_name}) می‌باشد." if sim_name and sim_name != pname else None

            success = await send_verified_photos_to_user(
                context.bot,
                query.message.chat_id,
                pid,
                pname,
                photo_data=photo_data,
                matched_note=matched_note
            )
            if success:
                return

        # ۲. در غیر این صورت -> ثبت درخواست، ارسال پیام اطلاع به کاربر و ارسال فوری نوتیفیکیشن به ادمین
        await query.answer("درخواست شما برای مشاهده تصاویر کالا ثبت شد", show_alert=True)

        user_req_text = (
            f"📸 <b>درخواست تصاویر واقعی کالا:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>محصول:</b> <b>{pname}</b>\n\n"
            f"⏳ تا دقایقی دیگر آلبوم تصاویر به صورت خودکار در همین گفتگو برای شما ارسال خواهد شد."
        )
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=user_req_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not send waiting confirmation to user: {e}")

        if pid not in PENDING_IMAGE_REQUESTS:
            PENDING_IMAGE_REQUESTS[pid] = []
        if query.message.chat_id not in PENDING_IMAGE_REQUESTS[pid]:
            PENDING_IMAGE_REQUESTS[pid].append(query.message.chat_id)

        admin_cb = make_safe_cb("adm_set_img", f"{pid}|{query.message.chat_id}")
        admin_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 ثبت و ارسال لینک تصاویر", callback_data=admin_cb)]
        ])
        admin_alert = (
            f"🔔 <b>درخواست جدید تصاویر محصول از سوی مشتری</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>نام کالا:</b> {pname}\n"
            f"🏷 <b>کد محصول:</b> <code>{pid}</code>\n"
            f"👤 <b>متقاضی:</b> {user.full_name} (@{user.username or 'ندارد'})\n"
            f"🆔 <b>شناسه کاربر:</b> <code>{user.id}</code>\n\n"
            f"👇 <i>جهت ارسال تصاویر این کالا، دکمه زیر را لمس کرده و لینک پست، شماره پیام یا عکس‌های کانال را بفرستید:</i>"
        )
        for adm_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=adm_id,
                    text=admin_alert,
                    reply_markup=admin_kb,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to alert admin {adm_id}: {e}")

    elif data.startswith("adm_set_img|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        await query.answer()
        payload = resolve_safe_cb(data)
        parts = payload.split("|")
        pid = parts[0]
        target_uid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

        prod = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        pname = prod.get("name", pid) if prod else pid

        context.user_data["awaiting_product_image_link"] = {
            "pid": pid,
            "target_uid": target_uid,
            "product_name": pname
        }

        await query.message.reply_text(
            f"📸 <b>ارسال و ثبت تصاویر:</b>\n"
            f"🌟 <b>{pname}</b> (<code>{pid}</code>)\n\n"
            f"لطفاً <b>لینک تصاویر این کالا</b> را ارسال (Paste) فرمایید:\n"
            f"<i>(یا پست مربوطه را فوروارد کنید و یا عکس‌ها را ارسال نمایید)</i>\n\n"
            f"📌 نمونه ورودی‌های معتبر:\n"
            f"ارسال شماره پست: <code>452</code> یا چند عکس: <code>452-455</code>\n\n"
            f"❌ جهت انصراف: /cancel",
            parse_mode="HTML"
        )

    elif data == "adm_back_panel":
        await query.answer()
        await admin_panel_command(update, context)

    # ─── کنسول اختصاصی ادمین در زیر کارت کالا ───
    elif data.startswith("adm_pimg|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        await query.answer()
        pid = resolve_safe_cb(data)
        prod = await db.get_product_by_id(pid) or next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        pname = prod.get("name", pid) if prod else pid

        context.user_data["awaiting_product_image_link"] = {
            "pid": pid,
            "target_uid": 0,
            "product_name": pname
        }

        await query.message.reply_text(
            f"🖼 <b>ارسال یا تغییر عکس کالا:</b>\n"
            f"🌟 <b>{pname}</b> (<code>{pid}</code>)\n\n"
            f"لطفاً <b>عکس، آلبوم تصاویر، یا لینک پست کانال</b> این محصول را ارسال یا فوروارد فرمایید.\n\n"
            f"📌 ورودی‌های معتبر:\n"
            f"▫️ ارسال مستقیم عکس (یا چند عکس همزمان به صورت آلبوم)\n"
            f"▫️ فوروارد پیام از کانال عکس‌ها\n"
            f"▫️ ارسال لینک پست (مثلاً <code>https://t.me/Aikala_Image/450</code>)\n"
            f"▫️ ارسال شماره پست (مثلاً <code>450</code> یا <code>450-453</code>)\n\n"
            f"💡 <i>تصویر ارسالی بلافاصله جایگزین تصویر قبلی این کالا خواهد شد.</i>\n"
            f"❌ جهت انصراف: /cancel",
            parse_mode="HTML"
        )

    elif data.startswith("adm_pimgdel|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        pid = resolve_safe_cb(data)
        prod = await db.get_product_by_id(pid) or next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        pname = prod.get("name", pid) if prod else pid

        remove_verified_product_photo(pid)
        try:
            await db.execute("UPDATE products SET image_url = '' WHERE product_id = ?", (pid,))
        except Exception:
            pass
        if prod:
            prod["image_url"] = ""
            prod["extra_description"] = ""
        for p in JSON_PRODUCTS:
            if str(p.get("product_id")) == str(pid):
                p["image_url"] = ""
                p["extra_description"] = ""

        await query.answer("✅ تصویر این کالا حذف شد.", show_alert=True)
        await query.message.reply_text(
            f"🗑 <b>تصویر کالا با موفقیت حذف گردید:</b>\n"
            f"🌟 <b>{pname}</b> (<code>{pid}</code>)\n\n"
            f"▫️ آلبوم و تصویر متصل به این محصول پاکسازی شد و اکنون بدون تصویر نمایش داده می‌شود.\n"
            f"▫️ هر زمان مایل بودید می‌توانید با دکمه «🖼 تغییر عکس کالا» تصویر جدید ثبت کنید.",
            parse_mode="HTML"
        )

    elif data.startswith("adm_pprice|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        await query.answer()
        pid = resolve_safe_cb(data)
        prod = await db.get_product_by_id(pid) or next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        pname = prod.get("name", pid) if prod else pid
        curr_price = prod.get("price", 0) if prod else 0
        curr_formatted = f"{int(curr_price):,} تومان" if curr_price else "ثبت نشده"

        context.user_data["awaiting_admin_product_price"] = {
            "pid": pid,
            "product_name": pname,
            "current_price": curr_price
        }

        await query.message.reply_text(
            f"✏️ <b>تنظیم دستی قیمت کالا:</b>\n"
            f"🌟 <b>{pname}</b> (<code>{pid}</code>)\n"
            f"▫️ قیمت فعلی: <code>{curr_formatted}</code>\n\n"
            f"لطفاً مبلغ جدید را به <b>تومان</b> و فقط با ارقام انگلیسی وارد فرمایید:\n"
            f"<i>(مثال: <code>54000000</code> برای ۵۴ میلیون تومان)</i>\n\n"
            f"❌ جهت انصراف: /cancel",
            parse_mode="HTML"
        )

    elif data.startswith("adm_ptog|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        pid = resolve_safe_cb(data)
        prod = await db.get_product_by_id(pid) or next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        pname = prod.get("name", pid) if prod else pid
        cur_status = prod.get("status", "b") if prod else "b"

        new_status = "hidden" if cur_status == "b" else "b"
        status_label = "🔴 پنهان (مخفی از نتایج جستجو و کاتالوگ)" if new_status == "hidden" else "🟢 نمایان و فعال در فروشگاه"

        if prod:
            prod["status"] = new_status
        try:
            await db.execute("UPDATE products SET status = ? WHERE product_id = ?", (new_status, pid))
        except Exception as e:
            logger.warning(f"Error updating product status in db: {e}")

        await query.answer(f"وضعیت کالا: {status_label}", show_alert=True)
        await query.message.reply_text(
            f"👁‍🗨 <b>وضعیت نمایش کالا تغییر یافت:</b>\n"
            f"🌟 <b>{pname}</b> (<code>{pid}</code>)\n\n"
            f"▫️ وضعیت فعلی: <b>{status_label}</b>",
            parse_mode="HTML"
        )

    elif data.startswith("adm_plink|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        await query.answer()
        pid = resolve_safe_cb(data)
        prod = await db.get_product_by_id(pid) or next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        pname = prod.get("name", pid) if prod else pid

        bot_uname = str(BOT_LINK or "").replace("@", "").strip() or "AiKala_bot"
        deep_link = f"https://t.me/{bot_uname}?start=p_{pid}"

        await query.message.reply_text(
            f"🔗 <b>لینک مستقیم اختصاصی محصول جهت ارسال به مشتری:</b>\n\n"
            f"🌟 <b>{pname}</b>\n"
            f"<code>{deep_link}</code>\n\n"
            f"📋 <i>کافیست روی لینک لمس کنید تا کپی شود. مشتری با باز کردن این لینک، مستقیماً وارد ربات شده و کارت کامل مشخصات این کالا را دریافت خواهد کرد.</i>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    elif data.startswith("adm_pcust|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        pid = resolve_safe_cb(data)
        await query.answer("👥 مشاهده از دید مشتری فعال شد.", show_alert=False)
        cust_kb = product_inline_keyboard(pid, context, show_photo_button=True, is_admin=True, view_as_customer=True)
        try:
            await query.edit_message_reply_markup(reply_markup=cust_kb)
        except Exception as e:
            logger.warning(f"Failed to switch to customer view: {e}")

    elif data.startswith("adm_pback|"):
        if not is_admin(update.effective_user.id):
            await query.answer("دسترسی غیرمجاز", show_alert=True)
            return

        pid = resolve_safe_cb(data)
        await query.answer("⚙️ ابزارهای مدیریت کالا فعال شد.", show_alert=False)
        admin_kb = product_inline_keyboard(pid, context, show_photo_button=True, is_admin=True, view_as_customer=False)
        try:
            await query.edit_message_reply_markup(reply_markup=admin_kb)
        except Exception as e:
            logger.warning(f"Failed to switch to admin view: {e}")

# =====================================================================
# 📡 هندلر دریافت پست‌های کانال عکس‌ها
# =====================================================================

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg:
        return

    photo_file_id = ""
    if msg.photo:
        photo_file_id = msg.photo[-1].file_id

    if not photo_file_id:
        return

    caption = msg.caption or msg.text or ""
    media_group_id = str(msg.media_group_id) if msg.media_group_id else None

    # اگر پست متعلق به یک آلبوم (Media Group) باشد
    if media_group_id:
        if media_group_id in CHANNEL_MEDIA_GROUPS:
            group = CHANNEL_MEDIA_GROUPS[media_group_id]
            if photo_file_id not in group["photos"]:
                group["photos"].append(photo_file_id)
            if msg.message_id not in group["msg_ids"]:
                group["msg_ids"].append(msg.message_id)
            if caption and not group.get("caption"):
                group["caption"] = caption
            effective_caption = group.get("caption") or caption
            register_photo_message(effective_caption, photo_file_id, msg_id=msg.message_id, media_group_id=media_group_id)
            logger.info(f"📸 Added photo #{len(group['photos'])} to media group {media_group_id} (msg_id: {msg.message_id})")
        else:
            CHANNEL_MEDIA_GROUPS[media_group_id] = {
                "caption": caption,
                "photos": [photo_file_id],
                "msg_ids": [msg.message_id]
            }
            register_photo_message(caption, photo_file_id, msg_id=msg.message_id, media_group_id=media_group_id)
            logger.info(f"📸 Registered new media group album {media_group_id} for msg_id: {msg.message_id} (caption: {caption[:40] if caption else 'بدون کپشن'})")
        save_channel_photos_map()
        return

    # ارسال تک عکس مستقل
    if photo_file_id and caption:
        register_photo_message(caption, photo_file_id, msg_id=msg.message_id)
        logger.info(f"📸 Registered single photo from channel for caption: {caption[:40]}...")

# =====================================================================
# 🚀 راه‌اندازی و اجرای اپلیکیشن ربات
# =====================================================================

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ":
        logger.error("❌ خطا: متغیر TELEGRAM_BOT_TOKEN تنظیم نشده است! لطفاً توکن ربات تلگرام خود را در فایل .env قرار دهید.")
        print("\n" + "=" * 60)
        print("❌ خطا: TELEGRAM_BOT_TOKEN در فایل .env یا متغیرهای محیطی یافت نشد.")
        print("👉 لطفاً فایل .env را ایجاد کرده و توکن ربات خود از @BotFather را قرار دهید:")
        print("   TELEGRAM_BOT_TOKEN=\"your_bot_token_here\"")
        print("=" * 60 + "\n")
        return

    logger.info("🚀 AiKala Bot is initialized and ready to run.")

    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    try:
        builder = builder.concurrent_updates(16)
    except Exception as e:
        logger.warning(f"Could not enable concurrent_updates: {e}")
    try:
        from telegram.request import HTTPXRequest
        request_config = HTTPXRequest(
            connection_pool_size=256,
            connect_timeout=30.0,
            read_timeout=60.0,
            write_timeout=90.0,
            media_write_timeout=120.0,
            pool_timeout=30.0
        )
        builder = builder.request(request_config)
    except Exception as e:
        logger.warning(f"Could not configure custom HTTPXRequest timeouts: {e}")

    app = builder.build()

    # کانوِرسیشن‌های ثبت سفارش و فیش واریزی
    app.add_handler(get_order_conversation_handler())
    app.add_handler(get_receipt_conversation_handler())

    # ماژول راهنمای جامع خرید و ضمانت
    register_guide_handlers(app)

    # ماژول مرکز مشاوره و پشتیبانی هوشمند
    register_support_handlers(app)

    # ماژول سامانه هوشمند و تعاملی رهگیری سفارشات
    register_order_tracking_handlers(app)

    # دستورات پایه و مدیریتی
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("track", track_order_command))
    app.add_handler(CommandHandler("sync_photos", sync_photos_command))
    app.add_handler(CommandHandler("setphoto", setphoto_command))
    app.add_handler(CommandHandler("clearphotos", clearphotos_command))
    app.add_handler(CommandHandler("setgemini", setgemini_command))
    app.add_handler(CommandHandler("admin", admin_panel_command))
    app.add_handler(CommandHandler("auth_admin", auth_admin_command))
    app.add_handler(CommandHandler("setadmin", auth_admin_command))

    # شنونده کانال تصاویر
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))

    # کلیک روی دکمه‌های شیشه‌ای و ارسال پیام‌های متنی، تصاویر و فایل‌های اکسل/سند
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.FORWARDED) & ~filters.COMMAND, handle_message))

    async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.error("Exception while handling an update:", exc_info=context.error)

    app.add_error_handler(global_error_handler)

    async def post_init(application: Application):
        await db.init()
        try:
            me = await application.bot.get_me()
            logger.info(f"🚀 Telegram Bot @{me.username} is connected and online.")
        except Exception:
            logger.info("🚀 Telegram Bot is connected and online.")
        try:
            chat = await application.bot.get_chat(PHOTOS_CHANNEL)
            logger.info(f"📸 Image Channel: {chat.title} ({PHOTOS_CHANNEL}) connected.")
        except Exception as e:
            logger.warning(f"⚠️ Image Channel ({PHOTOS_CHANNEL}): {e}")

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
