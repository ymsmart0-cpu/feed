# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import subprocess

# ============================
# الإعدادات والثوابت
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"

# اسم ملف الخط الذي سيتم استخدامه أو تحميله
FONT_FILENAME = "Cairo-Bold.ttf"
# رابط مباشر لتحميل الخط في حال عدم وجوده
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/cairo/static/Cairo-Bold.ttf"
START_FONT_SIZE = 42

# مسارات الصور الأساسية
BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

# أبعاد الصورة النهائية
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1080

# إعدادات مكان صورة الخبر
ARTICLE_IMG_SIZE = (855, 460)
ARTICLE_IMG_Y = 185

# إعدادات مكان النص (المستطيل الأبيض في الأسفل)
TEXT_BOX_LEFT = 110
TEXT_BOX_RIGHT = 960
TEXT_BOX_TOP = 725
TEXT_BOX_BOTTOM = 885
MAX_TEXT_WIDTH = TEXT_BOX_RIGHT - TEXT_BOX_LEFT
MAX_TEXT_HEIGHT = TEXT_BOX_BOTTOM - TEXT_BOX_TOP
LINE_SPACING = 15  # المسافة بين الأسطر

# استرجاع المفاتيح السرية من إعدادات GitHub
PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_API_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None

POSTED_LOG_FILE = "posted_articles.txt"

# ============================
# دوال مساعدة
# ============================

