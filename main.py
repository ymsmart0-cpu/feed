# -*- coding: utf-8 -*-
import feedparser
import requests
import time
import hashlib
import os
import re
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import arabic_reshaper
from bidi.algorithm import get_display

# ============================
# الإعدادات (تأكد من وضع قيمك هنا)
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "29ltbukrabolditalic.otf"
START_FONT_SIZE = 40
BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

IMAGE_WIDTH, IMAGE_HEIGHT = 1080, 1080
ARTICLE_IMG_SIZE = (855, 460)
ARTICLE_IMG_Y = 185

# إحداثيات مربع النص (من الكود الثاني)
LEFT_X, RIGHT_X = 110, 960
TOP_Y, BOTTOM_Y = 725, 885
PADDING = 5
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

PAGE_ID = "YOUR_PAGE_ID"
PAGE_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"
POSTED_FILE = "posted_articles.txt"

SENSITIVE_WORDS = ["قتل","جريمة","ذبح","جثة","دم","اشترك","الآن","اربح"] # أضف ما تشاء
SEPARATORS = ["$", "&", "*", "|", "•", "="]

# ============================
# معالجة النصوص (طريقة الكود الثاني)
# ============================
def split_sensitive_word(word):
    if word in SENSITIVE_WORDS:
        pos = 2 if len(word) >= 3 else 1
        return word[:pos] + random.choice(SEPARATORS) + word[pos:]
    return word

def process_sensitive_text(text):
    return " ".join(split_sensitive_word(w) for w in text.split())

def wrap_text_rtl(text, draw, font, max_width):
    reshaped = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped)
    words = bidi_text.split(" ")
    lines, current = [], ""
    for word in words:
        test = word if not current else current + " " + word
        w = draw.textbbox((0, 0), test, font=font)[2]
        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word
    if current: lines.append(current)
    return lines

def fit_text_to_box(text, draw, font_path, max_width, max_height):
    size = START_FONT_SIZE
    while size >= 12:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_rtl(text, draw, font, max_width)
        # حساب الارتفاع الكلي للأسطر
        total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) + (len(lines) * PADDING)
        if total_h <= max_height:
            return font, lines
        size -= 1
    return ImageFont.truetype(font_path, size), lines

def draw_text_box(draw, lines, font):
    # حساب الارتفاع الكلي للكتلة النصية لتوسيطها رأسياً إذا أردت
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines)
    current_y = TOP_Y + (MAX_HEIGHT - total_h) // 2 # توسيط رأسي داخل المربع
    
    for line in lines: # الكود الثاني لا يستخدم reversed هنا لضمان ترتيب القراءة
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        x = LEFT_X + (MAX_WIDTH - w) // 2 # توسيط أفقي
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING

# ============================
# العمليات الرئيسية
# ============================
def main():
    feed = feedparser.parse(RSS_URL)
    if not os.path.exists(POSTED_FILE): open(POSTED_FILE, "w").close()
    with open(POSTED_FILE, "r") as f: posted = set(f.read().splitlines())

    for entry in feed.entries[:7]:
        title = entry.title
        h = hashlib.md5((title).encode()).hexdigest()
        if h in posted: continue

        # إنشاء الصورة
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        
        # جلب صورة المقال ومعالجتها (طريقة الظل من الكود الثاني)
        try:
            img_url = re.search(r'<img[^>]+src="([^">]+)"', entry.summary).group(1)
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA").resize(ARTICLE_IMG_SIZE)
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA").resize(ARTICLE_IMG_SIZE)

        # إضافة الظل (Drop Shadow) كما في الكود الثاني
        shadow = Image.new("RGBA", (ARTICLE_IMG_SIZE[0]+20, ARTICLE_IMG_SIZE[1]+20), (0,0,0,0))
        sh_draw = ImageDraw.Draw(shadow)
        sh_draw.rectangle([10, 10, ARTICLE_IMG_SIZE[0]+10, ARTICLE_IMG_SIZE[1]+10], fill=(0,0,0,45))
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        
        bg.paste(shadow, ((IMAGE_WIDTH-ARTICLE_IMG_SIZE[0])//2 - 10, ARTICLE_IMG_Y - 4), shadow)
        bg.paste(article_img, ((IMAGE_WIDTH-ARTICLE_IMG_SIZE[0])//2, ARTICLE_IMG_Y), article_img)

        # كتابة النص (الطريقة المطلوبة)
        draw = ImageDraw.Draw(bg)
        safe_title = process_sensitive_text(title)
        font, lines = fit_text_to_box(safe_title, draw, FONT_FILE, MAX_WIDTH, MAX_HEIGHT)
        draw_text_box(draw, lines, font)

        # حفظ ونشر
        out = f"post_{h}.png"
        bg.save(out)
        print(f"✅ تم تجهيز الصورة: {title}")
        # هنا تضع دالة النشر لفيسبوك...
        
        break # نشر واحد ثم توقف

if __name__ == "__main__":
    main()
