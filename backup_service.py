"""
AiKala - Backup & Restore Service (backup_service.py)
=====================================================
سرویس جامع و ایمن پشتیبان‌گیری و بازگردانی کلی سیستم:
۱. ساخت فایل یکپارچه ZIP شامل:
   - دیتابیس SQLite (bot_data.db) با تمام سفارشات، فاکتورها، تاریخچه‌ها و کانال‌ها
   - نقشه تصاویر و آلبوم‌های متصل به محصولات (verified_photos.json, channel_photos_map.json)
   - کاتالوگ جامع محصولات و مشخصات غنی‌شده هوش مصنوعی (catalog_products.json, laptops_catalog.json)
   - تنظیمات بانکی و پرداخت (bank_settings.json)
   - تنظیمات موتورهای هوش مصنوعی (ai_settings.json)
   - مانیفست کامل متادیتا (manifest.json) با آمار دقیق و زمان تولید
۲. بازگردانی کامل با رونویسی (Full Replace Restore) با ایجاد اسنپ‌شات ایمنی اضطراری
۳. ادغام هوشمند (Smart Merge / Append) جهت افزودن داده‌های بک‌آپ به سیستم جاری بدون حذف داده‌های جدید
۴. سیستم پشتیبان‌گیری خودکار ۲۴ ساعته (غیرفعال به صورت پیش‌فرض، با قابلیت فعال‌سازی از پنل ادمین)
"""

import os
import io
import json
import time
import zipfile
import sqlite3
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger(__name__)

BACKUP_DIR = "backups"
BACKUP_SETTINGS_FILE = "backup_settings.json"

DEFAULT_BACKUP_SETTINGS = {
    "auto_backup_enabled": False,
    "interval_hours": 24,
    "last_auto_backup": "",
    "keep_max_backups": 7
}

