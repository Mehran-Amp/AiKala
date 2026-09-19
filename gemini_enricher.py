# -*- coding: utf-8 -*-
"""
gemini_enricher.py
==================
موتور مدیریت هوشمند مشخصات فنی محصولات با قابلیت تنظیم در پنل ادمین
(Google Gemini / DeepSeek / خاموش)
کاملاً تقاضامحور (On-Demand / Lazy):
۱. فقط در صورت کلیک کاربر روی کارت یا پست محصول اجرا می‌شود.
۲. مشخصات ۱۰۰٪ منطبق با نام، برند و کد مدل دقیق کالا جهت جلوگیری از اطلاعات الکی و غیرواقعی استخراج می‌شود.
۳. مشخصات استخراج‌شده «یکبار برای همیشه» در کاتالوگ و دیتابیس ذخیره می‌شود.
۴. امکان تغییر موتور (جمینای، دیپ‌سیک یا خاموش) از طریق پنل مدیریت ربات.
"""

import os
import re
import json
import sqlite3
import asyncio
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

logger = logging.getLogger("AIEnricher")

CATALOG_FILE = "catalog_products.json"
DB_FILE = "bot_data.db"
AI_SETTINGS_FILE = "ai_settings.json"

# تنظیمات پیش‌فرض مدل‌ها
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
FALLBACK_GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ─── مدیریت تنظیمات هوش مصنوعی (Gemini / DeepSeek / Off) ───

