"""
AiKala - Search Engine & Natural Language Processor (search_engine.py)
======================================================================
موتور جستجوی دولایه با تطبیق دقیق کدهای مدل و توکن‌های برندی،
تشخیص رنگ، ظرفیت، برند، دسته‌بندی و بارگذاری پایدار محصولات.
"""

import os
import re
import json
import logging
from typing import List, Dict, Any, Tuple, Set, Optional

logger = logging.getLogger(__name__)

# ─── دیکشنری مترادف‌ها و واژگان کلیدی ───

COLOR_SYNONYMS: Dict[str, List[str]] = {
    "دودی": ["دودی", "سیلور تیره", "مشکی تیتانیوم", "dark silver", "graphite", "titanium"],
    "سفید": ["سفید", "سفید صدفی", "سفید چرمی", "white"],
    "نقره‌ای": ["نقره ای", "نقره‌ای", "سیلور", "silver", "استیل", "steel", "ایناکس", "inox"],
    "مشکی": ["مشکی", "سیاه", "black", "black steel", "تیره"],
    "کربن": ["کربن", "carbon", "خاکستری", "gray", "grey", "طوسی"],
}

BRAND_SYNONYMS: Dict[str, List[str]] = {
    "الجی": ["الجی", "ال جی", "ال‌جی", "lg", "ال جي"],
    "سامسونگ": ["سامسونگ", "samsung", "سام"],
    "سونی": ["سونی", "sony", "سوني"],
    "بوش": ["بوش", "bosch"],
    "هایسنس": ["هایسنس", "hisense", "های‌سنس", "های سنس"],
    "شیائومی": ["شیائومی", "شیاومی", "xiaomi"],
    "پاناسونیک": ["پاناسونیک", "panasonic"],
    "فیلیپس": ["فیلیپس", "philips"],
    "توشیبا": ["توشیبا", "toshiba"],
    "دوو": ["دوو", "daewoo"],
    "شارپ": ["شارپ", "sharp"],
    "جنرال": ["جنرال", "general", "جنرال شکار", "جنرال گلد"],
    "گری": ["گری", "gree"],
    "ایران رادیاتور": ["ایران رادیاتور", "iran radiator"],
    "تفال": ["تفال", "tefal"],
    "دلونگی": ["دلونگی", "delonghi"],
    "براون": ["براون", "braun"],
    "کنوود": ["کنوود", "kenwood"],
    "نوتریکوک": ["نوتریکوک", "nutricook"],
    "نینجا": ["نینجا", "ninja"],
    "میگل": ["میگل", "migel"],
    "گوسونیک": ["گوسونیک", "gosonic", "گاسونیک"],
    "فلر": ["فلر", "feller"],
    "اسمگ": ["اسمگ", "smeg"],
    "روگن": ["روگن", "rugen"],
    "هنریچ": ["هنریچ", "heinrich", "heinrichs"],
    "سنکور": ["سنکور", "sencor"],
    "بلک اند دکر": ["بلک اند دکر", "black and decker", "black+decker", "black & decker"],
    "مولینکس": ["مولینکس", "moulinex"],
    "پارس خزر": ["پارس خزر", "pars khazar"],
    "بکو": ["بکو", "beko"],
    "ویرپول": ["ویرپول", "whirlpool"],
    "بیسل": ["بیسل", "bissell"],
    "روونتا": ["روونتا", "rowenta"],
    "کیچن اید": ["کیچن اید", "kitchenaid"],
    "عرشیا": ["عرشیا", "arshia"],
    "فوما": ["فوما", "fuma"],
    "فکیر": ["فکیر", "fakir", "فکر"],
    "ژانومه": ["ژانومه", "janome"],
    "آاگ": ["آاگ", "آ ا گ", "aeg"],
    "میله": ["میله", "miele"],
    "دایسون": ["دایسون", "dyson"],
    "کارچر": ["کارچر", "کرشر", "karcher"],
    "مباشی": ["مباشی", "mebashi"],
    "نوا": ["نوا", "nova"],
    "زیگما": ["زیگما", "zigma"],
    "باریتون": ["باریتون", "bariton"],
    "هاردستون": ["هاردستون", "hardstone"],
    "مورفی ریچاردز": ["مورفی ریچاردز", "morphy richards"],
    "جیپاس": ["جیپاس", "geepas"],
    "کرکماز": ["کرکماز", "korkmaz"],
    "برویل": ["برویل", "breville"],
    "گاسترو بک": ["گاسترو بک", "گاستروبک", "gastroback"],
    "مایر": ["مایر", "maier"],
    "سیلور کرست": ["سیلور کرست", "سیلورکرست", "silvercrest"],
    "بایترون": ["بایترون", "bitron"],
    "تکنو": ["تکنو", "tecno"],
    "اچ پی": ["اچ پی", "اچ‌پی", "hp", "hewlett packard"],
    "ایسوس": ["ایسوس", "asus"],
    "لنوو": ["لنوو", "lenovo"],
    "دل": ["دل", "dell"],
    "اپل": ["اپل", "apple", "macbook", "مک بوک"],
    "ایسر": ["ایسر", "acer"],
    "ام اس آی": ["ام اس آی", "ام‌اس‌ای", "msi"],
}

