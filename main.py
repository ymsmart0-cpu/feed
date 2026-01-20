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
START_FONT_SIZE = 45 # تم زيادة الحجم قليلاً لوضوح أفضل

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

# ============================
# فيسبوك (قراءة آمنة)
# ============================
PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None

POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة الكلمات الحساسة
# ============================
SEPARATORS = ["$", "&", "%", "*", "|", "•", "=", "!", "؟"]
SENSITIVE_WORDS = ["قتل","جريمة","ذبح","جثة","دم","دماء","اغتصاب","تعذيب","طعن","انتحار","اشترك","الآن"]

def process_sensitive_text(text):
    if not text: return ""
    words = text.split()
    new_words = []
    for word in words:
        if word in SENSITIVE_WORDS:
            pos = 2 if len(word) >= 3 else 1
            word = word[:pos] + random.choice(SEPARATORS) + word[pos:]
        new_words.append(word)
    return " ".join(new_words)

# ============================
# أدوات Git والملفات
# ============================
def load_posted():
    if not os.path.exists(POSTED_FILE): return set()
    with open(POSTED_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_posted(hash_id):
    with open(POSTED_FILE, "a", encoding="utf-8") as f:
        f.write(hash_id + "\n")

def git_commit():
    try:
        subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Bot"])
        subprocess.run(["git", "add", POSTED_FILE])
        subprocess.run(["git", "commit", "-m", "Update logs"], check=False)
        subprocess.run(["git", "push"], check=False)
    except: pass

# ============================
# دوال معالجة النص العربي (إصلاح الـ RTL)
# ============================
def prepare_arabic_display(text):
    # الخطوة 1: إعادة تشكيل الحروف لتتصل ببعضها (Reshaping)
    reshaped_text = arabic_reshaper.reshape(text)
    # الخطوة 2: قلب النص ليعرض من اليمين لليسار (Bidi)
    bidi_text = get_display(reshaped_text)
    return bidi_text

def wrap_text_arabic(text, draw, font, max_width):
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        # نجرب إضافة الكلمة للسطر الحالي
        test_line = " ".join(current_line + [word])
        # نحتاج تشكيل النص قبل قياس عرضه
        display_line = prepare_arabic_display(test_line)
        w = draw.textbbox((0, 0), display_line, font=font)[2]
        
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    # تحويل كل سطر للعرض العربي الصحيح
    return [prepare_arabic_display(line) for line in lines]

def fit_text_to_box(text, draw, font_path, max_width, max_height):
    size = START_FONT_SIZE
    while size >= 18:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_arabic(text, draw, font, max_width)
        # حساب الارتفاع الكلي
        total_h = sum(draw.textbbox((0, 0), line, font=font)[3] for line in lines) + (len(lines) * PADDING)
        if total_h <= max_height:
            return font, lines
        size -= 2
    return ImageFont.truetype(font_path, 18), wrap_text_arabic(text, draw, font, max_width)

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    if not FB_PHOTO_URL or "None" in FB_PHOTO_URL:
        print("❌ خطأ: PAGE_ID غير معرف في Secrets")
        return

    feed = feedparser.parse(RSS_URL)
    posted = load_posted()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        
        if h in posted: continue

        print(f"🔄 جاري معالجة: {title[:50]}...")
        
        # إنشاء التصميم
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        
        # جلب الصورة
        img_url = None
        if hasattr(entry, "media_content"): img_url = entry.media_content[0].get("url")
        if not img_url:
            match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
            img_url = match.group(1) if match else None

        try:
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        # دمج صورة المقال
        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        bg.paste(article_img, ((IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2, ARTICLE_IMG_Y), article_img)

        # رسم النص
        draw = ImageDraw.Draw(bg)
        processed_title = process_sensitive_text(title)
        font, lines = fit_text_to_box(processed_title, draw, FONT_FILE, MAX_WIDTH, MAX_HEIGHT)

        # حساب البداية لتوسيط النص عمودياً
        total_text_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) + (len(lines)-1)*PADDING
        current_y = TOP_Y + (MAX_HEIGHT - total_text_h) // 2

        for line in lines:
            w = draw.textbbox((0, 0), line, font=font)[2]
            x = LEFT_X + (MAX_WIDTH - w) // 2
            draw.text((x, current_y), line, font=font, fill="black")
            current_y += draw.textbbox((0, 0), line, font=font)[3] + PADDING

        # حفظ ونشر
        output = "final_post.png"
        bg.save(output)
        
        caption = f"{processed_title}\n\nالتفاصيل: {entry.link}"
        with open(output, "rb") as img_file:
            res = requests.post(FB_PHOTO_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption}, files={"source": img_file})
            
        if res.status_code == 200:
            save_posted(h)
            git_commit()
            print("✅ تم النشر بنجاح!")
            break
        else:
            print(f"❌ فشل: {res.text}")

if __name__ == "__main__":
    main()
