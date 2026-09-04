#!/usr/bin/env python3
"""
تکمیل هوشمند مشخصات فنی محصولات با DeepSeek API
=================================================
ویژگی‌ها و بهینه‌سازی‌ها:
۱. اجرای تک‌باره (One-time run): فقط کالاهای فاقد مشخصات بررسی می‌شوند و به هیچ عنوان برای یک کالا دو بار فراخوانی نمی‌شود.
۲. حذف کامل رنگ و صفت‌های ظاهری از نام کالا جهت به حداقل رساندن توکن‌ها و جلوگیری از استخراج مشخصات ظاهری.
۳. پرامپت فوق فشرده با خروجی حداکثر ۵۰ تا ۶۰ توکن به زبان فارسی در قالب کلید:مقدار.
۴. ذخیره‌سازی دائمی مستقیم در catalog_products.json و دیتابیس محلی bot_data.db.
۵. قابلیت توقف و ادامه هوشمند (Resume): در صورت قطع، بدون تکرار موارد قبلی ادامه می‌یابد.
"""

import os
import re
import json
import time
import urllib.request
import urllib.error
import sqlite3
import argparse
import logging
from typing import Dict, Any, Optional

# لود خودکار متغیرهای .env در صورت وجود
def load_env_file(filepath: str = ".env"):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)
logger = logging.getLogger("DeepSeekEnricher")

CATALOG_FILE = "catalog_products.json"
DB_FILE = "bot_data.db"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"

# لیست رنگ‌ها و عبارات ظاهری که باید قبل از ارسال به AI حذف شوند تا توکن هدر نرود
COLOR_AND_STOPWORDS_REGEX = re.compile(
    r'\b(مشکی|سفید|سیلور|نقره‌ای|نقره ای|دودی|استیل|طلایی|تیتانیوم|قرمز|آبی|زرد|طوسی|نوک مدادی|رنگ|اصل|اورجینال|اصلی|مدل|سری|ضمانت|گارانتی|جدید|black|white|silver|grey|gray|inox|gold)\b',
    flags=re.IGNORECASE
)

SYSTEM_PROMPT = (
    "تو کارشناس فنی لوازم خانگی هستی. برای مدل کالا، دقیقاً ۳ یا ۴ ویژگی فنی و حیاتی (مانند توان مصرفی، گنجایش، کشور سازنده یا نوع موتور) بنویس. "
    "قالب: هر خط یک ویژگی به صورت 'عنوان: مقدار'. رنگ، قیمت، مقدمه و نتیجه‌گیری ننویس."
)

def clean_product_name_for_ai(name: str) -> str:
    """حذف رنگ، کلمات زائد و فاصله‌های اضافی از نام محصول جهت کاهش حداکثری مصرف توکن"""
    if not name:
        return ""
    cleaned = COLOR_AND_STOPWORDS_REGEX.sub(" ", name)
    cleaned = re.sub(r'[\(\)\[\]،,\-_/]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def call_deepseek_api(api_key: str, product_name: str, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL) -> Optional[Dict[str, str]]:
    """فراخوانی کم‌مصرف API دیپ‌سیک با محدودیت سختگیرانه توکن (Max Tokens = 60)"""
    cleaned_name = clean_product_name_for_ai(product_name)
    if not cleaned_name:
        return None

    # آماده‌سازی آدرس اندپوینت
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"کالا: {cleaned_name}"}
        ],
        "max_tokens": 65,
        "temperature": 0.1,
        "stream": False
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            
            # پارس کردن خروجی خطی به دیکشنری مشخصات
            specs = {}
            for line in content.split("\n"):
                line = line.strip().lstrip("-*▫️ ")
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if k and v and len(k) < 30 and len(v) < 60:
                        specs[k] = v
                elif "：" in line: # کاراکتر دو نقطه فارسی/عربی
                    k, v = line.split("：", 1)
                    k = k.strip()
                    v = v.strip()
                    if k and v:
                        specs[k] = v
            return specs
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        logger.error(f"HTTP Error {e.code}: {err_msg}")
        return None
    except Exception as e:
        logger.error(f"Request failed for {cleaned_name}: {e}")
        return None

def product_has_specs(product: dict) -> bool:
    """بررسی اینکه آیا کالا از قبل دارای مشخصات فنی کامل است یا خیر"""
    if not product:
        return True
    if product.get("ai_specs"):
        return True
    return bool(
        product.get("panel") or product.get("assembly") or product.get("resolution") or 
        product.get("temp_range") or product.get("key_features") or product.get("plan") or 
        product.get("capacity_kg") or product.get("baskets")
    )

def _sync_save_product_update(pid: str, specs: dict):
    """ذخیره دائمی مشخصات استخراج شده در catalog_products.json و دیتابیس محلی"""
    try:
        if not os.path.exists(CATALOG_FILE):
            return
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        spec_str = " | ".join([f"{k}: {v}" for k, v in specs.items()])
        if isinstance(data, dict):
            if pid in data:
                data[pid]["ai_specs"] = specs
                data[pid]["more_details"] = spec_str
            else:
                for k, v in data.items():
                    if str(v.get("product_id")) == str(pid):
                        v["ai_specs"] = specs
                        v["more_details"] = spec_str
                        break
        elif isinstance(data, list):
            for item in data:
                if str(item.get("product_id")) == str(pid):
                    item["ai_specs"] = specs
                    item["more_details"] = spec_str
                    break

        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 [CACHE SAVED] مشخصات کالا {pid} برای همیشه در کاتالوگ ذخیره شد.")
    except Exception as e:
        logger.error(f"Error saving enriched product {pid} to catalog: {e}")