def load_backup_settings() -> Dict[str, Any]:
    """بارگذاری تنظیمات بک‌آپ خودکار"""
    settings = dict(DEFAULT_BACKUP_SETTINGS)
    if os.path.exists(BACKUP_SETTINGS_FILE):
        try:
            with open(BACKUP_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    settings.update(data)
        except Exception as e:
            logger.warning(f"Error loading backup_settings.json: {e}")
    return settings

def save_backup_settings(settings: Dict[str, Any]) -> bool:
    """ذخیره تنظیمات بک‌آپ خودکار"""
    try:
        with open(BACKUP_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving backup_settings.json: {e}")
        return False

def set_auto_backup_state(enabled: bool) -> Dict[str, Any]:
    """تغییر وضعیت فعال/غیرفعال بودن بک‌آپ خودکار"""
    settings = load_backup_settings()
    settings["auto_backup_enabled"] = enabled
    settings["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_backup_settings(settings)
    return settings


def _collect_database_summary(db_path: str = "bot_data.db") -> Dict[str, int]:
    """جمع‌آوری خلاصه آماری جداول دیتابیس برای درج در مانیفست"""
    summary = {}
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    cnt = cur.fetchone()[0]
                    summary[t] = cnt
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            logger.warning(f"Error reading db summary: {e}")
    return summary


def create_full_backup_zip() -> Tuple[str, Dict[str, Any]]:
    """
    تولید یک فایل فشرده ZIP حاوی تمام داده‌های حیاتی پروژه.
    خروجی: (مسیر_فایل_زیپ, دیکشنری_مانیفست)
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    readable_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    zip_filename = f"AiKala_Backup_{timestamp}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_filename)

    db_summary = _collect_database_summary("bot_data.db")

    # جمع‌آوری آمار کاتالوگ و تصاویر
    catalog_count = 0
    if os.path.exists("catalog_products.json"):
        try:
            with open("catalog_products.json", "r", encoding="utf-8") as f:
                c_data = json.load(f)
                catalog_count = len(c_data)
        except Exception:
            pass

    verified_photos_count = 0
    if os.path.exists("verified_photos.json"):
        try:
            with open("verified_photos.json", "r", encoding="utf-8") as f:
                v_data = json.load(f)
                verified_photos_count = len(v_data)
        except Exception:
            pass

    manifest = {
        "backup_name": zip_filename,
        "created_at": readable_date,
        "version": "2.5.0",
        "orders_count": db_summary.get("orders", 0),
        "products_catalog_count": catalog_count,
        "verified_photos_count": verified_photos_count,
        "database_summary": db_summary,
        "included_files": []
    }

    files_to_pack = [
        ("bot_data.db", "database/bot_data.db"),
        ("catalog_products.json", "catalogs/catalog_products.json"),
        ("laptops_catalog.json", "catalogs/laptops_catalog.json"),
        ("verified_photos.json", "photos/verified_photos.json"),
        ("channel_photos_map.json", "photos/channel_photos_map.json"),
        ("bank_settings.json", "settings/bank_settings.json"),
        ("ai_settings.json", "settings/ai_settings.json"),
        ("backup_settings.json", "settings/backup_settings.json"),
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in files_to_pack:
            if os.path.exists(src):
                try:
                    zf.write(src, arcname=arc)
                    manifest["included_files"].append({
                        "source": src,
                        "archive_path": arc,
                        "size_bytes": os.path.getsize(src)
                    })
                except Exception as e:
                    logger.warning(f"Error adding {src} to backup zip: {e}")

        # درج شناسنامه (manifest.json) در ریشه فایل زیپ
        manifest_data = json.dumps(manifest, ensure_ascii=False, indent=2)
        zf.writestr("manifest.json", manifest_data)

    logger.info(f"Full backup created successfully: {zip_path} (Orders: {manifest['orders_count']}, Products: {manifest['products_catalog_count']})")
    return zip_path, manifest


def inspect_backup_zip(zip_file_bytes_or_path) -> Optional[Dict[str, Any]]:
    """
    بررسی و اعتبارسنجی فایل زیپ آپلود شده توسط ادمین و استخراج مانیفست.
    در صورت نامعتبر بودن یا عدم وجود فایل‌های حیاتی، None برمی‌گرداند.
    """
    try:
        zf = zipfile.ZipFile(zip_file_bytes_or_path, "r")
        namelist = zf.namelist()
        manifest = {}

        if "manifest.json" in namelist:
            try:
                manifest_raw = zf.read("manifest.json").decode("utf-8")
                manifest = json.loads(manifest_raw)
            except Exception:
                manifest = {}

        # بررسی وجود دیتابیس یا کاتالوگ
        has_db = any(n.endswith("bot_data.db") for n in namelist)
        has_catalog = any(n.endswith("catalog_products.json") for n in namelist)

        if not has_db and not has_catalog:
            zf.close()
            return None

        manifest["namelist"] = namelist
        manifest["has_db"] = has_db
        manifest["has_catalog"] = has_catalog
        zf.close()
        return manifest
    except Exception as e:
        logger.error(f"Failed to inspect backup zip: {e}")
        return None


def restore_full_replace(zip_file_bytes_or_path) -> Tuple[bool, str]:
    """
    بازگردانی کامل (Replace All):
    ۱. ساخت بک‌آپ اضطراری از داده‌های فعلی
    ۲. جایگزینی دیتابیس، کاتالوگ‌ها، عکس‌ها و تنظیمات با محتوای فایل زیپ
    """
    try:
        # ساخت اسنپ‌شات ایمنی قبل از بازنویسی
        safety_path, _ = create_full_backup_zip()
        logger.info(f"Safety snapshot saved before full restore: {safety_path}")

        zf = zipfile.ZipFile(zip_file_bytes_or_path, "r")
        namelist = zf.namelist()

        restored_items = []

        # ۱. استخراج دیتابیس
        for name in namelist:
            if name.endswith("bot_data.db"):
                data = zf.read(name)
                with open("bot_data.db", "wb") as f:
                    f.write(data)
                restored_items.append("پایگاه داده اصلی (bot_data.db)")
                break

        # ۲. استخراج کاتالوگ‌ها
        for name in namelist:
            if name.endswith("catalog_products.json"):
                data = zf.read(name)
                with open("catalog_products.json", "wb") as f:
                    f.write(data)
                restored_items.append("کاتالوگ محصولات (catalog_products.json)")
            elif name.endswith("laptops_catalog.json"):
                data = zf.read(name)
                with open("laptops_catalog.json", "wb") as f:
                    f.write(data)
                restored_items.append("کاتالوگ لپ‌تاپ‌ها (laptops_catalog.json)")

        # ۳. استخراج نقشه تصاویر
        for name in namelist:
            if name.endswith("verified_photos.json"):
                data = zf.read(name)
                with open("verified_photos.json", "wb") as f:
                    f.write(data)
                restored_items.append("تصاویر تایید شده محصولات (verified_photos.json)")
            elif name.endswith("channel_photos_map.json"):
                data = zf.read(name)
                with open("channel_photos_map.json", "wb") as f:
                    f.write(data)
                restored_items.append("نقشه پست‌های کانال عکس (channel_photos_map.json)")

        # ۴. استخراج تنظیمات
        for name in namelist:
            if name.endswith("bank_settings.json"):
                data = zf.read(name)
                with open("bank_settings.json", "wb") as f:
                    f.write(data)
                restored_items.append("تنظیمات حساب بانکی و بیعانه")
            elif name.endswith("ai_settings.json"):
                data = zf.read(name)
                with open("ai_settings.json", "wb") as f:
                    f.write(data)
                restored_items.append("تنظیمات هوش مصنوعی کالا")

        zf.close()

        # بازخوانی حافظه رم سرویس‌ها
        _reload_in_memory_services()

        msg = f"✅ بازگردانی کامل با موفقیت انجام شد:\n" + "\n".join([f"▫️ {it}" for it in restored_items])
        return True, msg
    except Exception as e:
        logger.error(f"Full restore failed: {e}")
        return False, f"خطا در بازگردانی فایل بک‌آپ: {e}"


def restore_smart_merge(zip_file_bytes_or_path) -> Tuple[bool, str, Dict[str, int]]:
    """
    ادغام هوشمند (Smart Merge / Append):
    - سفارش‌های موجود در بک‌آپ که در دیتابیس فعلی نیستند، اضافه می‌شوند (INSERT OR IGNORE).
    - تاریخچه قیمت و کانال‌های جدید ادغام می‌شوند.
    - تصاویر تایید شده جدید به نقشه تصاویر جاری اضافه می‌شوند.
    - مشخصات محصولات جدید یا کامل‌تر در کاتالوگ ادغام می‌گردند.
    - هیچ داده فعلی حذف یا بازنویسی نمی‌شود.
    """
    stats = {
        "orders_added": 0,
        "photos_added": 0,
        "products_enriched": 0,
        "channels_added": 0
    }

    try:
        zf = zipfile.ZipFile(zip_file_bytes_or_path, "r")
        namelist = zf.namelist()

        # ۱. ادغام دیتابیس SQLite
        db_member = next((n for n in namelist if n.endswith("bot_data.db")), None)
        if db_member and os.path.exists("bot_data.db"):
            temp_db_path = "temp_backup_restore.db"
            try:
                with open(temp_db_path, "wb") as f:
                    f.write(zf.read(db_member))

                curr_conn = sqlite3.connect("bot_data.db")
                backup_conn = sqlite3.connect(temp_db_path)

                # ادغام سفارشات (orders)
                try:
                    b_cur = backup_conn.cursor()
                    b_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
                    if b_cur.fetchone():
                        b_cur.execute("PRAGMA table_info(orders)")
                        cols = [r[1] for r in b_cur.fetchall() if r[1] != "id"]
                        cols_str = ", ".join(cols)
                        placeholders = ", ".join(["?"] * len(cols))

                        b_cur.execute(f"SELECT {cols_str} FROM orders")
                        b_orders = b_cur.fetchall()

                        c_cur = curr_conn.cursor()
                        for row in b_orders:
                            try:
                                c_cur.execute(
                                    f"INSERT OR IGNORE INTO orders ({cols_str}) VALUES ({placeholders})",
                                    row
                                )
                                if c_cur.rowcount > 0:
                                    stats["orders_added"] += 1
                            except Exception:
                                pass
                        curr_conn.commit()
                except Exception as e:
                    logger.warning(f"Error merging orders: {e}")

                # ادغام کانال‌های تحت پایش (monitored_channels)
                try:
                    b_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monitored_channels'")
                    if b_cur.fetchone():
                        b_cur.execute("SELECT channel_id, channel_name, keywords, active FROM monitored_channels")
                        channels = b_cur.fetchall()
                        c_cur = curr_conn.cursor()
                        for ch in channels:
                            try:
                                c_cur.execute(
                                    "INSERT OR IGNORE INTO monitored_channels (channel_id, channel_name, keywords, active) VALUES (?, ?, ?, ?)",
                                    ch
                                )
                                if c_cur.rowcount > 0:
                                    stats["channels_added"] += 1
                            except Exception:
                                pass
                        curr_conn.commit()
                except Exception as e:
                    logger.warning(f"Error merging monitored channels: {e}")

                curr_conn.close()
                backup_conn.close()
            finally:
                if os.path.exists(temp_db_path):
                    try:
                        os.remove(temp_db_path)
                    except Exception:
                        pass

        # ۲. ادغام تصاویر تایید شده (verified_photos.json)
        v_member = next((n for n in namelist if n.endswith("verified_photos.json")), None)
        if v_member:
            try:
                b_photos = json.loads(zf.read(v_member).decode("utf-8"))
                curr_photos = {}
                if os.path.exists("verified_photos.json"):
                    with open("verified_photos.json", "r", encoding="utf-8") as f:
                        curr_photos = json.load(f)

                added = 0
                for pid, pdata in b_photos.items():
                    if pid not in curr_photos:
                        curr_photos[pid] = pdata
                        added += 1
                if added > 0:
                    with open("verified_photos.json", "w", encoding="utf-8") as f:
                        json.dump(curr_photos, f, ensure_ascii=False, indent=2)
                    stats["photos_added"] = added
            except Exception as e:
                logger.warning(f"Error merging verified photos: {e}")

        # ۳. ادغام کاتالوگ محصولات و مشخصات فنی (catalog_products.json)
        c_member = next((n for n in namelist if n.endswith("catalog_products.json")), None)
        if c_member and os.path.exists("catalog_products.json"):
            try:
                b_catalog = json.loads(zf.read(c_member).decode("utf-8"))
                with open("catalog_products.json", "r", encoding="utf-8") as f:
                    curr_catalog = json.load(f)

                enriched_count = 0
                if isinstance(curr_catalog, dict) and isinstance(b_catalog, dict):
                    for pid, b_prod in b_catalog.items():
                        if pid in curr_catalog:
                            c_prod = curr_catalog[pid]
                            # اگر محصول فعلی فاقد مشخصات است ولی در بک‌آپ هست
                            if not c_prod.get("extra_description") and b_prod.get("extra_description"):
                                c_prod["extra_description"] = b_prod["extra_description"]
                                enriched_count += 1
                            if not c_prod.get("image_url") and b_prod.get("image_url"):
                                c_prod["image_url"] = b_prod["image_url"]
                        else:
                            # محصول کلاً در کاتالوگ فعلی نبوده
                            curr_catalog[pid] = b_prod
                            enriched_count += 1

                if enriched_count > 0:
                    with open("catalog_products.json", "w", encoding="utf-8") as f:
                        json.dump(curr_catalog, f, ensure_ascii=False, indent=2)
                    stats["products_enriched"] = enriched_count
            except Exception as e:
                logger.warning(f"Error merging catalog: {e}")

        zf.close()
        _reload_in_memory_services()

        msg = (
            f"✅ <b>ادغام هوشمند داده‌ها با موفقیت انجام شد:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"▫️ سفارش‌های جدید اضافه‌شده: <b>{stats['orders_added']}</b> مورد\n"
            f"▫️ تصاویر اختصاصی متصل‌شده: <b>{stats['photos_added']}</b> کالا\n"
            f"▫️ مشخصات و کالاهای تکمیل‌شده کاتالوگ: <b>{stats['products_enriched']}</b> قلم\n"
            f"▫️ کانال‌های پایش جدید: <b>{stats['channels_added']}</b> کانال\n\n"
            f"✨ <i>تمام داده‌های جاری بدون کم‌وکاست حفظ گردیدند.</i>"
        )
        return True, msg, stats
    except Exception as e:
        logger.error(f"Smart merge failed: {e}")
        return False, f"خطا در ادغام هوشمند فایل بک‌آپ: {e}", stats


def _reload_in_memory_services():
    """بازنشانی متغیرهای درون حافظه بعد از بازگردانی فایل‌ها"""
    try:
        import photo_service
        photo_service.load_verified_photos()
    except Exception:
        pass

    try:
        import search_engine
        search_engine.JSON_PRODUCTS = search_engine.load_json_products()
    except Exception:
        pass

    try:
        import config
        config.BANK_SETTINGS = config._load_bank_settings()
        config.DEPOSIT_CARD_NUMBER = config.BANK_SETTINGS.get("card_number", config.DEPOSIT_CARD_NUMBER)
        config.DEPOSIT_CARD_NAME = config.BANK_SETTINGS.get("card_holder", config.DEPOSIT_CARD_NAME)
        config.DEPOSIT_CARD_SHABA = config.BANK_SETTINGS.get("card_shaba", config.DEPOSIT_CARD_SHABA)
        config.DEPOSIT_PERCENT = config.BANK_SETTINGS.get("deposit_percent", config.DEPOSIT_PERCENT)
    except Exception:
        pass


# =====================================================================
# ⏰ تسک بک‌آپ خودکار ۲۴ ساعته (پیش‌فرض غیرفعال)
# =====================================================================

async def auto_backup_background_task(bot, admin_ids: List[int]):
    """
    تسک پس‌زمینه پشتیبان‌گیری دوره‌ای:
    - هر ساعت بررسی می‌کند.
    - اگر توسط ادمین فعال شده باشد و ۲۴ ساعت از آخرین بک‌آپ گذشته باشد، بک‌آپ می‌گیرد
      و فایل آن را مستقیماً برای ادمین در تلگرام ارسال می‌کند.
    """
    logger.info("Auto-backup background scheduler initialized.")
    while True:
        try:
            settings = load_backup_settings()
            if settings.get("auto_backup_enabled"):
                interval_hours = settings.get("interval_hours", 24)
                last_backup_str = settings.get("last_auto_backup", "")
                should_run = False

                if not last_backup_str:
                    should_run = True
                else:
                    try:
                        last_dt = datetime.strptime(last_backup_str, "%Y-%m-%d %H:%M:%S")
                        elapsed_hours = (datetime.now() - last_dt).total_seconds() / 3600.0
                        if elapsed_hours >= interval_hours:
                            should_run = True
                    except Exception:
                        should_run = True

                if should_run:
                    logger.info("Executing scheduled 24-hour backup...")
                    zip_path, manifest = create_full_backup_zip()
                    settings["last_auto_backup"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_backup_settings(settings)

                    caption = (
                        f"⏰ <b>پشتیبان‌گیری خودکار ۲۴ ساعته سیستم:</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📦 نام فایل: <code>{manifest['backup_name']}</code>\n"
                        f"📅 تاریخ: <b>{manifest['created_at']}</b>\n"
                        f"▫️ تعداد سفارش‌ها: <b>{manifest['orders_count']}</b>\n"
                        f"▫️ کاتالوگ محصولات: <b>{manifest['products_catalog_count']}</b>\n"
                        f"▫️ تصاویر اختصاصی: <b>{manifest['verified_photos_count']}</b>\n\n"
                        f"💡 <i>این فایل به صورت خودکار ذخیره و در فضای امن تلگرام آرشیو گردید.</i>"
                    )

                    for aid in admin_ids:
                        try:
                            with open(zip_path, "rb") as f_zip:
                                await bot.send_document(
                                    chat_id=aid,
                                    document=f_zip,
                                    filename=manifest["backup_name"],
                                    caption=caption,
                                    parse_mode="HTML"
                                )
                        except Exception as e:
                            logger.warning(f"Could not send auto-backup to admin {aid}: {e}")
        except Exception as e:
            logger.error(f"Error in auto_backup_background_task: {e}")

        # بررسی هر ۱ ساعت
        await asyncio.sleep(3600)
