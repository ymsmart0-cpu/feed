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

MAX_WIDTH = TEXT_RIGHT - TEXT_LEFT
MAX_HEIGHT = TEXT_BOTTOM - TEXT_TOP
CENTER_X = TEXT_LEFT + (MAX_WIDTH // 2)

POSTED_FILE = "posted_articles.txt"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()

# الرابط الصحيح لنشر الصور في الإصدارات الحديثة
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

# ============================
# معالجة الكلمات الحساسة والهاشتاجات
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

def break_sensitive_inside_word(word):
    for sensitive in SENSITIVE_WORDS:
        if sensitive in word:
            symbol = random.choice(SEPARATORS)
            pos = len(sensitive) // 2
            broken = sensitive[:pos] + symbol + sensitive[pos:]
            return word.replace(sensitive, broken, 1)
    return word

def process_sensitive_text(text, limit_once=False):
    words = text.split(); used = False; result = []
    for w in words:
        has_sensitive = any(s in w for s in SENSITIVE_WORDS)
        if has_sensitive and (not used or not limit_once):
            result.append(break_sensitive_inside_word(w)); used = True
        else: result.append(w)
    return " ".join(result)

PLACES = ["القاهرة","الجيزة","الإسكندرية","سوهاج","قنا","الأقصر","أسوان","مدينة قنا","نجع حمادي","دشنا","قفط","قوص","أبو تشت","فرشوط","نقادة","الوقف"]
GOV_ENTITIES = ["النيابة العامة","وزارة الداخلية","محكمة","الشرطة"]

def extract_safe_hashtags(text):
    tags = ["قنا24"]
    for p in PLACES:
        if p in text: tags.append(p.replace(" ", "_")); break
    for g in GOV_ENTITIES:
        if g in text: tags.append(g.replace(" ", "_")); break
    return " ".join(f"#{t}" for t in tags)

# ============================
# دوال معالجة الصور والنصوص
# ============================
def wrap_text_pixel_based(text, drawing, canvas, max_width_px):
    words = text.split(); lines = []; current_line = []
    for word in words:
        test_line = current_line + [word]
        reshaped = get_display(arabic_reshaper.reshape(" ".join(test_line)))
        if drawing.get_font_metrics(canvas, reshaped).text_width <= max_width_px:
            current_line = test_line
        else:
            if current_line: lines.append(get_display(arabic_reshaper.reshape(" ".join(current_line))))
            current_line = [word]
    if current_line: lines.append(get_display(arabic_reshaper.reshape(" ".join(current_line))))
    return lines

def fit_text_dynamic(text, canvas):
    font_size = 60; min_font = 20
    with Drawing() as draw:
        draw.font = FONT_FILE
        while font_size >= min_font:
            draw.font_size = font_size
            line_height = int(font_size * 1.3)
            lines = wrap_text_pixel_based(text, draw, canvas, MAX_WIDTH)
            if (len(lines) * line_height) <= MAX_HEIGHT and len(lines) > 0:
                return lines, font_size, line_height
            font_size -= 2
    return lines, min_font, int(min_font * 1.3)

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            posted = f.read().splitlines()

    for entry in feed.entries:
        raw_title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(raw_title.encode("utf-8")).hexdigest()
        if h in posted: continue

        # معالجة النصوص
        title = process_sensitive_text(raw_title, limit_once=True)
        summary = re.sub("<.*?>", "", entry.summary).strip()
        summary_processed = process_sensitive_text(summary)
        first_50 = " ".join(summary_processed.split()[:50])

        # الكابشن الرئيسي (بدون رابط)
        caption = (
            f"{first_50}...\n\n"
            f"التفاصيل ورابط الخبر في أول تعليق 👇\n\n"
            f"{extract_safe_hashtags(raw_title)}"
        )
        
        # نص التعليق (العنوان + الرابط)
        comment_text = f"{title}\nالخبر كامل هنا 👇\n{entry.link}"

        with Image(filename=BG_IMAGE) as canvas:
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    r = requests.get(match.group(1), timeout=10)
                    with Image(blob=r.content) as art:
                        art.transform(resize='855x460^'); art.extent(855, 460)
                        canvas.composite(art, 112, 185)
                else:
                    with Image(filename=LOGO_IMAGE) as logo:
                        logo.resize(855, 460); canvas.composite(logo, 112, 185)
            except: pass

            lines, font_size, line_height = fit_text_dynamic(title, canvas)
            total_h = len(lines) * line_height
            current_y = TEXT_TOP + (MAX_HEIGHT - total_h) // 2 + int(line_height * 0.8)

            with Drawing() as draw:
                draw.font = FONT_FILE; draw.font_size = font_size
                draw.fill_color = Color("black"); draw.text_alignment = "center"
                for line in lines:
                    draw.text(CENTER_X, current_y, line)
                    current_y += line_height
                draw(canvas)
            canvas.save(filename="final.png")

        # النشر على فيسبوك
        try:
            with open("final.png", "rb") as img:
                # إرسال البيانات بشكل صحيح لتجنب خطأ (#200)
                payload = {
                    "caption": caption,
                    "access_token": PAGE_ACCESS_TOKEN
                }
                files = {"source": img}
                res = requests.post(FB_URL, data=payload, files=files)
            
            if res.status_code == 200:
                data = res.json()
                post_id = data.get("post_id") or data.get("id")
                print(f"✅ تم النشر بنجاح: {post_id}")
                
                # إضافة التعليق التلقائي
                if post_id:
                    comment_url = f"https://graph.facebook.com/v19.0/{post_id}/comments"
                    c_res = requests.post(comment_url, data={
                        "message": comment_text,
                        "access_token": PAGE_ACCESS_TOKEN
                    })
                    if c_res.status_code == 200: print("💬 تم إضافة التعليق بنجاح")
                    else: print(f"⚠️ فشل التعليق: {c_res.text}")

                # حفظ الحالة وتحديث GitHub
                with open(POSTED_FILE, "a", encoding="utf-8") as f: f.write(h + "\n")
                subprocess.run(["git", "config", "--global", "user.name", "Bot"])
                subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
                subprocess.run(["git", "add", POSTED_FILE])
                subprocess.run(["git", "commit", "-m", "update posted articles"], check=False)
                subprocess.run(["git", "push"], check=False)
                break
            else:
                print(f"❌ فشل النشر: {res.text}")
        except Exception as e:
            print(f"❌ خطأ: {e}")

if __name__ == "__main__":
    main()