def ensure_font_exists():
    """تتأكد من وجود ملف الخط، وتقوم بتحميله إذا لم يكن موجوداً."""
    if not os.path.exists(FONT_FILENAME):
        print(f"⚠️ ملف الخط {FONT_FILENAME} غير موجود. جاري التحميل...")
        try:
            response = requests.get(FONT_URL, timeout=30)
            response.raise_for_status()
            with open(FONT_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ تم تحميل الخط بنجاح.")
        except Exception as e:
            print(f"❌ فشل تحميل الخط: {e}")
            return False
    return True

def process_arabic_text(text):
    """تقوم بتشكيل النص العربي (ربط الحروف) ثم قلب اتجاهه للعرض الصحيح."""
    if not text:
        return ""
    # خطوة 1: ربط الحروف ببعضها (Reshaping)
    reshaped_text = arabic_reshaper.reshape(text)
    # خطوة 2: قلب اتجاه النص ليبدأ من اليمين لليسار (Bidi)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def wrap_text_for_drawing(text, font, max_width, draw_engine):
    """تقسم النص إلى أسطر بناءً على العرض المتاح، مع مراعاة المعالجة العربية."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        # نجرب إضافة الكلمة للسطر الحالي
        test_line_words = current_line + [word]
        test_line_raw = " ".join(test_line_words)
        
        # نقيس عرض السطر *بعد* معالجته عربياً ليكون القياس دقيقاً
        processed_test_line = process_arabic_text(test_line_raw)
        bbox = draw_engine.textbbox((0, 0), processed_test_line, font=font)
        line_width = bbox[2] - bbox[0]

        if line_width <= max_width:
            current_line.append(word)
        else:
            # السطر اكتمل، نضيفه للقائمة ونبدأ سطراً جديداً
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            
    # إضافة آخر سطر
    if current_line:
        lines.append(" ".join(current_line))
    
    return lines

def draw_title_on_image(base_image, title):
    """ترسم العنوان على الصورة باستخدام طبقة شفافة لضمان الجودة."""
    if not ensure_font_exists():
        return base_image # إرجاع الصورة الأصلية في حال فشل تحميل الخط

    # إنشاء طبقة شفافة للكتابة عليها
    text_layer = Image.new('RGBA', base_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_layer)
    
    try:
        font = ImageFont.truetype(FONT_FILENAME, START_FONT_SIZE)
    except Exception as e:
        print(f"❌ خطأ في تحميل ملف الخط: {e}")
        return base_image

    # تقسيم النص إلى أسطر
    raw_lines = wrap_text_for_drawing(title, font, MAX_TEXT_WIDTH, draw)
    
    # معالجة كل سطر عربياً بشكل نهائي
    processed_lines = [process_arabic_text(line) for line in raw_lines]

    # حساب الارتفاع الكلي للنص لتوسيطه عمودياً
    total_text_height = 0
    line_heights = []
    for line in processed_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_text_height += h
    total_text_height += (len(processed_lines) - 1) * LINE_SPACING

    # نقطة البداية العمودية (Y) للتوسيط
    current_y = TEXT_BOX_TOP + (MAX_TEXT_HEIGHT - total_text_height) // 2

    # رسم الأسطر
    for i, line in enumerate(processed_lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        # نقطة البداية الأفقية (X) للتوسيط
        current_x = TEXT_BOX_LEFT + (MAX_TEXT_WIDTH - line_width) // 2
        
        # رسم النص على الطبقة الشفافة باللون الأسود
        draw.text((current_x, current_y), line, font=font, fill="black")
        
        # تحديث الموضع للسطر التالي
        current_y += line_heights[i] + LINE_SPACING

    # دمج الطبقة الشفافة فوق الصورة الأساسية
    final_image = Image.alpha_composite(base_image.convert('RGBA'), text_layer)
    return final_image

# ============================
# الدالة الرئيسية
# ============================

def main():
    if not FB_API_URL:
        print("❌ خطأ: لم يتم العثور على PAGE_ID في متغيرات البيئة (Secrets).")
        return

    print("🔄 جاري جلب آخر الأخبار...")
    feed = feedparser.parse(RSS_URL)
    
    posted_hashes = set()
    if os.path.exists(POSTED_LOG_FILE):
        with open(POSTED_LOG_FILE, "r", encoding="utf-8") as f:
            posted_hashes = set(f.read().splitlines())

    for entry in feed.entries:
        # تنظيف العنوان من أي أكواد HTML
        title_raw = re.sub("<.*?>", "", entry.title).strip()
        if not title_raw: continue
        
        # إنشاء بصمة فريدة للخبر
        title_hash = hashlib.md5(title_raw.encode("utf-8")).hexdigest()
        
        if title_hash in posted_hashes:
            continue

        print(f"✨ خبر جديد: {title_raw[:50]}...")

        # 1. تجهيز خلفية الصورة
        if not os.path.exists(BG_PATH):
             print(f"❌ ملف الخلفية {BG_PATH} غير موجود.")
             return
        base_image = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))

        # 2. جلب ودمج صورة الخبر
        article_image = None
        try:
            img_url = None
            html_summary = entry.summary if hasattr(entry, 'summary') else ""
            img_match = re.search(r'<img[^>]+src="([^">]+)"', html_summary)
            if img_match:
                img_url = img_match.group(1)
            
            if img_url:
                print("⬇️ جاري تحميل صورة الخبر...")
                resp = requests.get(img_url, timeout=15)
                resp.raise_for_status()
                article_image = Image.open(BytesIO(resp.content)).convert("RGBA")
        except Exception as e:
            print(f"⚠️ تعذر تحميل صورة الخبر: {e}")

        # استخدام اللوجو كبديل إذا لم تتوفر صورة للخبر
        if article_image is None:
             if os.path.exists(LOGO_PATH):
                 article_image = Image.open(LOGO_PATH).convert("RGBA")
             else:
                 # إنشاء صورة رمادية كبديل أخير
                 article_image = Image.new('RGBA', ARTICLE_IMG_SIZE, (200, 200, 200, 255))

        # تغيير حجم صورة الخبر ووضعها في المكان المحدد
        article_image_resized = article_image.resize(ARTICLE_IMG_SIZE)
        # حساب التوسيط الأفقي لصورة الخبر
        art_img_x = (IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2
        base_image.paste(article_image_resized, (art_img_x, ARTICLE_IMG_Y), article_image_resized)

        # 3. كتابة عنوان الخبر على الصورة
        print("✍️ جاري كتابة العنوان على الصورة...")
        final_image = draw_title_on_image(base_image, title_raw)

        # 4. حفظ الصورة والنشر
        output_filename = "post_ready.png"
        # تحويل الصورة إلى RGB قبل الحفظ بصيغة PNG/JPEG
        final_image.convert("RGB").save(output_filename)
        
        print("🚀 جاري النشر على فيسبوك...")
        with open(output_filename, "rb") as img_file:
            post_data = {
                "access_token": PAGE_ACCESS_TOKEN,
                # نضع العنوان أيضاً في وصف الصورة كنسخة احتياطية نصية
                "caption": f"{title_raw}\n\nاقرأ المزيد: {entry.link}"
            }
            files = {"source": img_file}
            
            try:
                response = requests.post(FB_API_URL, data=post_data, files=files, timeout=60)
                response.raise_for_status()
                
                print("✅ تم النشر بنجاح!")
                
                # تسجيل الخبر كمنشور
                with open(POSTED_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(title_hash + "\n")
                
                # تحديث ملف السجل على GitHub
                print("🗂️ تحديث سجل النشر على GitHub...")
                subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=False)
                subprocess.run(["git", "config", "--global", "user.name", "News Bot"], check=False)
                subprocess.run(["git", "add", POSTED_LOG_FILE], check=False)
                subprocess.run(["git", "commit", "-m", f"Automated post: {title_hash}"], check=False)
                subprocess.run(["git", "push"], check=False)
                
                # نشر خبر واحد فقط في كل دورة تشغيل
                break
                
            except requests.exceptions.RequestException as e:
                print(f"❌ فشل النشر على فيسبوك: {e}")
                if 'response' in locals() and response.text:
                    print(f"تفاصيل الخطأ من فيسبوك: {response.text}")

if __name__ == "__main__":
    main()
