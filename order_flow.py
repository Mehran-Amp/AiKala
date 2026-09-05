"""
AiKala - Order Flow & Proforma Invoice Generator (order_flow.py)
================================================================
فرآیند چندمرحله‌ای صدور پیش‌فاکتور رسمی، اخذ بیعانه و آپلود فیش بانکی.
"""

import os
import re
import random
import logging
from datetime import datetime
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
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

CARD_NUMBER = getattr(config, "CARD_NUMBER", getattr(config, "CARD_NO", "6104-3386-4929-6106"))
CARD_HOLDER = getattr(config, "CARD_HOLDER", getattr(config, "CARD_NAME", "فروشگاه آاگ کالا مهران امین پور"))
CARD_SHABA = getattr(config, "CARD_SHABA", "IR 620120020000005786685564")
SHABA_HTML = getattr(config, "SHABA_HTML", "IR <code>620120020000005786685564</code>")
DEPOSIT_AMOUNT = getattr(config, "DEPOSIT_AMOUNT", "۲,۰۰۰,۰۰۰")
SUPPORT_USERNAME = getattr(config, "SUPPORT_USERNAME", "@AiKala_Admin")
ADMIN_IDS = getattr(config, "ADMIN_IDS", [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()] if os.getenv("ADMIN_IDS") else [])

from database import Database
from search_engine import JSON_PRODUCTS, _normalize_digits
from keyboards import resolve_safe_cb, main_menu_keyboard, is_admin
from invoice_service import generate_invoice_png, build_invoice_data_from_order, to_fa_digits

logger = logging.getLogger(__name__)
db = Database()

# ─── متغیرهای استیت کانوِرسیشن ───
ORDER_NAME, ORDER_PHONE1, ORDER_PHONE2, ORDER_CITY, ORDER_ADDRESS, ORDER_POSTAL = range(6)
RECEIPT_FILE = 20

# ─── مراحل گفتگوی ثبت سفارش ───

async def start_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    raw_payload = resolve_safe_cb(query.data)

    req_id = None
    if ":" in raw_payload:
        pid, req_id_str = raw_payload.split(":", 1)
        if req_id_str.isdigit():
            req_id = int(req_id_str)
    else:
        pid = raw_payload

    user_id = update.effective_user.id if update.effective_user else 0

    product = None
    for p in JSON_PRODUCTS:
        if str(p.get("product_id")) == str(pid):
            product = p
            break

    if not product:
        product = await db.get_product_by_id(pid)

    if not product:
        product = context.user_data.get("last_viewed_product") or context.user_data.get("current_product")

    if not product:
        product = {
            "product_id": pid or "CUSTOM",
            "name": f"کالای انتخابی هوشمند کالا (کد {pid})",
            "brand": "اورجینال شرکتی",
            "price": "طبق استعلام روز"
        }

    # استخراج قیمت قطعی اعلامی توسط ادمین (مبنای اصلی) یا قیمت کاتالوگ
    inq = None
    if req_id:
        inq = await db.get_price_inquiry(req_id)
    if not inq and user_id:
        inq = await db.get_latest_user_inquiry(user_id, pid)

    total_price = 0
    if inq:
        p_raw = str(inq.get("final_price") or inq.get("admin_response") or "")
        clean_p = _normalize_digits(p_raw).replace(",", "").replace("،", "").strip()
        digits = re.findall(r'\d+', clean_p)
        if digits:
            try:
                total_price = int("".join(digits))
            except Exception:
                total_price = 0

    if total_price == 0 and product and product.get("price"):
        clean_p = _normalize_digits(str(product.get("price"))).replace(",", "").replace("،", "").strip()
        digits = re.findall(r'\d+', clean_p)
        if digits:
            try:
                total_price = int("".join(digits))
            except Exception:
                total_price = 0

    # محاسبه ۸٪ بیعانه رند شده به عنوان پیش‌پرداخت
    deposit = 0
    if total_price > 0:
        deposit = int(round((total_price * 0.08) / 10000)) * 10000
        if deposit == 0:
            deposit = int(round((total_price * 0.08) / 1000)) * 1000

    context.user_data["order_total_price"] = total_price
    context.user_data["order_deposit"] = deposit
    context.user_data["order_inquiry_id"] = req_id or (inq.get("id") if inq else None)
    if total_price > 0:
        product["price"] = str(total_price)

    context.user_data["order_product"] = product
    await query.message.reply_text(
        f"📝 <b>مرحله ۱ از ۵:</b>\n"
        f"شما در حال ثبت سفارش برای <b>{product.get('name')}</b> هستید.\n\n"
        f"👤 لطفاً <b>نام و نام‌خانوادگی</b> تحویل‌گیرنده را ارسال فرمایید:"
        f"\n<i>(جهت انصراف /cancel را ارسال کنید یا دکمه بازگشت را بزنید)</i>",
        parse_mode="HTML"
    )
    return ORDER_NAME

