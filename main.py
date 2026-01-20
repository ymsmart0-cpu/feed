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
# تأكد من تحميل ملف Cairo-Bold.ttf ووضعه بجانب الكود
FONT_FILE = "Cairo-Bold.ttf" 
START_FONT_SIZE = 42

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
PADDING = 8
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None

POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة النص العربي
# ============================
def process_arabic(text):
    # تشكيل الحروف + ضبط الاتجاه من اليمين لليسار
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def wrap_arabic_text(text, draw, font, max_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        w = draw.textbbox((0, 0), process_arabic(test_line), font=font)[2]
        if w <= max_width:
            current_line.append(word)
        else:
            lines.append(process_arabic(" ".join(current_line)))
            current_line = [word]
    if current_line:
        lines.append(process_arabic(" ".join(current_line)))
    return lines

# ============================
# دالة الطبقة الشفافة (الفكرة التي اقترحتها)
# ============================
def apply_text_layer(base_img, lines, font):
    # إنشاء طبقة شفافة تماماً
    txt_layer = Image.new('RGBA', base_img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    # حساب إجمالي ارتفاع الكتلة النصية لتوسيطها
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) + (len(lines)-1)*PADDING
    current_y = TOP_Y + (MAX_HEIGHT - total_h) // 2

    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        x = LEFT_X + (MAX_WIDTH - w) // 2
        # نرسم النص على الطبقة الشفافة
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING
    
    # دمج الطبقة الشفافة فوق الصورة الأصلية
    return Image.alpha_composite(base_img.convert('RGBA'), txt_layer)

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    if not FB_PHOTO_URL or "None" in FB_PHOTO_URL:
        print("❌ خطأ: الـ PAGE_ID غير صحيح")
        return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 جاري العمل على: {title[:40]}")
        
        # 1. فتح الخلفية وصورة المقال
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        try:
            img_match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
            r = requests.get(img_match.group(1), timeout=10)
            art_img = Image.open(BytesIO(r.content)).convert("RGBA").resize(ARTICLE_IMG_SIZE)
        except:
            art_img = Image.open(LOGO_PATH).convert("RGBA").resize(ARTICLE_IMG_SIZE)
        
        bg.paste(art_img, ((IMAGE_WIDTH-ARTICLE_IMG_SIZE[0])//2, ARTICLE_IMG_Y), art_img)

        # 2. معالجة النص باستخدام الطبقة الشفافة
        draw = ImageDraw.Draw(bg)
        font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE)
        lines = wrap_arabic_text(title, draw, font, MAX_WIDTH)
        
        # استدعاء دالة الطبقة الشفافة
        final_img = apply_text_layer(bg, lines, font)

        # 3. الحفظ والنشر
        output = "final.png"
        final_img.convert("RGB").save(output) # تحويل لـ RGB للنشر
        
        with open(output, "rb") as f:
            res = requests.post(FB_PHOTO_URL, 
                                data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, 
                                files={"source": f})
        
        if res.status_code == 200:
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            print("✅ تم النشر!")
            break

if __name__ == "__main__":
    main()
