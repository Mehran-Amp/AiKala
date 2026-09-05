"""
ماژول استخراج هوشمند و ساختارمند لیست قیمت و موجودی لپ‌تاپ از تصاویر جداول (مانند اسکرین‌شات اکسل).
این ماژول از مدل‌های چندوجهی Gemini Vision (از طریق REST API استاندارد بدون نیاز به پکیج‌های اضافی) استفاده می‌کند.

قوانین اکید کسب‌وکار:
1. ستون «همکاری» (قیمت همکار) به هیچ عنوان خوانده، ذخیره یا نمایش داده نمی‌شود.
2. نام‌های فروشگاه، شماره‌های تماس افراد، لینک‌ها و آدرس‌ها به طور کامل فیلتر و حذف می‌شوند.
3. دسته‌بندی اصلی همه این کالاها «لپ‌تاپ» و زیرمجموعه آن‌ها منحصراً بر اساس «برند» است.
"""

import os
import json
import base64
import logging
import urllib.request
import urllib.error
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

LAPTOPS_CATALOG_FILE = "laptops_catalog.json"

EXTRACTION_SYSTEM_PROMPT = """
شما یک دستیار متخصص در استخراج جداول مشخصات و قیمت لپ‌تاپ از تصاویر و اسکرین‌شات‌ها هستید.
وظیفه شما تبدیل دقیق سطرهای جدول به یک آرایه JSON ساختارمند است.

قوانین بسیار مهم و غیرقابل تخطی:
1. ستون «همکاری» (قیمت همکار) را کاملاً نادیده بگیرید و به هیچ عنوان استخراج نکنید.
2. فقط و فقط ستون «قیمت» (قیمت تک‌فروشی / مصرف‌کننده) را استخراج کنید.
3. هدر تصویر شامل نام فروشگاه‌ها، شماره تماس اشخاص (مانند درویشی، رحمانی، خاکساران و...)، آیدی تلگرام، آدرس و لینک‌های وب‌سایت، و همچنین فوترها و متون پایانی را کاملاً نادیده بگیرید و هیچ ردی از آن‌ها در خروجی نباشد.
4. اگر قیمت به هزار تومان نوشته شده (مثلاً 248,000 یا 67,000)، به عدد تبدیل کنید یا همان فرمت عددی را بیاورید؛ اما اطمینان حاصل کنید که مربوط به ستون «قیمت» است نه «همکاری».
5. دسته‌بندی کالا حتماً "لپ‌تاپ" باشد.
6. برند را از روی لوگو یا نام مدل تشخیص دهید (مثلاً HP, ASUS, LENOVO, DELL, APPLE, ACER, MSI و...).
7. فیلدهای هر آیتم در خروجی باید به این شکل باشد:
   - "code": کد کالا (مثلاً "H101")
   - "brand": نام برند با حروف بزرگ انگلیسی (مثلاً "HP")
   - "model": نام مدل دقیق کالا (مثلاً "ZBOOK FURY 16 G9")
   - "cpu": مشخصات پردازنده (مثلاً "CORE I9 - 12950HX")
   - "ram": رم دستگاه (مثلاً "16G")
   - "storage": هارد یا حافظه داخلی (مثلاً "512G")
   - "gpu": کارت گرافیک (مثلاً "8GB NVIDIA RTX A2000")
   - "display": اندازه و مشخصات صفحه نمایش (مثلاً "16\"")
   - "grade": گرید سلامت و تمیزی دستگاه (مثلاً "A++")
   - "price": قیمت تک‌فروشی از ستون قیمت به صورت عدد یا رشته تمیز (مثلاً "248000" یا 248000)

خروجی شما باید منحصراً و فقط یک کد JSON خالص (بدون هیچ متن توضیحی اضافه) باشد:
[
  {
    "code": "H101",
    "brand": "HP",
    "model": "ZBOOK FURY 16 G9",
    "cpu": "CORE I9 - 12950HX",
    "ram": "16G",
    "storage": "512G",
    "gpu": "8GB NVIDIA RTX A2000",
    "display": "16\\"",
    "grade": "A++",
    "price": "248000"
  }
]
"""

