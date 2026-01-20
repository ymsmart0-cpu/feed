# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
from io import BytesIO
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import random
import subprocess

# ============================
# إعدادات عامة
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"

# تأكد أن هذا الاسم مطابق تماماً لاسم الملف الذي رفعته (بما في ذلك الحروف الكبيرة)
FONT_FILE = "Cairo-Bold.ttf" 
START_FONT_SIZE = 42

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
PADDING = 12
MAX_WIDTH = RIGHT_X - LEFT_X
MAX_HEIGHT = BOTTOM_Y - TOP_Y

# استدعاء البيانات من Secrets
PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_PHOTO_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None

POSTED_FILE = "posted_articles.txt"

# ============================
# معالجة النص العربي (اليمين لليسار)
# ============================
def fix_arabic_display(text):
    """إعادة تشكيل الحروف وعكس الاتجاه للعرض الصحيح"""
    if not text: return ""
    # 1. ربط الحروف ببعضها
    reshaped = arabic_reshaper.reshape(text)
    # 2. ترتيب السطر من اليمين لليسار
    return get_display(reshaped)

def wrap_arabic_text(text, draw, font, max_width):
    """تقسيم النص لأسطر مع الحفاظ على ترتيب الكلمات الصحيح"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        # نقيس العرض بالنص المشكل برمجياً
        display_test = fix_arabic_display(test_line)
        w = draw.textbbox((0, 0), display_test, font=font)[2]
        
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                # معالجة السطر المكتمل ليصبح RTL
                lines.append(fix_arabic_display(" ".join(current_line)))
            current_line = [word]
            
    if current_line:
        lines.append(fix_arabic_display(" ".join(current_line)))
        
    return lines

# ============================
# دالة الرسم باستخدام الطبقة الشفافة
# ============================
def apply_text_layer(base_img, lines, font):
    # إنشاء طبقة شفافة
    txt_layer = Image.new('RGBA', base_img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    # حساب إجمالي الارتفاع لتوسيط النص عمودياً
    line_heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
    total_text_h = sum(line_heights) + (len(lines) - 1) * PADDING
    current_y = TOP_Y + (MAX_HEIGHT - total_text_h) // 2

    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        h = draw.textbbox((0, 0), line, font=font)[3]
        # التوسيط الأفقي
        x = LEFT_X + (MAX_WIDTH - w) // 2
        draw.text((x, current_y), line, font=font, fill="black")
        current_y += h + PADDING
    
    # دمج الطبقة الشفافة مع الخلفية
    return Image.alpha_composite(base_img.convert('RGBA'), txt_layer)

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    if not FB_PHOTO_URL or "None" in FB_PHOTO_URL:
        print("❌ خطأ: الـ PAGE_ID غير موجود في Secrets")
        return

    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f: 
            posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        print(f"🔄 جاري معالجة المقال: {title[:50]}...")
        
        # 1. فتح الخلفية
        if not os.path.exists(BG_PATH):
            print(f"❌ خطأ: ملف الخلفية {BG_PATH} غير موجود")
            return
        bg = Image.open(BG_PATH).convert("RGBA").resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        
        # 2. جلب صورة المقال
        try:
            html = entry.summary if hasattr(entry, "summary") else ""
            img_match = re.search(r'<img[^>]+src="([^">]+)"', html)
            r = requests.get(img_match.group(1), timeout=10)
            art_img = Image.open(BytesIO(r.content)).convert("RGBA").resize(ARTICLE_IMG_SIZE)
        except:
            print("⚠️ لم يتم العثور على صورة للمقال، سيتم استخدام اللوجو.")
            art_img = Image.open(LOGO_PATH).convert("RGBA").resize(ARTICLE_IMG_SIZE)
        
        bg.paste(art_img, ((IMAGE_WIDTH-ARTICLE_IMG_SIZE[0])//2, ARTICLE_IMG_Y), art_img)

        # 3. معالجة النص
        draw = ImageDraw.Draw(bg)
        if not os.path.exists(FONT_FILE):
            print(f"❌ خطأ: ملف الخط {FONT_FILE} غير موجود في المستودع!")
            return

        font = ImageFont.truetype(FONT_FILE, START_FONT_SIZE)
        lines = wrap_arabic_text(title, draw, font, MAX_WIDTH)
        
        # استخدام الطبقة الشفافة لضمان جودة النص
        final_img = apply_text_layer(bg, lines, font)

        # 4. الحفظ والنشر
        output = "final_post.png"
        final_img.convert("RGB").save(output)
        
        with open(output, "rb") as f:
            res = requests.post(FB_PHOTO_URL, 
                                data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, 
                                files={"source": f})
        
        if res.status_code == 200:
            with open(POSTED_FILE, "a", encoding="utf-8") as f: 
                f.write(h + "\n")
            print("✅ تم النشر بنجاح على فيسبوك!")
            
            # دفع التحديثات لـ Git لحفظ حالة المقالات المنشورة
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "GitHub Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "Update posted log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break 
        else:
            print(f"❌ فشل النشر: {res.text}")

if __name__ == "__main__":
    main()
