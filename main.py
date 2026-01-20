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
# الإعدادات الأساسية
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
# تأكد أن هذا الاسم مطابق تماماً للملف الموجود في GitHub
FONT_FILE = "Cairo-Bold.ttf" 
START_FONT_SIZE = 40

BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

# إحداثيات الصندوق النصي (المستطيل الأبيض)
LEFT_X, RIGHT_X = 110, 960
TOP_Y, BOTTOM_Y = 725, 885
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y
PADDING = 12

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة النصوص (الحل الجذري)
# ============================

def process_arabic_final(text):
    """ربط الحروف وقلب الاتجاه لسطر واحد فقط"""
    if not text: return ""
    # 1. ربط الحروف (بـ، ـبـ، ـب)
    reshaped = arabic_reshaper.reshape(text)
    # 2. قلب الاتجاه (RTL)
    return get_display(reshaped)

def wrap_text_correctly(text, draw, font, max_width):
    """تقسيم النص لأسطر وهو نص عادي لضمان ترتيب الكلمات"""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # نقيس العرض باستخدام المعالجة المؤقتة
        w = draw.textbbox((0, 0), process_arabic_final(test_line), font=font)[2]
        
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    # تحويل كل سطر نهائياً للعرض العربي
    return [process_arabic_final(line) for line in lines]

# ============================
# وظيفة الرسم
# ============================

def create_post_image(title, entry):
    # فتح الخلفية
    bg = Image.open(BG_PATH).convert("RGBA").resize((1080, 1080))
    
    # جلب صورة المقال
    try:
        img_url = None
        html = entry.summary if hasattr(entry, 'summary') else ""
        match = re.search(r'<img[^>]+src="([^">]+)"', html)
        img_url = match.group(1) if match else None
        
        if img_url:
            r = requests.get(img_url, timeout=10)
            art_img = Image.open(BytesIO(r.content)).convert("RGBA")
        else:
            art_img = Image.open(LOGO_PATH).convert("RGBA")
    except:
        art_img = Image.open(LOGO_PATH).convert("RGBA")

    # دمج صورة المقال
    art_img = art_img.resize((855, 460))
    bg.paste(art_img, ((1080 - 855) // 2, 185), art_img)

    # رسم النص
    draw = ImageDraw.Draw(bg)
    
    # التحقق من وجود الخط
    if not os.path.exists(FONT_FILE):
        print(f"❌ خطأ حرج: ملف الخط {FONT_FILE} غير موجود!")
        return None

    font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE)
    processed_lines = wrap_text_correctly(title, draw, font, MAX_WIDTH)
    
    # حساب التوسيط العمودي
    total_h = sum(draw.textbbox((0, 0), l, font=font)[3] for l in processed_lines) + (len(processed_lines)-1)*PADDING
    y = TOP_Y + (MAX_HEIGHT - total_h) // 2

    for line in processed_lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        x = LEFT_X + (MAX_WIDTH - w) // 2
        draw.text((x, y), line, font=font, fill="black")
        y += h + PADDING
        
    return bg

def main():
    if not FB_URL or "None" in FB_URL:
        print("❌ خطأ: لم يتم ضبط PAGE_ID في Secrets")
        return
    
    feed = feedparser.parse(RSS_URL)
    posted = set()
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            posted = set(f.read().splitlines())

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 جاري معالجة: {title[:50]}...")
        
        final_img = create_post_image(title, entry)
        if final_img is None: break

        output = "final.png"
        final_img.convert("RGB").save(output)
        
        with open(output, "rb") as f:
            res = requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        if res.status_code == 200:
            with open(POSTED_FILE, "a", encoding="utf-8") as f: f.write(h + "\n")
            print("✅ تم النشر!")
            # تحديث الـ Log في GitHub
            subprocess.run(["git", "config", "--global", user.email "bot@github.com"])
            subprocess.run(["git", "config", "--global", user.name "Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "Update log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

if __name__ == "__main__":
    main()
