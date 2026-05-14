import os
import io
import json
import random
import textwrap
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import anthropic

ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_REFRESH_TOKEN = os.environ["GOOGLE_REFRESH_TOKEN"]
GOOGLE_CLIENT_ID     = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
OUTPUT_FOLDER_ID     = os.environ["OUTPUT_FOLDER_ID"]

FOLDER_CYCLING          = os.environ["FOLDER_CYCLING"]
FOLDER_RUNNING          = os.environ["FOLDER_RUNNING"]
FOLDER_GYM_WEIGHTS      = os.environ["FOLDER_GYM_WEIGHTS"]
FOLDER_NUTRITION        = os.environ["FOLDER_NUTRITION"]
FOLDER_CONTENT_CREATION = os.environ["FOLDER_CONTENT_CREATION"]

FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
IG_SIZE   = (1080, 1080)

FITNESS_TOPICS = [
    {"topic": "How to improve your running",               "folder": "running"},
    {"topic": "How to stay on track training on holiday",  "folder": "running"},
    {"topic": "Cycling for beginners in Dubai",            "folder": "cycling"},
    {"topic": "How to build muscle eating normal food",    "folder": "gym"},
    {"topic": "Running in the Dubai heat — survival guide","folder": "running"},
    {"topic": "Zone 2 training — why slow makes you fast", "folder": "cycling"},
    {"topic": "How to get your first pull up",             "folder": "gym"},
    {"topic": "What to eat before a long ride or run",     "folder": "nutrition"},
    {"topic": "How to recover faster after hard training", "folder": "gym"},
    {"topic": "Al Qudra cycling tips for beginners",       "folder": "cycling"},
    {"topic": "Progressive overload — the only rule that matters", "folder": "gym"},
    {"topic": "Why most people never see results",         "folder": "gym"},
    {"topic": "How to run further without burning out",    "folder": "running"},
    {"topic": "Nutrition basics every athlete needs to know","folder": "nutrition"},
]

BUSINESS_TOPICS = [
    {"topic": "How to film yourself better on your phone",   "folder": "content"},
    {"topic": "How to talk confidently on camera",           "folder": "content"},
    {"topic": "How to grow from 0 followers organically",    "folder": "content"},
    {"topic": "How to pitch yourself to brands",             "folder": "content"},
    {"topic": "How to turn your hobby into income",          "folder": "content"},
    {"topic": "Content creation tips for complete beginners","folder": "content"},
    {"topic": "How to build a personal brand with no budget","folder": "content"},
    {"topic": "How to land your first brand sponsorship",    "folder": "content"},
    {"topic": "Mindset shifts every new entrepreneur needs", "folder": "content"},
    {"topic": "How to stay consistent when nobody is watching","folder": "content"},
]

SYSTEM_FITNESS = """You are writing high-value Instagram carousel content for @reubenhurter — a Dubai-based fitness, cycling and running creator with a real, authentic voice.

His backstory: grew up in South Africa, used lockdown to get serious about fitness, moved to Dubai with no plan and built everything from scratch. He trains hard, cycles Al Qudra, runs in the heat, and talks straight.

Generate content that gives REAL value — not generic tips. Think like a knowledgeable training partner giving honest advice.

Return ONLY valid JSON — no markdown, no extra text:
{
  "hook": "Scroll-stopping title. Bold, direct, max 8 words. Make someone STOP scrolling.",
  "slides": [
    {"heading": "Short punchy heading max 6 words", "body": "One concrete, specific insight. No fluff. Max 20 words. Real advice someone can use TODAY."},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."}
  ],
  "cta": "Save this / Share with someone who needs it — max 10 words",
  "caption": "Write a DEEP VALUE caption. Structure: 1) Hook line that makes them stop (not the same as the slide hook). 2) Brief personal angle from Reuben — why this matters, real experience. 3) The actual value — go deeper than the slides. Expand each point with specific detail, numbers, real examples. 4) What most people get wrong about this topic. 5) One honest closing line. 6) Blank line. 7) 25 hashtags — mix of: Dubai fitness niche tags, cycling/running specific, broad fitness, lifestyle Dubai. No spaces between tags. Caption should feel like it was written by a real person who actually trains, not an AI."
}"""

