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

# =========================
# أدوات مساعدة
# =========================
def get_next_feed_index():
    if not os.path.exists(INDEX_FILE):
        return 0
    with open(INDEX_FILE, "r") as f:
        return int(f.read().strip())

def save_next_feed_index(i):
    with open(INDEX_FILE, "w") as f:
        f.write(str(i))

def shape_text(txt):
    return get_display(arabic_reshaper.reshape(txt))

# =========================
# التنفيذ
# =========================
def main():
    feed_index = get_next_feed_index()
    feed_cfg = FEEDS[feed_index % len(FEEDS)]
    save_next_feed_index(feed_index + 1)

    feed = feedparser.parse(feed_cfg["url"])

    posted = []
    if os.path.exists(POSTED_FILE):
        posted = open(POSTED_FILE, encoding="utf-8").read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title).strip()
        h = hashlib.md5(title.encode()).hexdigest()
        if h in posted:
            continue

        # =========================
        # جلب صورة الخبر
        # =========================
        img_url = None
        m = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
        if m:
            img_url = m.group(1)

        if not img_url:
            continue

        r = requests.get(img_url, timeout=15)

        # =========================
        # إنشاء Canvas
        # =========================
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

            # =========================
            # كتابة العنوان
            # =========================
            with Drawing() as draw:
                draw.font = FONT_FILE
                draw.font_size = 52
                draw.fill_color = Color(feed_cfg["text_color"])
                draw.text_alignment = "center"

                shaped = shape_text(title)
                draw.text(540, 780, shaped)
                draw(canvas)

            canvas.format = "png"
            canvas.alpha_channel = 'remove'
            canvas.save(filename="final.png")

        # =========================
        # نشر فيسبوك
        # =========================
        with open("final.png", "rb") as img:
            res = requests.post(
                FB_URL,
                data={"access_token": PAGE_ACCESS_TOKEN, "caption": title},
                files={"source": img},
            )

        if res.status_code == 200:
            with open(POSTED_FILE, "a", encoding="utf-8") as f:
                f.write(h + "\n")
            print("✅ تم النشر")
            break
        else:
            print("❌ فشل النشر", res.text)

if __name__ == "__main__":
    main()