async def order_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_name"] = update.message.text.strip()
    await update.message.reply_text(
        "📱 <b>مرحله ۲ از ۵:</b>\nلطفاً <b>شماره موبایل اصلی</b> جهت هماهنگی ارسال را وارد کنید:",
        parse_mode="HTML"
    )
    return ORDER_PHONE1

async def order_phone1_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = _normalize_digits(update.message.text.strip())
    if not re.search(r'09\d{9}', phone):
        await update.message.reply_text("❌ لطفاً یک شماره موبایل معتبر ۱۱ رقمی (مثال: 09123456789) وارد فرمایید:")
        return ORDER_PHONE1

    context.user_data["order_phone1"] = phone
    await update.message.reply_text(
        "📞 <b>مرحله ۳ از ۵:</b>\nلطفاً <b>شماره تماس اضطراری یا دوم</b> را ارسال فرمایید (یا در صورت عدم تمایل بنویسید «ندارم»):",
        parse_mode="HTML"
    )
    return ORDER_PHONE2

async def order_phone2_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_phone2"] = update.message.text.strip()
    await update.message.reply_text(
        "📍 <b>مرحله ۴ از ۵:</b>\nلطفاً <b>استان و شهر</b> مقصد را وارد فرمایید (مثال: تهران - تهران):",
        parse_mode="HTML"
    )
    return ORDER_CITY

async def order_city_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_city"] = update.message.text.strip()
    await update.message.reply_text(
        "🏠 <b>مرحله ۵ از ۵:</b>\nلطفاً <b>آدرس دقیق پستی</b> (شامل خیابان، کوچه، پلاک و واحد) را ارسال فرمایید:",
        parse_mode="HTML"
    )
    return ORDER_ADDRESS

async def order_address_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_address"] = update.message.text.strip()
    await update.message.reply_text(
        "📮 لطفاً <b>کد پستی ۱۰ رقمی</b> را ارسال فرمایید (یا در صورت نداشتن بنویسید «ندارم»):",
        parse_mode="HTML"
    )
    return ORDER_POSTAL