CATEGORY_SYNONYMS: Dict[str, List[str]] = {
    "تلویزیون": ["تلویزیون", "تلوزیون", "تی وی", "تیوی", "tv", "oled", "qled", "اولد", "کیولد", "ال ای دی", "led", "ال‌سی‌دی", "lcd", "پلاسما"],
    "لباسشویی": ["لباسشویی", "لباس شویی", "لباسشويي", "washing", "washer", "واش", "پتوشور", "واشر"],
    "ظرفشویی": ["ظرفشویی", "ظرف شویی", "ظرفشويي", "dishwasher", "دیش واشر", "دیشواشر"],
    "یخچال": ["یخچال", "ساید", "ساید بای ساید", "سایدبای‌ساید", "فریزر", "دوقلو", "دو قلو", "refrigerator", "fridge", "فرنچ"],
    "کولر": ["کولر", "اسپلیت", "اسپیلت", "split", "کولرگازی", "کولر گازی", "داکت اسپلیت", "ایستاده", "کولر پنجره ای"],
    "جاروبرقی": ["جاروبرقی", "جارو برقی", "جاروبرقي", "جارو", "مخزنی", "کیسه ای", "vacuum", "جارو شارژی", "جاروشارژی"],
    "مایکروویو": ["مایکروویو", "ماکروویو", "ماکروفر", "مایکروفر", "سولاردام", "سولاردوم", "microwave", "solardom"],
    "لپ‌تاپ": ["لپ‌تاپ", "لپتاپ", "لپ تاپ", "laptop", "نوت بوک", "notebook"],
}

BRAND_AND_CATEGORY_SYNONYMS = {**BRAND_SYNONYMS, **CATEGORY_SYNONYMS}

STOP_WORDS_NOT_MODELS: Set[str] = {
    "bot", "aikala", "kala", "shop", "org", "ir", "com", "net", "tel", "link",
    "model", "code", "post", "chan", "join", "chat", "قیمت", "خرید", "فروش",
    "کانال", "تعداد", "استعلام", "لحظه", "سفارش", "ضمانت", "کتبی", "اصلی",
    "موجود", "ارسال", "جدید", "مستقیم", "مدل", "رنگ", "توان", "موتور",
    "اسمارت", "فورکی", "4k", "smart", "pro", "plus", "ultra", "mini", "max",
    "new", "سلام", "لطفا", "میخوام", "می‌خوام", "دارید", "داری", "چنده"
}

BROAD_CATEGORIES_AND_BRANDS = set([w for syns in BRAND_AND_CATEGORY_SYNONYMS.values() for w in syns])

KNOWN_MARKET_CORE_PATTERNS = [
    (r'(?:f4|wv|fdh|fh4|f2|wd)[-_]?(v9|y1|r5|2j3|j6|v5|v3|v1|t1|g1|g6)', r'\1'),
    (r'ww[-_]?(\d{2})', r'w\1'),
    (r'(?:grf?|gc|gr)[-_]?([a-z]?\d{3,4})', r'\1'),
    (r'dfb[-_]?(\d{3})', r'\1'),
    (r'oled\d{2}[-_]?([a-z]\d|[a-z]{2})', r'\1'),
    (r'\d{2}(xr\d{2,3}|x\d{2}[a-z]?)', r'\1'),
    (r'dw\d{2}[a-z](\d{4})', r'\1'),
]

