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

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None

POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة النص العربي (الإصلاح الجذري)
# ============================
def fix_arabic_text(text):
    # الخطوة 1: إعادة تشكيل الحروف (Reshape)
    reshaped_text = arabic_reshaper.reshape(text)
    # الخطوة 2: تطبيق خوارزمية الاتجاهات (Bidi) لقلب النص بشكل صحيح
    bidi_text = get_display(reshaped_text)
    return bidi_text

def wrap_text_rtl(text, draw, font, max_width):
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # نقيس العرض باستخدام النص المعالج
        display_test = fix_arabic_text(test_line)
        w = draw.textbbox((0, 0), display_test, font=font)[2]
        
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    # معالجة كل سطر بشكل نهائي للعرض
    return [fix_arabic_text(line) for line in lines]

def draw_text_box(draw, lines, font):
    # حساب إجمالي الارتفاع
    line_heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
    total_text_h = sum(line_heights) + (len(lines) - 1) * PADDING
    
    # نقطة البداية لضمان التوسيط العمودي
    current_y = TOP_Y + (MAX_HEIGHT - total_text_h) // 2
    
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        x = LEFT_X + (MAX_WIDTH - w) // 2
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING

# ============================
# بقية الدوال المساعدة
# ============================
def clean_html(text):
    if not text: return ""
    return re.sub("<.*?>", "", text)

def get_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def load_posted():
    if not os.path.exists(POSTED_FILE): return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_posted(hash_id):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(hash_id + "\n")

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    if not FB_PHOTO_URL or "None" in FB_PHOTO_URL:
        print("❌ خطأ: PAGE_ID غير موجود")
        return

    feed = feedparser.parse(RSS_URL)
    posted = load_posted()

    for entry in feed.entries:
        title = clean_html(entry.title)
        h = get_hash(title)
        
        if h in posted: continue

        print(f"🔄 جاري النشر: {title[:50]}")
        
        # إنشاء الصورة
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        
        # جلب صورة المقال
        try:
            html = entry.summary if hasattr(entry, "summary") else ""
            match = re.search(r'<img[^>]+src="([^">]+)"', html)
            img_url = match.group(1) if match else None
            
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        # دمج الصورة
        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        bg.paste(article_img, ((IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2, ARTICLE_IMG_Y), article_img)

        # رسم النص المصلح
        draw = ImageDraw.Draw(bg)
        font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE)
        
        # تصغير الخط تلقائياً إذا كان النص كبيراً
        lines = wrap_text_rtl(title, draw, font, MAX_WIDTH)
        total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines)
        if total_h > MAX_HEIGHT:
            font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE - 10)
            lines = wrap_text_rtl(title, draw, font, MAX_WIDTH)

        draw_text_box(draw, lines, font)

        # حفظ وإرسال
        output = "post.png"
        bg.save(output)
        
        with open(output, "rb") as img:
            res = requests.post(FB_PHOTO_URL, 
                                data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, 
                                files={"source": img})
        
        if res.status_code == 200:
            save_posted(h)
            print("✅ نجاح")
            break
        else:
            print(f"❌ خطأ: {res.text}")

if __name__ == "__main__":
    main()
