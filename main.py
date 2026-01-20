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
PADDING = 8  # زيادة بسيطة للمسافة بين الأسطر لجمال التصميم
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
    except:
        pass

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
# رسم النص (RTL صحيح ومُعدل)
# ============================
def wrap_text_rtl(text, draw, font, max_width):
    # الخطوة 1: تشكيل الحروف العربية فقط
    reshaped_text = arabic_reshaper.reshape(text)
    words = reshaped_text.split(" ")
    
    lines = []
    current_line_words = []

    for word in words:
        # اختبار العرض بإضافة الكلمة للسطر الحالي
        test_line = " ".join(current_line_words + [word])
        # استخدام textbbox لحساب العرض الحقيقي
        w = draw.textbbox((0, 0), test_line, font=font)[2]
        
        if w <= max_width:
            current_line_words.append(word)
        else:
            # عندما يمتلئ السطر، نقوم بقلبه (Bidi) وإضافته للقائمة
            if current_line_words:
                line_to_process = " ".join(current_line_words)
                lines.append(get_display(line_to_process))
            current_line_words = [word]

    # إضافة ما تبقى من الكلمات في آخر سطر
    if current_line_words:
        line_to_process = " ".join(current_line_words)
        lines.append(get_display(line_to_process))

    return lines

def fit_text_to_box(text, draw, font_path, max_width, max_height):
    size = START_FONT_SIZE
    while size >= 12:
        font = ImageFont.truetype(font_path, size)
        lines = wrap_text_rtl(text, draw, font, max_width)
        
        # حساب الارتفاع الكلي الفعلي للأسطر المقسمة
        total_height = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_height = bbox[3] - bbox[1]
            total_height += line_height + PADDING
            
        if total_height - PADDING <= max_height:
            return font, lines
        size -= 1
    return ImageFont.truetype(font_path, 12), lines

# ============================
# نشر فيسبوك
# ============================
def post_to_facebook(image_path, title, article, url):
    caption = (
        f"{process_sensitive_text(title)}\n\n"
        f"{process_sensitive_text(' '.join(clean_html(article).split()[:40]))}...\n\n"
        f"{url}"
    )

    with open(image_path, "rb") as img:
        r = requests.post(
            FB_PHOTO_URL,
            data={
                "access_token": PAGE_ACCESS_TOKEN,
                "caption": caption
            },
            files={"source": img}
        )
    return r.status_code == 200

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    now = datetime.now()

    # مسموح من 8 صباحًا إلى 1 صباحًا (اختياري)
    if 1 < now.hour < 8:
        print("⏭ خارج وقت النشر")
        return

    feed = feedparser.parse(RSS_URL)
    posted = load_posted()

    for entry in feed.entries:
        title = clean_html(entry.title)
        summary = clean_html(entry.summary if hasattr(entry, 'summary') else "")

        h = get_hash(title + summary)
        if h in posted:
            continue

        # تجهيز الخلفية
        try:
            bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        except Exception as e:
            print(f"❌ خطأ في تحميل الخلفية: {e}")
            return

        # تحميل صورة المقال
        img_url = get_article_image(entry)
        try:
            r = requests.get(img_url, timeout=10)
            article_img = Image.open(BytesIO(r.content)).convert("RGBA")
        except:
            article_img = Image.open(LOGO_PATH).convert("RGBA")

        # تغيير حجم صورة المقال ووضعها في المنتصف
        article_img = article_img.resize(ARTICLE_IMG_SIZE)
        base_x = (IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2
        bg.paste(article_img, (base_x, ARTICLE_IMG_Y), article_img)

        # رسم النص المعالج
        draw = ImageDraw.Draw(bg)
        processed_title = process_sensitive_text(title)
        
        font, lines = fit_text_to_box(
            processed_title,
            draw,
            FONT_FILE,
            MAX_WIDTH,
            MAX_HEIGHT
        )

        # حساب الارتفاع الكلي لبدء الرسم من المنتصف الرأسي للبوكس أو من الأعلى
        total_lines_height = sum([draw.textbbox((0, 0), l, font=font)[3] - draw.textbbox((0, 0), l, font=font)[1] for l in lines]) + (len(lines)-1)*PADDING
        y = TOP_Y + (MAX_HEIGHT - total_lines_height) // 2 # للتوسيط الرأسي داخل المنطقة المحددة

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            
            x = LEFT_X + (MAX_WIDTH - w) // 2 # توسيط أفقي
            draw.text((x, y), line, font=font, fill="black")
            y += line_h + PADDING

        output = f"output_{h}.png"
        bg.save(output)

        # محاولة النشر
        if post_to_facebook(output, title, summary, entry.link):
            save_posted(h)
            git_commit()
            print(f"✅ تم النشر بنجاح: {title}")
            # حذف الصورة بعد النشر لتوفير المساحة
            if os.path.exists(output): os.remove(output)
            break
        else:
            print(f"❌ فشل النشر على فيسبوك.")

# ============================
if __name__ == "__main__":
    main()