async def order_postal_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_postal"] = update.message.text.strip()
    user = update.effective_user
    prod = context.user_data.get("order_product", {})
    
    order_code = f"AK-{int(datetime.now().timestamp())%1000000:06d}"
    
    total_price = context.user_data.get("order_total_price", 0)
    deposit = context.user_data.get("order_deposit", 0)

    if total_price == 0 or deposit == 0:
        clean_p = _normalize_digits(str(prod.get("price", "0"))).replace(",", "").replace("،", "").strip()
        digits = re.findall(r'\d+', clean_p)
        if digits:
            try:
                total_price = int("".join(digits))
                deposit = int(round((total_price * 0.08) / 10000)) * 10000
                if deposit == 0:
                    deposit = int(round((total_price * 0.08) / 1000)) * 1000
            except Exception:
                pass

    remaining = max(0, total_price - deposit)

    order_data = {
        "order_code": order_code,
        "user_id": user.id,
        "username": f"@{user.username}" if user.username else "",
        "product_id": prod.get("product_id", ""),
        "product_name": prod.get("name", ""),
        "full_name": context.user_data.get("order_name"),
        "phone1": context.user_data.get("order_phone1"),
        "phone2": context.user_data.get("order_phone2"),
        "province_city": context.user_data.get("order_city"),
        "address": context.user_data.get("order_address"),
        "postal_code": context.user_data.get("order_postal"),
        "total_price": str(total_price),
        "deposit_amount": str(deposit),
        "status": "Awaiting_Payment"
    }

    await db.create_order(order_data)

    # ۱. تولید پیش‌فاکتور رسمی دیجیتال (Ultra HD PNG) با برچسب نارنجی در انتظار بیعانه
    invoice_path = None
    out_png = f"invoices/pre_invoice_{order_code}.png"
    try:
        import asyncio
        inv_data = build_invoice_data_from_order(order_data, prod)
        os.makedirs("invoices", exist_ok=True)
        invoice_path = await asyncio.to_thread(generate_invoice_png, inv_data, output_path=out_png, is_pre_invoice=True)
    except Exception as e:
        logger.error(f"Async pre-invoice generation failed: {e}")

    # فال‌بک تولید مستقیم سنکرون در صورت عدم موفقیت در ترد
    if not invoice_path or not os.path.exists(invoice_path):
        try:
            inv_data = build_invoice_data_from_order(order_data, prod)
            invoice_path = generate_invoice_png(inv_data, output_path=out_png, is_pre_invoice=True)
        except Exception as e2:
            logger.error(f"Sync fallback pre-invoice generation error: {e2}")

    f_total_price = to_fa_digits(f"{total_price:,}")
    f_deposit = to_fa_digits(f"{deposit:,}")
    f_remaining = to_fa_digits(f"{remaining:,}")

    invoice_msg = (
        f"🧾 <b>پیش‌فاکتور رسمی سفارش @AiKala_bot هوشمند کالا</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 <b>شماره سفارش:</b> <code>{order_code}</code>\n"
        f"📦 <b>کالای انتخابی:</b> {prod.get('name', 'کالای سفارشی')}\n"
        f"👤 <b>تحویل‌گیرنده:</b> {order_data['full_name']}\n"
        f"📱 <b>شماره تماس:</b> {order_data['phone1']}\n"
        f"📍 <b>مقصد تحویل:</b> {order_data['province_city']} - {order_data['address']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>وضعیت سند: پیش‌فاکتور رسمی (در انتظار واریز بیعانه)</b>\n"
        f"💰 <b>قیمت قطعی روز با احتساب هزینه ارسال درب منزل:</b> <b>{f_total_price} تومان</b>\n"
        f"💳 <b>مبلغ بیعانه پیش‌پرداخت (۸٪):</b> <b>{f_deposit} تومان</b>\n"
        f"▫️ <b>مانده تسویه پس از تحویل و تست سلامت:</b> <b>{f_remaining} تومان</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"▫️ شماره کارت رسمی: <code>{CARD_NUMBER}</code>\n"
        f"▫️ شماره شبا بانکی: {SHABA_HTML}\n"
        f"▫️ به نام: <b>{CARD_HOLDER}</b>\n"
        f"⏱ <b>مهلت اعتبار رزرو انبار:</b> ۵ ساعت کاری\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>نکته مهم: جهت قطعی شدن سفارش و صدور فاکتور نهایی فروش با مهر شرکتی، لطفاً بیعانه ({f_deposit} تومان) را از طریق کارت به کارت یا شماره شبا واریز و عکس فیش را ارسال فرمایید.</i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 ارسال تصویر فیش واریزی", callback_data=f"uprec|{order_code}")],
        [InlineKeyboardButton("🔄 پیگیری لحظه‌ای وضعیت سفارش", callback_data=f"track_ord|{order_code}")],
        [InlineKeyboardButton("📞 پشتیبانی و مشاوره", callback_data="show_support")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])

    chat_id = update.effective_chat.id if update.effective_chat else update.effective_user.id
    photo_sent = False

    if invoice_path and os.path.exists(invoice_path):
        # کپشن مختصر، پایدار و بدون ریسک شکستن تگ HTML در محدودیت کاراکتر تلگرام
        photo_caption = (
            f"🧾 <b>تصویر پیش‌فاکتور رسمی سفارش @AiKala_bot</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔖 شماره سفارش: <code>{order_code}</code>\n"
            f"📦 کالا: {prod.get('name', 'کالای سفارشی')}\n"
            f"💰 قیمت کل: <b>{f_total_price} تومان</b>\n"
            f"💳 بیعانه پیش‌پرداخت (۸٪): <b>{f_deposit} تومان</b>\n"
            f"▫️ مانده تسویه در محل: <b>{f_remaining} تومان</b>\n"
            f"⏳ وضعیت: در انتظار واریز بیعانه"
        )

        # تلاش ۱: ارسال به عنوان Photo
        try:
            with open(invoice_path, "rb") as f_img:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f_img,
                    caption=photo_caption,
                    parse_mode="HTML",
                    read_timeout=60.0,
                    write_timeout=90.0,
                    connect_timeout=30.0
                )
            photo_sent = True
        except Exception as e_photo:
            logger.warning(f"send_photo for pre-invoice failed ({e_photo}), attempting send_document fallback...")
            # تلاش ۲: ارسال به عنوان Document در صورت خطای شبکه یا فشرده‌سازی
            try:
                with open(invoice_path, "rb") as f_doc:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f_doc,
                        filename=f"pre_invoice_{order_code}.png",
                        caption=photo_caption,
                        parse_mode="HTML",
                        read_timeout=60.0,
                        write_timeout=90.0,
                        connect_timeout=30.0
                    )
                photo_sent = True
            except Exception as e_doc:
                logger.error(f"send_document also failed: {e_doc}")

    # ارسال اطلاعات کامل حساب، جزئیات سفارش و کلیدهای شیشه‌ای عملیاتی
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=invoice_msg,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as ex_msg:
        logger.error(f"Error sending invoice text message: {ex_msg}")
        if update.message:
            await update.message.reply_text(invoice_msg, reply_markup=kb, parse_mode="HTML")

    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    await update.message.reply_text("❌ عملیات لغو گردید.", reply_markup=main_menu_keyboard(is_admin(user_id)))
    return ConversationHandler.END

