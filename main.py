# -*- coding: utf-8 -*-
import feedparser
import requests
import hashlib
import os
import re
from html2image import Html2Image
import subprocess

# ============================
# الإعدادات
# ============================
RSS_URL = "https://qenanews-24.blogspot.com/feeds/posts/default?alt=rss"
BG_PATH = "BG.png"
LOGO_PATH = "logo1.png"

PAGE_ID = str(os.getenv("PAGE_ID", "")).strip()
PAGE_ACCESS_TOKEN = str(os.getenv("PAGE_ACCESS_TOKEN", "")).strip()
FB_URL = f"https://graph.facebook.com/v19.0/{PAGE_ID}/photos" if PAGE_ID else None
POSTED_FILE = "posted_articles.txt"

# إعداد محرك الصور (يستخدم متصفح داخلي)
hti = Html2Image(size=(1080, 1080))

# ============================
# تصميم الخبر (HTML + CSS)
# ============================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@700&display=swap" rel="stylesheet">
    <style>
        body {{
            margin: 0; padding: 0; width: 1080px; height: 1080px;
            background: url('file://{bg_abs_path}') no-repeat;
            font-family: 'Cairo', sans-serif;
        }}
        .article-img {{
            position: absolute;
            top: 185px; left: 112px;
            width: 855px; height: 460px;
            object-fit: cover;
            border-radius: 5px;
        }}
        .title-container {{
            position: absolute;
            top: 725px; left: 110px;
            width: 850px; height: 160px;
            display: flex;
            align-items: center;
            justify-content: center;
            direction: rtl;
            text-align: center;
        }}
        .title-text {{
            font-size: 42px;
            color: #000;
            line-height: 1.4;
            margin: 0;
            padding: 0 10px;
        }}
    </style>
</head>
<body>
    <img src="{article_img_url}" class="article-img">
    <div class="title-container">
        <h1 class="title-text">{title}</h1>
    </div>
</body>
</html>
"""

def main():
    if not FB_URL: return
    
    feed = feedparser.parse(RSS_URL)
    posted = []
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f: posted = f.read().splitlines()

    for entry in feed.entries:
        title = re.sub("<.*?>", "", entry.title)
        h = hashlib.md5(title.encode("utf-8")).hexdigest()
        if h in posted: continue

        # جلب صورة المقال
        img_url = ""
        try:
            match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
            img_url = match.group(1) if match else "file://" + os.path.abspath(LOGO_PATH)
        except:
            img_url = "file://" + os.path.abspath(LOGO_PATH)

        # تجهيز الـ HTML
        bg_abs_path = os.path.abspath(BG_PATH)
        html_content = HTML_TEMPLATE.format(
            bg_abs_path=bg_abs_path,
            article_img_url=img_url,
            title=title
        )

        # التقاط الصورة
        print(f"📸 جاري توليد صورة الخبر: {title[:30]}...")
        hti.screenshot(html_str=html_content, save_as='final.png')

        # النشر
        with open("final.png", "rb") as f:
            res = requests.post(FB_URL, data={"access_token": PAGE_ACCESS_TOKEN, "caption": title}, files={"source": f})
        
        if res.status_code == 200:
            with open(POSTED_FILE, "a") as f: f.write(h + "\n")
            print("✅ تم النشر!")
            # تحديث GitHub
            subprocess.run(["git", "config", "--global", "user.email", "bot@github.com"])
            subprocess.run(["git", "config", "--global", "user.name", "Bot"])
            subprocess.run(["git", "add", POSTED_FILE])
            subprocess.run(["git", "commit", "-m", "update log"], check=False)
            subprocess.run(["git", "push"], check=False)
            break

if __name__ == "__main__":
    main()