def get_gemini_api_key() -> str:
    """دریافت کلید API از محیط یا فایل .env"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key and os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception as e:
            logger.error(f"Error reading .env: {e}")
    return api_key

def set_gemini_api_key(new_key: str) -> bool:
    """تنظیم و ذخیره کلید جدید Gemini در متغیر محیط و فایل .env"""
    key = str(new_key).strip()
    if not key:
        return False
    os.environ["GEMINI_API_KEY"] = key
    lines = []
    found = False
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        lines.append(f"GEMINI_API_KEY={key}\n")
                        found = True
                    else:
                        lines.append(line)
        except Exception:
            pass
    if not found:
        lines.append(f"GEMINI_API_KEY={key}\n")
    try:
        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        logger.error(f"Error saving to .env: {e}")
        return False

def extract_laptops_from_text(raw_text: str) -> List[Dict[str, Any]]:
    """
    استخراج سطرهای لپ‌تاپ از متن کپی‌شده از تلگرام یا جدول اکسل (بدون نیاز به هوش مصنوعی)
    قوانین: حذف کامل شماره‌های تماس، همکار، تبلیغات و تشخیص برند و مدل و قیمت.
    """
    if not raw_text:
        return []
    lines = raw_text.strip().split("\n")
    results = []
    
    brand_patterns = [
        ("HP", r'\b(hp|اچ\s*پی)\b'),
        ("ASUS", r'\b(asus|ایسوس)\b'),
        ("LENOVO", r'\b(lenovo|لنوو)\b'),
        ("DELL", r'\b(dell|دل)\b'),
        ("APPLE", r'\b(apple|macbook|اپل|مک\s*بوک)\b'),
        ("ACER", r'\b(acer|ایسر)\b'),
        ("MSI", r'\b(msi|ام\s*اس\s*ای)\b'),
        ("MICROSOFT", r'\b(surface|microsoft|سرفیس)\b'),
    ]

    for line in lines:
        line_clean = line.strip()
        if not line_clean or len(line_clean) < 10:
            continue
        # فیلتر کردن هدرها و ستون همکاری یا شماره تماس
        if re.search(r'(همکار|همکاری|تلفن|تماس|۰۹\d{9}|09\d{9}|کانال|آدرس|مشخصات|قیمت\s*همکار)', line_clean):
            continue
        
        # استخراج قیمت از انتهای خط یا بعد از ستون قیمت
        # ارقام را پیدا می‌کنیم
        price_matches = re.findall(r'(\d[\d\,\.]{3,}\d)', line_clean)
        if not price_matches:
            continue
        
        # آخرین عدد بزرگ معمولاً قیمت مصرف‌کننده است
        price_str = price_matches[-1].replace(",", "").replace(".", "").replace("،", "")
        try:
            p_val = int(price_str)
            # اگر به هزار تومان نوشته شده (مثلاً 248000 به جای 248000000 یا 35000 به جای 35000000)
            if 10000 <= p_val <= 900000:
                p_val = p_val * 1000
        except Exception:
            continue

        # تشخیص برند
        detected_brand = "متفرقه"
        for b_name, b_regex in brand_patterns:
            if re.search(b_regex, line_clean, re.IGNORECASE):
                detected_brand = b_name
                break
        
        # اگر برندی تشخیص داده نشد، سطر ممکن است لپ‌تاپ نباشد
        if detected_brand == "متفرقه" and not re.search(r'\b(core|i[3579]|ryzen|ram|ssd|gb)\b', line_clean, re.IGNORECASE):
            continue

        # مدل را از متن تمیز استخراج می‌کنیم
        parts = re.split(r'[\t\|\-\–]', line_clean)
        model = parts[0].strip() if parts else line_clean[:40]
        # حذف ارقام قیمت از مدل
        model = re.sub(r'\d[\d\,\.]{3,}\d', '', model).strip()
        if len(model) < 4:
            model = f"لپ‌تاپ {detected_brand}"

        results.append({
            "code": f"L{len(results)+101}",
            "brand": detected_brand,
            "model": model,
            "cpu": "مندرج در مدل",
            "ram": "-",
            "storage": "-",
            "gpu": "-",
            "display": "-",
            "grade": "A++",
            "price": str(p_val)
        })

    if results:
        return clean_and_normalize_laptops(results)
    return []

def extract_laptops_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> List[Dict[str, Any]]:
    """
    ارسال تصویر به مدل بینایی ماشین Gemini Vision و بازگرداندن آرایه تمیز لپ‌تاپ‌ها.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured.")
        raise ValueError("کلید GEMINI_API_KEY تنظیم نشده است. لطفاً آن را در بخش Settings یا .env وارد کنید.")

    base64_data = base64.b64encode(image_bytes).decode("utf-8")
    
    # استفاده از مدل‌های دارای قابلیت Vision
    models_to_try = [
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro"
    ]
    
    last_error = ""
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": EXTRACTION_SYSTEM_PROMPT},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                result_json = json.loads(resp.read().decode("utf-8"))
                
                candidates = result_json.get("candidates", [])
                if not candidates:
                    continue
                
                content_parts = candidates[0].get("content", {}).get("parts", [])
                raw_text = "".join([p.get("text", "") for p in content_parts]).strip()
                
                # پاکسازی بلوک‌های کد مارک‌داون در صورت وجود
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
                    raw_text = re.sub(r"\n?```$", "", raw_text).strip()
                
                parsed_data = json.loads(raw_text)
                if isinstance(parsed_data, list):
                    logger.info(f"Successfully extracted {len(parsed_data)} laptops using {model_name}.")
                    return clean_and_normalize_laptops(parsed_data)
                elif isinstance(parsed_data, dict) and "laptops" in parsed_data:
                    return clean_and_normalize_laptops(parsed_data["laptops"])
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            logger.warning(f"Model {model_name} HTTP {e.code}: {err_msg}")
            last_error = f"HTTP {e.code}: {err_msg}"
            # اگر خطای API_KEY نامعتبر باشد بلافاصله اکسپشن بدهیم
            if "API_KEY_INVALID" in err_msg or e.code == 400 and "API key not valid" in err_msg:
                raise ValueError("کلید GEMINI_API_KEY نامعتبر است. لطفاً یک کلید معتبر از Google AI Studio وارد کنید.")
            continue
        except Exception as e:
            logger.error(f"Error calling Gemini with model {model_name}: {e}")
            last_error = str(e)
            continue
            
    raise RuntimeError(f"خطا در پردازش تصویر با هوش مصنوعی: {last_error}")