# ─── توابع نرمال‌سازی متون و ارقام ───

def _normalize_digits(text: str) -> str:
    """تبدیل اعداد فارسی و عربی به انگلیسی"""
    if not text:
        return ""
    persian = "۰۱۲۳۴۵۶۷۸۹"
    arabic = "٠١٢٣٤٥٦٧٨٩"
    res = []
    for c in text:
        if c in persian:
            res.append(str(persian.index(c)))
        elif c in arabic:
            res.append(str(arabic.index(c)))
        else:
            res.append(c)
    return "".join(res)

def clean_key(text: str) -> str:
    if not text:
        return ""
    t = _normalize_digits(text).lower()
    return re.sub(r'[^a-z0-9\u0600-\u06FF]', '', t)

def _canonicalize_for_search(text: str) -> str:
    if not text:
        return ""
    t = _normalize_digits(text).lower()
    t = t.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه").replace("‌", " ")
    
    # تفکیک واحدهای چسبیده به عدد (مانند 85اینچ، 9کیلو، 30فوت، 14نفره)
    t = re.sub(r'(\d+)\s*(اینچ|کیلو|فوت|نفره|نفر|وات|ولت|هرتز|گرمی|لیتری|لیتر|inch|kg|ft|w)', r' \1 \2 ', t)
    t = re.sub(r'(اینچ|کیلو|فوت|نفره|نفر|سایز)\s*(\d+)', r' \1 \2 ', t)
    
    # اصلاح غلط‌های املایی متداول در زبان فارسی
    t = re.sub(r'\bتلوزیون\b', 'تلویزیون', t)
    t = re.sub(r'\b(تیوی|تی\s*وی)\b', 'تلویزیون', t)
    t = re.sub(r'\bاسپیلت\b', 'اسپلیت', t)
    t = re.sub(r'\b(ماکروفر|مایکروفر|ماکروویو)\b', 'مایکروویو', t)
    t = re.sub(r'\bلباس\s+شوی\b', 'لباسشویی', t)
    t = re.sub(r'\bظرف\s+شوی\b', 'ظرفشویی', t)
    t = re.sub(r'\bساید\s+بای\s+ساید\b', 'ساید', t)

    return re.sub(r'[\r\n\t,،\-_/\\#()]+', ' ', t).strip()

def extract_brand_from_text(text: str) -> str:
    if not text:
        return ""
    t_clean = _canonicalize_for_search(text)
    for brand, syns in BRAND_SYNONYMS.items():
        if any(s in t_clean for s in syns):
            return brand
    return ""

INVALID_BRAND_WORDS = {
    "ساز", "کن", "برقی", "بدون", "روغن", "پز", "گیر", "دستی", "شارژی", "خانگی",
    "سایر", "ریز", "نامشخص", "لوازم", "مدل", "سماوری", "کاسه", "دار", "اصل", "اصلی",
    "جدید", "هوشمند", "دیجیتال", "لمسی", "پایه", "چند", "کاره", "چندکاره", "مخزن"
}

APPLIANCE_PREFIXES = [
    "بستنی ساز", "چای ساز", "چایی ساز", "قهوه ساز", "اسپرسو ساز", "اسپرسوساز",
    "سرخ کن بدون روغن", "سرخ کن", "مخلوط کن", "خرد کن", "خردکن", "همزن برقی", "همزن کاسه دار", "همزن",
    "آبمیوه گیری", "آبلیمو گیری", "جارو برقی", "جاروبرقی", "جارو شارژی", "جاروشارژی", "بخار شوی", "بخارشوی",
    "پلوپز", "زودپز", "آرام پز", "هواپز", "ساندویچ ساز", "وافل ساز", "توستر", "نان پز",
    "آسیاب برقی", "آسیاب", "چرخ گوشت", "غذاساز", "میوه خشک کن", "اتو بخار", "اتو مخزن دار", "اتو پرسی", "اتو دستی", "اتو",
    "سشوار", "ریش تراش", "ماشین اصلاح", "پیتزاپز", "گریل", "باربیکیو", "تصفیه آب", "تصفیه هوا",
    "پنکه", "بخاری", "شوفاژ", "هیتر", "کتری برقی", "کتری", "سماور برقی", "سماور"
]

