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
import arabic_reshaper
from bidi.algorithm import get_display
import subprocess

# ============================
# الإعدادات
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "Cairo-Bold.ttf"  # تأكد من وجوده في المستودع

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

def process_text(text):
    # Wand تحتاج أحياناً للتشكيل والعكس لضمان النتيجة 100%
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def main():
    if not FB_URL: return
    
    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        # 1. فتح الخلفية بـ Wand
        with Image(filename="BG.png") as bg:
            # 2. إضافة صورة الخبر
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                img_url = match.group(1)
                r = requests.get(img_url, timeout=10)
                with Image(blob=r.content) as art_img:
                    art_img.resize(855, 460)
                    bg.composite(art_img, left=112, top=185)
            except:
                with Image(filename="logo1.png") as logo:
                    logo.resize(855, 460)
                    bg.composite(logo, left=112, top=185)

            # 3. كتابة النص العربي
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 42
                draw.fill_color = Color('black')
                draw.text_alignment = 'center'
                
                processed_title = process_text(title)
                
                # استخدام خاصية caption لرسم النص داخل مربع محدد تلقائياً
                bg.caption(processed_title, left=110, top=725, 
                           width=850, height=160, font=font, gravity='center')

            bg.save(filename="final.png")

        # 4. النشر (نفس كود النشر السابق)
        with open("final.png", "rb") as f:
            requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        # ... تكملة كود الـ Git log ...
        break

if __name__ == "__main__":
    main()