SYSTEM_BUSINESS = """You are writing high-value Instagram carousel content for Radical Marketing Productions — Reuben Hurter's Dubai-based creative brand helping people build businesses and personal brands from scratch.

Reuben's story: South African, worked as a financial adviser cold-calling strangers (hated it), bought a camera, taught himself video, got his first client, visited Dubai, fell in love, moved with no clear plan. Now builds brands, shoots content, grows Instagrams. Real experience, no theory.

Generate content that gives REAL value — not motivational fluff. Practical, honest, from someone who actually did it.

Return ONLY valid JSON — no markdown, no extra text:
{
  "hook": "Scroll-stopping title. Bold, direct, max 8 words. Make someone STOP scrolling.",
  "slides": [
    {"heading": "Short punchy heading max 6 words", "body": "One concrete, actionable insight. No fluff. Max 20 words. Something they can do TODAY."},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."}
  ],
  "cta": "Save this / Follow for more — max 10 words",
  "caption": "Write a DEEP VALUE caption. Structure: 1) Hook — real talk opener, makes them feel seen. 2) Personal angle — Reuben's real experience with this (cold calling, moving to Dubai, building from zero). 3) Deep value — go further than the slides. Specific tactics, real numbers, what actually works. 4) The mistake most people make. 5) Honest closing line — no fake motivation. 6) Blank line. 7) 25 hashtags — mix of: Dubai entrepreneur, personal brand, content creator, marketing, business growth tags. Caption should sound like a real person sharing hard-earned lessons, not a template."
}"""


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


def get_folder_id(folder_key):
    mapping = {
        "cycling":  FOLDER_CYCLING,
        "running":  FOLDER_RUNNING,
        "gym":      FOLDER_GYM_WEIGHTS,
        "nutrition":FOLDER_NUTRITION,
        "content":  FOLDER_CONTENT_CREATION,
    }
    return mapping[folder_key]


def list_images(drive, folder_id, limit=20):
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
    raw = buf.read()
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


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


def generate(pillar, topic):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-5", max_tokens=2000,
        system=SYSTEM_FITNESS if pillar == "fitness" else SYSTEM_BUSINESS,
        messages=[{"role": "user", "content": f"Topic: {topic}"}]
    )
    raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
    return json.loads(raw)


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


def pick_post(drive, topic_list, used_topics):
    available = [t for t in topic_list if t["topic"] not in used_topics]
    if not available:
        available = topic_list
    chosen = random.choice(available)
    photos = list_images(drive, get_folder_id(chosen["folder"]), 20)
    random.shuffle(photos)
    return chosen["topic"], photos


def main():
    week = datetime.now().strftime("%Y-%m-%d")
    print(f"\n🚀 RMP Automation — week of {week}\n")

    drive      = get_drive()
    out_folder = make_folder(drive, f"📅 Posts — Week of {week}", OUTPUT_FOLDER_ID)
    print(f"📁 Weekly folder created\n")

    used = []

    # Post 1 — Monday fitness
    t1, p1 = pick_post(drive, FITNESS_TOPICS, used)
    used.append(t1)
    if len(p1) >= 3:
        build_carousel(drive, p1[:6], generate("fitness", t1),
                       f"POST 1 — Monday (Fitness) — {t1}", out_folder)
    else:
        print(f"⚠️  Not enough photos for: {t1}")

    # Post 2 — Wednesday fitness
    t2, p2 = pick_post(drive, FITNESS_TOPICS, used)
    used.append(t2)
    if len(p2) >= 3:
        build_carousel(drive, p2[:6], generate("fitness", t2),
                       f"POST 2 — Wednesday (Fitness) — {t2}", out_folder)
    else:
        print(f"⚠️  Not enough photos for: {t2}")

    # Post 3 — Friday business
    t3, p3 = pick_post(drive, BUSINESS_TOPICS, [])
    if len(p3) >= 3:
        build_carousel(drive, p3[:6], generate("business", t3),
                       f"POST 3 — Friday (Business) — {t3}", out_folder)
    else:
        print(f"⚠️  Not enough photos for: {t3}")

    print(f"\n✅ Done! Google Drive → '📅 Posts — Week of {week}'\n")


if __name__ == "__main__":
    main()
