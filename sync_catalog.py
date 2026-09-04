# -*- coding: utf-8 -*-
"""
sync_catalog.py
استخراج مو به موی مشخصات فنی محصولات و تولید درخت دسته‌بندی پویا (بدون تصاویر و کاملاً White-Label).
"""

import urllib.request
import ssl
import json
import re
import os
import sqlite3

BASE_URLS = {
    "tv": "https://momtazkalla.com/price/tv/",
    "conditioner": "https://momtazkalla.com/price/conditioner/",
    "refrigerator": "https://momtazkalla.com/price/refrigerator/",
    "washing_machine": "https://momtazkalla.com/price/washing-machine/",
    "dishwasher": "https://momtazkalla.com/price/dishwasher/",
    "small_appliances": "https://momtazkalla.com/price/small-appliances/"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def clean_text(text: str) -> str:
    """حذف تگ‌های HTML، فاصله‌های اضافه و نام‌های سایت مبدأ جهت White-Label کامل"""
    if not text:
        return ""
    t = re.sub(r'<[^>]+>', ' ', text)
    # سانسور کامل هرگونه ردپای مبدأ
    t = re.sub(r'(ممتازکالا|ممتاز\s*کالا|momtazkala|momtazkalla|\.com)', '', t, flags=re.IGNORECASE)
    t = ' '.join(t.split())
    return t.strip()

def parse_price(val: str) -> int:
    """استخراج عدد قیمت به تومان"""
    if not val:
        return 0
    clean = re.sub(r'[^\d]', '', val)
    return int(clean) if clean else 0

def fetch_html(url: str) -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return resp.read().decode('utf-8', errors='ignore')

def extract_products():
    catalog = {}
    categories_tree = {
        "tv": {"title": "📺 تلویزیون", "brands": {}, "sizes": {}},
        "conditioner": {"title": "❄️ کولر گازی", "capacities": {}, "brands": {}, "types": {}},
        "refrigerator": {"title": "🧊 یخچال فریزر", "plans": {}, "brands": {}, "capacities": {}},
        "washing_machine": {"title": "🧺 ماشین لباسشویی", "capacities": {}, "brands": {}, "plans": {}},
        "dishwasher": {"title": "🍽 ماشین ظرفشویی", "baskets": {}, "brands": {}},
        "small_appliances": {"title": "☕️ لوازم ریز برقی", "subcategories": {}}
    }

    # =========================================================================
    # 1. تلویزیون (TV)
    # =========================================================================
    print("در حال استخراج کاتالوگ تلویزیون...")
    try:
        html_tv = fetch_html(BASE_URLS["tv"])
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html_tv, re.DOTALL)
        for tbl in tables:
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
            current_subgroup = ""
            for tr in trs:
                if 'colspan' in tr:
                    # تیترهای تفکیک‌کننده سایز یا برند
                    dt = re.search(r'data-title=[\"\']([^\"\']+)[\"\']', tr)
                    if dt:
                        current_subgroup = clean_text(dt.group(1))
                    continue
                if '<th' in tr:
                    continue

                tds = re.findall(r'<td([^>]*)>(.*?)</td>', tr, re.DOTALL)
                if not tds:
                    continue

                row_dict = {}
                row_id = ""
                for attrs, content in tds:
                    col_m = re.search(r'data-column=[\"\']([^\"\']+)[\"\']', attrs)
                    col = col_m.group(1) if col_m else ""
                    id_m = re.search(r'data-id=[\"\']([^\"\']+)[\"\']', attrs)
                    if id_m and not row_id:
                        row_id = id_m.group(1).strip()
                    row_dict[col] = clean_text(content)

                model = row_dict.get("model-number", "")
                if not model:
                    continue

                pid = row_id or f"tv_{model.replace(' ', '_')}"
                price = parse_price(row_dict.get("price", "0"))
                score = row_dict.get("overall-score", "")
                assembly = row_dict.get("pa_assembly", "")
                year = row_dict.get("pa_year-of-construction", "")
                resolution = row_dict.get("pa_image-quality", "")
                panel = row_dict.get("pa_panel", "")
                refresh_rate = row_dict.get("pa_refresh-rate", "")
                backlight = row_dict.get("pa_backlight", "")
                os_sys = row_dict.get("pa_operating-system", "")

                # تشخیص سایز و برند از روی مدل یا ساب‌گروپ
                brand = "سایر"
                for b_name in ["سونی", "ال جی", "سامسونگ", "شیائومی", "هایسنس", "توشیبا", "فیلیپس", "پاناسونیک", "شارپ"]:
                    if b_name in current_subgroup or b_name in model:
                        brand = b_name
                        break

                size_m = re.search(r'(\d{2,3})\s*(?:اینچ|inch)?', model)
                size_str = f"{size_m.group(1)} اینچ" if size_m else (current_subgroup if "اینچ" in current_subgroup else "نامشخص")

                catalog[pid] = {
                    "product_id": pid,
                    "category_key": "tv",
                    "category_name": "تلویزیون",
                    "name": f"تلویزیون {size_str} {brand} مدل {model}".strip(),
                    "model_number": model,
                    "brand": brand,
                    "size": size_str,
                    "price": price,
                    "status": "b" if price > 0 else "o",
                    "assembly": assembly,
                    "score": score,
                    "year": year,
                    "resolution": resolution,
                    "panel": panel,
                    "refresh_rate": refresh_rate,
                    "backlight": backlight,
                    "os": os_sys,
                    "more_details": f"پنل {panel} | بکلایت {backlight} | سیستم‌عامل {os_sys}".strip(" |")
                }

                # اضافه به درخت دسته‌بندی پویا
                if brand not in categories_tree["tv"]["brands"]:
                    categories_tree["tv"]["brands"][brand] = []
                if pid not in categories_tree["tv"]["brands"][brand]:
                    categories_tree["tv"]["brands"][brand].append(pid)

                if size_str not in categories_tree["tv"]["sizes"]:
                    categories_tree["tv"]["sizes"][size_str] = []
                if pid not in categories_tree["tv"]["sizes"][size_str]:
                    categories_tree["tv"]["sizes"][size_str].append(pid)

    except Exception as e:
        print("خطا در پردازش تلویزیون:", e)

    # =========================================================================
    # 2. کولر گازی (Air Conditioner)
    # =========================================================================
    print("در حال استخراج کاتالوگ کولر گازی...")
    try:
        html_ac = fetch_html(BASE_URLS["conditioner"])
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html_ac, re.DOTALL)
        for tbl in tables:
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
            current_subgroup = ""
            for tr in trs:
                if 'colspan' in tr:
                    dt = re.search(r'data-title=[\"\']([^\"\']+)[\"\']', tr)
                    if dt:
                        current_subgroup = clean_text(dt.group(1))
                    continue
                if '<th' in tr:
                    continue

                tds = re.findall(r'<td([^>]*)>(.*?)</td>', tr, re.DOTALL)
                if not tds:
                    continue

                row_dict = {}
                row_id = ""
                for attrs, content in tds:
                    col_m = re.search(r'data-column=[\"\']([^\"\']+)[\"\']', attrs)
                    col = col_m.group(1) if col_m else ""
                    id_m = re.search(r'data-id=[\"\']([^\"\']+)[\"\']', attrs)
                    if id_m and not row_id:
                        row_id = id_m.group(1).strip()
                    row_dict[col] = clean_text(content)

                model = row_dict.get("model-number") or row_dict.get("title") or ""
                if not model:
                    continue

                pid = row_id or f"ac_{model[:20].replace(' ', '_')}"
                price = parse_price(row_dict.get("price", "0"))
                score = row_dict.get("overall-score", "")
                temp_range = row_dict.get("pa_temp-range", "")
                room_size = row_dict.get("pa_room-size", "")
                energy = row_dict.get("pa_energy-consumption", "")
                performance = row_dict.get("pa_performance-air", "")
                key_features = row_dict.get("pa_key-features", "") or row_dict.get("pa_more-details", "")

                # استخراج برند و ظرفیت
                brand = "سایر"
                for b_name in ["گری", "کریر", "جنرال گلد", "جنرال شکار", "جنرال برلین", "اجنرال", "ال جی", "سامسونگ", "یونیوا", "هایسنس", "ایوولی", "توشیبا", "گیبسون"]:
                    if b_name in current_subgroup or b_name in model:
                        brand = b_name
                        break

                cap_m = re.search(r'(\d{4,5})', model) or re.search(r'(\d{4,5})', current_subgroup)
                cap_str = cap_m.group(1) if cap_m else "سایر"

                ac_type = "اسپلیت دیواری"
                if "ایستاده" in model or "ایستاده" in current_subgroup:
                    ac_type = "ایستاده"
                elif "پرتابل" in model or "پرتابل" in current_subgroup:
                    ac_type = "پرتابل"
                elif "پنجره" in model or "پنجره" in current_subgroup:
                    ac_type = "پنجره‌ای"
                elif "داکت" in model or "سقفی" in model:
                    ac_type = "داکت اسپلیت"

                catalog[pid] = {
                    "product_id": pid,
                    "category_key": "conditioner",
                    "category_name": "کولر گازی",
                    "name": model if "کولر" in model else f"کولر گازی {brand} {cap_str} {model}".strip(),
                    "model_number": model,
                    "brand": brand,
                    "capacity_btu": cap_str,
                    "ac_type": ac_type,
                    "price": price,
                    "status": "b" if price > 0 else "o",
                    "score": score,
                    "temp_range": temp_range,
                    "room_size": room_size,
                    "energy_consumption": energy,
                    "performance": performance,
                    "key_features": key_features,
                    "more_details": f"عملکرد: {performance} | پوشش: {room_size} | ویژگی: {key_features}".strip(" |")
                }

                # درخت دسته‌بندی پویا
                if cap_str not in categories_tree["conditioner"]["capacities"]:
                    categories_tree["conditioner"]["capacities"][cap_str] = []
                categories_tree["conditioner"]["capacities"][cap_str].append(pid)

                if brand not in categories_tree["conditioner"]["brands"]:
                    categories_tree["conditioner"]["brands"][brand] = []
                categories_tree["conditioner"]["brands"][brand].append(pid)

                if ac_type not in categories_tree["conditioner"]["types"]:
                    categories_tree["conditioner"]["types"][ac_type] = []
                categories_tree["conditioner"]["types"][ac_type].append(pid)

    except Exception as e:
        print("خطا در پردازش کولر گازی:", e)

    # =========================================================================
    # 3. یخچال و فریزر (Refrigerator)
    # =========================================================================
    print("در حال استخراج کاتالوگ یخچال و فریزر...")
    try:
        html_rf = fetch_html(BASE_URLS["refrigerator"])
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html_rf, re.DOTALL)
        for tbl in tables:
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
            current_brand = ""
            for tr in trs:
                if 'colspan' in tr:
                    dt = re.search(r'data-title=[\"\']([^\"\']+)[\"\']', tr)
                    if dt:
                        current_brand = clean_text(dt.group(1))
                    continue
                if '<th' in tr:
                    continue

                tds = re.findall(r'<td([^>]*)>(.*?)</td>', tr, re.DOTALL)
                if not tds:
                    continue

                row_dict = {}
                row_id = ""
                for attrs, content in tds:
                    col_m = re.search(r'data-column=[\"\']([^\"\']+)[\"\']', attrs)
                    col = col_m.group(1) if col_m else ""
                    id_m = re.search(r'data-id=[\"\']([^\"\']+)[\"\']', attrs)
                    if id_m and not row_id:
                        row_id = id_m.group(1).strip()
                    row_dict[col] = clean_text(content)

                model = row_dict.get("model-number", "")
                if not model:
                    continue

                pid = row_id or f"rf_{model.replace(' ', '_')}"
                price = parse_price(row_dict.get("price", "0"))
                plan = row_dict.get("pa_plan", "")
                capacity_foot = row_dict.get("pa_total-capacity-foot", "")
                num_doors = row_dict.get("pa_num-door", "")
                assembly = row_dict.get("pa_assembly", "")
                score = row_dict.get("overall-score", "")
                more_details = row_dict.get("pa_more-details", "")

                brand = current_brand or "سایر"
                for b_name in ["ال جی", "سامسونگ", "بوش", "هایسنس", "هیتاچی", "گرنیه", "توشیبا"]:
                    if b_name in current_brand or b_name in model:
                        brand = b_name
                        break

                catalog[pid] = {
                    "product_id": pid,
                    "category_key": "refrigerator",
                    "category_name": "یخچال فریزر",
                    "name": f"یخچال {brand} {plan} مدل {model}".strip(),
                    "model_number": model,
                    "brand": brand,
                    "plan": plan,
                    "capacity_foot": capacity_foot,
                    "num_doors": num_doors,
                    "price": price,
                    "status": "b" if price > 0 else "o",
                    "assembly": assembly,
                    "score": score,
                    "more_details": f"طرح: {plan} | ظرفیت: {capacity_foot} فوت | تعداد درب: {num_doors} | مونتاژ: {assembly}".strip(" |")
                }

                # درخت دسته‌بندی پویا
                plan_key = plan if plan else "سایر"
                if plan_key not in categories_tree["refrigerator"]["plans"]:
                    categories_tree["refrigerator"]["plans"][plan_key] = []
                categories_tree["refrigerator"]["plans"][plan_key].append(pid)

                if brand not in categories_tree["refrigerator"]["brands"]:
                    categories_tree["refrigerator"]["brands"][brand] = []
                categories_tree["refrigerator"]["brands"][brand].append(pid)

                foot_key = f"{capacity_foot} فوت" if capacity_foot else "سایر"
                if foot_key not in categories_tree["refrigerator"]["capacities"]:
                    categories_tree["refrigerator"]["capacities"][foot_key] = []
                categories_tree["refrigerator"]["capacities"][foot_key].append(pid)

    except Exception as e:
        print("خطا در پردازش یخچال:", e)

    # =========================================================================
    # 4. ماشین لباسشویی (Washing Machine)
    # =========================================================================
    print("در حال استخراج کاتالوگ ماشین لباسشویی...")
    try:
        html_wm = fetch_html(BASE_URLS["washing_machine"])
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html_wm, re.DOTALL)
        for tbl in tables:
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
            current_brand = ""
            for tr in trs:
                if 'colspan' in tr:
                    dt = re.search(r'data-title=[\"\']([^\"\']+)[\"\']', tr)
                    if dt:
                        current_brand = clean_text(dt.group(1))
                    continue
                if '<th' in tr:
                    continue

                tds = re.findall(r'<td([^>]*)>(.*?)</td>', tr, re.DOTALL)
                if not tds:
                    continue

                row_dict = {}
                row_id = ""
                for attrs, content in tds:
                    col_m = re.search(r'data-column=[\"\']([^\"\']+)[\"\']', attrs)
                    col = col_m.group(1) if col_m else ""
                    id_m = re.search(r'data-id=[\"\']([^\"\']+)[\"\']', attrs)
                    if id_m and not row_id:
                        row_id = id_m.group(1).strip()
                    row_dict[col] = clean_text(content)

                model = row_dict.get("model-number", "")
                if not model:
                    continue

                pid = row_id or f"wm_{model.replace(' ', '_')}"
                price = parse_price(row_dict.get("price", "0"))
                capacity_kg = row_dict.get("pa_washing-machine-capacity", "")
                plan = row_dict.get("pa_plan", "") or "درب از جلو"
                assembly = row_dict.get("pa_assembly", "")
                score = row_dict.get("overall-score", "")
                more_details = row_dict.get("pa_more-details", "")

                brand = current_brand or "سایر"
                for b_name in ["بوش", "ال جی", "سامسونگ", "هایسنس", "هیتاچی"]:
                    if b_name in current_brand or b_name in model:
                        brand = b_name
                        break

                cap_str = f"{capacity_kg} کیلو" if capacity_kg else "سایر"

                catalog[pid] = {
                    "product_id": pid,
                    "category_key": "washing_machine",
                    "category_name": "ماشین لباسشویی",
                    "name": f"لباسشویی {brand} {cap_str} مدل {model}".strip(),
                    "model_number": model,
                    "brand": brand,
                    "capacity_kg": capacity_kg,
                    "plan": plan,
                    "price": price,
                    "status": "b" if price > 0 else "o",
                    "assembly": assembly,
                    "score": score,
                    "more_details": f"ظرفیت: {cap_str} | مونتاژ: {assembly} | طرح: {plan}".strip(" |")
                }

                # درخت دسته‌بندی پویا
                if cap_str not in categories_tree["washing_machine"]["capacities"]:
                    categories_tree["washing_machine"]["capacities"][cap_str] = []
                categories_tree["washing_machine"]["capacities"][cap_str].append(pid)

                if brand not in categories_tree["washing_machine"]["brands"]:
                    categories_tree["washing_machine"]["brands"][brand] = []
                categories_tree["washing_machine"]["brands"][brand].append(pid)

                if plan not in categories_tree["washing_machine"]["plans"]:
                    categories_tree["washing_machine"]["plans"][plan] = []
                categories_tree["washing_machine"]["plans"][plan].append(pid)

    except Exception as e:
        print("خطا در پردازش لباسشویی:", e)

    # =========================================================================
    # 5. ماشین ظرفشویی (Dishwasher)
    # =========================================================================
    print("در حال استخراج کاتالوگ ماشین ظرفشویی...")
    try:
        html_dw = fetch_html(BASE_URLS["dishwasher"])
        tables = re.findall(r'<table[^>]*>(.*?)</table>', html_dw, re.DOTALL)
        for tbl in tables:
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL)
            current_brand = ""
            for tr in trs:
                if 'colspan' in tr:
                    dt = re.search(r'data-title=[\"\']([^\"\']+)[\"\']', tr)
                    if dt:
                        current_brand = clean_text(dt.group(1))
                    continue
                if '<th' in tr:
                    continue

                tds = re.findall(r'<td([^>]*)>(.*?)</td>', tr, re.DOTALL)
                if not tds:
                    continue

                row_dict = {}
                row_id = ""
                for attrs, content in tds:
                    col_m = re.search(r'data-column=[\"\']([^\"\']+)[\"\']', attrs)
                    col = col_m.group(1) if col_m else ""
                    id_m = re.search(r'data-id=[\"\']([^\"\']+)[\"\']', attrs)
                    if id_m and not row_id:
                        row_id = id_m.group(1).strip()
                    row_dict[col] = clean_text(content)

                model = row_dict.get("model-number", "")
                if not model:
                    continue

                pid = row_id or f"dw_{model.replace(' ', '_')}"
                price = parse_price(row_dict.get("price", "0"))
                assembly = row_dict.get("pa_assembly", "")
                score = row_dict.get("overall-score", "")
                more_details = row_dict.get("pa_more-details", "")

                brand = current_brand or "سایر"
                for b_name in ["بوش", "ال جی", "سامسونگ", "هایسنس", "توشیبا", "دوو", "هیتاچی"]:
                    if b_name in current_brand or b_name in model:
                        brand = b_name
                        break

                baskets = "3 طبقه" if any(k in model for k in ["325", "425", "6050", "SMS8", "SMS6", "SMS4"]) else "2 یا 3 طبقه"

                catalog[pid] = {
                    "product_id": pid,
                    "category_key": "dishwasher",
                    "category_name": "ماشین ظرفشویی",
                    "name": f"ظرفشویی {brand} مدل {model}".strip(),
                    "model_number": model,
                    "brand": brand,
                    "baskets": baskets,
                    "price": price,
                    "status": "b" if price > 0 else "o",
                    "assembly": assembly,
                    "score": score,
                    "more_details": f"مونتاژ: {assembly} | مشخصات: {more_details}".strip(" |")
                }

                if brand not in categories_tree["dishwasher"]["brands"]:
                    categories_tree["dishwasher"]["brands"][brand] = []
                categories_tree["dishwasher"]["brands"][brand].append(pid)

                if baskets not in categories_tree["dishwasher"]["baskets"]:
                    categories_tree["dishwasher"]["baskets"][baskets] = []
                categories_tree["dishwasher"]["baskets"][baskets].append(pid)

    except Exception as e:
        print("خطا در پردازش ظرفشویی:", e)

    # =========================================================================
    # 6. لوازم ریز برقی (Small Appliances)
    # =========================================================================
    print("در حال استخراج کاتالوگ لوازم ریز...")
    try:
        html_sm = fetch_html(BASE_URLS["small_appliances"])
        # تجزیه آکاردئون‌ها بر اساس ساختار دقیق وردپرس
        panes = re.findall(r'<div class=[\"\']wd-accordion-title-text[\"\']><span>(.*?)</span></div>.*?<div class=[\"\']wd-accordion-content[\"\']>(.*?)(?=<div class=[\"\']wd-accordion-title-text|$)', html_sm, re.DOTALL)

        for sub_name, pane_body in panes:
            sub_title = clean_text(sub_name)
            cards = re.findall(r'<section class=[\"\']procode-full-card[\"\'][^>]*data-id=[\"\']([^\"\']+)[\"\']>(.*?)</section>', pane_body, re.DOTALL)
            for cid, cbody in cards:
                title_m = re.search(r'<p class=[\"\']procode-full-title[\"\']>.*?<a[^>]*>(.*?)</a>', cbody, re.DOTALL)
                full_name = clean_text(title_m.group(1)) if title_m else ""
                if not full_name:
                    continue

                price_m = re.search(r'data-live-id=[\"\'][^\"\']+[\"\']>([^<]+)</span>', cbody)
                price = parse_price(price_m.group(1)) if price_m else 0

                score_m = re.search(r'<span class=[\"\']procode-score[^\"\']*[\"\']>([^<]+)</span>', cbody)
                score = score_m.group(1).strip() if score_m else ""

                desc_m = re.search(r'<div class=[\"\']procode-full-desc[^\"\']*[\"\']>(.*?)</div>', cbody, re.DOTALL)
                desc = clean_text(desc_m.group(1)) if desc_m else ""

                pid = cid.strip()

                catalog[pid] = {
                    "product_id": pid,
                    "category_key": "small_appliances",
                    "category_name": "لوازم ریز برقی",
                    "subcategory": sub_title,
                    "name": full_name,
                    "model_number": full_name,
                    "brand": full_name.split()[1] if len(full_name.split()) > 1 else "",
                    "price": price,
                    "status": "b" if price > 0 else "o",
                    "score": score,
                    "more_details": desc[:250]
                }

                if sub_title not in categories_tree["small_appliances"]["subcategories"]:
                    categories_tree["small_appliances"]["subcategories"][sub_title] = []
                categories_tree["small_appliances"]["subcategories"][sub_title].append(pid)

    except Exception as e:
        print("خطا در پردازش لوازم ریز:", e)

    # ذخیره در فایل کاتالوگ و ساختار درختی
    with open("catalog_products.json", "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    with open("categories_tree.json", "w", encoding="utf-8") as f:
        json.dump(categories_tree, f, ensure_ascii=False, indent=2)

    print(f"\n✅ استخراج با موفقیت انجام شد: {len(catalog)} محصول دریافت و ذخیره شد.")
    return catalog, categories_tree

if __name__ == "__main__":
    extract_products()
