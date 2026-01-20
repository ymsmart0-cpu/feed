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
# الإعدادات
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "Cairo-Bold.ttf"  # التأكد من مطابقة الاسم تماماً
START_FONT_SIZE = 40

BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

IMAGE_WIDTH, IMAGE_HEIGHT = 1080, 1080
ARTICLE_IMG_SIZE = (855, 460)
ARTICLE_IMG_Y = 185

# إحداثيات صندوق النص (المستطيل الأبيض في الأسفل)
LEFT_X, RIGHT_X = 110, 960
TOP_Y, BOTTOM_Y = 725, 885
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y
PADDING = 10

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة النصوص (الحل الجذري)
# ============================

def process_line_arabic(text):
    """ربط الحروف وقلب الاتجاه لسطر واحد"""
    if not text: return ""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def wrap_text_logical(text, draw, font, max_width):
    """تقسيم النص لأسطر وهو نص عادي (قبل القلب) لضمان الترتيب"""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # نقيس العرض بعد المعالجة المؤقتة للتجربة
        w = draw.textbbox((0, 0), process_line_arabic(test_line), font=font)[2]
        
        if w <= max_width:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    # الآن نعالج كل سطر نهائياً (ربط حروف وقلب اتجاه)
    return [process_line_arabic(line) for line in lines]

# ============================
# وظائف الرسم والنشر
# ============================

def draw_text_on_image(image, title):
    draw = ImageDraw.Draw(image)
    
    # التأكد من وجود الخط
    if not os.path.exists(FONT_FILE):
        print(f"❌ خطأ: لم يتم العثور على {FONT_FILE}")
        return image

    font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE)
    
    # 1. تقسيم النص (Logical Wrap) ثم المعالجة (Reshape & Bidi)
    processed_lines = wrap_text_logical(title, draw, font, MAX_WIDTH)
    
    # 2. حساب الارتفاع الكلي للتوسيط العمودي
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in processed_lines) + (len(processed_lines)-1)*PADDING
    current_y = TOP_Y + (MAX_HEIGHT - total_h) // 2

    # 3. رسم الأسطر
    for line in processed_lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        x = LEFT_X + (MAX_WIDTH - w) // 2  # توسيط أفقي
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING
        
    return image

def main():
    if not FB_URL: return
    
    feed = feedparser.parse(RSS_URL)
    posted = set()
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            posted = set(f.read().splitlines())

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 جاري المعالجة: {title[:50]}...")
        
        # إنشاء الصورة
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        
        # جلب صورة المقال
        try:
            img_url = None
            if hasattr(entry, 'media_content'): img_url = entry.media_content[0]['url']
            elif 'summary' in entry:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match: img_url = match.group(1)
            
            if img_url:
                r = requests.get(img_url, timeout=10)
                art_img = Image.open(BytesIO(r.content)).convert("RGBA")
            else:
                art_img = Image.open(LOGO_PATH).convert("RGBA")
        except:
            art_img = Image.open(LOGO_PATH).convert("RGBA")

        art_img = art_img.resize(ARTICLE_IMG_SIZE)
        bg.paste(art_img, ((IMAGE_WIDTH - ARTICLE_IMG_SIZE[0]) // 2, ARTICLE_IMG_Y), art_img)

        # رسم النص العربي المصلح
        final_image = draw_text_on_image(bg, title)
        
        # حفظ ونشر
        output = "final.png"
        final_image.convert("RGB").save(output)
        
        with open(output, "rb") as f:
            res = requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        if res.status_code == 200:
            with open(POSTED_FILE, "a", encoding="utf-8") as f: f.write(h + "\n")
            print("✅ تم النشر!")
            # تحديث Git
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "Update log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

if __name__ == "__main__":
    main()