def normalize_price_value(price_val: Any) -> int:
    """تبدیل رشته یا عدد قیمت لیست به مبلغ نهایی بر حسب تومان"""
    if not price_val:
        return 0
    clean_str = re.sub(r"[^\d]", "", str(price_val))
    if not clean_str:
        return 0
    val = int(clean_str)
    # اگر مثلاً نوشته شده ۲۴۸,۰۰۰ (که منظورش ۲۴۸ میلیون تومان است)
    if val < 1000000:
        return val * 1000
    return val

def clean_and_normalize_laptops(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """پاکسازی، اعتبارسنجی و نرمال‌سازی اقلام لپ‌تاپ استخراج‌شده"""
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        
        brand = str(item.get("brand", "HP")).strip().upper()
        if not brand:
            brand = "HP"
        
        model = str(item.get("model", "")).strip()
        if not model:
            continue
            
        code = str(item.get("code", "")).strip()
        cpu = str(item.get("cpu", "")).strip()
        ram = str(item.get("ram", "")).strip()
        storage = str(item.get("storage", "")).strip()
        gpu = str(item.get("gpu", "")).strip()
        display = str(item.get("display", "")).strip()
        grade = str(item.get("grade", "")).strip()
        
        price_num = normalize_price_value(item.get("price", 0))
        
        # شناسه یکتا برای جستجو و کاتالوگ
        clean_code = code.replace(" ", "") if code else ""
        product_id = f"LAPTOP_{brand}_{clean_code}" if clean_code else f"LAPTOP_{brand}_{re.sub(r'[^A-Za-z0-9]', '', model)}"
        
        # نام نمایشی کامل
        full_title = f"{brand} {model}"
        
        specs = {}
        if cpu: specs["پردازنده (CPU)"] = cpu
        if ram: specs["حافظه رم (RAM)"] = ram
        if storage: specs["حافظه داخلی (SSD/HDD)"] = storage
        if gpu: specs["کارت گرافیک (GPU)"] = gpu
        if display: specs["صفحه نمایش"] = display
        if grade: specs["گرید و تمیزی"] = grade
        if code: specs["کد مدل"] = code
        
        entry = {
            "id": product_id,
            "code": code,
            "title": full_title,
            "brand": brand,
            "model": model,
            "category": "لپ‌تاپ",
            "subcategory": brand,
            "price": price_num,
            "price_formatted": f"{price_num:,} تومان" if price_num else "تماس بگیرید",
            "specs": specs,
            "available": True,
            "source": "image_extractor"
        }
        cleaned.append(entry)
        
    return cleaned

def load_laptops_catalog() -> List[Dict[str, Any]]:
    """خواندن لیست لپ‌تاپ‌های ذخیره‌شده از فایل JSON"""
    if os.path.exists(LAPTOPS_CATALOG_FILE):
        try:
            with open(LAPTOPS_CATALOG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.error(f"Error reading {LAPTOPS_CATALOG_FILE}: {e}")
    return []

def save_laptops_catalog(laptops: List[Dict[str, Any]]) -> bool:
    """ذخیره یا به‌روزرسانی لیست لپ‌تاپ‌ها در فایل دیتابیس محلی"""
    try:
        with open(LAPTOPS_CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(laptops, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving {LAPTOPS_CATALOG_FILE}: {e}")
        return False

def merge_extracted_laptops(new_laptops: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    ادغام لپ‌تاپ‌های جدید با دیتابیس قبلی:
    اگر مدل از قبل وجود داشت، قیمت و مشخصات آن آپدیت می‌شود وگرنه اضافه می‌شود.
    """
    existing = load_laptops_catalog()
    existing_map = {item.get("id"): item for item in existing}
    
    added_count = 0
    updated_count = 0
    
    for item in new_laptops:
        item_id = item.get("id")
        if item_id in existing_map:
            existing_map[item_id].update(item)
            updated_count += 1
        else:
            existing_map[item_id] = item
            added_count += 1
            
    save_laptops_catalog(list(existing_map.values()))
    return {"added": added_count, "updated": updated_count, "total": len(existing_map)}

def format_laptops_preview_for_admin(laptops: List[Dict[str, Any]], max_display: int = 10) -> str:
    """ایجاد پیام پیش‌نمایش متنی برای ادمین تلگرام جهت تایید نهایی"""
    if not laptops:
        return "⚠️ هیچ آیتم معتبری در تصویر جدول شناسایی نشد."
    
    total = len(laptops)
    lines = [
        f"📊 <b>گزارش تحلیل هوشمند لیست قیمت لپ‌تاپ:</b>",
        f"✅ <b>تعداد کل ردیف‌های شناسایی‌شده:</b> <code>{total}</code> مدل",
        f"🛡 <i>قیمت‌های همکار و شماره تماس‌ها کاملاً فیلتر شدند.</i>",
        "────────────────────",
        "<b>نمونه سطرهای استخراج‌شده:</b>\n"
    ]
    
    for i, item in enumerate(laptops[:max_display], 1):
        code = item.get("code", "-")
        brand = item.get("brand", "")
        model = item.get("model", "")
        specs = item.get("specs", {})
        cpu = specs.get("پردازنده (CPU)", "")
        ram = specs.get("حافظه رم (RAM)", "")
        storage = specs.get("حافظه داخلی (SSD/HDD)", "")
        gpu = specs.get("کارت گرافیک (GPU)", "")
        grade = specs.get("گرید و تمیزی", "")
        price_str = item.get("price_formatted", "")
        
        detail_line = f"<b>{i}. [{code}] {brand} {model}</b>\n"
        detail_line += f"   ▫️ سی‌پی‌یو: <code>{cpu}</code> | رم: <code>{ram}</code> | حافظه: <code>{storage}</code>\n"
        if gpu:
            detail_line += f"   ▫️ گرافیک: <code>{gpu}</code> | گرید: <code>{grade}</code>\n"
        detail_line += f"   💰 قیمت تک‌فروشی: <b>{price_str}</b>\n"
        lines.append(detail_line)
        
    if total > max_display:
        lines.append(f"<i>... و {total - max_display} مدل دیگر</i>\n")
        
    lines.append("────────────────────")
    lines.append("❓ آیا مایلید این لیست در کاتالوگ و دسته‌بندی لپ‌تاپ ربات ثبت و به‌روزرسانی شود؟")
    return "\n".join(lines)
