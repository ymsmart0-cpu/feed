# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
from io import BytesIO
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import arabic_reshaper
from bidi.algorithm import get_display
import random
import subprocess

# ============================
# إعدادات عامة
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "29ltbukrabolditalic.otf"
START_FONT_SIZE = 40
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
PADDING = 12 
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

# ============================
# دوال معالجة النصوص (إصلاح اتجاه اليمين لليسار)
# ============================

def wrap_text_rtl(text, draw, font, max_width):
    """
    تقسم النص لأسطر مع الحفاظ على الترتيب من اليمين لليسار.
    """
    # 1. تقسيم النص لكلمات خام (الترتيب طبيعي هنا)
    words = text.split()
    lines = []
    current_line_words = []

    for word in words:
        # اختبار طول السطر بإضافة الكلمة (مع تشكيل مؤقت للقياس)
        test_line = " ".join(current_line_words + [word])
        reshaped_test = arabic_reshaper.reshape(test_line)
        display_test = get_display(reshaped_test)
        
        w = draw.textbbox((0, 0), display_test, font=font)[2]
        
        if w <= max_width:
            current_line_words.append(word)
        else:
            # السطر اكتمل: تشكيله وقلبه ليصبح RTL صحيحاً
            if current_line_words:
                full_line = " ".join(current_line_words)
                reshaped_line = arabic_reshaper.reshape(full_line)
                lines.append(get_display(reshaped_line))
            current_line_words = [word]

    # إضافة السطر الأخير
    if current_line_words:
        full_line = " ".join(current_line_words)
        reshaped_line = arabic_reshaper.reshape(full_line)
        lines.append(get_display(reshaped_line))

    return lines

def fit_text_to_box(text, draw, font_path, max_width, max_height):
    size = START_FONT_SIZE
    while size >= 14:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_rtl(text, draw, font, max_width)
        
        # حساب الارتفاع الكلي الفعلي
        total_h = sum([draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]) + (len(lines)-1)*PADDING
            
        if total_h <= max_height:
            return font, lines
        size -= 1
    return ImageFont.truetype(font_path, 14), lines

# ============================
# بقية وظائف النظام
# ============================

def clean_html(text):
    return re.sub("<.*?>", "", text).strip() if text else ""

def get_article_image(entry):
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url")
    html = entry.summary if hasattr(entry, "summary") else ""
    match = re.search(r'<img[^>]+src="([^">]+)"', html)
    return match.group(1) if match else None

def main():
    PAGE_ID = os.getenv("PAGE_ID")
    PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
    FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
    POSTED_FILE = "posted_articles.txt"

    feed = feedparser.parse(RSS_URL)
    if not os.path.exists(POSTED_FILE): open(POSTED_FILE, "w").close()
    with open(POSTED_FILE, "r") as f: posted_hashes = f.read().splitlines()

    for entry in feed.entries:
        title = clean_html(entry.title)
        h = hashlib.md5(title.encode()).hexdigest()
        if h in posted_hashes: continue

        try:
            bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
            draw = ImageDraw.Draw(bg)
        except: print("❌ خطأ: ملف BG.png مفقود"); break

        img_url = get_article_image(entry)
        try:
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        bg.paste(article_img, ((IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2, ARTICLE_IMG_Y), article_img)

        # تجهيز الخط والأسطر (الأسطر الآن مخزنة في مصفوفة lines مقلوبة وجاهزة للرسم)
        font, lines = fit_text_to_box(title, draw, FONT_FILE, MAX_WIDTH, MAX_HEIGHT)
        
        # حساب التوسيط الرأسي في المربع الأبيض السفلي
        total_text_h = sum([draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]) + (len(lines)-1)*PADDING
        y_cursor = TOP_Y + (MAX_HEIGHT - total_text_h) // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            
            # رسم السطر في المنتصف الأفقي (سيظهر من اليمين لليسار لأننا استخدمنا get_display داخل الدالة)
            draw.text((LEFT_X + (MAX_WIDTH - line_w) // 2, y_cursor), line, font=font, fill="black")
            y_cursor += line_h + PADDING

        output = f"post_{h}.png"
        bg.save(output)
        
        with open(output, "rb") as img_file:
            res = requests.post(FB_PHOTO_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": img_file})
            
        if res.status_code == 200:
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            print(f"✅ تم النشر بنجاح: {title}")
            break 

if __name__ == "__main__":
    main()
