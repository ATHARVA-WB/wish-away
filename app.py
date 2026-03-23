from flask import Flask, render_template, request, redirect, url_for
import uuid
import sqlite3
import qrcode
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, AudioFileClip
from apscheduler.schedulers.background import BackgroundScheduler
import cloudinary
import cloudinary.uploader
import os
import requests
import io

cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET")
)
app = Flask(__name__)

UPLOAD_FOLDER = "static/uploads"
VIDEO_FOLDER = "static/videos"
AUDIO_FOLDER = "static/audio"
QR_FOLDER = "static/qr"
ASSETS_FOLDER = "static/assets"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
os.makedirs(ASSETS_FOLDER, exist_ok=True)


# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect("wishes.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wishes (
        id TEXT PRIMARY KEY,
        receiver TEXT,
        message TEXT,
        occasion TEXT,
        photo TEXT,
        video TEXT,
        voice TEXT,
        schedule_time TEXT,
        email TEXT,
        sent INTEGER,
        template TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------- EMAIL ----------
def send_email(to_email, wish_url):
    sender = "gatharva354@gmail.com"
    password = "rzgj jyjc kzif seay"

    msg = MIMEText(
        f"🎉 Your wish is ready!\n\n"
        f"Open it here:\n{wish_url}\n\n"
        f"Made with Wish Away ✨"
    )
    msg["Subject"] = "Your Wish is Ready!"
    msg["From"] = sender
    msg["To"] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print("📩 Email sent successfully")
    except Exception as e:
        print("Email error:", e)


# ---------- TEMPLATE TEXT IMAGE ----------
def create_text_image_template(msg, rec, wid, template):
    img = Image.new("RGBA", (720, 250), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 42)
    except Exception:
        font = ImageFont.load_default()

    text = f"{msg}\n\n— {rec}"

    if template == "love":
        color = (255, 120, 180)
    elif template == "birthday":
        color = (255, 220, 120)
    elif template == "celebration":
        color = (120, 255, 200)
    else:
        color = (255, 255, 255)

    draw.text((42, 42), text, font=font, fill=(0, 0, 0, 200))
    draw.text((40, 40), text, font=font, fill=color)

    path = f"{VIDEO_FOLDER}/text_{wid}.png"
    img.save(path)
    return path


# ---------- TEMPLATE ASSETS ----------
def get_template_assets(template):
    if template == "birthday":
        return {
            "bg": "static/assets/fireworks.mp4",
            "music": "static/assets/birthday.mp3"
        }
    if template == "love":
        return {
            "bg": "static/assets/love.mp4",
            "music": "static/assets/romantic.mp3"
        }
    if template == "celebration":
        return {
            "bg": "static/assets/party.mp4",
            "music": "static/assets/music.mp3"
        }
    return {
        "bg": "static/assets/fireworks.mp4",
        "music": "static/assets/music.mp3"
    }


# ---------- VIDEO ----------
from moviepy.audio.AudioClip import CompositeAudioClip

# 🔁 manual audio loop (fix for your moviepy version)
def loop_audio(clip, duration):
    clips = []
    total = 0

    while total < duration:
        clips.append(clip)
        total += clip.duration

    return CompositeAudioClip(clips).subclipped(0, duration)


def generate_wish_video(photo, rec, msg, wid, voice=None, template="minimal"):
    duration = 10
    assets = get_template_assets(template)

    bg = None
    final = None
    audio = None

    try:
        # 🎬 BACKGROUND
        bg = (
            VideoFileClip(assets["bg"])
            .subclipped(0, duration)
            .resized(height=720)
            .with_fps(30)
        )

        clips = [bg]

        # 🌫️ OVERLAY
        overlay_path = "static/assets/overlay.png"
        if os.path.exists(overlay_path):
            overlay = (
                ImageClip(overlay_path)
                .with_duration(duration)
                .resized(bg.size)
                .with_opacity(0.35)
            )
            clips.append(overlay)

        # 🖼️ PHOTO
        if photo:
            response = requests.get(photo)
            img_data = io.BytesIO(response.content)
            img = (
                ImageClip(img_data)
                .with_duration(duration - 2)
                .resized(height=320)
                .with_position("center")
                .resize(lambda t: 1 + 0.08 * t)
                .with_start(1)
            )
            clips.append(img)

        # 📝 TEXT
        text_img = create_text_image_template(msg, rec, wid, template)

        txt = (
            ImageClip(text_img)
            .with_duration(duration - 3)
            .with_position(("center", 520))
            .with_start(2)
            .crossfadein(1)
        )

        clips.append(txt)

        final = CompositeVideoClip(clips)

        # =========================
        # 🔊 AUDIO (FIXED)
        # =========================
        try:
            music = AudioFileClip(assets["music"])
            music = loop_audio(music, duration).volumex(0.4)

            if voice and os.path.exists(voice):
                voice_clip = AudioFileClip(voice)
                voice_clip = loop_audio(voice_clip, duration).volumex(1.6)

                audio = CompositeAudioClip([music, voice_clip])
            else:
                audio = music

            final = final.with_audio(audio)

        except Exception as e:
            print("Audio error:", e)

        # 🎬 EXPORT
        path = f"{VIDEO_FOLDER}/{wid}.mp4"

        final.write_videofile(
            path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=4,
            temp_audiofile=f"{VIDEO_FOLDER}/temp-{wid}.m4a",
            remove_temp=True
        )

        return f"static/videos/{wid}.mp4"

    except Exception as e:
        print("Video generation error:", e)
        return None

    finally:
        # 🔥 VERY IMPORTANT (fix crash)
        try:
            if final:
                final.close()
        except:
            pass

        try:
            if bg:
                bg.close()
        except:
            pass

        try:
            if audio:
                audio.close()
        except:
            pass


