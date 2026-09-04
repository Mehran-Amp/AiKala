"""
Configuration Module — Home Appliance Bot
=========================================
All settings and environment variables for @AiKala_bot.
"""

import os
from typing import List, Dict, Any
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ------------------- Telegram Settings -------------------
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "8837314491:AAGjg67CywBAubXmM2lPm1j3hhhe9W9TdCI")
ADMIN_IDS: List[int] = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "86900909").split(",")
    if x.strip().isdigit()
]
TARGET_CHANNEL_ID: str = os.getenv("TARGET_CHANNEL_ID", "@BanehErsal,@mahmodii_shop,@bazarganisalimi99,@bazargani_faghihzadeh,@solimanybanehtv,@LGBaneh,@arbil_gold")
BOT_LINK: str = os.getenv("BOT_LINK", "@AiKala_bot")
SATISFACTION_CHANNEL: str = os.getenv("SATISFACTION_CHANNEL", "https://t.me/AiKala_bot")

# کانال مقصد انتشار عکس‌ها و مشخصات پاکسازی شده (همگام‌سازی نام‌های PHOTOS_CHANNEL و TARGET_IMAGE_CHANNEL)
TARGET_IMAGE_CHANNEL: str = os.getenv("TARGET_IMAGE_CHANNEL", "@Aikala_Image")
PHOTOS_CHANNEL: str = TARGET_IMAGE_CHANNEL

# نام کاربری رسمی پشتیبانی در تلگرام
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@faridamp")

# ------------------- Telethon (Channel Monitor) -------------------
TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID", "31810703"))
TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "43e05e117c0abddd1004e2bc2c478959")
TELEGRAM_SESSION: str = os.getenv("TELEGRAM_SESSION", "bot_session")
TG_PHONE: str = os.getenv("TG_PHONE", "+989195859434")

# ------------------- Google Sheets -------------------
GOOGLE_SHEETS_CREDENTIALS: str = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "credentials.json")
SHEET_NAME: str = os.getenv("SHEET_NAME", "HomeApplianceBot")
SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "1GGhqfVod6u54r0ceF7YLKLMoojgmjXKXEl5nqlLO9Zk")

# ------------------- Database -------------------
DB_PATH: str = os.getenv("DB_PATH", "bot_data.db")

# ------------------- Scraper Settings -------------------
MOMTAZ_BASE_URL: str = "https://momtazkalla.com"
PRICE_LIST_URL: str = f"{MOMTAZ_BASE_URL}/price/"
SYNC_INTERVAL_HOURS: int = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
PRICE_HISTORY_DAYS: int = int(os.getenv("PRICE_HISTORY_DAYS", "10"))
HEADLESS_BROWSER: bool = os.getenv("HEADLESS_BROWSER", "true").lower() == "true"

# ------------------- Shop Info & Payment -------------------
SHOP_NAME: str = os.getenv("SHOP_NAME", "فروشگاه آی‌کالا (آاگ کالا)")
SHOP_PHONE: str = os.getenv("SHOP_PHONE", "۰۹۱۹۵۸۵۹۴۳۴")
SHOP_ADDRESS: str = os.getenv("SHOP_ADDRESS", "بانه، بازارچه اصلی، فروشگاه آی کالا")
LICENSE_NO: str = os.getenv("LICENSE_NO", "125366980")

DEPOSIT_PERCENT: int = 8
DEPOSIT_CARD_NUMBER: str = os.getenv("DEPOSIT_CARD_NUMBER", "6104-3386-4929-6106")
DEPOSIT_CARD_NAME: str = os.getenv("DEPOSIT_CARD_NAME", "فروشگاه آاگ کالا مهران امین پور")

# متغیرهای معادل جهت سازگاری کامل با تمامی توابع bot.py
CARD_NUMBER: str = DEPOSIT_CARD_NUMBER
CARD_HOLDER: str = DEPOSIT_CARD_NAME
DEPOSIT_AMOUNT: str = "۲,۰۰۰,۰۰۰"
PRICE_NOTE: str = "⚠️ به علت نوسانات لحظه‌ای ارز، استعلام قیمت قطعی قبل از بارگیری الزامی است."

def round_deposit(amount: int) -> int:
    """گرد کردن مبلغ بیعانه به ارقام رند"""
    if amount >= 1_000_000:
        return round(amount / 1_000_000) * 1_000_000
    elif amount >= 100_000:
        return round(amount / 100_000) * 100_000
    return amount

