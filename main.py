# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
import json
import random
from datetime import datetime

from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color

import arabic_reshaper
from bidi.algorithm import get_display

# ============================
# تحميل الكلمات الحساسة
# ============================
with open("sensitive_words.json", "r", encoding="utf-8") as f:
    SENSITIVE_WORDS = json.load(f)["words"]

IMAGE_SEPARATORS = ["$", "•", "~", "+", "|", "^", "·"]
CAPTION_SEPARATORS = ["/"]

def split_word(word, separators):
    sep = random.choice(separators)
    mid = max(1, len(word) // 2)
    return word[:mid] + sep + word[mid:]

def process_sensitive_text(text, separators, limit_once=False):
    used = False
    for sensitive in sorted(SENSITIVE_WORDS, key=len, reverse=True):
        pattern = rf'(?<!\w){re.escape(sensitive)}(?!\w)'

        def repl(match):
            nonlocal used
            if used and limit_once:
                return match.group(0)
            used = True
            return split_word(match.group(0), separators)

        text = re.sub(pattern, repl, text)
    return text

# ============================
# إعدادات التغذية
# ============================
FEEDS = [
    {"name": "اخبار قنا", "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/اخبار%20قنا?alt=rss", "image": "qena.png", "text_color": "white"},
    {"name": "حوادث", "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/حوادث?alt=rss", "image": "news.png", "text_color": "white"},
    {"name": "برلمان 25", "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/برلمان%2025?alt=rss", "image": "barlman.png", "text_color": "white"},
    {"name": "رياضة", "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/رياضة?alt=rss", "image": "sport.png", "text_color": "black"},
    {"name": "علوم وتكنولوجيا", "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/علوم%20وتكنولوجيا?alt=rss", "image": "tecno.png", "text_color": "black"},
    {"name": "صحة وفن", "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/صحة%20وفن?alt=rss", "image": "art.png", "text_color": "black"}
]

# ============================
# إعدادات عامة
# ============================
FONT_FILE = "29ltbukrabolditalic.otf"

CANVAS_W = 1080
CANVAS_H = 1080

TEXT_LEFT = 55
TEXT_RIGHT = 1030
TEXT_TOP = 765
TEXT_BOTTOM = 980

MAX_WIDTH = TEXT_RIGHT - TEXT_LEFT
MAX_HEIGHT = TEXT_BOTTOM - TEXT_TOP
CENTER_X = TEXT_LEFT + MAX_WIDTH // 2

POSTED_FILE = "posted_articles.txt"
FEED_INDEX_FILE = "last_feed_index.txt"
LOG_FILE = "publish_log.txt"

PAGE_ID = os.getenv("PAGE_ID", "").strip()
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "").strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos"

# ============================
# أدوات مساعدة
# ============================
def get_next_feed_index():
    try:
        with open(FEED_INDEX_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0

def save_next_feed_index(i):
    with open(FEED_INDEX_FILE, "w") as f:
        f.write(str(i))

def write_log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] {msg}\n")

# ============================
# تنسيق النص
# ============================
def wrap_text(text, draw, canvas):
    words = text.split()
    lines, current = [], []

    for word in words:
        test = current + [word]
        shaped = get_display(arabic_reshaper.reshape(" ".join(test)))
        if draw.get_font_metrics(canvas, shaped).text_width <= MAX_WIDTH:
            current = test
        else:
            lines.append(get_display(arabic_reshaper.reshape(" ".join(current))))
            current = [word]

    if current:
        lines.append(get_display(arabic_reshaper.reshape(" ".join(current))))
    return lines

def fit_text(text, canvas):
    size = 60
    while size >= 24:
        with Drawing() as d:
            d.font = FONT_FILE
            d.font_size = size
            lines = wrap_text(text, d, canvas)
            if len(lines) * size * 1.3 <= MAX_HEIGHT:
                return lines, size, int(size * 1.3)
        size -= 2
    return lines, 24, int(24 * 1.3)

# ============================
# التنفيذ الرئيسي
# ============================
def main():
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r", encoding="utf-8") as f:
            posted = f.read().splitlines()

    start_index = get_next_feed_index()

    for offset in range(len(FEEDS)):
        feed_index = (start_index + offset) % len(FEEDS)
        feed_data = FEEDS[feed_index]

        feed = feedparser.parse(feed_data["url"])
        if not feed.entries:
            continue

        for entry in feed.entries:
            title = re.sub("<.*?>", "", entry.title).strip()
            h = hashlib.md5(title.encode("utf-8")).hexdigest()

            if h in posted:
                continue

            summary = re.sub("<.*?>", "", entry.summary).strip()

            caption = process_sensitive_text(
                f"{title}\n\n{' '.join(summary.split()[:40])}...\n\n",
                CAPTION_SEPARATORS,
                True
            )
            caption += "\n👇 تابع الخبر 👇\n" + entry.link

            safe_title = process_sensitive_text(title, IMAGE_SEPARATORS)

            with Image(width=CANVAS_W, height=CANVAS_H, background=Color("white")) as canvas:

                match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                if match:
                    try:
                        r = requests.get(match.group(1), timeout=10)
                        with Image(blob=r.content) as art:
                            art.transform(resize="1080x715^")
                            art.extent(1080, 715)
                            canvas.composite(art, 0, 0)
                    except:
                        pass

                with Image(filename=feed_data["image"]) as overlay:
                    overlay.transform(resize="1080x")
                    canvas.composite(overlay, 0, 0)

                lines, font_size, line_height = fit_text(safe_title, canvas)
                y = TEXT_TOP

                with Drawing() as d:
                    d.font = FONT_FILE
                    d.font_size = font_size
                    d.fill_color = Color(feed_data["text_color"])
                    d.text_alignment = "center"

                    for line in lines:
                        d.text(CENTER_X, y, line)
                        y += line_height

                    d(canvas)

                canvas.save(filename="final.png")

            # === نشر الصورة كمنشور حقيقي ===
            with open("final.png", "rb") as img:
                res = requests.post(
                    FB_URL,
                    data={
                        "access_token": PAGE_ACCESS_TOKEN,
                        "message": caption,
                        "published": "true"
                    },
                    files={"source": img}
                )

            if res.status_code == 200:
                with open(POSTED_FILE, "a", encoding="utf-8") as f:
                    f.write(h + "\n")
                save_next_feed_index(feed_index + 1)
                write_log(f"تم النشر: {title}")
                print("✅ تم النشر بنجاح")
                return

    print("⚠️ لا يوجد أخبار جديدة")

# ============================
if __name__ == "__main__":
    main()