def get_ai_settings() -> dict:
    """دریافت تنظیمات فعلی هوش مصنوعی از فایل یا مقدار پیش‌فرض"""
    default_settings = {
        "provider": "gemini",  # gemini | deepseek | off
        "gemini_model": DEFAULT_GEMINI_MODEL,
        "deepseek_model": DEFAULT_DEEPSEEK_MODEL,
        "updated_at": ""
    }
    if os.path.exists(AI_SETTINGS_FILE):
        try:
            with open(AI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_settings.update({k: v for k, v in saved.items() if v is not None})
        except Exception as e:
            logger.debug(f"Error loading AI settings: {e}")
    return default_settings

def set_ai_provider(provider: str) -> bool:
    """تغییر موتور فعال هوش مصنوعی (gemini, deepseek, off)"""
    clean_provider = provider.lower().strip()
    if clean_provider not in ["gemini", "deepseek", "off", "disabled"]:
        return False
    if clean_provider == "disabled":
        clean_provider = "off"

    settings = get_ai_settings()
    settings["provider"] = clean_provider
    try:
        import datetime
        settings["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(AI_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        logger.info(f"🔧 [AI SETTINGS] موتور فعال هوش مصنوعی به '{clean_provider}' تغییر یافت.")
        return True
    except Exception as e:
        logger.error(f"Error saving AI settings: {e}")
        return False

def get_active_provider_label() -> str:
    """عنوان فارسی و نشانگر موتور فعال هوش مصنوعی"""
    provider = get_ai_settings().get("provider", "gemini")
    if provider == "gemini":
        return "♊️ گوگل جمینای (Google Gemini) - فعال"
    elif provider == "deepseek":
        return "🤖 دیپ‌سیک (DeepSeek) - فعال"
    else:
        return "🛑 خاموش (غیرفعال)"

# ─── دریافت امن کلیدهای API ───

def _read_key_from_env_files(key_name: str) -> str:
    """جستجوی کلید در فایل‌های .env مسیر پروژه"""
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        ".env"
    ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith(f"{key_name}="):
                            _, val = line.split("=", 1)
                            clean_val = val.strip().strip('"').strip("'")
                            if clean_val and not clean_val.startswith("MY_"):
                                os.environ[key_name] = clean_val
                                return clean_val
            except Exception:
                pass
    return ""

def get_gemini_api_key() -> str:
    """دریافت کلید API جمینای"""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key and not key.startswith("MY_") and key != "your_api_key_here":
        return key

    file_key = _read_key_from_env_files("GEMINI_API_KEY")
    if file_key:
        return file_key

    try:
        import config
        c_key = getattr(config, "GEMINI_API_KEY", "").strip()
        if c_key and not c_key.startswith("MY_"):
            return c_key
    except Exception:
        pass
    return key

def get_deepseek_api_key() -> str:
    """دریافت کلید API دیپ‌سیک"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key and not key.startswith("MY_") and key != "your_api_key_here":
        return key

    file_key = _read_key_from_env_files("DEEPSEEK_API_KEY")
    if file_key:
        return file_key

    try:
        import config
        c_key = getattr(config, "DEEPSEEK_API_KEY", "").strip()
        if c_key and not c_key.startswith("MY_"):
            return c_key
    except Exception:
        pass
    return key

# ─── بررسی وجود مشخصات در کالا (Zero Delay / 0 Latency) ───

def product_has_specs(product: dict) -> bool:
    """
    بررسی اینکه آیا کالا از قبل مشخصات فنی معتبر دارد یا خیر.
    در صورت داشتن مشخصات، نیازی به استعلام هوش مصنوعی نیست.
    """
    if not product or not isinstance(product, dict):
        return True

    ai_specs = product.get("ai_specs")
    if ai_specs and isinstance(ai_specs, dict) and len(ai_specs) > 0:
        return True

    specs = product.get("specs")
    if isinstance(specs, str):
        try:
            specs = json.loads(specs)
        except Exception:
            specs = {}
    if isinstance(specs, dict) and len(specs) > 0:
        actual_specs = {
            k: v for k, v in specs.items()
            if k not in ["ضمانت اصالت", "گارانتی", "گارانتی و مهلت تست", "مهلت تست و تعویض"]
        }
        if len(actual_specs) >= 2:
            return True

    meaningful_fields = [
        product.get("assembly"), product.get("resolution"), product.get("panel"),
        product.get("refresh_rate"), product.get("os"), product.get("capacity_btu"),
        product.get("temp_range"), product.get("room_size"), product.get("energy_consumption"),
        product.get("plan"), product.get("capacity_foot"), product.get("num_doors"),
        product.get("capacity_kg"), product.get("baskets"), product.get("key_features"),
        product.get("cpu"), product.get("ram"), product.get("gpu"), product.get("power"),
        product.get("capacity"), product.get("blade")
    ]
    if any(bool(str(f).strip()) for f in meaningful_fields if f is not None):
        return True

    more_details = str(product.get("more_details") or "").strip()
    if len(more_details) > 12 and ("|" in more_details or ":" in more_details):
        return True

    return False

# ─── تولید پرامپت با تاکید موکد بر مدل دقیق جهت جلوگیری از مشخصات فیک ───

def build_grounded_specs_prompt(product: dict) -> str:
    """
    پرامپت تخصصی و فوق‌العاده سخت‌گیرانه برای استخراج منحصراً مشخصات واقعی کارخانه‌ای
    بر اساس نام کالا، برند و کد مدل دقیق.
    """
    name = str(product.get("name") or "").strip()
    brand = str(product.get("brand") or "").strip()
    model = str(product.get("model_number") or "").strip()
    subcat = str(product.get("subcategory") or "").strip()
    cat = str(product.get("category_name") or product.get("category_key") or "").strip()

    prompt = (
        f"تو کارشناس ارشد و متخصص فنی دیتاشیت کاتالوگ لوازم خانگی و صوتی‌تصویری هستی.\n\n"
        f"کالای مورد نظر برای استخراج مشخصات فنی:\n"
        f"▫️ نام کامل محصول: «{name}»\n"
        f"▫️ برند سازنده: «{brand}»\n"
        f"▫️ کد مدل دقیق: «{model}»\n"
        f"{f'▫️ نوع کالا: «{subcat}»' if subcat else ''}\n"
        f"{f'▫️ دسته‌بندی: «{cat}»' if cat else ''}\n\n"
        f"⚠️ دستورات بسیار حیاتی جهت دقت ۱۰۰٪ و جلوگیری از هرگونه اطلاعات غیرواقعی و الکی:\n"
        f"۱. مشخصات فنی باید منحصراً و دقیقاً مطابق با مدارک فنی و کاتالوگ رسمی کارخانه همین کد مدل («{model}») باشد.\n"
        f"۲. اکیداً از حدس زدن، تقریب‌زدن یا آوردن ویژگی‌های عمومی و سایر مدل‌های برند بپرهیز؛ خریدار بر اساس این مشخصات هزینه پرداخت می‌کند، پس تنها اطلاعات قطعی و مستند را بیاور.\n"
        f"۳. اگر درباره مشخصه خاصی از این مدل اطمینان ۱۰۰٪ نداری، آن را کلاً نیاور و فقط ۳ تا ۵ ویژگی کلیدی که از آنها کاملاً مطمئن هستی را ذکر کن.\n"
        f"۴. مقادیر باید کاملاً فنی، مستند و همراه با عدد و واحد اندازه‌گیری رسمی باشند (مانند توان مصرفی به وات W، گنجایش به لیتر L یا کیلوگرم kg، نوع فیلتر بهداشتی HEPA، نوع موتور اینورتر/دایرکت درایو، کشور سازنده و مونتاژ قطعات، جنس تیغه یا بدنه).\n"
        f"۵. عبارات کیفی کلی مثل 'خوب'، 'دارد'، 'قوی'، 'عالی' و 'مناسب' بدون عدد و مشخصه دقیق ممنوع است.\n"
        f"۶. از ذکر قیمت، رنگ، گارانتی یا شعار تبلیغاتی اکیداً خودداری کن.\n"
        f"۷. خروجی را فقط و فقط به صورت یک شیء JSON با کلید و مقدار متنی فارسی برگردان.\n\n"
        f"نمونه ساختار استاندارد مورد انتظار:\n"
        f'{{"توان مصرفی": "۲۲۰۰ وات", "ظرفیت مخزن": "۴ لیتر", "نوع فیلتر": "فیلتر بهداشتی HEPA 13", "کشور سازنده": "لهستان"}}'
    )
    return prompt

def _validate_and_filter_specs(raw_dict: dict) -> Optional[Dict[str, str]]:
    """فیلتر و اعتبارسنجی دقیق مشخصات برای تضمین فنی و غیرالکی بودن"""
    if not isinstance(raw_dict, dict):
        return None

    banned_keywords = ["قیمت", "رنگ", "خرید", "تومان", "گارانتی", "ضمانت", "تخفیف", "فروش"]
    vague_values = ["بله", "دارد", "خوب", "عالی", "مناسب", "بسیار خوب", "قوی", "کیفیت بالا", "موجود", "ندارد"]

    specs = {}
    for k, v in raw_dict.items():
        k_clean = str(k).strip().lstrip("-*▫️• ")
        v_clean = str(v).strip()

        # بررسی کلمات ممنوعه در کلید
        if any(b in k_clean for b in banned_keywords):
            continue

        # بررسی مقادیر مبهم و بدون محتوای فنی
        if v_clean in vague_values or len(v_clean) < 2:
            continue

        if len(k_clean) < 35 and len(v_clean) < 110:
            specs[k_clean] = v_clean

    return specs if len(specs) >= 2 else None

def _parse_ai_json_response(raw_text: str) -> Optional[Dict[str, str]]:
    """پارس امن خروجی هوش مصنوعی به صورت شیء مشخصات معتبر"""
    if not raw_text:
        return None

    cleaned_text = raw_text.strip()
    if "```" in cleaned_text:
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned_text)
        if m:
            cleaned_text = m.group(1).strip()

    try:
        data = json.loads(cleaned_text)
        if isinstance(data, dict):
            filtered = _validate_and_filter_specs(data)
            if filtered:
                return filtered
    except Exception:
        pass

    # روش پشتیبان خط‌به‌خط
    specs = {}
    for line in cleaned_text.split("\n"):
        line = line.strip().lstrip("-*▫️•#▪️ ")
        line = re.sub(r'^\s*[\d۰-۹]+[\.\-\)\s]+\s*', '', line)
        clean_line = line.replace("**", "").replace("__", "").strip()
        if ":" in clean_line:
            parts = clean_line.split(":", 1)
            k = parts[0].strip()
            v = parts[1].strip()
            specs[k] = v

    return _validate_and_filter_specs(specs)

# ─── فراخوانی Gemini API ───

def call_gemini_api(api_key: str, product: dict) -> Optional[Dict[str, str]]:
    """فراخوانی جمینای با تنظیم دما روی 0.1 جهت بیشترین انطباق و کمترین خطا"""
    if not api_key:
        return None

    prompt = build_grounded_specs_prompt(product)
    pname = product.get("name", "")

    models_to_try = [DEFAULT_GEMINI_MODEL, FALLBACK_GEMINI_MODEL]

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,  # دمای پایین برای دقت علمی و عدم توهم
                "maxOutputTokens": 600,
                "responseMimeType": "application/json"
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=6.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    continue
                raw_text = parts[0].get("text", "")
                specs = _parse_ai_json_response(raw_text)
                if specs:
                    logger.info(f"✅ [GEMINI AI] مشخصات دقیق '{pname}' با موفقیت استخراج شد.")
                    return specs
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="ignore")
            logger.warning(f"⚠️ [GEMINI HTTP {he.code}] Model {model_name}: {err_body[:180]}")
            if he.code in [400, 403]:
                break
        except Exception as e:
            logger.warning(f"⚠️ [GEMINI ERROR] Model {model_name} for '{pname}': {e}")

    return None

# ─── فراخوانی DeepSeek API ───

def call_deepseek_api(api_key: str, product: dict) -> Optional[Dict[str, str]]:
    """فراخوانی دیپ‌سیک با پرامپت دقیق منطبق بر مدل"""
    if not api_key:
        return None

    prompt = build_grounded_specs_prompt(product)
    pname = product.get("name", "")

    endpoint = f"{DEFAULT_DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": DEFAULT_DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "تو متخصص فنی کاتالوگ لوازم خانگی هستی. خروجی فقط یک شیء JSON با مشخصات فنی واقعی کارخانه است."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 600,
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
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choice = data.get("choices", [{}])[0]
            content = (choice.get("message", {}).get("content") or "").strip()
            reasoning = (choice.get("message", {}).get("reasoning_content") or "").strip()
            if not content and reasoning:
                content = reasoning
            specs = _parse_ai_json_response(content)
            if specs:
                logger.info(f"✅ [DEEPSEEK AI] مشخصات دقیق '{pname}' با موفقیت استخراج شد.")
                return specs
    except Exception as e:
        logger.warning(f"⚠️ [DEEPSEEK ERROR] for '{pname}': {e}")

    return None

# ─── ذخیره‌سازی دائمی یکبار برای همیشه ───

def sync_save_ai_specs(pid: str, specs: dict):
    """ذخیره دائمی مشخصات در catalog_products.json و bot_data.db"""
    if not pid or not specs:
        return

    spec_str = " | ".join([f"{k}: {v}" for k, v in specs.items()])

    # ۱. ذخیره در کاتالوگ JSON
    try:
        if os.path.exists(CATALOG_FILE):
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            updated = False
            if isinstance(data, dict):
                if pid in data:
                    data[pid]["ai_specs"] = specs
                    data[pid]["more_details"] = spec_str
                    updated = True
                else:
                    for _, v in data.items():
                        if str(v.get("product_id")) == str(pid):
                            v["ai_specs"] = specs
                            v["more_details"] = spec_str
                            updated = True
                            break
            elif isinstance(data, list):
                for item in data:
                    if str(item.get("product_id")) == str(pid):
                        item["ai_specs"] = specs
                        item["more_details"] = spec_str
                        updated = True
                        break

            if updated:
                with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"💾 [AI DISK SAVED] مشخصات کالا {pid} برای همیشه در کاتالوگ ذخیره شد.")
    except Exception as e:
        logger.error(f"Error saving AI specs for {pid} to JSON: {e}")

    # ۲. ذخیره در جدول SQLite
    try:
        if os.path.exists(DB_FILE):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            specs_json = json.dumps(specs, ensure_ascii=False)
            cursor.execute("""
                UPDATE products
                SET specs_json = ?, more_details = ?, updated_at = CURRENT_TIMESTAMP
                WHERE product_id = ?
            """, (specs_json, spec_str, pid))
            conn.commit()
            conn.close()
            logger.info(f"💾 [AI DB SAVED] مشخصات کالا {pid} در جدول دیتابیس SQLite ثبت شد.")
    except Exception as e:
        logger.error(f"Error saving AI specs for {pid} to SQLite: {e}")

# ─── روال اصلی On-Demand با مدیریت ارائه‌دهنده فعال ───

async def async_enrich_product_with_gemini_on_demand(product: dict) -> bool:
    """
    روال آن‌دیمند یکپارچه:
    ۱. بررسی وضعیت هوش مصنوعی (خاموش/روشن، جمینای یا دیپ‌سیک)
    ۲. بررسی اینکه آیا کالا از قبل مشخصات دارد؟ (در صورت داشتن مشخصات ۰ معطلی)
    ۳. استخراج منحصراً مشخصات واقعی کارخانه‌ای مدل
    ۴. ذخیره‌سازی دائمی یکبار برای همیشه
    """
    if not product or not isinstance(product, dict):
        return False

    # بررسی تنظیمات فعال ادمین
    ai_settings = get_ai_settings()
    provider = ai_settings.get("provider", "gemini")

    if provider in ["off", "disabled"]:
        logger.debug("AI specs enrichment is currently disabled by admin.")
        return False

    # بررسی اولیه مشخصات کالا
    if product_has_specs(product):
        return False

    pname = product.get("name", "")
    if not pname:
        return False

    specs = None

    if provider == "gemini":
        api_key = get_gemini_api_key()
        if not api_key:
            logger.debug("GEMINI_API_KEY is not set or empty.")
            return False
        logger.info(f"🤖 [GEMINI LAZY] استعلام مشخصات موثق برای: '{pname}'...")
        try:
            specs = await asyncio.wait_for(
                asyncio.to_thread(call_gemini_api, api_key, product),
                timeout=7.0
            )
        except Exception as e:
            logger.warning(f"Gemini on-demand note for '{pname}': {e}")
            return False

    elif provider == "deepseek":
        api_key = get_deepseek_api_key()
        if not api_key:
            logger.debug("DEEPSEEK_API_KEY is not set or empty.")
            return False
        logger.info(f"🤖 [DEEPSEEK LAZY] استعلام مشخصات موثق برای: '{pname}'...")
        try:
            specs = await asyncio.wait_for(
                asyncio.to_thread(call_deepseek_api, api_key, product),
                timeout=8.5
            )
        except Exception as e:
            logger.warning(f"DeepSeek on-demand note for '{pname}': {e}")
            return False

    if specs and isinstance(specs, dict):
        product["ai_specs"] = specs
        if not isinstance(product.get("specs"), dict):
            product["specs"] = {}
        for k, v in specs.items():
            product["specs"][k] = v
        product["more_details"] = " | ".join([f"{k}: {v}" for k, v in specs.items()])

        pid = str(product.get("product_id") or "").strip()

        # به‌روزرسانی کش درون‌حافظه‌ای ربات
        try:
            from search_engine import JSON_PRODUCTS
            for p in JSON_PRODUCTS:
                if str(p.get("product_id")) == pid:
                    p["ai_specs"] = specs
                    if not isinstance(p.get("specs"), dict):
                        p["specs"] = {}
                    for k, v in specs.items():
                        p["specs"][k] = v
                    p["more_details"] = product["more_details"]
                    break
        except Exception:
            pass

        # ذخیره‌سازی دائمی یکبار برای همیشه در پس‌زمینه
        if pid:
            asyncio.create_task(asyncio.to_thread(sync_save_ai_specs, pid, specs))

        logger.info(f"🎉 [AI APPLIED] مشخصات کالا '{pname}' با موفقیت روی کارت اعمال و ذخیره شد.")
        return True

    return False
