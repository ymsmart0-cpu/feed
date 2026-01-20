# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
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
# استخدام الخط الجديد الذي حددته
FONT_FILE = "29ltbukrabolditalic.otf" 

# إحداثيات الرسم (تأكد أن المسارات صحيحة في مستودعك)
CENTER_X = 540
START_Y = 780 
LINE_HEIGHT = 75

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

def process_arabic_title(text, max_chars=35):
    """تقسيم النص لأسطر ومعالجته لضمان اتصال الحروف وعدم اختفائها"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        if len(test_line) <= max_chars:
            current_line.append(word)
        else:
            if current_line:
                # معالجة السطر: تشكيل (Reshape) ثم ضبط الاتجاه (Bidi)
                reshaped = arabic_reshaper.reshape(" ".join(current_line))
                lines.append(get_display(reshaped))
            current_line = [word]
            
    if current_line:
        reshaped = arabic_reshaper.reshape(" ".join(current_line))
        lines.append(get_display(reshaped))
    return lines

def main():
    print(f"🚀 بدء المحرك باستخدام الخط: {FONT_FILE}")
    if not FB_URL:
        print("❌ خطأ: لم يتم العثور على صلاحيات فيسبوك (Secrets)")
        return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: 
            posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        
        if h in posted:
            continue

        print(f"🔄 معالجة الخبر: {title}")

        # التحقق من وجود الخط لتجنب توقف الكود
        if not os.path.exists(FONT_FILE):
            print(f"❌ خطأ: ملف الخط {FONT_FILE} غير موجود في المستودع!")
            return

        with Image(filename="BG.png") as canvas:
            # 1. إضافة صورة الخبر
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    r = requests.get(match.group(1), timeout=10)
                    with Image(blob=r.content) as art_img:
                        art_img.transform(resize='855x460^')
                        art_img.extent(width=855, height=460)
                        canvas.composite(art_img, left=112, top=185)
                else:
                    with Image(filename="logo1.png") as logo:
                        logo.resize(855, 460)
                        canvas.composite(logo, left=112, top=185)
            except Exception as e:
                print(f"⚠️ فشل دمج الصورة: {e}")

            # 2. رسم النص العربي يدوياً سطر بسطر
            lines = process_arabic_title(title)
            
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 50 # تم تكبير الخط قليلاً ليناسب نوع الخط الجديد
                draw.fill_color = Color('black')
                draw.text_alignment = 'center'
                draw.text_antialias = True
                
                current_y = START_Y
                for line in lines:
                    draw.text(x=int(CENTER_X), y=int(current_y), body=line)
                    current_y += LINE_HEIGHT
                
                draw(canvas)

            canvas.format = 'png'
            canvas.save(filename="final.png")

        # 3. النشر على فيسبوك
        with open("final.png", "rb") as f:
            res = requests.post(FB_URL, data={
                "access_token": PAGE_ACCESS_TOKEN, 
                "caption": f"🔴 {title}\n\n#قنا #أخبار\n{entry.link}"
            }, files={"source": f})
        
        if res.status_code == 200:
            print("✅ تم النشر!")
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            
            # تحديث السجل في GitHub
            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "Update posted log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break 

if __name__ == "__main__":
    main()
