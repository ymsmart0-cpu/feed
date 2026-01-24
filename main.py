# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re

from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color

import arabic_reshaper
from bidi.algorithm import get_display

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

        feed = feedparser.parse(feed_data["url"])
        if not feed.entries:
            continue

        for entry in feed.entries:
            title = re.sub("<.*?>", "", entry.title).strip()
            h = hashlib.md5(title.encode("utf-8")).hexdigest()
            if h in posted:
                continue

            summary = re.sub("<.*?>", "", entry.summary).strip()

            caption = (
                f"{title}\n\n"
                f"{' '.join(summary.split()[:40])}...\n\n"
                f"{entry.link}"
            )

            with Image(width=CANVAS_W, height=CANVAS_H, background=Color("white")) as canvas:

                # ===== صورة القسم (Overlay) =====
                with Image(filename=feed_data["image"]) as overlay:
                    overlay.transform(resize="1080x1080^")
                    overlay.extent(
                        1080,
                        1080,
                        (overlay.width - 1080) // 2,
                        (overlay.height - 1080) // 2
                    )
                    canvas.composite(overlay, 0, 0)

                # ===== صورة الخبر =====
                try:
                    match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
                    if match:
                        r = requests.get(match.group(1), timeout=10)
                        with Image(blob=r.content) as art:
                            art.transform(resize="1080x715^")
                            art.extent(
                                1080,
                                715,
                                (art.width - 1080) // 2,
                                (art.height - 715) // 2
                            )
                            canvas.composite(art, 0, NEWS_Y)
                except:
                    pass

                # ===== النص =====
                lines, font_size, line_height = fit_text(title, canvas)
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

            # ===== نشر على فيسبوك =====
            with open("final.png", "rb") as img:
                res = requests.post(
                    FB_URL,
                    data={"access_token": PAGE_ACCESS_TOKEN, "caption": caption},
                    files={"source": img}
                )

            if res.status_code == 200:
                with open(POSTED_FILE, "a", encoding="utf-8") as f:
                    f.write(h + "\n")

                save_next_feed_index((feed_index + 1) % feeds_count)
                print("✅ تم النشر بنجاح")
                return

    print("⚠️ لا يوجد أخبار جديدة")

if __name__ == "__main__":
    main()
