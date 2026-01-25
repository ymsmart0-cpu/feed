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
# تحميل الكلمات الحساسة (إضافة)
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
# إعدادات روابط التغذية
# ============================
FEEDS = [
    {
        "name": "اخبار قنا",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/اخبار%20قنا?alt=rss",
        "image": "qena.png",
        "text_color": "white"
    },
    {
        "name": "حوادث",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/حوادث?alt=rss",
        "image": "news.png",
        "text_color": "white"
    },
    {
        "name": "برلمان 25",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/برلمان%2025?alt=rss",
        "image": "barlman.png",
        "text_color": "white"
    },
    {
        "name": "رياضة",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/رياضة?alt=rss",
        "image": "sport.png",
        "text_color": "black"
    },
    {
        "name": "علوم وتكنولوجيا",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/علوم%20وتكنولوجيا?alt=rss",
        "image": "tecno.png",
        "text_color": "black"
    },
    {
        "name": "صحة وفن",
        "url": "https://qenanews-24.blogspot.com/feeds/posts/default/-/صحة%20وفن?alt=rss",
        "image": "art.png",
        "text_color": "black"
    }
]

# ============================
# إعدادات عامة
# ============================
FONT_FILE = "29ltbukrabolditalic.otf"

CANVAS_W = 1080
CANVAS_H = 1080

NEWS_IMG_H = 715
NEWS_Y = 0

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
    if not os.path.exists(FEED_INDEX_FILE):
        return 0
    try:
        with open(FEED_INDEX_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return 0

def save_next_feed_index(i):
    with open(FEED_INDEX_FILE, "w") as f:
        f.write(str(i))

def write_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

# ============================
# تنسيق النص العربي
# ============================
def wrap_text(text, draw, canvas):
    words = text.split()
    lines = []
    current = []

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
    feeds_count = len(FEEDS)

    for offset in range(feeds_count):
        feed_index = (start_index + offset) % feeds_count
        feed_data = FEEDS[feed_index]

        write_log(f"🔎 فحص قسم: {feed_data['name']}")

        feed = feedparser.parse(feed_data["url"])
        if not feed.entries:
            write_log(f"⚠️ لا يوجد أخبار في قسم: {feed_data['name']}")
            continue

        for entry in feed.entries:
            title = re.sub("<.*?>", "", entry.title).strip()
            h = hashlib.md5(title.encode("utf-8")).hexdigest()

            if h in posted:
                write_log(
                    f"⏭️ متخطّي (منشور سابقًا) | قسم: {feed_data['name']} | عنوان: {title}"
                )
                continue

            write_log(f"🆕 خبر جديد | قسم: {feed_data['name']} | عنوان: {title}")

            summary = re.sub("<.*?>", "", entry.summary).strip()

            raw_caption = (
                f"{title}\n\n"
                f"{' '.join(summary.split()[:40])}...\n\n"
            )

            caption = process_sensitive_text(
                raw_caption,
                CAPTION_SEPARATORS,
                limit_once=True
            )
            caption += "\n\n👇 تابع كامل الخبر من هنا 👇\n" + entry.link

            safe_title_image = process_sensitive_text(
                title,
                IMAGE_SEPARATORS,
                limit_once=False
            )

            with Image(width=CANVAS_W, height=CANVAS_H, background=Color("white")) as canvas:

                try:
                    match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                    if match:
                        r = requests.get(match.group(1), timeout=10)
                        with Image(blob=r.content) as art:
                            art.transform(resize="1080x715^")
                            art.extent(
                                1080, 715,
                                (art.width - 1080) // 2,
                                (art.height - 715) // 2
                            )
                            canvas.composite(art, 0, NEWS_Y)
                except:
                    pass

                with Image(filename=feed_data["image"]) as overlay:
                    overlay.alpha_channel = 'activate'
                    overlay.transform(resize="1080x")
                    canvas.composite(overlay, 0, 0, operator='over')

                lines, font_size, line_height = fit_text(safe_title_image, canvas)
                start_y = TEXT_TOP + (MAX_HEIGHT - len(lines) * line_height) // 2

                with Drawing() as draw:
                    draw.font = FONT_FILE
                    draw.font_size = font_size
                    draw.fill_color = Color(feed_data["text_color"])
                    draw.text_alignment = "center"

                    y = start_y + int(font_size * 0.8)
                    for line in lines:
                        draw.text(CENTER_X, y, line)
                        y += line_height

                    draw(canvas)

                canvas.save(filename="final.png")

            with open("final.png", "rb") as img:
                res = requests.post(
                    FB_URL,
                    data={
                        "access_token": PAGE_ACCESS_TOKEN,
                        "caption": caption
                    },
                    files={"source": img}
                )

            if res.status_code == 200:
                with open(POSTED_FILE, "a", encoding="utf-8") as f:
                    f.write(h + "\n")

                next_index = (feed_index + 1) % feeds_count
                save_next_feed_index(next_index)

                write_log(
                    f"✅ تم النشر بنجاح | قسم: {feed_data['name']} | عنوان: {title}"
                )
                print("✅ تم النشر بنجاح")
                return
            else:
                write_log(
                    f"❌ فشل النشر | قسم: {feed_data['name']} | عنوان: {title} | Status: {res.status_code}"
                )

    write_log("⚠️ لا يوجد أخبار جديدة في أي قسم")
    print("⚠️ لا يوجد أخبار جديدة")

if __name__ == "__main__":
    main()