# ------------------- Support Staff -------------------
SUPPORT_STAFF: List[Dict[str, str]] = [
    {
        "name": "مهران امین‌پور (مدیریت فروش)",
        "landline": "087-34220000",
        "mobile": "09195859434",
        "whatsapp_link": "https://wa.me/989195859434",
        "telegram_link": "https://t.me/faridamp",
    },
    {
        "name": "کارشناس استعلام کرایه و باربری",
        "landline": "087-34220001",
        "mobile": "09195859434",
        "whatsapp_link": "https://wa.me/989195859434",
        "telegram_link": "https://t.me/faridamp",
    },
]

SUPPORT_HOURS: str = "۹ صبح تا ۹ شب (پاسخگویی همه‌روزه)"

# ------------------- Category Detection -------------------
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "تلویزیون": ["tv", "television", "تلویزیون", "ال ای دی", "led", "oled", "qled", "qned", "nano", "اینچ", "inch", "اولد", "کیولد"],
    "یخچال": ["یخچال", "refrigerator", "فریزر", "ساید", "side", "دوقلو", "بالا فریزر", "دور این دور"],
    "لباسشویی": ["لباسشویی", "washing", "ماشین لباسشویی", "خشکشویی", "پتوشور", "پتو شور", "گیربکسی"],
    "ظرفشویی": ["ظرفشویی", "dishwasher", "ماشین ظرفشویی", "زئولیت"],
    "کولرگازی": ["کولر", "اسپلیت", "split", "air conditioner", "کولرگازی", "کولر گازی", "موتور سنگین"],
    "فر و مایکروویو": ["فر", "مایکروویو", "micro", "oven", "توکار", "سولاردام", "سولاردوم", "سولدام"],
    "جاروبرقی": ["جارو", "vacuum", "جاروشارژی", "جاروبرقی", "رباتیک", "جارو برقی"],
    "اتو": ["اتو", "iron", "بخارشو", "اتوپرس", "بخارگر"],
    "ساندبار و اسپیکر": ["ساندبار", "soundbar", "اسپیکر", "سیستم صوتی", "سینما خانگی"],
    "لوازم آشپزخانه": ["غذاساز", "مخلوط‌کن", "آبمیوه‌گیری", "ساندویچ‌ساز", "سرخ‌کن", "قهوه‌ساز", "چای‌ساز"],
    "لوازم ریز": ["خردکن", "همزن", "چرخ گوشت", "گوشت کوب", "آسیاب", "اسپرسوساز", "سرخ کن", "هواپز", "لوازم ریز"],
}

IMPORTANT_SPECS: Dict[str, List[str]] = {
    "تلویزیون": ["سایز", "اینچ", "کیفیت تصویر", "رزولوشن", "پنل", "رفرش ریت", "سیستم عامل", "مونتاژ", "سال"],
    "یخچال": ["ظرفیت", "لیتر", "فوت", "نوع موتور", "سیستم سرمایش", "رنگ", "مونتاژ", "ابعاد"],
    "لباسشویی": ["ظرفیت", "کیلوگرم", "دور خشک کن", "نوع موتور", "برنامه شستشو", "رنگ", "مونتاژ"],
    "ظرفشویی": ["ظرفیت", "نفره", "تعداد طبقات", "برنامه شستشو", "موتور", "مونتاژ"],
    "default": ["برند", "مدل", "رنگ", "ابعاد", "وزن", "توان", "مونتاژ"]
}

def detect_category(product_name: str) -> str:
    name_lower = product_name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in name_lower:
                return category
    return "default"

def get_important_specs(category: str) -> List[str]:
    return IMPORTANT_SPECS.get(category, IMPORTANT_SPECS["default"])

def format_price(num_str: str) -> str:
    if not num_str:
        return "استعلام"
    try:
        clean = str(num_str).replace(",", "").replace("،", "").strip()
        if not clean or clean == "0":
            return "استعلام"
        num = int(clean)
        return f"{num:,}".replace(",", "،")
    except:
        return str(num_str)

DEFAULT_CHANNELS = [
    {
        "channel_id": "@bazargani_faghihzadeh",
        "channel_name": "بازرگانی فقیه‌زاده",
        "keywords": [],
        "active": True
    },
    {
        "channel_id": "@LG_SAMSUNG_DEAWOO",
        "channel_name": "الجی سامسونگ دوو",
        "keywords": [],
        "active": True
    }
]

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")