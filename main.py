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
FONT_FILE = "Cairo-Bold.ttf" # تأكد من تحميل نسخة حديثة من Google Fonts

# إحداثيات منطقة النص (مضبوطة لضمان التوسيط)
CENTER_X = 540  # منتصف عرض الصورة (1080/2)
START_Y = 780   # بداية كتابة أول سطر من الأعلى
LINE_HEIGHT = 75 # المسافة الرأسية بين الأسطر لضمان عدم تداخل النقاط

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

def process_arabic_text(text, max_chars=38):
    """تقسيم النص لأسطر ومعالجة كل سطر بشكل مستقل لضمان اتصال الحروف"""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        # إذا كان إضافة الكلمة لن يتجاوز الحد الأقصى للسطر
        if len(current_line) + len(word) <= max_chars:
            current_line += word + " "
        else:
            # معالجة السطر المكتمل (تشكيل + قلب اتجاه)
            reshaped = arabic_reshaper.reshape(current_line.strip())
            lines.append(get_display(reshaped))
            current_line = word + " "
            
    # إضافة آخر سطر
    if current_line:
        reshaped = arabic_reshaper.reshape(current_line.strip())
        lines.append(get_display(reshaped))
    
    return lines

def main():
    print("🚀 بدء المحرك العربي المطور لـ Wand...")
    if not FB_URL:
        print("❌ خطأ: لم يتم ضبط Secrets في GitHub!")
        return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: 
            posted = f.read().splitlines()

    for entry in feed.entries:
        # تنظيف العنوان
        title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        
        if h in posted:
            continue

        print(f"🔄 معالجة الخبر: {title}")

        with Image(filename="BG.png") as canvas:
            # 1. جلب صورة المقال أو اللوجو
            try:
                img_url = ""
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    img_url = match.group(1)
                    r = requests.get(img_url, timeout=10)
                    with Image(blob=r.content) as art_img:
                        # ضبط الصورة لتملأ الفراغ المخصص (855x460)
                        art_img.transform(resize='855x460^')
                        art_img.extent(width=855, height=460)
                        canvas.composite(art_img, left=112, top=185)
                else:
                    raise Exception("No image in entry")
            except:
                print("⚠️ استخدام اللوجو الافتراضي")
                with Image(filename="logo1.png") as logo:
                    logo.resize(855, 460)
                    canvas.composite(logo, left=112, top=185)

            # 2. رسم النص العربي (الحل اليدوي لضمان عدم التقطيع)
            processed_lines = process_arabic_text(title)
            
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 48  # حجم الخط
                draw.fill_color = Color('black')
                draw.text_alignment = 'center'
                draw.text_antialias = True # لتنعيم حواف الحروف
                
                current_y = START_Y
                for line in processed_lines:
                    # رسم السطر في المنتصف تماماً
                    draw.text(x=int(CENTER_X), y=int(current_y), body=line)
                    # الانتقال للسطر التالي مع مسافة كافية للنقاط
                    current_y += LINE_HEIGHT
                
                draw(canvas)

            # 3. حفظ الصورة النهائية
            canvas.format = 'png'
            canvas.save(filename="final.png")

        # 4. النشر على فيسبوك
        print("📤 جاري الرفع لفيسبوك...")
        with open("final.png", "rb") as f:
            res = requests.post(FB_URL, data={
                "access_token": PAGE_ACCESS_TOKEN, 
                "caption": f"🔴 {title}\n\n{entry.link}"
            }, files={"source": f})
        
        if res.status_code == 200:
            print("✅ تم النشر بنجاح!")
            with open(POSTED_FILE, "a") as f: 
                f.write(h + "\n")
            
            # تحديث GitHub لضمان عدم تكرار الخبر
            subprocess.run(["git", "config", "--global", "user.email", "actions@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "Update posted articles log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break # نشر خبر واحد في كل دورة
        else:
            print(f"❌ فشل النشر: {res.text}")

if __name__ == "__main__":
    main()
