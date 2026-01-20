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
# الإعدادات
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "Cairo-Bold.ttf" 

# إحداثيات الصندوق النصي
TEXT_BOX_X = 540 # المركز الأفقي للتوسيط
TEXT_BOX_Y_START = 750 # نقطة البداية الرأسية
LINE_HEIGHT = 60 # المسافة بين الأسطر
MAX_CHARS_PER_LINE = 40 # عدد الحروف التقريبي في السطر

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

def wrap_and_fix_arabic(text):
    """تقسيم النص لأسطر ومعالجته عربياً بشكل سليم"""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) <= MAX_CHARS_PER_LINE:
            current_line += word + " "
        else:
            lines.append(get_display(arabic_reshaper.reshape(current_line.strip())))
            current_line = word + " "
    if current_line:
        lines.append(get_display(arabic_reshaper.reshape(current_line.strip())))
    
    return lines

def main():
    print("🚀 تشغيل المحرك العربي لـ Wand...")
    if not FB_URL: return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 معالجة الخبر: {title[:50]}...")

        with Image(filename="BG.png") as canvas:
            # 1. دمج صورة الخبر (أو اللوجو)
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                img_url = match.group(1) if match else ""
                r = requests.get(img_url, timeout=10)
                with Image(blob=r.content) as art_img:
                    art_img.transform(resize='855x460^')
                    art_img.extent(width=855, height=460)
                    canvas.composite(art_img, left=112, top=185)
            except:
                with Image(filename="logo1.png") as logo:
                    logo.resize(855, 460)
                    canvas.composite(logo, left=112, top=185)

            # 2. رسم النص العربي يدوياً (الحل هنا)
            processed_lines = wrap_and_fix_arabic(title)
            
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 45
                draw.fill_color = Color('black')
                draw.text_alignment = 'center' # التوسيط من المركز
                
                current_y = TEXT_BOX_Y_START
                for line in processed_lines:
                    # نرسم السطر في إحداثيات X المركزية
                    draw.text(x=int(TEXT_BOX_X), y=int(current_y), body=line)
                    current_y += LINE_HEIGHT
                
                draw(canvas) # تطبيق الرسم على الصورة

            canvas.format = 'png'
            canvas.save(filename="final.png")

        # 3. النشر على فيسبوك
        with open("final.png", "rb") as f:
            res = requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        if res.status_code == 200:
            print("✅ تم النشر بنجاح!")
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "update log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

if __name__ == "__main__":
    main()
