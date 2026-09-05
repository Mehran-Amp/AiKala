"""
Laptop PDF Price List Generator for AiKala Telegram Bot (@AiKala_bot)
=====================================================================
Generates high-resolution, beautifully styled Persian PDF price lists
for available laptops with specs, grade, and current price.
Guaranteed to never fail with encoding or font errors.
"""

import os
import json
import logging
import urllib.request
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
FONT_BOLD_PATH = os.path.join(FONTS_DIR, "Vazirmatn-Bold.ttf")
FONT_REGULAR_PATH = os.path.join(FONTS_DIR, "Vazirmatn-Regular.ttf")


def _ensure_fonts():
    """Ensure Vazirmatn fonts exist or download them if missing"""
    try:
        os.makedirs(FONTS_DIR, exist_ok=True)
        urls = {
            FONT_REGULAR_PATH: "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Regular.ttf",
            FONT_BOLD_PATH: "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf",
        }
        for path, url in urls.items():
            if not os.path.isfile(path) or os.path.getsize(path) < 1000:
                cwd_path = os.path.join(os.getcwd(), "fonts", os.path.basename(path))
                if os.path.isfile(cwd_path) and os.path.getsize(cwd_path) > 1000:
                    try:
                        import shutil
                        shutil.copy2(cwd_path, path)
                        continue
                    except Exception:
                        pass
                try:
                    urllib.request.urlretrieve(url, path)
                    logger.info(f"Downloaded font: {path}")
                except Exception as e:
                    logger.warning(f"Could not download font {path}: {e}")
    except Exception as e:
        logger.warning(f"Error in _ensure_fonts: {e}")


# Run font check once
_ensure_fonts()

# Arabic/Persian Reshaper & Bidi
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    def fa(text: Any) -> str:
        if text is None:
            return ""
        s = str(text)
        if not s.strip():
            return ""
        try:
            config = {
                'delete_harakat': False,
                'support_ligatures': True,
                'RIAL': True
            }
            reshaper = arabic_reshaper.ArabicReshaper(configuration=config)
            reshaped = reshaper.reshape(s)
            return get_display(reshaped)
        except Exception:
            return s
except ImportError:
    def fa(text: Any) -> str:
        return str(text) if text is not None else ""


def to_fa_digits(text: Any) -> str:
    """Convert English digits to Persian digits"""
    if text is None:
        return ""
    s = str(text)
    mapping = {
        '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
        '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
    }
    return "".join(mapping.get(ch, ch) for ch in s)


def get_shamsi_date_str() -> str:
    """Returns formatted Persian/Shamsi date and time"""
    try:
        import jdatetime
        now = jdatetime.datetime.now()
        return now.strftime("%Y/%m/%d - %H:%M")
    except ImportError:
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M")


