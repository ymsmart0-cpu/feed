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
FONT_FILE = "Cairo-Bold.ttf"  # تأكد من وجود الملف في المستودع بنفس الاسم

# إحداثيات ومقاسات (نفس التي كنت تستخدمها في Pillow)
IMAGE_SIZE = (1080, 1080)
ARTICLE_IMG_SIZE = (855, 460)
ARTICLE_IMG_POS = (112, 185)

# منطقة النص
TEXT_BOX = {'left': 110, 'top': 725, 'width': 850, 'height': 160}

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

def fix_arabic(text):
    """إصلاح النص العربي ليناسب الرسم برمجياً"""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def main():
    print("🚀 بدء العمل باستخدام Wand...")
    
    if not FB_URL:
        print("❌ خطأ في الإعدادات")
        return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 معالجة الخبر: {title[:50]}...")

        # 1. فتح الخلفية
        with Image(filename="BG.png") as canvas:
            canvas.resize(*IMAGE_SIZE)

            # 2. إضافة صورة الخبر
            try:
                img_url = ""
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    r = requests.get(match.group(1), timeout=10)
                    with Image(blob=r.content) as art_img:
                        art_img.resize(*ARTICLE_IMG_SIZE)
                        canvas.composite(art_img, left=ARTICLE_IMG_POS[0], top=ARTICLE_IMG_POS[1])
            except Exception as e:
                print(f"⚠️ فشل جلب صورة الخبر، سيتم استخدام اللوجو: {e}")
                with Image(filename="logo1.png") as logo:
                    logo.resize(*ARTICLE_IMG_SIZE)
                    canvas.composite(logo, left=ARTICLE_IMG_POS[0], top=ARTICLE_IMG_POS[1])

            # 3. كتابة النص العربي باستخدام Wand
            processed_text = fix_arabic(title)
            
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 45
                draw.fill_color = Color('black')
                draw.text_alignment = 'center'
                # رسم النص داخل المساحة المحددة مع توزيع الأسطر تلقائياً
                canvas.caption(processed_text, 
                               left=TEXT_BOX['left'], 
                               top=TEXT_BOX['top'], 
                               width=TEXT_BOX['width'], 
                               height=TEXT_BOX['height'], 
                               font=draw.font, 
                               gravity='center')

            # 4. الحفظ
            canvas.format = 'png'
            canvas.save(filename="final.png")

        # 5. النشر على فيسبوك
        with open("final.png", "rb") as f:
            res = requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        if res.status_code == 200:
            print("✅ تم النشر!")
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            
            # تحديث GitHub
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "update log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

if __name__ == "__main__":
    main()
