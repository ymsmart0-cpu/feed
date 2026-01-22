# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
import random
import subprocess
import json

from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color

import arabic_reshaper
from bidi.algorithm import get_display

# ============================
# الإعدادات العامة
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
FONT_FILE = "29ltbukrabolditalic.otf"

BG_IMAGE = "BG.png"
LOGO_IMAGE = "logo1.png"

# حدود النص
TEXT_LEFT = 110
TEXT_RIGHT = 960
TEXT_TOP = 725
TEXT_BOTTOM = 880

# حساب المساحات المتاحة تلقائياً
MAX_WIDTH = TEXT_RIGHT - TEXT_LEFT  # 850px
MAX_HEIGHT = TEXT_BOTTOM - TEXT_TOP # 155px
CENTER_X = TEXT_LEFT + (MAX_WIDTH // 2)

POSTED_FILE = "posted_articles.txt"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

# ============================
# كلمات حساسة
# ============================
SEPARATORS = ["$", "•", "~", "+", "|", "=", "^", "!", "·", "⁃"]

SENSITIVE_WORDS = [
    "قتل","مقتل","قتيل","يقتل","قتلته","جريمة","جرائم","مجرم",
    "ذبح","مذبوح","طعن","مطعون","ضرب","اعتداء","اعتداءات",
    "عنف","تعذيب","دم","دماء","نزيف","سلاح","أسلحة","سلاح أبيض",
    "سكين","مطواة","إطلاق نار","رصاص","طلقات","تفجير","انفجار",
    "قنبلة","اختطاف","خطف","مخطوف","سرقة","سطو","نهب","تهديد","ابتزاز",
    "تحرش","التحرش","تحرش جنسي","اعتداء جنسي","اعتداءات جنسية",
    "اغتصاب","مغتصب","هتك عرض","انتهاك","انتهاك جسدي","استغلال جنسي",
    "تحريض جنسي","طفلة","طفل","قاصر","قاصرة","الاعتداء على طفل",
    "التحرش بالأطفال","استغلال الأطفال","انتحار","انتحر","ينتحر",
    "إيذاء النفس","أذى النفس","شنق","شنق نفسه","تناول سُم","جرعة زائدة",
    "إرهاب","إرهابي","تفجير إرهابي","تنظيم إرهابي","داعش","تفجيرات",
    "عمليات إرهابية","جنس","جنسية","علاقة جنسية","إباحية","مواد إباحية",
    "ممارسة جنسية","عنصرية","كراهية","خطاب كراهية","تحريض",
    "تحريض على العنف","سب","إهانة","تشهير","مخدرات","مخدر","حشيش",
    "بانجو","هيروين","كوكايين","ترامادول","تعاطي","ترويج مخدرات",
    "فساد","رشوة","اختلاس","تزوير","تزوير أوراق","غسيل أموال"
]

def split_sensitive_word(word):
    if word not in SENSITIVE_WORDS:
        return word
    symbol = random.choice(SEPARATORS)
    pos = len(word) // 2
    return word[:pos] + symbol + word[pos:]

def process_sensitive_text(text, limit_once=False):
    words = text.split()
    used = False
    out = []
    for w in words:
        stripped_w = re.sub(r'[^\w]', '', w) 
        has_sensitive = any(s in w for s in SENSITIVE_WORDS)
        
        if has_sensitive and (not used or not limit_once):
            out.append(split_sensitive_word(w))
            used = True
        else:
            out.append(w)
    return " ".join(out)

# ============================
# الأماكن والهاشتاجات
# ============================
PLACES = [
    "القاهرة","الجيزة","الإسكندرية","الدقهلية","الشرقية","القليوبية",
    "كفر الشيخ","الغربية","المنوفية","البحيرة","دمياط",
    "بورسعيد","الإسماعيلية","السويس",
    "الفيوم","بني سويف","المنيا","أسيوط","سوهاج","قنا","الأقصر","أسوان",
    "البحر الأحمر","الوادي الجديد","مطروح","شمال سيناء","جنوب سيناء",
    "مدينة قنا","مركز قنا","نجع حمادي","مركز نجع حمادي",
    "دشنا","مركز دشنا","قفط","مركز قفط","قوص","مركز قوص",
    "أبو تشت","مركز أبو تشت","فرشوط","مركز فرشوط",
    "نقادة","مركز نقادة","الوقف","مركز الوقف"
]

GOV_ENTITIES = ["النيابة العامة","وزارة الداخلية","وزارة العدل","محكمة","الشرطة","الأجهزة الأمنية"]

SECTIONS = {
    "قضائي": ["محكمة","النيابة","حكم","قضت"],
    "أمني": ["القبض","الأمن","الشرطة","تفتيش"],
    "تعليمي": ["مدرس","طلاب","تعليم","مدرسة"],
    "رياضي": ["مباراة","لاعب","نادي","بطولة"]
}

def detect_section(text):
    for sec, keys in SECTIONS.items():
        for k in keys:
            if k in text:
                return sec
    return "أخبار"

def normalize_hashtag(text):
    return text.replace(" ", "_")

def extract_safe_hashtags(text):
    tags = ["قنا24"]
    for p in PLACES:
        if p in text:
            tags.append(normalize_hashtag(p))
            break
    for g in GOV_ENTITIES:
        if g in text:
            tags.append(normalize_hashtag(g))
            break
    tags.append(normalize_hashtag(detect_section(text)))
    return " ".join(f"#{t}" for t in tags)

# ============================
# دالة التفاف النص حسب البكسل
# ============================
def wrap_text_pixel_based(text, drawing, canvas, max_width_px):
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = current_line + [word]
        test_str = " ".join(test_line)
        reshaped_text = arabic_reshaper.reshape(test_str)
        bidi_text = get_display(reshaped_text)
        metrics = drawing.get_font_metrics(canvas, bidi_text)
        
        if metrics.text_width <= max_width_px:
            current_line = test_line
        else:
            if current_line:
                final_str = " ".join(current_line)
                lines.append(get_display(arabic_reshaper.reshape(final_str)))
            current_line = [word]
            
    if current_line:
        final_str = " ".join(current_line)
        lines.append(get_display(arabic_reshaper.reshape(final_str)))
        
    return lines

# ============================
# دالة ملائمة النص للمربع
# ============================
def fit_text_dynamic(text, canvas):
    font_size = 60
    min_font = 20
    
    with Drawing() as draw:
        draw.font = FONT_FILE
        
        while font_size >= min_font:
            draw.font_size = font_size
            line_height = int(font_size * 1.3)
            lines = wrap_text_pixel_based(text, draw, canvas, MAX_WIDTH)
            total_text_height = len(lines) * line_height
            
            if total_text_height <= MAX_HEIGHT and len(lines) > 0:
                return lines, font_size, line_height
            
            font_size -= 2
            
    return lines, min_font, int(min_font * 1.3)

# ============================
# التنفيذ الرئيسي (معدل)
# ============================
def main():
    feed = feedparser.parse(RSS_URL)

    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            posted = f.read().splitlines()

    for entry in feed.entries:
        raw_title = re.sub("<.*?>", "", entry.title).strip()
        raw_summary = re.sub("<.*?>", "", entry.summary).strip()

        h = hashlib.md5(raw_title.encode("utf-8")).hexdigest()
        if h in posted:
            continue

        title = process_sensitive_text(raw_title, limit_once=True)
        summary = process_sensitive_text(raw_summary)

        first_50 = " ".join(summary.split()[:50])

        # === 1. تجهيز الكابشن (بدون رابط) ===
        caption = (
            f"{first_50}...\n\n"
            f"التفاصيل ورابط الخبر في أول تعليق 👇\n\n"
            f"{extract_safe_hashtags(raw_title)}"
        )

        # === 2. تجهيز التعليق (الرابط والعنوان) ===
        comment_text = (
            f"{title}\n"
            f"الخبر كامل هنا 👇\n"
            f"{entry.link}"
        )

        with Image(filename=BG_IMAGE) as canvas:
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    r = requests.get(match.group(1), timeout=10)
                    with Image(blob=r.content) as art:
                        art.transform(resize='855x460^')
                        art.extent(855, 460)
                        canvas.composite(art, 112, 185)
                else:
                    with Image(filename=LOGO_IMAGE) as logo:
                        logo.resize(855, 460)
                        canvas.composite(logo, 112, 185)
            except:
                pass

            lines, font_size, line_height = fit_text_dynamic(title, canvas)
            total_h = len(lines) * line_height
            start_y = TEXT_TOP + (MAX_HEIGHT - total_h) // 2 + int(font_size * 0.8)

            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = font_size
                draw.fill_color = Color("black")
                draw.text_alignment = "center"
                
                current_y = TEXT_TOP + (MAX_HEIGHT - total_h) // 2 + int(line_height * 0.8)

                for line in lines:
                    draw.text(CENTER_X, current_y, line)
                    current_y += line_height

                draw(canvas)

            canvas.save(filename="final.png")

        # === عملية النشر والتعليق ===
        try:
            with open("final.png", "rb") as img:
                # 1. نشر البوست
                res = requests.post(
                    FB_URL,
                    data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption},
                    files={"source": img}
                )

            if res.status_code == 200:
                # 2. جلب ID البوست لنشر التعليق
                post_data = res.json()
                # أحياناً يكون المعرف post_id وأحياناً id حسب الرد
                post_id = post_data.get("post_id") or post_data.get("id")
                
                print(f"✅ تم نشر البوست: {post_id}")

                if post_id:
                    # 3. نشر التعليق
                    comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
                    comment_res = requests.post(
                        comment_url,
                        data={
                            "access_token": PAGE_ACCESS_TOKEN,
                            "message": comment_text
                        }
                    )
                    if comment_res.status_code == 200:
                        print("💬 تم إضافة التعليق بنجاح")
                    else:
                        print(f"⚠️ خطأ في التعليق: {comment_res.text}")

                # حفظ وتحديث Git
                with open(POSTED_FILE, "a", encoding="utf-8") as f:
                    f.write(h + "\n")

                subprocess.run(["git", "config", "--global", "user.name", "Bot"])
                subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
                subprocess.run(["git", "add", POSTED_FILE])
                subprocess.run(["git", "commit", "-m", "update posted articles"], check=False)
                subprocess.run(["git", "push"], check=False)

                break
            else:
                print(f"❌ فشل النشر: {res.text}")
        except Exception as e:
            print(f"❌ خطأ أثناء العملية: {e}")

if __name__ == "__main__":
    main()