def load_all_laptops() -> List[Dict[str, Any]]:
    """Loads all available laptops from laptops_catalog.json and general cache"""
    laptops = []
    seen_ids = set()

    # 1. From laptops_catalog.json
    laptops_file = "laptops_catalog.json"
    if os.path.exists(laptops_file):
        try:
            with open(laptops_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for lp in data:
                        lid = lp.get("id") or lp.get("product_id") or f"{lp.get('brand')}_{lp.get('model')}"
                        if lid not in seen_ids:
                            seen_ids.add(lid)
                            laptops.append(lp)
        except Exception as e:
            logger.warning(f"Error loading {laptops_file}: {e}")

    # 2. From search_engine / catalog_products if any
    try:
        from search_engine import JSON_PRODUCTS
        for p in JSON_PRODUCTS:
            cat_key = p.get("category_key")
            cat_name = p.get("category") or p.get("category_name")
            pid = p.get("product_id") or p.get("id")
            if (cat_key == "laptop" or cat_name in ["لپ‌تاپ", "لپ تاپ", "laptop"] or str(pid).upper().startswith("LAP")):
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    laptops.append(p)
    except Exception:
        pass

    return laptops


def generate_laptops_price_list_pdf(output_path: str = "AiKala_Laptops_PriceList.pdf") -> str:
    """
    Generates a professional PDF containing the laptops inventory list.
    Safely catches any encoding/font issues and uses clean fallbacks.
    """
    laptops = load_all_laptops()

    try:
        from PIL import Image, ImageDraw, ImageFont
        return _generate_pdf_with_pil(laptops, output_path)
    except Exception as e:
        logger.warning(f"PIL PDF generation skipped/failed ({e}), using reliable pure-PDF generator")
        return _generate_fallback_pdf(laptops, output_path)


def _generate_pdf_with_pil(laptops: List[Dict[str, Any]], output_path: str) -> str:
    """Generates multi-page A4 PDF using Pillow with Vazirmatn fonts"""
    from PIL import Image, ImageDraw, ImageFont

    PAGE_WIDTH = 1240
    PAGE_HEIGHT = 1754

    def get_font_tuple(size: int, bold: bool = False):
        candidate_paths = [
            FONT_BOLD_PATH if bold else FONT_REGULAR_PATH,
            os.path.join(os.getcwd(), "fonts", "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        for fp in candidate_paths:
            if os.path.isfile(fp) and os.path.getsize(fp) > 1000:
                try:
                    return (ImageFont.truetype(fp, size), True)
                except Exception:
                    pass
        # Fallback to default
        try:
            return (ImageFont.load_default(), False)
        except Exception:
            return (None, False)

    font_title = get_font_tuple(34, bold=True)
    font_subtitle = get_font_tuple(20, bold=False)
    font_badge = get_font_tuple(18, bold=True)
    font_th = get_font_tuple(18, bold=True)
    font_cell_bold = get_font_tuple(17, bold=True)
    font_cell = get_font_tuple(15, bold=False)
    font_footer = get_font_tuple(16, bold=False)
    font_tag = get_font_tuple(14, bold=True)

    # If even the main title font cannot handle unicode, throw to let pure-pdf take over
    if not font_title[1]:
        raise ValueError("No TrueType Unicode font available for Pillow, falling back to pure PDF")

    def safe_text(draw, xy, text, font_info, fill, anchor="mm"):
        font, is_ttf = font_info
        if not font:
            return
        if not is_ttf:
            # Strip non-latin1 characters
            text = text.encode("ascii", "replace").decode("ascii")
        try:
            draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        except UnicodeEncodeError:
            clean = text.encode("ascii", "replace").decode("ascii")
            draw.text(xy, clean, font=font, fill=fill, anchor=anchor)

    # Palette
    NAVY_DARK = (15, 23, 42)       # #0F172A
    NAVY_LIGHT = (30, 41, 59)      # #1E293B
    TEXT_MUTED = (100, 116, 139)   # #64748B
    TEXT_DARK = (30, 41, 59)
    BG_ROW_ALT = (248, 250, 252)   # #F8FAFC
    BORDER_COLOR = (226, 232, 240) # #E2E8F0
    WHITE = (255, 255, 255)
    GREEN_COLOR = (16, 185, 129)   # #10B981
    BLUE_COLOR = (2, 132, 199)     # #0284C7
    BG_BADGE = (236, 253, 245)

    ITEMS_PER_PAGE = 7
    total_items = len(laptops)
    num_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE) if total_items > 0 else 1

    shamsi_date = get_shamsi_date_str()
    pages_images = []

    for page_idx in range(num_pages):
        img = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), color=WHITE)
        draw = ImageDraw.Draw(img)

        # ── Header Banner ──
        draw.rectangle([0, 0, PAGE_WIDTH, 175], fill=NAVY_DARK)
        draw.rectangle([0, 175, PAGE_WIDTH, 182], fill=BLUE_COLOR)

        # Title & Subtitle
        safe_text(draw, (PAGE_WIDTH // 2, 55), fa("لیست قیمت ربات تلگرامی AiKala_bot"), font_title, fill=WHITE, anchor="mm")
        safe_text(draw, (PAGE_WIDTH // 2, 110), fa(f"فروشگاه تخصصی لپ‌تاپ و کالای دیجیتال • تاریخ استعلام: {to_fa_digits(shamsi_date)}"), font_subtitle, fill=(203, 213, 225), anchor="mm")

        # ── Guarantee Badge ──
        draw.rounded_rectangle([60, 205, PAGE_WIDTH - 60, 260], radius=8, fill=BG_BADGE, outline=GREEN_COLOR, width=2)
        safe_text(draw, (PAGE_WIDTH // 2, 232), fa("🛡 کلیه محصولات لپ‌تاپ دارای یک هفته ضمانت تست و تعویض با فاکتور معتبر می‌باشند"), font_badge, fill=(6, 95, 70), anchor="mm")

        # ── Table Coordinates ──
        table_top = 280
        table_left = 60
        table_right = PAGE_WIDTH - 60

        draw.rounded_rectangle([table_left, table_top, table_right, table_top + 45], radius=6, fill=NAVY_LIGHT)

        # Column positions (RTL)
        c_price = (table_left + 10, table_left + 200)
        c_grade = (table_left + 205, table_left + 335)
        c_specs = (table_left + 340, table_left + 780)
        c_model = (table_left + 785, table_right - 70)
        c_row = (table_right - 65, table_right - 10)

        safe_text(draw, ((c_row[0] + c_row[1]) // 2, table_top + 22), fa("ردیف"), font_th, fill=WHITE, anchor="mm")
        safe_text(draw, ((c_model[0] + c_model[1]) // 2, table_top + 22), fa("برند و مدل دستگاه"), font_th, fill=WHITE, anchor="mm")
        safe_text(draw, ((c_specs[0] + c_specs[1]) // 2, table_top + 22), fa("مشخصات کلیدی (CPU / RAM / SSD / GPU / LCD)"), font_th, fill=WHITE, anchor="mm")
        safe_text(draw, ((c_grade[0] + c_grade[1]) // 2, table_top + 22), fa("گرید تمیزی"), font_th, fill=WHITE, anchor="mm")
        safe_text(draw, ((c_price[0] + c_price[1]) // 2, table_top + 22), fa("قیمت روز"), font_th, fill=WHITE, anchor="mm")

        # ── Render Rows ──
        cur_y = table_top + 50
        row_height = 180

        start_idx = page_idx * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
        page_items = laptops[start_idx:end_idx] if total_items > 0 else []

        if not page_items and total_items == 0:
            safe_text(draw, (PAGE_WIDTH // 2, cur_y + 150), fa("در حال حاضر لیست موجودی لپ‌تاپ‌ها توسط ادمین در حال بارگذاری است."), font_subtitle, fill=TEXT_MUTED, anchor="mm")
            safe_text(draw, (PAGE_WIDTH // 2, cur_y + 200), fa("جهت استعلام لحظه‌ای و سفارش مدل‌ها با پشتیبانی ۰۹۱۹۵۸۵۹۴۳۴ تماس حاصل فرمایید."), font_badge, fill=BLUE_COLOR, anchor="mm")
        else:
            for i, lp in enumerate(page_items):
                item_num = start_idx + i + 1
                bg_color = WHITE if i % 2 == 0 else BG_ROW_ALT

                draw.rectangle([table_left, cur_y, table_right, cur_y + row_height], fill=bg_color, outline=BORDER_COLOR, width=1)

                # 1. Row number
                safe_text(draw, ((c_row[0] + c_row[1]) // 2, cur_y + row_height // 2), to_fa_digits(str(item_num)), font_cell_bold, fill=TEXT_DARK, anchor="mm")

                # 2. Brand & Model
                b_name = str(lp.get("brand", "")).strip()
                m_name = str(lp.get("model", "") or lp.get("name", "") or lp.get("title", ""))
                m_name = m_name.replace("لپ‌تاپ", "").replace("لپ تاپ", "").strip()
                p_code = lp.get("code") or (lp.get("specs", {}).get("کد مدل") if isinstance(lp.get("specs"), dict) else "")

                safe_text(draw, (c_model[1] - 10, cur_y + 35), fa(b_name), font_cell_bold, fill=BLUE_COLOR, anchor="rm")
                if len(m_name) > 32:
                    m_name = m_name[:30] + "..."
                safe_text(draw, (c_model[1] - 10, cur_y + 70), fa(m_name), font_cell, fill=TEXT_DARK, anchor="rm")
                if p_code:
                    safe_text(draw, (c_model[1] - 10, cur_y + 105), fa(f"کد کالا: {to_fa_digits(p_code)}"), font_tag, fill=TEXT_MUTED, anchor="rm")

                # 3. Specs Details
                specs = lp.get("specs", {}) if isinstance(lp.get("specs"), dict) else {}
                cpu = specs.get("پردازنده (CPU)") or specs.get("cpu", "")
                ram = specs.get("حافظه رم (RAM)") or specs.get("رم", "")
                ssd = specs.get("حافظه داخلی (SSD/HDD)") or specs.get("هارد", "")
                gpu = specs.get("کارت گرافیک (GPU)") or specs.get("گرافیک", "")
                lcd = specs.get("صفحه نمایش") or specs.get("نمایشگر", "")

                sy = cur_y + 30
                if cpu:
                    safe_text(draw, (c_specs[1] - 10, sy), fa(f"• پردازنده: {cpu}"), font_cell, fill=TEXT_DARK, anchor="rm")
                    sy += 28
                if ram or ssd:
                    ram_ssd_str = f"• رم: {ram}  |  حافظه: {ssd}" if (ram and ssd) else (f"• رم: {ram}" if ram else f"• حافظه: {ssd}")
                    safe_text(draw, (c_specs[1] - 10, sy), fa(ram_ssd_str), font_cell, fill=TEXT_DARK, anchor="rm")
                    sy += 28
                if gpu:
                    safe_text(draw, (c_specs[1] - 10, sy), fa(f"• کارت گرافیک: {gpu}"), font_cell, fill=TEXT_DARK, anchor="rm")
                    sy += 28
                if lcd:
                    safe_text(draw, (c_specs[1] - 10, sy), fa(f"• صفحه نمایش: {lcd}"), font_cell, fill=TEXT_DARK, anchor="rm")

                # 4. Grade
                grade = specs.get("گرید و تمیزی") or specs.get("گرید", "A++")
                draw.rounded_rectangle([c_grade[0] + 15, cur_y + 65, c_grade[1] - 15, cur_y + 110], radius=6, fill=(241, 245, 249), outline=BORDER_COLOR)
                safe_text(draw, ((c_grade[0] + c_grade[1]) // 2, cur_y + 88), fa(f"⭐️ {grade}"), font_badge, fill=NAVY_DARK, anchor="mm")

                # 5. Price
                price_val = lp.get("price", 0)
                if isinstance(price_val, (int, float)) and price_val > 0:
                    price_str = f"{int(price_val):,} تومان"
                    price_display = fa(to_fa_digits(price_str))
                else:
                    price_display = fa("استعلام تلفنی")

                safe_text(draw, ((c_price[0] + c_price[1]) // 2, cur_y + 75), price_display, font_cell_bold, fill=NAVY_DARK, anchor="mm")
                safe_text(draw, ((c_price[0] + c_price[1]) // 2, cur_y + 105), fa("✅ آماده ارسال"), font_tag, fill=GREEN_COLOR, anchor="mm")

                cur_y += row_height + 4

        # ── Footer ──
        footer_y = PAGE_HEIGHT - 90
        draw.line([60, footer_y, PAGE_WIDTH - 60, footer_y], fill=BORDER_COLOR, width=2)

        page_str = fa(f"صفحه {to_fa_digits(str(page_idx + 1))} از {to_fa_digits(str(num_pages))}")
        safe_text(draw, (PAGE_WIDTH // 2, footer_y + 40), page_str, font=font_footer, fill=TEXT_MUTED, anchor="mm")

        bot_str = fa("ربات استعلام و ثبت سفارش تلگرام: @AiKala_bot  |  پشتیبانی: ۰۹۱۹۵۸۵۹۴۳۴")
        safe_text(draw, (PAGE_WIDTH - 70, footer_y + 40), bot_str, font=font_footer, fill=NAVY_LIGHT, anchor="rm")

        pages_images.append(img)

    if pages_images:
        pages_images[0].save(
            output_path,
            "PDF",
            resolution=150.0,
            save_all=True,
            append_images=pages_images[1:] if len(pages_images) > 1 else []
        )
        logger.info(f"Generated PDF price list with {len(pages_images)} pages at {output_path}")

    return output_path


def _clean_ascii(val: Any) -> str:
    """Sanitizes text so it can never trigger latin-1 or postscript string syntax issues"""
    if val is None:
        return ""
    s = str(val)
    # Remove characters that conflict with PDF literal strings
    s = s.replace("(", "[").replace(")", "]").replace("\\", "/")
    # Encode to ASCII, ignoring invalid characters
    return s.encode("ascii", "ignore").decode("ascii").strip()


def _generate_fallback_pdf(laptops: List[Dict[str, Any]], output_path: str) -> str:
    """
    Robust pure-Python PDF 1.4 generator.
    Strictly uses clean ASCII encoding so it can NEVER fail with 'latin-1' or unicode codec errors.
    """
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "%PDF-1.4",
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
        "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> endobj",
    ]

    content_stream = (
        "BT\n"
        "/F1 18 Tf\n"
        "50 780 Td\n"
        "(AiKala_bot - Laptop Price List) Tj\n"
        "/F1 11 Tf\n"
        "0 -25 Td\n"
        f"(Date: {date_str}) Tj\n"
        "0 -20 Td\n"
        "(Guarantee: 1 Week Test & Replacement Guarantee) Tj\n"
        "0 -20 Td\n"
        "(Support: +98 919 585 9434 | Telegram: @AiKala_bot) Tj\n"
        "0 -30 Td\n"
        f"(Total Laptops in Catalog: {len(laptops)}) Tj\n"
        "0 -25 Td\n"
        "(----------------------------------------------------------------------) Tj\n"
    )

    for idx, lp in enumerate(laptops[:25], 1):
        brand = _clean_ascii(lp.get("brand", ""))
        model = _clean_ascii(lp.get("model", "") or lp.get("name", ""))
        price = lp.get("price", 0)
        price_str = f"{int(price):,} Toman" if price else "Call"
        item_line = f"{idx}. {brand} {model[:30]} | {price_str}"
        content_stream += f"0 -20 Td\n({_clean_ascii(item_line)}) Tj\n"

    content_stream += "ET\n"
    content_bytes = content_stream.encode("ascii", "ignore")

    lines.append(f"4 0 obj << /Length {len(content_bytes)} >> stream\n" + content_stream + "endstream\nendobj")

    body = "\n".join(lines) + "\n"
    xref_offset = len(body.encode("ascii", "ignore"))

    trailer = (
        f"xref\n0 6\n0000000000 65535 f \n"
        "trailer << /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )

    full_content = (body + trailer).encode("ascii", "ignore")

    with open(output_path, "wb") as f:
        f.write(full_content)

    logger.info(f"Fallback PDF written safely to {output_path}")
    return output_path
