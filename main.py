# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
from io import BytesIO
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import random
import subprocess

# ============================
# إعدادات عامة
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "29ltbukrabolditalic.otf"
START_FONT_SIZE = 45

BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1080
ARTICLE_IMG_SIZE = (855, 460)
ARTICLE_IMG_Y = 185

LEFT_X = 110
RIGHT_X = 960
TOP_Y = 725
BOTTOM_Y = 885
PADDING = 10
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

# استدعاء المتغيرات من GitHub Secrets
PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None

POSTED_FILE = "posted_articles.txt"

# ============================
# دوال معالجة النص العربي (اليمين لليسار)
# ============================
def fix_arabic_for_pil(text):
    # 1. إعادة تشكيل الحروف لتصبح متصلة (ب، بـ، ـبـ)
    reshaped_text = arabic_reshaper.reshape(text)
    # 2. عكس اتجاه النص ليعرض من اليمين لليسار بشكل صحيح
    bidi_text = get_display(reshaped_text)
    return bidi_text

def wrap_text_rtl(text, draw, font, max_width):
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # نقيس العرض دائماً بعد معالجة النص العربي
        display_test = fix_arabic_for_pil(test_line)
        w = draw.textbbox((0, 0), display_test, font=font)[2]
        
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                # نحفظ السطر الحالي بعد معالجته للظهور RTL
                lines.append(fix_arabic_for_pil(" ".join(current_line)))
            current_line = [word]
    
    if current_line:
        lines.append(fix_arabic_for_pil(" ".join(current_line)))
    
    return lines

def draw_text_box(draw, lines, font):
    # حساب إجمالي ارتفاع النص لتوسيطه عمودياً
    line_heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
    total_text_h = sum(line_heights) + (len(lines) - 1) * PADDING
    
    current_y = TOP_Y + (MAX_HEIGHT - total_text_h) // 2
    
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        # التوسيط الأفقي: (عرض الصندوق - عرض النص) / 2 + نقطة البداية اليسرى
        x = LEFT_X + (MAX_WIDTH - w) // 2
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING

# ============================
# وظائف النظام والفيسبوك
# ============================
def get_hash(text): return hashlib.md5(text.encode("utf-8")).hexdigest()

def load_posted():
    if not os.path.exists(POSTED_FILE): return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_posted(hash_id):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(hash_id + "\n")

# ============================
# المحرك الرئيسي
# ============================
def main():
    if not PAGE_ID or PAGE_ID == "None":
        print("❌ خطأ: PAGE_ID غير موجود في الإعدادات")
        return

    feed = feedparser.parse(RSS_URL)
    posted = load_posted()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title) # تنظيف النص من HTML
        h = get_hash(title)
        
        if h in posted: continue

        print(f"🔄 معالجة المقال: {title[:50]}")
        
        # تجهيز الصورة الخلفية
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        
        # جلب صورة المقال
        try:
            html = entry.summary if hasattr(entry, "summary") else ""
            img_match = re.search(r'<img[^>]+src="([^">]+)"', html)
            img_url = img_match.group(1) if img_match else None
            
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        # دمج صورة المقال في التصميم
        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        bg.paste(article_img, ((IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2, ARTICLE_IMG_Y), article_img)

        # رسم النص العربي RTL
        draw = ImageDraw.Draw(bg)
        font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE)
        
        # تقسيم النص لأسطر مع تطبيق الـ RTL
        lines = wrap_text_rtl(title, draw, font, MAX_WIDTH)
        draw_text_box(draw, lines, font)

        # الحفظ والنشر
        output = "final_post.png"
        bg.save(output)
        
        with open(output, "rb") as img:
            res = requests.post(FB_PHOTO_URL, 
                                data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, 
                                files={"source": img})
        
        if res.status_code == 200:
            save_posted(h)
            print("✅ تم النشر بنجاح على فيسبوك")
            break # نشر مقال واحد فقط في كل دورة
        else:
            print(f"❌ فشل النشر: {res.text}")

if __name__ == "__main__":
    main()
