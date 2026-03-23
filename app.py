from flask import Flask, render_template, request, redirect, url_for
import os
import uuid
import sqlite3
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

import qrcode
import cloudinary
import cloudinary.uploader
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 6 * 1024 * 1024

cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET"),
)

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
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")

    print("DEBUG sender exists:", bool(sender))
    print("DEBUG password exists:", bool(password))
    print("DEBUG to_email:", to_email)

    if not sender or not password:
        print("Email credentials missing")
        return False

    if not to_email:
        print("Recipient email missing")
        return False

    try:
        msg = MIMEText(
            f"Your wish is ready!\n\n"
            f"Open it here:\n{wish_url}\n\n"
            f"Made with Wish Away"
        )

        msg["Subject"] = "Your Wish is Ready!"
        msg["From"] = sender
        msg["To"] = to_email

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        
        server.ehlo()
        server.starttls()
        server.ehlo()

        server.login(sender, password)
        server.send_message(msg)
        server.quit()

        print("Email sent successfully")
        return True

    except Exception as e:
        print("Email error:", e)
        return False


# ---------- SAFE FILE CHECK ----------
def get_file_size(file_obj):
    try:
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        return size
    except Exception:
        return 0


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
            print("Sending scheduled wish:", wid)

            video = None

            cur.execute(
                "UPDATE wishes SET video=?, sent=1 WHERE id=?",
                (video, wid)
            )

            if email:
                send_email(email, f"https://wish-away.onrender.com/wish/{wid}")

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
        try:
            rec = request.form.get("receiver", "").strip()
            msg = request.form.get("message", "").strip()
            occ = request.form.get("occasion", "").strip()
            email = request.form.get("email", "").strip()
            sch = request.form.get("schedule_time", "").strip()
            template = request.form.get("template", "minimal").strip()

            photo = request.files.get("photo")
            voice = request.files.get("voice")

            p = None
            v = None
            video = None

            # ---------- PHOTO ----------
            if photo and photo.filename:
                try:
                    photo.seek(0, os.SEEK_END)
                    size = photo.tell()
                    photo.seek(0)

                    if size > 5 * 1024 * 1024:
                        return "Photo too large"

                    result = cloudinary.uploader.upload(photo)
                    p = result.get("secure_url")

                except Exception as e:
                    print("Photo error:", e)

            # ---------- VOICE ----------
            if voice and voice.filename:
                try:
                    voice.seek(0, os.SEEK_END)
                    size = voice.tell()
                    voice.seek(0)

                    if size > 10 * 1024 * 1024:
                        return "Voice too large"

                    result = cloudinary.uploader.upload(
                        voice,
                        resource_type="video"
                    )
                    v = result.get("secure_url")

                except Exception as e:
                    print("Voice error:", e)

            wid = str(uuid.uuid4())[:8]

            sent_value = 0 if sch else 1

            conn = sqlite3.connect("wishes.db")
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO wishes
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                wid, rec, msg, occ,
                p, video, v,
                sch, email,
                sent_value,
                template
            ))

            conn.commit()
            conn.close()

            if not sch and email:
                send_email(email, f"https://wish-away.onrender.com/wish/{wid}")

            return redirect(url_for("show", wish_id=wid))

        except Exception as e:
            print("Create error:", e)
            return "Something went wrong"

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
        return "Not found", 404

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
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)