def detect_product_brand(name: str, fallback_brand: str = "") -> str:
    """استخراج و اعتبارسنجی دقیق برند محصول، جلوگیری از برندهای اشتباه مثل 'ساز' یا 'کن'"""
    # ۱. بررسی با دیکشنری مترادف‌های برند روی نام محصول
    extracted = extract_brand_from_text(name)
    if extracted:
        return extracted

    # اگر برند کنونی معتبر باشد و جزء کلمات نامعتبر نباشد
    clean_fallback = fallback_brand.strip() if fallback_brand else ""
    if clean_fallback and clean_fallback not in INVALID_BRAND_WORDS and len(clean_fallback) > 1:
        extracted_fb = extract_brand_from_text(clean_fallback)
        if extracted_fb:
            return extracted_fb
        return clean_fallback

    # ۲. استخراج بر اساس الگوهای عنوان فارسی (حذف پیشوند کالا مانند 'بستنی ساز' و برداشتن کلمه بعد)
    t = name.strip()
    for prefix in sorted(APPLIANCE_PREFIXES, key=len, reverse=True):
        if t.startswith(prefix):
            remainder = t[len(prefix):].strip()
            tokens = remainder.split()
            for token in tokens:
                clean_tok = token.strip(" ,.-_()،")
                if clean_tok and clean_tok not in INVALID_BRAND_WORDS and len(clean_tok) > 1:
                    if not re.match(r'^[0-9a-zA-Z\-_]+$', clean_tok):
                        return clean_tok
                    elif clean_tok.isalpha() and len(clean_tok) > 2:
                        return clean_tok.capitalize()
            break

    # ۳. پیمایش توکن‌های عنوان برای یافتن اولین کلمه‌ای که مشخصه نامعتبر نباشد
    tokens = t.split()
    for token in tokens[1:]:
        clean_tok = token.strip(" ,.-_()،")
        if clean_tok and clean_tok not in INVALID_BRAND_WORDS and len(clean_tok) > 1:
            if not re.match(r'^[0-9]+$', clean_tok):
                return clean_tok

    return clean_fallback if (clean_fallback and clean_fallback not in INVALID_BRAND_WORDS) else "اورجینال شرکتی"

def normalize_brand(brand_str: str) -> str:
    if not brand_str:
        return ""
    b_clean = _canonicalize_for_search(brand_str)
    for b_std, syns in BRAND_SYNONYMS.items():
        if any(s in b_clean for s in syns):
            return b_std
    return b_clean

def extract_category_from_text(text: str) -> str:
    if not text:
        return ""
    t_clean = _canonicalize_for_search(text)
    for cat, syns in CATEGORY_SYNONYMS.items():
        if any(s in t_clean for s in syns):
            return cat
    return ""

def normalize_category(cat_str: str) -> str:
    if not cat_str:
        return ""
    c_clean = _canonicalize_for_search(cat_str)
    for c_std, syns in CATEGORY_SYNONYMS.items():
        if any(s in c_clean for s in syns):
            return c_std
    return c_clean

def extract_color_from_text(text: str) -> str:
    if not text:
        return ""
    t_lower = text.lower()
    for standard_color, synonyms in COLOR_SYNONYMS.items():
        for syn in synonyms:
            if syn in t_lower:
                return standard_color
    return ""

def extract_capacity_from_text(text: str) -> str:
    if not text:
        return ""
    t_norm = _canonicalize_for_search(text).replace("/", ".").replace("،", ".")
    cap_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:کیلو|kg|اینچ|فوت|نفر|inch)', t_norm, flags=re.IGNORECASE)
    if cap_match:
        return cap_match.group(1)
    num_match = re.search(r'\b(32|40|42|43|50|55|65|75|77|83|85|86|98|7|8|8\.5|9|10\.5|12|14|28|30|32|34|40)\b', t_norm)
    if num_match:
        return num_match.group(1)
    return ""

def is_model_code(token: str) -> bool:
    if not token or len(token) < 2:
        return False
    t_lower = token.lower()
    if t_lower in BROAD_CATEGORIES_AND_BRANDS or t_lower in STOP_WORDS_NOT_MODELS:
        return False
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    if has_digit and has_alpha:
        return True
    if has_digit and not has_alpha and 2 <= len(token) <= 4:
        return True
    return False

