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
PADDING = 8
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

# ============================
# فيسبوك (من Secrets)
# ============================
PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

# ============================
# منع التكرار
# ============================
POSTED_FILE = "posted_articles.txt"

# ============================
# كلمات حساسة
# ============================
SEPARATORS = ["$", "&", "%", "*", "~", "+", "|", "•", "=", "^", ":", "!"]

SENSITIVE_WORDS = [
    "اشترك","الآن","اضغط","شاهد","فرصة","اربح","مجانا","عرض","تفوت","الفرصة",
    "قتل","جريمة","ذبح","جثة","دم","دماء","اغتصاب","تعذيب","طعن","تفجير","انتحار"
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
# أدوات مساعدة
# ============================
def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
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
    except Exception as e:
        print(f"⚠️ Git error: {e}")

def get_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def clean_html(text):
    if not text: return ""
    return re.sub("<.*?>", "", text)

# ============================
# صورة المقال
# ============================
def get_article_image(entry):
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url")
    html = entry.summary if hasattr(entry, "summary") else ""
    match = re.search(r'<img[^>]+src="([^">]+)"', html)
    return match.group(1) if match else None

# ============================
# دوال تنسيق ورسم النصوص (الجديدة)
# ============================
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
    if current:
        lines.append(current)
    return lines

def fit_text_to_box(text, draw, font_path, max_width, max_height):
    size = START_FONT_SIZE
    font = ImageFont.truetype(font_path, size)
    while size >= 14:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_rtl(text, draw, font, max_width)
        total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in lines) + (len(lines) * PADDING)
        if total_h <= max_height:
            return font, lines
        size -= 2
    return font, lines

def draw_text_box(draw, lines, font):
    # حساب إجمالي الارتفاع لتوسيط الكتلة النصية عمودياً
    line_heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
    total_text_h = sum(line_heights) + (len(lines) - 1) * PADDING
    
    start_y = TOP_Y + (MAX_HEIGHT - total_text_h) // 2
    
    current_y = start_y
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        x = LEFT_X + (MAX_WIDTH - w) // 2
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING

# ============================
# نشر فيسبوك (مع تشخيص الأخطاء)
# ============================
def post_to_facebook(image_path, title, article, url):
    caption = (
        f"{process_sensitive_text(title)}\n\n"
        f"{process_sensitive_text(' '.join(article.split()[:40]))}...\n\n"
        f"التفاصيل: {url}"
    )

    try:
        with open(image_path, "rb") as img:
            payload = {"access_token": PAGE_ACCESS_TOKEN, "caption": caption}
            files = {"source": img}
            r = requests.post(FB_PHOTO_URL, data=payload, files=files)
            
            if r.status_code == 200:
                return True
            else:
                print(f"❌ فشل النشر. كود الخطأ: {r.status_code}")
                print(f"❌ رسالة فيسبوك: {r.text}")
                return False
    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بفيسبوك: {e}")
        return False

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    now = datetime.now()
    if 1 < now.hour < 8:
        print("⏭ خارج وقت النشر المسموح (حالياً فترة توقف)")
        return

    feed = feedparser.parse(RSS_URL)
    posted = load_posted()
    
    # محاولة نشر مقال واحد جديد فقط في كل دورة تشغيل
    for entry in feed.entries:
        title = clean_html(entry.title)
        text = clean_html(entry.summary)
        h = get_hash(title + text)

        if h in posted:
            continue

        print(f"🔄 جاري معالجة: {title[:50]}...")

        # تجهيز الصورة الأساسية
        if not os.path.exists(BG_PATH):
            print(f"❌ خطأ: ملف الخلفية {BG_PATH} غير موجود!")
            return

        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        img_url = get_article_image(entry)

        try:
            r = requests.get(img_url, timeout=15)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            print("⚠️ تعذر جلب صورة المقال، سيتم استخدام اللوجو.")
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        # دمج صورة المقال
        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        base_x = (IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2
        bg.paste(article_img, (base_x, ARTICLE_IMG_Y), article_img)

        # رسم النص
        draw = ImageDraw.Draw(bg)
        processed_title = process_sensitive_text(title)
        
        if not os.path.exists(FONT_FILE):
            print(f"❌ خطأ: ملف الخط {FONT_FILE} غير موجود!")
            return

        font, lines = fit_text_to_box(processed_title, draw, FONT_FILE, MAX_WIDTH, MAX_HEIGHT)
        draw_text_box(draw, lines, font)

        # حفظ وإرسال
        output_file = f"temp_post.png"
        bg.save(output_file)

        if post_to_facebook(output_file, title, text, entry.link):
            save_posted(h)
            git_commit()
            print("✅ تم النشر بنجاح على فيسبوك.")
            if os.path.exists(output_file):
                os.remove(output_file)
            break # توقف بعد نشر مقال واحد لتجنب الحظر
        else:
            if os.path.exists(output_file):
                os.remove(output_file)

# ============================
if __name__ == "__main__":
    main()
