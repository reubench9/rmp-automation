import os
import io
import json
import random
import textwrap
import zipfile
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import anthropic

# ── Credentials ───────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
GOOGLE_CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
FITNESS_FOLDER_ID    = os.environ["FITNESS_FOLDER_ID"]
BUSINESS_FOLDER_ID   = os.environ["BUSINESS_FOLDER_ID"]
OUTPUT_FOLDER_ID     = os.environ["OUTPUT_FOLDER_ID"]

FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
IG_SIZE   = (1080, 1080)

FITNESS_TOPICS = [
    "How to improve your running",
    "How to stay on track when going on holiday",
    "Cycling for beginners in Dubai",
    "How to build muscle eating normal food",
    "Running in the Dubai heat — survival guide",
    "Zone 2 training explained simply",
    "How to get your first pull up",
    "Nutrition basics for endurance athletes",
    "How to recover faster after training",
    "Al Qudra cycling tips for beginners",
]

BUSINESS_TOPICS = [
    "How to film yourself better",
    "How to talk confidently on camera",
    "How to grow from 0 followers",
    "How to pitch yourself to brands",
    "How to turn your hobby into income",
    "Content creation tips for beginners",
    "How to build a personal brand with no budget",
    "How to land your first sponsorship",
    "Mindset shifts every new entrepreneur needs",
    "How to stay consistent when nobody is watching",
]

SYSTEM_FITNESS = """You write Instagram carousel content for @reubenhurter, a Dubai fitness/cycling/running creator.
Return ONLY valid JSON — no markdown fences, no extra text.
{
  "hook": "punchy title max 8 words",
  "slides": [
    {"heading": "max 6 words", "body": "1-2 sentences max 25 words"},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."}
  ],
  "cta": "final slide CTA max 10 words",
  "caption": "Full IG caption — conversational, authentic, 3-5 lines then blank line then 20 hashtags mixing Dubai fitness cycling running lifestyle tags"
}"""

SYSTEM_BUSINESS = """You write Instagram carousel content for Radical Marketing Productions, a Dubai creative brand for entrepreneurs.
Return ONLY valid JSON — no markdown fences, no extra text.
{
  "hook": "punchy title max 8 words",
  "slides": [
    {"heading": "max 6 words", "body": "1-2 sentences max 25 words"},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."}
  ],
  "cta": "final slide CTA max 10 words",
  "caption": "Full IG caption — punchy, real talk, motivational, 3-5 lines then blank line then 20 hashtags mixing Dubai business marketing personal brand entrepreneur tags"
}"""


# ── Google Drive ──────────────────────────────────────────────────────────────

def get_drive():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def list_images(drive, folder_id, limit=15):
    res = drive.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false",
        fields="files(id,name)", pageSize=limit, orderBy="createdTime desc"
    ).execute()
    return res.get("files", [])


def download_img(drive, file_id):
    req = drive.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl  = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def make_folder(drive, name, parent):
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}
    return drive.files().create(body=meta, fields="id").execute()["id"]


def upload_img(drive, img, name, folder_id):
    tmp = f"/tmp/{name}"
    img.save(tmp, "JPEG", quality=95)
    drive.files().create(
        body={"name": name, "parents": [folder_id]},
        media_body=MediaFileUpload(tmp, mimetype="image/jpeg"),
        fields="id"
    ).execute()


def upload_txt(drive, text, name, folder_id):
    tmp = f"/tmp/{name}"
    with open(tmp, "w") as f:
        f.write(text)
    drive.files().create(
        body={"name": name, "parents": [folder_id]},
        media_body=MediaFileUpload(tmp, mimetype="text/plain"),
        fields="id"
    ).execute()


# ── AI Content ────────────────────────────────────────────────────────────────

def generate(pillar, topic):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-5", max_tokens=1200,
        system=SYSTEM_FITNESS if pillar == "fitness" else SYSTEM_BUSINESS,
        messages=[{"role": "user", "content": f"Topic: {topic}"}]
    )
    raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
    return json.loads(raw)


# ── Image Composition ─────────────────────────────────────────────────────────

def square_crop(img):
    w, h  = img.size
    side  = min(w, h)
    left  = (w - side) // 2
    top   = (h - side) // 2
    return img.crop((left, top, left+side, top+side)).resize(IG_SIZE, Image.LANCZOS)