def extract_model_market_cores(text: str) -> set:
    if not text:
        return set()
    cores = set()
    t_norm = _normalize_digits(text).lower()

    for ww in re.findall(r'ww[-_]?(\d{2})', t_norm):
        cores.add(f"w{ww}")
        cores.add(f"ww{ww}")

    for lg_w in re.findall(r'(?:f4|wv|fdh|fh4|f2|wd|مدل\s*)[-_]?(v9|y1|r5|r9|2j3|j6|v5|v3|v1|t1|g1|g6)', t_norm):
        cores.add(lg_w)

    for lg_ref in re.findall(r'(?:grf?|gc|gr)[-_]?([a-z]?\d{3,4})', t_norm):
        cores.add(lg_ref)

    for lg_dw in re.findall(r'dfb[-_]?(\d{3})', t_norm):
        cores.add(lg_dw)

    for lg_tv in re.findall(r'oled\d{2}[-_]?([a-z]\d|[a-z]{2})', t_norm):
        cores.add(lg_tv)

    for sony_tv in re.findall(r'\d{2}(xr\d{2,3}[a-z0-9]*|x\d{2}[a-z0-9]*)', t_norm):
        cores.add(sony_tv)
        base_sony = re.sub(r'm\d+$', '', sony_tv)
        if base_sony and base_sony != sony_tv:
            cores.add(base_sony)

    for sam_dw in re.findall(r'dw\d{2}[a-z](\d{4})', t_norm):
        cores.add(sam_dw)

    return cores

def tokenize_model_codes(text: str) -> set:
    if not text:
        return set()
    tokens = set()
    t_clean = re.sub(r'[\r\n\t,،\-_/\\#()]+', ' ', text)
    t_norm = _normalize_digits(t_clean).lower()

    for w in t_norm.split():
        w_clean = re.sub(r'[^a-z0-9]', '', w)
        if len(w_clean) >= 2 and is_model_code(w_clean):
            tokens.add(w_clean)

    for an in re.findall(r'[a-z]{1,4}[-_]?[0-9]{1,4}[a-z0-9]*|[0-9]{2,4}[-_]?[a-z]{1,4}[a-z0-9]*', t_norm):
        an_clean = re.sub(r'[^a-z0-9]', '', an)
        if len(an_clean) >= 2 and is_model_code(an_clean):
            tokens.add(an_clean)

    for n in re.findall(r'\b[0-9]{2,4}\b', t_norm):
        if is_model_code(n):
            tokens.add(n)

    cores = extract_model_market_cores(text)
    tokens.update(cores)
    return tokens

def parse_post_metadata(caption: str, photo_file_ids: List[str]) -> Dict[str, Any]:
    tokens = tokenize_model_codes(caption)
    cores = extract_model_market_cores(caption)
    return {
        "brand": extract_brand_from_text(caption),
        "category": extract_category_from_text(caption),
        "models": list(tokens),
        "cores": list(cores),
        "color": extract_color_from_text(caption),
        "capacity": extract_capacity_from_text(caption),
        "photos": photo_file_ids,
        "msg_ids": [int(p) for p in photo_file_ids if str(p).isdigit()],
        "caption": caption
    }

# ─── بارگذاری و یکتاسازی کش محصولات ───

JSON_PRODUCTS: List[Dict[str, Any]] = []

