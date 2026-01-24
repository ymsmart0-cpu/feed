# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
import subprocess

from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color

import arabic_reshaper
from bidi.algorithm import get_display

# =========================
# إعدادات RSS + الأقسام
# =========================
FEEDS = [
    {
        "name": "اخبار قنا",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/اخبار%20قنا?alt=rss",
        "overlay": "qena.png",
        "text_color": "white",
    },
    {
        "name": "حوادث",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/حوادث?alt=rss",
        "overlay": "news.png",
        "text_color": "white",
    },
    {
        "name": "برلمان 25",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/برلمان%2025?alt=rss",
        "overlay": "barlman.png",
        "text_color": "white",
    },
    {
        "name": "رياضة",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/رياضة?alt=rss",
        "overlay": "sport.png",
        "text_color": "black",
    },
    {
        "name": "علوم وتكنولوجيا",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/علوم%20وتكنولوجيا?alt=rss",
        "overlay": "tecno.png",
        "text_color": "black",
    },
    {
        "name": "صحة وفن",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/صحة%20وفن?alt=rss",
        "overlay": "art.png",
        "text_color": "black",
    },
]

FONT_FILE = "29ltbukrabolditalic.otf"
POSTED_FILE = "posted_articles.txt"
INDEX_FILE = "last_feed_index.txt"

PAGE_ID = os.getenv("PAGE_ID")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

# ============================
# حدود النص
# ============================
TEXT_LEFT = 55
TEXT_RIGHT = 1030
TEXT_TOP = 765
TEXT_BOTTOM = 980

CENTER_X = (TEXT_LEFT + TEXT_RIGHT) // 2
MAX_WIDTH = TEXT_RIGHT - TEXT_LEFT
MAX_HEIGHT = TEXT_BOTTOM - TEXT_TOP

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

# ============================
# أدوات مساعدة
# ============================
def shape_text(txt):
    return get_display(arabic_reshaper.reshape(txt))

def detect_section(text):
    for sec, keys in SECTIONS.items():
        for k in keys:
            if k in text:
                return sec
    return "أخبار"

def normalize_hashtag(text):
    return text.replace(" ", "_")

def extract_safe_hashtags(text):
    tags = ["قنا_نيوز_24"]
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

# =========================
# التنفيذ
# =========================
def main():
    feed_index = 0
    if os.path.exists(INDEX_FILE):
        feed_index = int(open(INDEX_FILE).read().strip())

    feed_cfg = FEEDS[feed_index % len(FEEDS)]
    open(INDEX_FILE, "w").write(str(feed_index + 1))

    feed = feedparser.parse(feed_cfg["url"])

    posted = []
    if os.path.exists(POSTED_FILE):
        posted = open(POSTED_FILE, encoding="utf-8").read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(title.encode()).hexdigest()
        if h in posted:
            continue

        m = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
        if not m:
            continue

        r = requests.get(m.group(1), timeout=15)

        with Image(width=1080, height=1080, background=Color("white")) as canvas:
            canvas.alpha_channel = 'activate'

            # صورة الخبر
            with Image(blob=r.content) as news:
                news.format = "png"
                news.alpha_channel = 'activate'
                news.resize(1080, 715)
                canvas.composite(news, 0, 0)

            # Overlay القسم
            with Image(filename=feed_cfg["overlay"]) as overlay:
                overlay.alpha_channel = 'activate'
                overlay.resize(1080, 1080)
                canvas.composite(overlay, 0, 0)

            # كتابة العنوان
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 52
                draw.fill_color = Color(feed_cfg["text_color"])
                draw.text_alignment = "center"

                shaped = shape_text(title)
                draw.text(CENTER_X, TEXT_TOP + 40, shaped)
                draw(canvas)

            canvas.format = "png"
            canvas.alpha_channel = 'remove'
            canvas.save(filename="final.png")

        # ---------- كابشن فيسبوك (أول 50 كلمة + تابع باقي الخبر + هاشتاجات) ----------
        clean_summary = re.sub("<.*?>", "", entry.summary)
        first_50 = " ".join(clean_summary.split()[:50])
        caption = (
            f"{title}

"
            f"{first_50}...
"
            f"تابع باقي الخبر من هنا 👇
"
            f"{entry.link}

"
            f"{extract_safe_hashtags(title)}"
        )

        with open("final.png", "rb") as img:
            res = requests.post(
                FB_URL,
                data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption},
                files={"source": img},
            )

        if res.status_code == 200:
            open(POSTED_FILE, "a", encoding="utf-8").write(h + "\n")
            print("✅ تم النشر")
            break
        else:
            print("❌ فشل النشر", res.text)

if __name__ == "__main__":
    main()