async def cancel_and_handle_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خروج ایمن از کانوِرسیشن و پردازش آنی دکمه‌های ناوبری شیشه‌ای"""
    query = update.callback_query
    if query:
        data = query.data
        try:
            await query.answer()
        except Exception:
            pass

        if data == "back_to_main":
            user_id = query.from_user.id
            await query.message.reply_text("🏠 بازگشت به منوی اصلی:", reply_markup=main_menu_keyboard(is_admin(user_id)))
        elif data in ["track_order_list", "track_refresh_list"]:
            from order_tracking import show_order_tracking
            await show_order_tracking(update, context)
        elif data.startswith("track_ord|"):
            from order_tracking import order_tracking_callback_handler
            await order_tracking_callback_handler(update, context)
        elif data == "show_support":
            from support_service import show_support_menu
            await show_support_menu(update, context)
        elif data.startswith("uprec|"):
            order_code = data.split("|")[1]
            context.user_data["upload_order_code"] = order_code
            await query.message.reply_text(
                f"📸 لطفاً <b>عکس فیش واریزی</b> مربوط به سفارش <code>{order_code}</code> را ارسال نمایید:",
                parse_mode="HTML"
            )
            return RECEIPT_FILE

    return ConversationHandler.END

# ─── مراحل ارسال فیش واریزی ───

async def start_receipt_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_code = query.data.split("|")[1]
    context.user_data["upload_order_code"] = order_code

    await query.message.reply_text(
        f"📸 لطفاً <b>عکس فیش واریزی</b> مربوط به سفارش <code>{order_code}</code> را ارسال نمایید:",
        parse_mode="HTML"
    )
    return RECEIPT_FILE

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_code = context.user_data.get("upload_order_code")
    photo = update.message.photo[-1]
    file_id = photo.file_id

    await db.update_order_status(order_code, status="Receipt_Uploaded", receipt_file_id=file_id)

    reply_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 پیگیری لحظه‌ای وضعیت سفارش", callback_data=f"track_ord|{order_code}")],
        [InlineKeyboardButton("📞 پشتیبانی و پیگیری مالی", callback_data="show_support")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])

    await update.message.reply_text(
        f"✅ <b>فیش واریزی شما با موفقیت در سامانه ثبت شد!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 شماره سفارش: <code>{order_code}</code>\n\n"
        f"واحد حسابداری حداکثر ظرف ۳۰ دقیقه فیش شما را تایید نموده و <b>فاکتور قطعی و نهایی فروش</b> به صورت خودکار برای شما ارسال خواهد شد.",
        reply_markup=reply_kb,
        parse_mode="HTML"
    )

    for adm_id in ADMIN_IDS:
        try:
            adm_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تایید فیش و صدور فاکتور قطعی", callback_data=f"adm_ok|{order_code}"),
                    InlineKeyboardButton("❌ رد فیش", callback_data=f"adm_no|{order_code}")
                ]
            ])
            await context.bot.send_photo(
                chat_id=adm_id,
                photo=file_id,
                caption=f"🔔 <b>فیش واریزی جدید دریافت شد!</b>\nکد سفارش: <code>{order_code}</code>\nکاربر: @{update.effective_user.username}",
                reply_markup=adm_kb,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error notifying admin {adm_id}: {e}")

    return ConversationHandler.END

# ─── توابع تولید هندلرها برای bot.py ───

def get_order_conversation_handler() -> ConversationHandler:
    nav_pattern = r"^(back_to_main|track_order_list|track_refresh_list|track_ord\||show_support|guide_main|close_window)"
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_order_flow, pattern=r"^buy\|")],
        states={
            ORDER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_name_step), CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)],
            ORDER_PHONE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_phone1_step), CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)],
            ORDER_PHONE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_phone2_step), CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)],
            ORDER_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_city_step), CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)],
            ORDER_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_address_step), CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)],
            ORDER_POSTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_postal_step), CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)
        ]
    )

def get_receipt_conversation_handler() -> ConversationHandler:
    nav_pattern = r"^(back_to_main|track_order_list|track_refresh_list|track_ord\||show_support|guide_main|close_window)"
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_receipt_upload, pattern=r"^uprec\|")],
        states={
            RECEIPT_FILE: [
                MessageHandler(filters.PHOTO, handle_receipt_photo),
                CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_and_handle_nav_callback, pattern=nav_pattern)
        ]
    )
