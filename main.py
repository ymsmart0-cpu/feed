# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
import random
import subprocess

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

CENTER_X = TEXT_LEFT + MAX_WIDTH // 2
LINE_HEIGHT = 70

POSTED_FILE = "posted_articles.txt"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

# ============================
# كلمات حساسة
# ============================
SEPARATORS = ["$", "•", "~", "+", "|", "=", "^", "!", "·", "⁃"]

def break_word_inside(word):
    """
    يكسر أي كلمة حساسة حتى لو كانت ملتصقة بحروف قبلها أو بعدها
    مثال: بالتحرش → بالتحر•ش
    """
    for sensitive in SENSITIVE_WORDS:
        if sensitive in word:
            symbol = random.choice(SEPARATORS)
            pos = len(sensitive) // 2
            broken = sensitive[:pos] + symbol + sensitive[pos:]
            return word.replace(sensitive, broken, 1)
    return word

def process_sensitive_text(text, limit_once=False):
    words = text.split()
    used = False
    result = []

    for w in words:
        has_sensitive = any(s in w for s in SENSITIVE_WORDS)

        if has_sensitive and (not used or not limit_once):
            result.append(break_word_inside(w))
            used = True
        else:
            result.append(w)

    return " ".join(result)

SENSITIVE_WORDS = [

    # ===== جرائم وعنف =====
    "قتل","مقتل","قتيل","يقتل","قتلته",
    "جريمة","جرائم","مجرم",
    "ذبح","مذبوح",
    "طعن","مطعون",
    "ضرب","اعتداء","اعتداءات",
    "عنف","تعذيب",
    "دم","دماء","نزيف",
    "سلاح","أسلحة","سلاح أبيض","سكين","مطواة",
    "إطلاق نار","رصاص","طلقات",
    "تفجير","انفجار","قنبلة",
    "اختطاف","خطف","مخطوف",
    "سرقة","سطو","نهب",
    "تهديد","ابتزاز",

    # ===== اعتداءات جنسية =====
    "تحرش","التحرش","تحرش جنسي",
    "اعتداء جنسي","اعتداءات جنسية",
    "اغتصاب","مغتصب",
    "هتك عرض",
    "انتهاك","انتهاك جسدي",
    "استغلال جنسي",
    "تحريض جنسي",

    # ===== أطفال وقُصَّر (حساسة جدًا) =====
    "طفلة","طفل","قاصر","قاصرة",
    "الاعتداء على طفل",
    "التحرش بالأطفال",
    "استغلال الأطفال",

    # ===== انتحار وإيذاء النفس =====
    "انتحار","انتحر","ينتحر",
    "إيذاء النفس","أذى النفس",
    "شنق","شنق نفسه",
    "تناول سُم","جرعة زائدة",

    # ===== إرهاب وتطرف =====
    "إرهاب","إرهابي","تفجير إرهابي",
    "تنظيم إرهابي","داعش",
    "تفجيرات","عمليات إرهابية",

    # ===== ألفاظ جنسية مباشرة =====
    "جنس","جنسية","علاقة جنسية",
    "إباحية","مواد إباحية",
    "ممارسة جنسية",

    # ===== تحريض وكراهية =====
    "عنصرية","كراهية","خطاب كراهية",
    "تحريض","تحريض على العنف",
    "سب","إهانة","تشهير",

    # ===== مخدرات =====
    "مخدرات","مخدر","حشيش","بانجو",
    "هيروين","كوكايين","ترامادول",
    "تعاطي","ترويج مخدرات",

    # ===== قضايا حساسة قانونيًا =====
    "فساد","رشوة","اختلاس",
    "تزوير","تزوير أوراق",
    "غسيل أموال"
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
        if w in SENSITIVE_WORDS and (not used or not limit_once):
            out.append(split_sensitive_word(w))
            used = True
        else:
            out.append(w)
    return " ".join(out)

# ============================
# الأماكن والهاشتاجات
# ============================
PLACES = [
    # محافظات مصر
    "القاهرة","الجيزة","الإسكندرية","الدقهلية","الشرقية","القليوبية",
    "كفر الشيخ","الغربية","المنوفية","البحيرة","دمياط",
    "بورسعيد","الإسماعيلية","السويس",
    "الفيوم","بني سويف","المنيا","أسيوط","سوهاج","قنا","الأقصر","أسوان",
    "البحر الأحمر","الوادي الجديد","مطروح","شمال سيناء","جنوب سيناء",

    # محافظة قنا
    "مدينة قنا","مركز قنا",
    "نجع حمادي","مركز نجع حمادي",
    "دشنا","مركز دشنا",
    "قفط","مركز قفط",
    "قوص","مركز قوص",
    "أبو تشت","مركز أبو تشت",
    "فرشوط","مركز فرشوط",
    "نقادة","مركز نقادة",
    "الوقف","مركز الوقف"
]

GOV_ENTITIES = [
    "النيابة العامة","وزارة الداخلية","وزارة العدل",
    "محكمة","الشرطة","الأجهزة الأمنية"
]

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
# تجهيز النص العربي للصورة
# ============================
def prepare_arabic_lines(text, max_chars=40):
    words = text.split()
    lines, current = [], []

    for w in words:
        test = " ".join(current + [w])
        if len(test) <= max_chars:
            current.append(w)
        else:
            reshaped = arabic_reshaper.reshape(" ".join(current))
            lines.append(get_display(reshaped))
            current = [w]

    if current:
        reshaped = arabic_reshaper.reshape(" ".join(current))
        lines.append(get_display(reshaped))

    return lines

def fit_text_to_box(text):
    font_size = 52
    while font_size >= 24:
        lines = prepare_arabic_lines(text)
        total_height = len(lines) * LINE_HEIGHT
        if total_height <= MAX_HEIGHT:
            return lines, font_size
        font_size -= 2
    return lines, font_size

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
        raw_summary = re.sub("<.*?>", "", entry.summary).strip()

        h = hashlib.md5(raw_title.encode("utf-8")).hexdigest()
        if h in posted:
            continue

        title = process_sensitive_text(raw_title, limit_once=True)
        summary = process_sensitive_text(raw_summary)

        first_50 = " ".join(summary.split()[:50])

        caption = (
            f"{title}\n\n"
            f"{first_50}...\n\n"
            f"تابع الخبر كامل هنا 👇\n{entry.link}\n\n"
            f"{extract_safe_hashtags(raw_title)}"
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

            lines, font_size = fit_text_to_box(title)
            total_h = len(lines) * LINE_HEIGHT
            start_y = TEXT_TOP + (MAX_HEIGHT - total_h) // 2

            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = font_size
                draw.fill_color = Color("black")
                draw.text_alignment = "center"

                y = start_y
                for line in lines:
                    draw.text(CENTER_X, y, line)
                    y += LINE_HEIGHT

                draw(canvas)

            canvas.save(filename="final.png")

        with open("final.png", "rb") as img:
            res = requests.post(
                FB_URL,
                data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption},
                files={"source": img}
            )

        if res.status_code == 200:
            with open(POSTED_FILE, "a", encoding="utf-8") as f:
                f.write(h + "\n")

            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "update posted articles"], check=False)
            subprocess.run(["git", "push"], check=False)

            print("✅ تم النشر بنجاح")
            break

if __name__ == "__main__":
    main()