def load_json_products(file_path: Optional[str] = None):
    global JSON_PRODUCTS
    JSON_PRODUCTS.clear()

    # اولویت ۱: فایل جدید و تمیزشده کاتالوگ با ۹۵۵ محصول و ۱۰ ستون کامل
    # اولویت ۲: فایل خام پشتیبان
    if file_path is None:
        if os.path.exists("catalog_products.json"):
            file_path = "catalog_products.json"
        elif os.path.exists("momtazkalla_all_products.json"):
            file_path = "momtazkalla_all_products.json"
        else:
            file_path = "catalog_products.json"

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            if isinstance(raw_data, dict):
                raw_products = list(raw_data.values())
            else:
                raw_products = raw_data

            seen_keys = set()
            for p in raw_products:
                if not isinstance(p, dict):
                    continue

                # یکسان‌سازی عنوان دسته‌بندی
                if "category" not in p and "category_name" in p:
                    p["category"] = p["category_name"]

                # تولید خودکار مشخصات فنی ۱۰ ستونه برای کارت محصول در تلگرام
                if "specs" not in p or not p["specs"]:
                    specs_dict = {}
                    if p.get("assembly"): specs_dict["کشور مونتاژ"] = p["assembly"]
                    if p.get("year"): specs_dict["سال ساخت"] = p["year"]
                    if p.get("resolution"): specs_dict["کیفیت تصویر"] = p["resolution"]
                    if p.get("panel"): specs_dict["نوع پنل"] = p["panel"]
                    if p.get("refresh_rate"): specs_dict["رفرش ریت"] = p["refresh_rate"]
                    if p.get("backlight"): specs_dict["بکلایت"] = p["backlight"]
                    if p.get("os"): specs_dict["سیستم‌عامل"] = p["os"]
                    if p.get("temp_range"): specs_dict["شرایط آب و هوایی"] = p["temp_range"]
                    if p.get("room_size"): specs_dict["پوشش فضا"] = p["room_size"]
                    if p.get("energy_consumption"): specs_dict["مصرف و موتور"] = p["energy_consumption"]
                    if p.get("performance"): specs_dict["عملکرد"] = p["performance"]
                    if p.get("key_features"): specs_dict["ویژگی‌ها"] = p["key_features"]
                    if p.get("plan"): specs_dict["طرح بدنه"] = p["plan"]
                    if p.get("capacity_foot"): specs_dict["ظرفیت به فوت"] = p["capacity_foot"]
                    if p.get("num_doors"): specs_dict["تعداد درب"] = p["num_doors"]
                    if p.get("capacity_kg"): specs_dict["ظرفیت شستشو"] = f"{p['capacity_kg']} کیلوگرم"
                    if p.get("baskets"): specs_dict["تعداد سبد"] = p["baskets"]
                    if p.get("subcategory"): specs_dict["زیرشاخه"] = p["subcategory"]
                    if p.get("score"): specs_dict["امتیاز کیفی"] = f"⭐️ {p['score']} از ۱۰"
                    if p.get("ai_specs") and isinstance(p["ai_specs"], dict):
                        for k, v in p["ai_specs"].items():
                            if k not in ["ضمانت اصالت", "گارانتی"]:
                                specs_dict[k] = v
                    specs_dict["ضمانت اصالت"] = "۱۰۰٪ اورجینال با تضمین کتبی"
                    specs_dict["گارانتی"] = "۱۸ ماه گارانتی شرکتی و ۵ سال خدمات پس از فروش"

                    if specs_dict:
                        p["specs"] = specs_dict
                    elif p.get("more_details"):
                        p["specs"] = {"مشخصات کلیدی": p["more_details"]}

                # فرمت خوانای قیمت تومان
                price_val = p.get("price", 0)
                if isinstance(price_val, (int, float)) and price_val > 0:
                    p["price_formatted"] = f"{int(price_val):,} تومان"

                pid = str(p.get("product_id", "")).strip()
                pname = str(p.get("name", "")).strip()
                unique_key = pid if pid else f"{pname}_{p.get('brand', '')}"

                if unique_key and unique_key not in seen_keys:
                    seen_keys.add(unique_key)
                    JSON_PRODUCTS.append(p)

            logger.info(f"[CACHE] Loaded {len(JSON_PRODUCTS)} UNIQUE products from {file_path} (Deduplicated)")
        except Exception as e:
            logger.warning(f"Error loading JSON products: {e}")

    # بارگذاری لپ‌تاپ‌های استخراج‌شده از کاتالوگ لپ‌تاپ
    laptops_file = "laptops_catalog.json"
    if os.path.exists(laptops_file):
        try:
            with open(laptops_file, "r", encoding="utf-8") as lf:
                laptops_data = json.load(lf)
                if isinstance(laptops_data, list):
                    l_count = 0
                    for lp in laptops_data:
                        lid = lp.get("id") or f"LAP_{lp.get('brand')}_{lp.get('model')}"
                        # تطبیق کلیدهای لازم برای سازگاری با سیستم نمایش کالا
                        if "name" not in lp and "title" in lp:
                            lp["name"] = lp["title"]
                        if "category_key" not in lp:
                            lp["category_key"] = "laptop"
                        if "category_name" not in lp:
                            lp["category_name"] = "لپ‌تاپ"
                        if "category" not in lp:
                            lp["category"] = "لپ‌تاپ"
                        if "product_id" not in lp:
                            lp["product_id"] = lid
                        if lid not in seen_keys:
                            seen_keys.add(lid)
                            JSON_PRODUCTS.append(lp)
                            l_count += 1
                    logger.info(f"[CACHE] Loaded {l_count} laptops from {laptops_file}")
        except Exception as le:
            logger.warning(f"Error loading laptops from {laptops_file}: {le}")

