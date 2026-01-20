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

# إحداثيات منطقة الكتابة (المربع الأبيض السفلي)
LEFT_X = 110
RIGHT_X = 960
TOP_Y = 725
BOTTOM_Y = 885
PADDING = 10 
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

# ============================
# فيسبوك وGitHub (من Secrets)
# ============================
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة النصوص الحساسة
# ============================
SEPARATORS = ["•", "|", "*", "•", "ـ", "-", "!", "^"]
SENSITIVE_WORDS = [
    "قتل","جريمة","ذبح","جثة","دم","دماء","اغتصاب","تعذيب","طعن","تفجير","انتحار",
    "اشترك","الآن","اضغط","شاهد","فرصة","اربح","مجانا","عرض"
]

def split_sensitive_word(word):
    if word in SENSITIVE_WORDS:
        pos = 2 if len(word) >= 3 else 1
        return word[:pos] + random.choice(SEPARATORS) + word[pos:]
    return word

def process_sensitive_text(text):
    if not text: return ""
    return " ".join(split_sensitive_word(w) for w in text.split())

# ============================
# أدوات مساعدة للبيانات
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
        subprocess.run(["git", "commit", "-m", "Update posted articles"], check=False)
        subprocess.run(["git", "push"], check=False)
    except: pass

def get_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def clean_html(text):
    if not text: return ""
    return re.sub("<.*?>", "", text).strip()

def get_article_image(entry):
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url")
    html = entry.summary if hasattr(entry, "summary") else ""
    match = re.search(r'<img[^>]+src="([^">]+)"', html)
    return match.group(1) if match else None

# ============================
# معالجة الرسم والكتابة (الحل الصحيح)
# ============================
def wrap_text_rtl(text, draw, font, max_width):
    # 1. تشكيل الحروف العربية أولاً (Reshape)
    reshaped_text = arabic_reshaper.reshape(text)
    words = reshaped_text.split()
    
    lines = []
    current_line_words = []

    for word in words:
        # اختبار إضافة كلمة للسطر
        test_line = " ".join(current_line_words + [word])
        w = draw.textbbox((0, 0), test_line, font=font)[2]
        
        if w <= max_width:
            current_line_words.append(word)
        else:
            # السطر اكتمل، نقوم بقلبه (Bidi) الآن ليظهر عربياً صحيحاً
            if current_line_words:
                line_to_process = " ".join(current_line_words)
                lines.append(get_display(line_to_process))
            current_line_words = [word]

    # إضافة آخر سطر
    if current_line_words:
        line_to_process = " ".join(current_line_words)
        lines.append(get_display(line_to_process))

    return lines

def fit_text_to_box(text, draw, font_path, max_width, max_height):
    size = START_FONT_SIZE
    while size >= 14:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_rtl(text, draw, font, max_width)
        
        # حساب الارتفاع الكلي الفعلي
        total_h = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            total_h += (bbox[3] - bbox[1]) + PADDING
            
        if total_h - PADDING <= max_height:
            return font, lines
        size -= 1
    return ImageFont.truetype(font_path, 14), lines

# ============================
# وظائف النشر
# ============================
def post_to_facebook(image_path, title, article_text, url):
    caption = (
        f"{process_sensitive_text(title)}\n\n"
        f"{process_sensitive_text(' '.join(clean_html(article_text).split()[:35]))}...\n\n"
        f"التفاصيل: {url}"
    )
    try:
        with open(image_path, "rb") as img:
            r = requests.post(
                FB_PHOTO_URL,
                data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption},
                files={"source": img}
            )
        return r.status_code == 200
    except: return False

# ============================
# التشغيل الرئيسي
# ============================
def main():
    now = datetime.now()
    if 1 < now.hour < 7: # التوقف وقت الفجر
        print("⏭ خارج وقت النشر")
        return

    feed = feedparser.parse(RSS_URL)
    posted = load_posted()

    for entry in feed.entries:
        title = clean_html(entry.title)
        summary = clean_html(entry.summary if hasattr(entry, 'summary') else "")
        h = get_hash(title)

        if h in posted: continue

        # 1. إنشاء صورة الخلفية
        try:
            bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        except: 
            print("❌ ملف الخلفية BG.png غير موجود"); return

        # 2. جلب صورة الخبر
        img_url = get_article_image(entry)
        try:
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        # 3. دمج صورة الخبر في التصميم
        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        bg.paste(article_img, ((IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2, ARTICLE_IMG_Y), article_img)

        # 4. معالجة ورسم النص
        draw = ImageDraw.Draw(bg)
        final_title = process_sensitive_text(title)
        font, lines = fit_text_to_box(final_title, draw, FONT_FILE, MAX_WIDTH, MAX_HEIGHT)

        # حساب التوسيط الرأسي
        total_text_h = sum([draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]) + (len(lines)-1)*PADDING
        y_cursor = TOP_Y + (MAX_HEIGHT - total_text_h) // 2

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            # رسم النص في المنتصف الأفقي
            draw.text((LEFT_X + (MAX_WIDTH - line_w) // 2, y_cursor), line, font=font, fill="black")
            y_cursor += line_h + PADDING

        # 5. الحفظ والنشر
        output = f"post_{h}.png"
        bg.save(output)
        
        if post_to_facebook(output, title, summary, entry.link):
            save_posted(h)
            git_commit()
            print(f"✅ تم نشر: {title}")
            if os.path.exists(output): os.remove(output)
            break # نشر خبر واحد في كل دورة تشغيل

if __name__ == "__main__":
    main()
