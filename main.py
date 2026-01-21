# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
import random
import subprocess
from io import BytesIO

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

BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

CENTER_X = 540
START_Y = 780
LINE_HEIGHT = 75

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

POSTED_FILE = "posted_articles.txt"

# ============================
# كلمات حساسة (فيسبوك)
# ============================
SEPARATORS = ["$", "&", "%", "*", "~", "+", "|", "•", "=", "^", ":", "!"]

SENSITIVE_WORDS = [
    # تفاعل مزعج
    "اشترك","الآن","اضغط","شاهد","فرصة","اربح","مجانا","عرض",

    # عنف ودم
    "قتل","جريمة","ذبح","جثة","دم","دماء","طعن","تفجير","انتحار",

    # تحرش واعتداء
    "تحرش","اغتصاب","اعتداء","اعتداءات","هتك","خدش","خطف",
    "اعتداء_جنسي","تحرش_جنسي",

    # كراهية
    "إرهابي","إرهاب","عنصرية","كراهية"
]

STOP_WORDS = [
    "هذا","هذه","ذلك","التي","الذي","على","في","من","إلى","عن",
    "مع","كان","كما","بعد","قبل","بين","أمام","خلال"
]

# ============================
# معالجة الكلمات الحساسة
# ============================
def split_sensitive_word(word):
    if word in SENSITIVE_WORDS:
        pos = 2 if len(word) >= 4 else 1
        return word[:pos] + random.choice(SEPARATORS) + word[pos:]
    return word

def process_sensitive_text(text):
    return " ".join(split_sensitive_word(w) for w in text.split())

# ============================
# معالجة النص العربي RTL
# ============================
def process_arabic_lines(text, max_chars=35):
    words = text.split()
    lines = []
    current = []

    for word in words:
        test = " ".join(current + [word])
        if len(test) <= max_chars:
            current.append(word)
        else:
            reshaped = arabic_reshaper.reshape(" ".join(current))
            lines.append(get_display(reshaped))
            current = [word]

    if current:
        reshaped = arabic_reshaper.reshape(" ".join(current))
        lines.append(get_display(reshaped))

    return lines

# ============================
# استخراج أول 50 كلمة
# ============================
def extract_summary(text, limit=50):
    words = text.split()
    short = " ".join(words[:limit])
    return process_sensitive_text(short)

# ============================
# استخراج هاشتاجات آمنة
# ============================
def extract_hashtags(text, max_tags=4):
    words = re.findall(r"[\u0600-\u06FF]{4,}", text)
    clean = []

    for w in words:
        if w not in STOP_WORDS and w not in SENSITIVE_WORDS:
            clean.append(w)

    unique = list(dict.fromkeys(clean))
    dynamic = unique[:max_tags]

    hashtags = ["قنا24"] + dynamic
    return " ".join(f"#{h}" for h in hashtags)

# ============================
# MAIN
# ============================
def main():
    if not PAGE_ID or not PAGE_ACCESS_TOKEN:
        print("❌ بيانات فيسبوك غير موجودة")
        return

    feed = feedparser.parse(RSS_URL)

    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            posted = f.read().splitlines()

    for entry in feed.entries:
        raw_title = re.sub("<.*?>", "", entry.title).strip()
        raw_text = re.sub("<.*?>", "", entry.summary).strip()

        h = hashlib.md5((raw_title + raw_text).encode("utf-8")).hexdigest()
        if h in posted:
            continue

        print("🔄 خبر جديد:", raw_title)

        # معالجة النص
        safe_title = process_sensitive_text(raw_title)
        safe_summary = extract_summary(raw_text)
        hashtags = extract_hashtags(raw_text)

        # إنشاء الصورة
        with Image(filename=BG_PATH) as canvas:

            # صورة الخبر
            try:
                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    r = requests.get(match.group(1), timeout=10)
                    with Image(blob=r.content) as img:
                        img.transform(resize='855x460^')
                        img.extent(width=855, height=460)
                        canvas.composite(img, left=112, top=185)
                else:
                    with Image(filename=LOGO_PATH) as logo:
                        logo.resize(855, 460)
                        canvas.composite(logo, left=112, top=185)
            except:
                pass

            # رسم العنوان
            lines = process_arabic_lines(safe_title)
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 50
                draw.fill_color = Color("black")
                draw.text_alignment = "center"

                y = START_Y
                for line in lines:
                    draw.text(CENTER_X, y, line)
                    y += LINE_HEIGHT

                draw(canvas)

            canvas.save(filename="final.png")

        # كابشن
        caption = (
            f"{safe_title}\n\n"
            f"{safe_summary}...\n\n"
            f"تابع الخبر كامل هنا 👇\n"
            f"{entry.link}\n\n"
            f"{hashtags}"
        )

        with open("final.png", "rb") as img:
            res = requests.post(
                FB_URL,
                data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption},
                files={"source": img}
            )

        if res.status_code == 200:
            print("✅ تم النشر")
            with open(POSTED_FILE, "a", encoding="utf-8") as f:
                f.write(h + "\n")

            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "Update posted articles"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

# ============================
if __name__ == "__main__":
    main()
