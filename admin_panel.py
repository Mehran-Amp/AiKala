"""
AiKala - Admin Panel & Photo Management Controller (admin_panel.py)
===================================================================
مدیریت و پایش کانال‌ها، تایید سفارشات و فیش‌ها، آمار فروشگاه
و دریافت هوشمند لینک‌های آلبوم عکس توسط ادمین با محافظت Debounce و وب‌پروبینگ.
"""

import os
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
    send_verified_photos_to_user
)

logger = logging.getLogger(__name__)
db = Database()

# ─── دستورات پنل مدیریت ───

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    stats = await db.get_stats()
    text = (
        f"⚙️ <b>پنل مدیریت هوشمند AiKala</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 تعداد کل کالاها: <b>{stats.get('total_products', 0)}</b>\n"
        f"🛒 کل سفارشات ثبت‌شده: <b>{stats.get('total_orders', 0)}</b>\n"
        f"📅 سفارشات امروز: <b>{stats.get('today_orders', 0)}</b>\n"
        f"📸 تصاویر اختصاصی ثبت‌شده: <b>{len(VERIFIED_PRODUCT_PHOTOS)} کالا</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"یک گزینه را انتخاب فرمایید:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 تصاویر تایید شده محصولات", callback_data="adm_verified_photos")],
        [InlineKeyboardButton("👥 مدیریت کارشناسان پشتیبانی", callback_data="adm_manage_support")],
        [InlineKeyboardButton("📡 مدیریت کانال‌های تحت پایش", callback_data="adm_channels")],
        [InlineKeyboardButton("📋 سفارشات در انتظار تایید", callback_data="adm_pending_orders")],
        [InlineKeyboardButton("📦 مدیریت و تغییر وضعیت سفارشات", callback_data="adm_manage_orders")],
        [InlineKeyboardButton("🔄 همگام‌سازی گالری عکس‌ها", callback_data="adm_sync_photos")],
        [InlineKeyboardButton("🗑 پاکسازی و ریست کل عکس‌ها", callback_data="adm_clear_photos_ask")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
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
            logger.info(f"🌐 [ADMIN INPUT] Probing channel album via public embed for {ch_clean}/{target_mid}...")
            scraped_photos, scraped_mids = await probe_telegram_channel_album(ch_clean, target_mid)
            if scraped_photos:
                logger.info(f"🎉 [ADMIN INPUT] Successfully extracted {len(scraped_photos)} album photos from embed!")
                for sp in scraped_photos:
                    if sp not in final_file_ids:
                        final_file_ids.append(sp)
                for sm in scraped_mids:
                    if sm not in final_msg_ids:
                        final_msg_ids.append(sm)

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
    try:
        from search_engine import JSON_PRODUCTS
        prod_obj = next((p for p in JSON_PRODUCTS if str(p.get("product_id")) == str(pid)), None)
        if prod_obj:
            prod_model = str(prod_obj.get("model_number", ""))
            prod_brand = prod_obj.get("brand", "")
            prod_cat = prod_obj.get("category_name", "") or prod_obj.get("category_key", "")
    except Exception:
        pass

    save_verified_product_entry(
        pid=pid,
        product_name=pname,
        channel=channel,
        message_ids=final_msg_ids,
        file_ids=final_file_ids,
        link=post_link,
        model_number=prod_model,
        brand=prod_brand,
        category=prod_cat
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
    await update.message.reply_text(
        f"✅ <b>تصاویر محصول با موفقیت تایید و ثبت شد!</b>\n\n"
        f"📦 <b>محصول:</b> {pname}\n"
        f"🖼 <b>تعداد تصاویر کشف شده آلبوم:</b> {total_photos_detected} عکس\n"
        f"🔗 <b>مرجع تصاویر:</b> <code>{post_link or final_msg_ids}</code>\n"
        f"👥 <b>ارسال آنی برای کاربران در انتظار:</b> {sent_count} کاربر\n\n"
        f"✨ <i>از این لحظه، هر کاربری دکمه «📸 تصاویر محصول» این کالا یا مدل‌های مشابه آن را لمس کند، کل آلبوم {total_photos_detected} تایی به صورت خودکار برای او ارسال خواهد شد.</i>",
        parse_mode="HTML"
    )
