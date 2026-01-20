# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
from io import BytesIO
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color
from wand.font import Font
import arabic_reshaper
from bidi.algorithm import get_display
import subprocess

# ============================
# الإعدادات الأساسية
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "Cairo-Bold.ttf" 

# إحداثيات منطقة النص (تعديل حسب تصميم خلفيتك)
CENTER_X = 540  # نصف عرض الصورة 1080
START_Y = 760   # نقطة بداية الكتابة من الأعلى
LINE_HEIGHT = 65 # المسافة بين كل سطر والآخر

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

def split_text_to_lines(text, max_chars=35):
    """تقسيم النص لأسطر يدوياً لضمان سلامة العربي"""
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) <= max_chars:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            # معالجة السطر المكتمل (ربط الحروف وقلب الاتجاه)
            full_line = " ".join(current_line)
            lines.append(get_display(arabic_reshaper.reshape(full_line)))
            current_line = [word]
            current_length = len(word)
            
    if current_line:
        full_line = " ".join(current_line)
        lines.append(get_display(arabic_reshaper.reshape(full_line)))
    
    return lines

def main():
    print("🚀 بدء معالجة الصور بالحل اليدوي...")
    if not FB_URL: return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 معالجة الخبر: {title}")

        with Image(filename="BG.png") as canvas:
            # 1. إضافة صورة الخبر أو اللوجو
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                img_url = match.group(1) if match else ""
                r = requests.get(img_url, timeout=10)
                with Image(blob=r.content) as art_img:
                    # ضبط حجم الصورة لتناسب التصميم
                    art_img.transform(resize='855x460^')
                    art_img.extent(width=855, height=460)
                    canvas.composite(art_img, left=112, top=185)
            except:
                with Image(filename="logo1.png") as logo:
                    logo.resize(855, 460)
                    canvas.composite(logo, left=112, top=185)

            # 2. رسم النص العربي (الحل اليدوي سطر بسطر)
            # نقوم بتقسيم العنوان لأسطر لا تزيد عن 35 حرفاً
            lines_to_draw = split_text_to_lines(title, max_chars=35)
            
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 48
                draw.fill_color = Color('black')
                draw.text_alignment = 'center'
                
                current_y = START_Y
                for line in lines_to_draw:
                    # رسم كل سطر في مكانه المحدد
                    draw.text(x=CENTER_X, y=current_y, body=line)
                    current_y += LINE_HEIGHT # النزول للسطر التالي
                
                draw(canvas)

            # 3. حفظ ونشر
            canvas.format = 'png'
            canvas.save(filename="final.png")

        with open("final.png", "rb") as f:
            res = requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        if res.status_code == 200:
            print("✅ تم النشر!")
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            # أوامر Git لتحديث السجل
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "update log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

if __name__ == "__main__":
    main()