# ---------- SCHEDULER ----------
def check():
    conn = sqlite3.connect("wishes.db")
    cur = conn.cursor()

    now = datetime.now()

    cur.execute("""
        SELECT id, receiver, message, photo, voice, email, schedule_time, template
        FROM wishes
        WHERE sent = 0
    """)
    wishes = cur.fetchall()

    for wish in wishes:
        wid, rec, msg, photo, voice, email, stime, template = wish

        if not stime:
            continue

        try:
            scheduled_dt = datetime.strptime(stime, "%Y-%m-%dT%H:%M")
        except Exception:
            continue

        if scheduled_dt <= now:
            print("⏰ Sending scheduled wish:", wid)

            photo_path = f"{UPLOAD_FOLDER}/{photo}" if photo else None
            voice_path = f"{AUDIO_FOLDER}/{voice}" if voice else None

            video = generate_wish_video(
                photo_path,
                rec,
                msg,
                wid,
                voice_path,
                template or "minimal"
            )

            cur.execute(
                "UPDATE wishes SET video=?, sent=1 WHERE id=?",
                (video, wid)
            )

            if email:
                send_email(email, f"http://127.0.0.1:5000/wish/{wid}")

    conn.commit()
    conn.close()


scheduler = BackgroundScheduler()
scheduler.add_job(check, "interval", seconds=30)
scheduler.start()


# ---------- ROUTES ----------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        rec = request.form.get("receiver")
        msg = request.form.get("message")
        occ = request.form.get("occasion")
        email = request.form.get("email")
        sch = request.form.get("schedule_time")
        template = request.form.get("template") or "minimal"

        photo = request.files.get("photo")
        voice = request.files.get("voice")

        wid = str(uuid.uuid4())[:8]

        p = None
        v = None

        if photo and photo.filename:
            result = cloudinary.uploader.upload(photo)
            p = result["secure_url"]
            

        if voice and voice.filename:
            result = cloudinary.uploader.upload(voice, resource_type="video")
            v = result["secure_url"]

        video = None

        if not sch:
            video = generate_wish_video(
                p if p else None,
                rec,
                msg,
                wid,
                v if v else None,
                template
            )

        conn = sqlite3.connect("wishes.db")
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO wishes
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            wid,
            rec,
            msg,
            occ,
            p,
            video,
            v,
            sch,
            email,
            0,
            template
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("show", wish_id=wid))

    return render_template("create_wish.html")


@app.route("/wish/<wish_id>")
def show(wish_id):
    conn = sqlite3.connect("wishes.db")
    cur = conn.cursor()

    cur.execute("""
        SELECT receiver, message, occasion, photo, video, template
        FROM wishes
        WHERE id=?
    """, (wish_id,))
    wish = cur.fetchone()

    conn.close()

    if not wish:
        return "Not found"

    rec, msg, occ, photo, video, template = wish

    qr = qrcode.make(request.url)
    qr.save(f"{QR_FOLDER}/{wish_id}.png")

    return render_template(
        "create_wish.html",
        receiver=rec,
        message=msg,
        occasion=occ,
        photo=photo,
        video=video,
        template=template,
        qr_code=f"/static/qr/{wish_id}.png"
    )


if __name__ == "__main__":
    app.run()