def add_text_bar(img, lines, position="bottom", sz_head=56, sz_body=34):
    img   = img.copy()
    W, H  = img.size
    pad   = 44
    try:
        fh = ImageFont.truetype(FONT_BOLD, sz_head)
        fb = ImageFont.truetype(FONT_REG,  sz_body)
    except:
        fh = fb = ImageFont.load_default()
    draw = ImageDraw.Draw(img)
    wrapped = []
    for i, line in enumerate(lines):
        font   = fh if i == 0 else fb
        max_ch = int((W - pad*2) / (sz_head*0.54)) if i == 0 else int((W - pad*2) / (sz_body*0.54))
        for wl in textwrap.wrap(line, width=max(max_ch, 10)):
            wrapped.append((wl, font, i == 0))
    spacing = 14
    heights = [draw.textbbox((0,0), t, font=f)[3] - draw.textbbox((0,0), t, font=f)[1]
               for t, f, _ in wrapped]
    bar_h   = sum(heights) + spacing*(len(heights)-1) + pad*2
    bar_top = 0 if position == "top" else H - bar_h
    overlay = Image.new("RGBA", img.size, (0,0,0,0))
    ImageDraw.Draw(overlay).rectangle([(0, bar_top),(W, bar_top+bar_h)], fill=(0,0,0,185))
    img  = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    y = bar_top + pad
    for text, font, is_head in wrapped:
        bb  = draw.textbbox((0,0), text, font=font)
        tw, th = bb[2]-bb[0], bb[3]-bb[1]
        col = (255,255,255) if is_head else (210,210,210)
        draw.text(((W-tw)//2, y), text, font=font, fill=col)
        y += th + spacing
    return img


def title_slide(photo, hook):
    return add_text_bar(square_crop(photo), [hook], "bottom", sz_head=60)

def content_slide(photo, heading, body, idx):
    pos = "top" if idx % 2 == 0 else "bottom"
    return add_text_bar(square_crop(photo), [heading, body], pos, sz_head=48, sz_body=33)

def cta_slide(photo, cta):
    img     = square_crop(photo)
    overlay = Image.new("RGBA", img.size, (0,0,0,90))
    img     = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return add_text_bar(img, [cta], "bottom", sz_head=52)


# ── Build Carousel ────────────────────────────────────────────────────────────

def build_carousel(drive, photos, content, label, out_folder_id):
    print(f"\n  📸 {label}")
    fid = make_folder(drive, label, out_folder_id)

    def photo(i):
        return download_img(drive, photos[i % len(photos)]["id"])

    upload_img(drive, title_slide(photo(0), content["hook"]), "slide_01_title.jpg", fid)
    print("     ✅ Slide 1 — Title")

    for i, s in enumerate(content["slides"][:4]):
        upload_img(drive, content_slide(photo(i+1), s["heading"], s["body"], i),
                   f"slide_0{i+2}_tip.jpg", fid)
        print(f"     ✅ Slide {i+2} — {s['heading']}")

    n = len(content["slides"][:4]) + 2
    upload_img(drive, cta_slide(photo(n), content["cta"]), f"slide_0{n}_cta.jpg", fid)
    print(f"     ✅ Slide {n} — CTA")

    upload_txt(drive, content["caption"], "CAPTION_AND_HASHTAGS.txt", fid)
    print("     ✅ Caption saved")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    week = datetime.now().strftime("%Y-%m-%d")
    print(f"\n🚀 RMP Automation — week of {week}\n")

    drive      = get_drive()
    out_folder = make_folder(drive, f"📅 Posts — Week of {week}", OUTPUT_FOLDER_ID)
    print(f"📁 Weekly folder created in Drive\n")

    fit = list_images(drive, FITNESS_FOLDER_ID, 15)
    biz = list_images(drive, BUSINESS_FOLDER_ID, 8)
    random.shuffle(fit)
    random.shuffle(biz)

    if len(fit) >= 3:
        t1 = random.choice(FITNESS_TOPICS)
        build_carousel(drive, fit[:6], generate("fitness", t1),
                       f"POST 1 — Monday (Fitness) — {t1}", out_folder)
    else:
        print("⚠️  Need at least 3 fitness photos.")

    remaining = fit[6:] if len(fit) > 6 else fit
    if len(remaining) >= 3:
        t2 = random.choice([t for t in FITNESS_TOPICS if t != t1])
        build_carousel(drive, remaining, generate("fitness", t2),
                       f"POST 2 — Wednesday (Fitness) — {t2}", out_folder)
    else:
        print("⚠️  Not enough fitness photos for 2nd post.")

    if len(biz) >= 3:
        t3 = random.choice(BUSINESS_TOPICS)
        build_carousel(drive, biz[:6], generate("business", t3),
                       f"POST 3 — Friday (Business) — {t3}", out_folder)
    else:
        print("⚠️  Need at least 3 business photos.")

    print(f"\n✅ All done! Check Google Drive → '📅 Posts — Week of {week}'\n")


if __name__ == "__main__":
    main()