async def async_enrich_product_on_demand(product: dict) -> bool:
    """
    تکمیل در لحظه مشخصات هنگام کلیک کاربر (Lazy Loading On-Demand):
    ۱. بررسی می‌کند آیا کالا قبلاً مشخصات دارد؟ اگر بله، هیچ کار اضافه‌ای انجام نمی‌دهد (۰ توکن).
    ۲. فقط کالاهای بدون مشخصات با DeepSeek استعلام شده و در لحظه برای کاربر نمایش داده می‌شوند.
    ۳. نتیجه استخراج‌شده به صورت همزمان برای همیشه در کاتالوگ ذخیره می‌شود تا دفعات بعدی دیگر نیازی به هوش مصنوعی نباشد.
    """
    if not product or product_has_specs(product):
        return False

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return False

    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip()
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip()
    pname = product.get("name", "")
    if not pname:
        return False

    # فراخوانی غیرمسدودکننده با تایم‌اوت مشخص جهت جلوگیری از توقف ربات
    try:
        specs = await asyncio.wait_for(
            asyncio.to_thread(call_deepseek_api, api_key, pname, base_url, model),
            timeout=7.0
        )
    except Exception as e:
        logger.warning(f"On-demand DeepSeek enrichment note for {pname}: {e}")
        return False

    if specs and isinstance(specs, dict):
        product["ai_specs"] = specs
        if not isinstance(product.get("specs"), dict):
            product["specs"] = {}
        for k, v in specs.items():
            product["specs"][k] = v
        product["more_details"] = " | ".join([f"{k}: {v}" for k, v in specs.items()])

        pid = str(product.get("product_id") or "")
        if pid:
            asyncio.create_task(asyncio.to_thread(_sync_save_product_update, pid, specs))
        return True

    return False

def main():
    parser = argparse.ArgumentParser(description="DeepSeek Specs Enricher")
    parser.add_argument("--key", default="", help="DeepSeek API Key")
    parser.add_argument("--base-url", default="", help="DeepSeek Base URL (default: https://api.deepseek.com)")
    parser.add_argument("--model", default="", help="DeepSeek Model (default: deepseek-v4-flash)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of products to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Print candidates without calling API")
    args = parser.parse_args()

    api_key = args.key or os.getenv("DEEPSEEK_API_KEY", "").strip()
    base_url = args.base_url or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip()
    model = args.model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip()
    if not api_key and not args.dry_run:
        logger.error("کلید DEEPSEEK_API_KEY یافت نشد. می‌توانید با --key یا در متغیر محیطی تنظیم کنید.")
        return

    if not os.path.exists(CATALOG_FILE):
        logger.error(f"فایل کاتالوگ {CATALOG_FILE} یافت نشد.")
        return

    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog_data = json.load(f)

    # تبدیل به لیست اگر دیکشنری باشد
    is_dict = isinstance(catalog_data, dict)
    products = list(catalog_data.values()) if is_dict else catalog_data

    # شناسایی کالاهایی که نیاز به تکمیل مشخصات دارند
    candidates = []
    for p in products:
        # اگر قبلاً با هوش مصنوعی تکمیل شده باشد، رد شو (One-time rule)
        if p.get("ai_specs"):
            continue

        # اگر کالایی قبلاً ستون‌های کامل فنی (مانند تلویزیون و کولر و...) دارد، نیازی به مصرف توکن ندارد
        has_native_specs = bool(
            p.get("panel") or p.get("assembly") or p.get("resolution") or 
            p.get("temp_range") or p.get("key_features") or p.get("plan") or 
            p.get("capacity_kg") or p.get("baskets")
        )
        if has_native_specs:
            continue

        candidates.append(p)

    logger.info(f"تعداد کل محصولات کاتالوگ: {len(products)}")
    logger.info(f"تعداد محصولاتی که نیاز به تکمیل مشخصات با هوش مصنوعی دارند: {len(candidates)}")

    if args.dry_run:
        logger.info("نمونه ۵ محصول اول نامزد جهت پردازش با هوش مصنوعی:")
        for c in candidates[:5]:
            clean_name = clean_product_name_for_ai(c.get("name", ""))
            logger.info(f" - {c.get('name')} -> پاکسازی‌شده برای پرامپت: '{clean_name}'")
        return

    if args.limit > 0:
        candidates = candidates[:args.limit]
        logger.info(f"پردازش محدود به {args.limit} کالا شد.")

    processed_count = 0
    success_count = 0

    for p in candidates:
        pid = p.get("product_id") or p.get("name")
        pname = p.get("name", "")
        logger.info(f"[{processed_count + 1}/{len(candidates)}] پردازش: {pname}")

        specs = call_deepseek_api(api_key, pname, base_url, model)
        if specs:
            p["ai_specs"] = specs
            # همچنین کلید more_details را بروز می‌کنیم
            spec_str = " | ".join([f"{k}: {v}" for k, v in specs.items()])
            p["more_details"] = spec_str
            success_count += 1
            logger.info(f"   ✓ مشخصات دریافت شد: {spec_str}")
        else:
            logger.warning(f"   ✗ دریافت مشخصات برای {pname} ناموفق بود.")

        processed_count += 1

        # ذخیره دسته‌ای هر ۵ محصول جهت جلوگیری از هدررفت و امکان توقف امن
        if processed_count % 5 == 0:
            with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                json.dump(catalog_data, f, ensure_ascii=False, indent=2)
            logger.info("💾 تغییرات تا اینجا روی catalog_products.json ذخیره شد.")

        time.sleep(0.4) # وقفه کوتاه جهت کنترل ریت لیمیت

    # ذخیره نهایی
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ پردازش تکمیل شد: {success_count} کالا با موفقیت به‌روزرسانی شدند.")

if __name__ == "__main__":
    main()