load_json_products()

def _get_active_products_pool(custom_list: Any = None) -> List[Dict[str, Any]]:
    """دسترسی به محصولات کش شده یا پایگاه داده محلی در صورت خالی بودن فایل JSON"""
    if custom_list is not None and len(custom_list) > 0:
        return custom_list
    if JSON_PRODUCTS:
        return JSON_PRODUCTS

    # تلاش برای خواندن محصولات از دیتابیس محلی
    try:
        import sqlite3
        for db_file in ["aikala.db", "bot_data.db"]:
            if os.path.exists(db_file) and os.path.getsize(db_file) > 0:
                conn = sqlite3.connect(db_file)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
                if c.fetchone():
                    c.execute("SELECT * FROM products")
                    rows = [dict(r) for r in c.fetchall()]
                    conn.close()
                    if rows:
                        return rows
                conn.close()
    except Exception as e:
        logger.debug(f"Fallback SQLite product read: {e}")
    return []

# ─── الگوریتم پیشرفته سرچ محصولات بر اساس اولویت پیشوند و تطبیق هوشمند ───

def search_products(query: str, products_list: Any = None) -> List[Dict[str, Any]]:
    """
    الگوریتم تطبیق و اولویت‌بندی نتایج جستجو:
    ۱. اولویت قطعی پیشوند (Prefix Match): مدل‌هایی که با رقم یا کلمه ورودی شروع می‌شوند (مانند 85X90L با جستجوی 85)
       بسیار بالاتر از مدل‌هایی که آن رقم را در وسط دارند (مانند 65X85K) قرار می‌گیرند.
    ۲. تفکیک واحدهای چسبیده (مانند 85اینچ، 9کیلو، 14نفره).
    ۳. شناسایی و تفکیک سایز/ظرفیت از کد اصلی مدل.
    ۴. تطبیق دقیق برند و دسته‌بندی با ضرایب افزایشی.
    """
    if not query or len(query.strip()) < 1:
        return []

    products_pool = _get_active_products_pool(products_list)
    if not products_pool:
        return []

    q_canon = _canonicalize_for_search(query)
    q_words = [w for w in q_canon.split() if len(w) >= 1 and w not in STOP_WORDS_NOT_MODELS]
    if not q_words:
        # اگر همه کلمات استاپ‌ورد بودند، همان کلمات اولیه کوئری را ملاک قرار می‌دهیم
        q_words = [w for w in q_canon.split() if len(w) >= 1]
    if not q_words:
        return []

    matched_items = []
    seen_keys = set()

    for p in products_pool:
        p_id = str(p.get("product_id", "")).strip()
        p_name = str(p.get("name", "")).strip()
        p_brand = str(p.get("brand", "")).strip()
        p_category = str(p.get("category", "")).strip()
        p_specs = str(p.get("specs", "")).strip()

        uid = p_id if p_id else clean_key(f"{p_name}_{p_brand}")
        if not uid or uid in seen_keys:
            continue

        product_full_text = f"{p_name} {p_brand} {p_category} {p_id} {p_specs}"
        prod_canon = _canonicalize_for_search(product_full_text)
        prod_words = set(re.sub(r'[\r\n\t,،\-_/\\#()]+', ' ', prod_canon).split())
        prod_model_tokens = tokenize_model_codes(product_full_text)
        prod_cores = extract_model_market_cores(product_full_text)
        prod_capacity = extract_capacity_from_text(product_full_text)

        # استخراج مدل‌های پایه تلویزیون و لوازم خانگی (مانند 85x90l -> پایه x90l)
        prod_base_models = set()
        for mt in list(prod_model_tokens):
            tv_m = re.match(r'^(32|40|42|43|50|55|65|75|77|83|85|86|98)([a-z].*)$', mt)
            if tv_m:
                prod_base_models.add(tv_m.group(2))

        all_words_matched = True
        total_score = 0

        for qw in q_words:
            qw_clean = clean_key(qw)
            word_matched = False
            w_score = 0

            # ۱. بررسی تطبیق برند
            for b_name, b_syns in BRAND_SYNONYMS.items():
                if qw in b_syns:
                    if any(bs in prod_canon for bs in b_syns):
                        w_score += 15000
                        word_matched = True
                    break

            # ۲. بررسی تطبیق دسته‌بندی
            for c_name, c_syns in CATEGORY_SYNONYMS.items():
                if qw in c_syns:
                    if any(cs in prod_canon for cs in c_syns):
                        w_score += 10000
                        word_matched = True
                    break

            # ۳. بررسی تطبیق رنگ
            prod_color = extract_color_from_text(product_full_text)
            for col_name, col_syns in COLOR_SYNONYMS.items():
                if qw in col_syns:
                    if prod_color == col_name or any(cs in prod_canon for cs in col_syns):
                        w_score += 8000
                        word_matched = True
                    break

            # ۴. اگر کلمه یک عدد باشد (مانند "85" یا "65" یا "9" یا "14")
            if qw.isdigit():
                # الف) تطبیق پیشوند در کد مدل: مدل با این عدد شروع شود (مانند 85X90L یا 85Q70C)
                is_prefix_of_model = False
                for mt in prod_model_tokens:
                    if mt.startswith(qw):
                        remainder = mt[len(qw):]
                        # مرز عدد: نباید دنباله‌اش عدد دیگری باشد (مثلاً 85 با 850 وات یا 8500 اشتباه نشود)
                        if not remainder or not remainder[0].isdigit():
                            is_prefix_of_model = True
                            break

                if is_prefix_of_model:
                    w_score += 65000
                    word_matched = True
                elif prod_capacity == qw:
                    # تطبیق دقیق سایز یا ظرفیت کالا
                    w_score += 45000
                    word_matched = True
                else:
                    # ب) تطبیق میانی در کد مدل (Infix Match - مانند 85 در 65X85K)
                    # این حالت نمره بسیار پایین‌تری نسبت به پیشوند دریافت می‌کند تا در انتهای لیست باشد
                    is_infix_of_model = False
                    for mt in prod_model_tokens:
                        if qw in mt and not mt.startswith(qw):
                            is_infix_of_model = True
                            break
                    if is_infix_of_model:
                        w_score += 2000
                        word_matched = True
                    elif qw in prod_words or qw in prod_canon:
                        w_score += 500
                        word_matched = True

            else:
                # ۵. اگر کلمه شامل حروف و ارقام باشد (کد مدل یا واژه متنی)
                if qw_clean in prod_words or qw_clean in prod_model_tokens:
                    # تطبیق کاملاً دقیق با مدل
                    w_score += 60000
                    word_matched = True
                elif qw_clean in prod_cores or qw_clean in prod_base_models:
                    # تطبیق دقیق هسته مدل (مانند v9 یا c3 یا x90)
                    w_score += 45000
                    word_matched = True
                elif any(pm.startswith(qw_clean) for pm in (prod_model_tokens | prod_base_models)):
                    # شروع مدل با این عبارت
                    w_score += 35000
                    word_matched = True
                elif any(qw_clean in pm for pm in (prod_model_tokens | prod_base_models)):
                    # کلمه در داخل مدل وجود دارد
                    w_score += 4000
                    word_matched = True
                elif qw in prod_words or qw in prod_canon:
                    w_score += 1500
                    word_matched = True

            if not word_matched:
                all_words_matched = False
                break

            total_score += w_score

        if not all_words_matched:
            continue

        # بونوس‌های تکمیلی برای تطبیق کامل و مرتب‌سازی دقیق
        if q_canon in _canonicalize_for_search(p_name):
            total_score += 2000
        if p_id and clean_key(p_id) in q_canon:
            total_score += 5000

        matched_items.append((total_score, p))
        seen_keys.add(uid)

    matched_items.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in matched_items]
