"""
app.py — เว็บแอป ระบบลงทะเบียน/จองสถานที่ฝึกงาน (ไฟล์หลัก)
====================================================================
รูปแบบของระบบ (ตามความต้องการล่าสุด)
  - สถานที่ฝึกงานแยกเป็น "ประเภท" เช่น ฟิตเนส, อคาเดมี่, โรงเรียน, สถานที่ราชการ
  - นิสิต "พิมพ์ชื่อสถานที่ฝึกงานของตัวเอง" ได้ ระบบจะจำชื่อนั้นไว้ให้ใช้ครั้งต่อไป
  - ไม่มีวันที่และเวลา (ไม่ต้องจองเป็นช่วงเวลา)
  - ข้อมูลนิสิตที่ใช้มีแค่ ชื่อ / นามสกุล / รหัสนิสิต / เบอร์โทรศัพท์
  - แนบไฟล์ Resume (จำเป็น) และเจ้าหน้าที่เป็นผู้อนุมัติ

โครงสร้างไฟล์
  ส่วนที่ 1  ตั้งค่าเริ่มต้น + ตัวช่วยต่าง ๆ
  ส่วนที่ 2  หน้าแรก / สมัครสมาชิก / เข้าสู่ระบบ / ออกจากระบบ
  ส่วนที่ 3  หน้าของนิสิต (หน้าหลัก, ยื่นคำขอ, คำขอของฉัน, โปรไฟล์)
  ส่วนที่ 4  หน้าของเจ้าหน้าที่ (ภาพรวม, คำขอทั้งหมด, พิจารณา, รายชื่อนิสิต, สถานที่ฝึกงาน)
  ส่วนที่ 5  ดาวน์โหลดไฟล์ Resume

วิธีเปิดใช้งาน: ดับเบิลคลิกไฟล์  run.bat
"""
import os
import re
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

import database as db

# ======================================================================
# ส่วนที่ 1 : ตั้งค่าเริ่มต้น
# ======================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# เผื่อกรณีต้องการย้ายที่เก็บไฟล์แนบ (เช่นตอนทดสอบ) โดยไม่ต้องแก้โค้ด
UPLOAD_DIR = os.environ.get("BOOKING_UPLOAD_DIR") or os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXT = {"pdf", "doc", "docx"}          # นามสกุลไฟล์ที่อนุญาต
MAX_FILE_SIZE_MB = 15                         # ขนาดสูงสุดต่อ 1 ไฟล์ (MB)
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_TOTAL_MB = 60                             # ขนาดรวมของทั้งคำขอ (MB)
MAX_EXTRA_FILES = 2                           # เอกสารประกอบเพิ่มเติมได้ไม่เกินกี่ไฟล์

STATUS_LABELS = {
    "pending": "รออนุมัติ",
    "approved": "อนุมัติแล้ว",
    "rejected": "ไม่อนุมัติ",
    "cancelled": "ยกเลิกแล้ว",
}
STATUS_COLORS = {
    "pending": "warn",
    "approved": "ok",
    "rejected": "bad",
    "cancelled": "gray",
}
PHONE_RE = re.compile(r"^[0-9+\-() ]{9,20}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_TOTAL_MB * 1024 * 1024   # จำกัดขนาดคำขอทั้งหมด
# SECRET_KEY: ใช้จาก ENV ถ้ามี (Render จะสร้างให้) ไม่งั้น fallback ไป database.py
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or db.get_secret_key()
# คุกกี้เซิร์ฟเวอร์ปลอดภัย
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER") == "true",  # HTTPS บน Render
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

# Trust proxy headers (Render ใช้ reverse proxy)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# ----------------------------------------------------------------------
# Security Headers (ป้องกัน XSS, Clickjacking, MIME sniffing, Referrer leak)
# ----------------------------------------------------------------------
@app.after_request
def add_security_headers(response):
    # กัน iframe embedding (Clickjacking)
    response.headers["X-Frame-Options"] = "DENY"
    # กัน MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Referrer Policy: ส่ง origin เฉพาะข้าม origin
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Permissions Policy: ปิดฟีเจอร์ที่ไม่ใช้
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Content Security Policy (CSP) - ระบบนี้ไม่ใช้ inline script/CDN จึงเข้มงวดได้
    # style-src 'self' 'unsafe-inline' เพื่อให้ inline <style> ใน template ทำงาน
    csp = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["Content-Security-Policy"] = csp
    # HSTS (บังคับ HTTPS) - เปิดเฉพาะบน Render (มี HTTPS จริง)
    if os.environ.get("RENDER") == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# ---- ความปลอดภัยเพิ่มเติม (Cookie + Security Headers) ----
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,        # True ถ้าใช้ HTTPS
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),   # เซสชันหมดอายุ 8 ชม.
)

# Security headers ทุก response
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


def get_client_ip():
    """ดึง IP ของผู้ใช้ (คำนึงถึง reverse proxy)"""
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


# ---------------------- ตัวช่วยทั่วไป ----------------------
def current_user():
    """ผู้ใช้ที่กำลังล็อกอินอยู่ (หรือ None ถ้ายังไม่ล็อกอิน)"""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.query(
        "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,), one=True
    )


def is_full_admin(user=None):
    """เจ้าหน้าที่ผู้ดูแลระบบ (สิทธิ์เต็ม: จัดการบัญชี/สถานที่/แต่งตั้งผู้ดูแล)"""
    user = user if user is not None else current_user()
    return bool(user and user["role"] == "admin")


def is_reviewer(user=None):
    """ผู้ที่ตรวจสอบ/อนุมัติคำขอได้ = ผู้ดูแลระบบ หรือ นิสิตที่ถูกแต่งตั้งเป็น 'ผู้ดูแล'"""
    user = user if user is not None else current_user()
    return bool(user and (user["role"] == "admin" or user["can_review"]))


def login_required(view):
    """ถ้ายังไม่ล็อกอิน ให้เด้งไปหน้า login"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            session.clear()
            flash("กรุณาเข้าสู่ระบบก่อนใช้งานครับ", "warn")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """เฉพาะเจ้าหน้าที่ผู้ดูแลระบบ (admin) เท่านั้น — ถ้ายังไม่ล็อกอินให้ไปหน้าล็อกอินของเจ้าหน้าที่"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("กรุณาเข้าสู่ระบบด้วยบัญชีเจ้าหน้าที่ก่อนใช้งานครับ", "warn")
            return redirect(url_for("admin_login", next=request.path))
        if user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def reviewer_required(view):
    """ผู้ที่ตรวจสอบ/อนุมัติได้ = เจ้าหน้าที่ผู้ดูแลระบบ หรือ 'ผู้ดูแล' ที่ได้รับแต่งตั้ง"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            flash("กรุณาเข้าสู่ระบบก่อนใช้งานครับ", "warn")
            return redirect(url_for("admin_login", next=request.path))
        if not (user["role"] == "admin" or user["can_review"]):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    """สร้างรหัสกันการปลอมแปลงฟอร์ม (CSRF token)"""
    if "_csrf" not in session:
        session["_csrf"] = uuid.uuid4().hex
    return session["_csrf"]


@app.before_request
def protect_forms():
    """ทุกฟอร์มที่ส่งข้อมูล (POST) ต้องมี CSRF token ที่ถูกต้อง"""
    if request.method == "POST":
        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("_csrf"):
            abort(400, "รหัสความปลอดภัยของฟอร์มไม่ถูกต้อง กรุณาโหลดหน้าเว็บใหม่แล้วลองอีกครั้ง")


@app.context_processor
def inject_globals():
    """ตัวแปรที่ทุกหน้าเว็บเรียกใช้ได้เลย"""
    user = current_user()
    return {
        "current_user": user,
        "is_admin": bool(user and user["role"] == "admin"),
        "is_reviewer": bool(user and (user["role"] == "admin" or user["can_review"])),
        "csrf_token": csrf_token(),
        "STATUS_LABELS": STATUS_LABELS,
        "STATUS_COLORS": STATUS_COLORS,
        "MAX_FILE_MB": MAX_FILE_SIZE_MB,
        "active_endpoint": request.endpoint,
        "all_venue_types": db.query(
            "SELECT * FROM venue_types WHERE is_active = 1 ORDER BY sort_order, name"
        ),
        "all_venues": db.query(
            """SELECT v.*, t.name AS type_name, t.sort_order AS type_order
               FROM venues v JOIN venue_types t ON t.id = v.type_id
               WHERE v.is_active = 1
               ORDER BY t.sort_order, t.name, v.name"""
        ),
    }


@app.template_filter("datetime_th")
def datetime_th(value):
    """แปลง 2026-10-22 13:31:00 -> 22/10/2026 13:31"""
    if not value:
        return "-"
    try:
        d = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value
    return d.strftime("%d/%m/%Y %H:%M")


@app.template_filter("date_th")
def date_th(value):
    """แปลง 2026-10-22 -> 22/10/2026"""
    if not value:
        return "-"
    try:
        d = datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except ValueError:
        return value
    return d.strftime("%d/%m/%Y")


@app.errorhandler(403)
def error_403(e):
    user = current_user()
    return render_template(
        "error.html",
        code=403,
        message="คุณไม่มีสิทธิ์เข้าถึงหน้านี้",
        detail=("บัญชีนิสิตไม่สามารถใช้งานหน้าของเจ้าหน้าที่ได้"
                if user and user["role"] == "student" else
                "กรุณาเข้าสู่ระบบด้วยบัญชีที่เหมาะสม แล้วลองอีกครั้ง"),
    ), 403


@app.errorhandler(404)
def error_404(e):
    return render_template(
        "error.html", code=404, message="ไม่พบหน้าที่คุณต้องการ",
        detail="ลิงก์อาจพิมพ์ผิด หรือข้อมูลถูกลบไปแล้ว",
    ), 404


@app.errorhandler(RequestEntityTooLarge)
def error_too_large(e):
    flash(
        f"ไฟล์แนบใหญ่เกินไป (รวมกันต้องไม่เกิน {MAX_TOTAL_MB} MB) "
        f"และไม่เกิน {MAX_FILE_SIZE_MB} MB ต่อไฟล์",
        "bad",
    )
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------- ตัวช่วยเรื่องไฟล์แนบ ----------------------
def file_ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def save_upload(file_storage, booking_id, kind):
    """
    บันทึกไฟล์ที่นิสิตอัปโหลดลงโฟลเดอร์ uploads
    แล้วคืนค่าเป็น dict สำหรับบันทึกลงตาราง attachments
    """
    original_name = (file_storage.filename or "").strip()
    ext = file_ext(original_name)
    if ext not in ALLOWED_EXT:
        raise ValueError(f"ไฟล์ '{original_name}' ต้องเป็น PDF, DOC หรือ DOCX เท่านั้น")

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, stored_name)
    file_storage.save(path)

    size = os.path.getsize(path)
    if size == 0:
        os.remove(path)
        raise ValueError(f"ไฟล์ '{original_name}' ว่างเปล่า กรุณาตรวจสอบไฟล์อีกครั้ง")
    if size > MAX_FILE_SIZE:
        os.remove(path)
        raise ValueError(
            f"ไฟล์ '{original_name}' มีขนาด {size / 1024 / 1024:.2f} MB "
            f"เกินขีดจำกัด {MAX_FILE_SIZE_MB} MB กรุณาย่อขนาดไฟล์ก่อน"
        )

    return {
        "booking_id": booking_id,
        "kind": kind,
        "original_name": original_name,
        "stored_name": stored_name,
        "size_bytes": size,
        "mime_type": file_storage.mimetype or "",
    }


def insert_attachment(info):
    return db.execute(
        """INSERT INTO attachments
           (booking_id, kind, original_name, stored_name, size_bytes, mime_type)
           VALUES (:booking_id, :kind, :original_name, :stored_name, :size_bytes, :mime_type)""",
        info,
    )


def human_size(num):
    if not num:
        return "-"
    if num < 1024:
        return f"{num} B"
    if num < 1024 * 1024:
        return f"{num / 1024:.0f} KB"
    return f"{num / 1024 / 1024:.1f} MB"


def generate_booking_code():
    """สร้างเลขที่คำขอ เช่น BK2611-0007 (อิงปี-เดือนที่ยื่นคำขอ)"""
    prefix = "BK" + datetime.now().strftime("%y%m")
    row = db.query(
        "SELECT COUNT(*) AS c FROM bookings WHERE booking_code LIKE ?",
        (prefix + "-%",),
        one=True,
    )
    return f"{prefix}-{row['c'] + 1:04d}"


# ---------------------- ดึงข้อมูลคำขอ ----------------------
BOOKING_SELECT = """
    SELECT b.*,
           u.student_id  AS student_code,
           u.first_name  AS student_first,
           u.last_name   AS student_last,
           u.phone       AS student_phone,
           v.name        AS venue_name,
           t.id          AS type_id,
           t.name        AS type_name,
           r.first_name  AS reviewer_first,
           r.last_name   AS reviewer_last
    FROM bookings b
    JOIN users       u ON u.id = b.user_id
    JOIN venues      v ON v.id = b.venue_id
    JOIN venue_types t ON t.id = v.type_id
    LEFT JOIN users  r ON r.id = b.reviewed_by
"""


def get_booking(booking_id):
    return db.query(BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)


def get_attachments(booking_id):
    return db.query(
        "SELECT * FROM attachments WHERE booking_id = ? ORDER BY kind, id",
        (booking_id,),
    )


def venue_type_counts():
    return db.query(
        """SELECT t.name AS type_name, COUNT(b.id) AS c
           FROM venue_types t
           LEFT JOIN venues  v ON v.type_id = t.id
           LEFT JOIN bookings b ON b.venue_id = v.id AND b.status IN ('pending', 'approved')
           GROUP BY t.id ORDER BY t.sort_order, t.name"""
    )


# ======================================================================
# ส่วนที่ 2 : หน้าแรก / สมัครสมาชิก / เข้าสู่ระบบ
# ======================================================================
@app.route("/")
def index():
    """หน้าแรกของระบบ: ถ้ายังไม่ล็อกอินจะแสดงหน้าเลือกทางเข้า 2 ทาง"""
    user = current_user()
    if not user:
        return render_template("landing.html")
    return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """หน้าเข้าสู่ระบบของ 'นิสิต' (เจ้าหน้าที่ใช้ /admin/login)"""
    user = current_user()
    if user:
        return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        client_ip = get_client_ip()

        user = db.query("SELECT * FROM users WHERE student_id = ?", (username,), one=True)

        # ตรวจสอบรหัสผ่านก่อน (ถ้าถูกต้อง -> อนุญาตล็อกอินและปลดล็อก IP ทันที)
        credentials_ok = bool(user and check_password_hash(user["password_hash"], password) and user["is_active"])

        # ถ้ารหัสผิด และ IP ถูกล็อก -> บล็อกทันที
        if not credentials_ok:
            locked, remaining = db.is_ip_locked(client_ip)
            if locked:
                flash(f"พยายามเข้าสู่ระบบผิดเกินกำหนด โปรดลองใหม่ใน {remaining} นาที", "bad")
                return render_template("login.html", next=request.args.get("next", ""))

        if user and user["role"] == "admin":
            db.record_login_attempt(client_ip, username, False)
            flash("บัญชีนี้เป็นของเจ้าหน้าที่ กรุณาเข้าสู่ระบบที่หน้า «สำหรับเจ้าหน้าที่»", "warn")
            return redirect(url_for("admin_login"))
        if not user or not check_password_hash(user["password_hash"], password):
            db.record_login_attempt(client_ip, username, False)
            flash("รหัสนิสิตหรือรหัสผ่านไม่ถูกต้อง", "bad")
        elif not user["is_active"]:
            db.record_login_attempt(client_ip, username, False)
            flash("บัญชีนี้ถูกระงับการใช้งาน กรุณาติดต่อเจ้าหน้าที่", "bad")
        else:
            # ล็อกอินสำเร็จ -> record_login_attempt จะปลดล็อก IP ให้อัตโนมัติ
            db.record_login_attempt(client_ip, username, True)
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["_csrf"] = uuid.uuid4().hex
            name = f"{user['first_name']} {user['last_name']}".strip()
            if user["can_review"]:
                flash(f"ยินดีต้อนรับผู้ดูแล {name}", "ok")
            else:
                flash(f"ยินดีต้อนรับคุณ {name}", "ok")
            nxt = request.form.get("next") or request.args.get("next")
            # บัญชีนิสิตทั่วไปพากลับได้เฉพาะหน้าของนิสิต (ผู้ดูแลเข้าโซนตรวจสอบได้)
            if nxt and nxt.startswith("/") and (not nxt.startswith("/admin") or user["can_review"]):
                return redirect(nxt)
            return redirect(url_for("dashboard"))

    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """หน้าเข้าสู่ระบบของ 'เจ้าหน้าที่' โดยแยกออกจากหน้าของนิสิต"""
    user = current_user()
    if user:
        return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        client_ip = get_client_ip()

        user = db.query("SELECT * FROM users WHERE student_id = ?", (username,), one=True)

        # ตรวจสอบรหัสผ่านก่อน (ถ้าถูกต้อง -> อนุญาตล็อกอินและปลดล็อก IP ทันที)
        is_admin_or_reviewer = bool(user and (user["role"] == "admin" or user["can_review"]))
        credentials_ok = bool(user and check_password_hash(user["password_hash"], password) and user["is_active"] and is_admin_or_reviewer)

        # ถ้ารหัสผิด และ IP ถูกล็อก -> บล็อกทันที
        if not credentials_ok:
            locked, remaining = db.is_ip_locked(client_ip)
            if locked:
                flash(f"พยายามเข้าสู่ระบบผิดเกินกำหนด โปรดลองใหม่ใน {remaining} นาที", "bad")
                return render_template("admin_login.html", next=request.args.get("next", ""))

        if not user or not check_password_hash(user["password_hash"], password):
            db.record_login_attempt(client_ip, username, False)
            flash("ชื่อผู้ใช้หรือรหัสผ่านของเจ้าหน้าที่ไม่ถูกต้อง", "bad")
        elif user["role"] != "admin" and not user["can_review"]:
            db.record_login_attempt(client_ip, username, False)
            flash("บัญชีนี้เป็นของนิสิต กรุณาเข้าสู่ระบบที่หน้า «สำหรับนิสิต»", "warn")
            return redirect(url_for("login"))
        elif not user["is_active"]:
            db.record_login_attempt(client_ip, username, False)
            flash("บัญชีนี้ถูกระงับการใช้งาน", "bad")
        else:
            db.record_login_attempt(client_ip, username, True)
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["_csrf"] = uuid.uuid4().hex
            name = f"{user['first_name']} {user['last_name']}".strip()
            if user["role"] == "admin":
                flash(f"ยินดีต้อนรับเจ้าหน้าที่ {name}", "ok")
            else:
                flash(f"ยินดีต้อนรับผู้ดูแล {name}", "ok")
            nxt = request.form.get("next") or request.args.get("next")
            if nxt and nxt.startswith("/admin"):
                return redirect(nxt)
            return redirect(url_for("admin_dashboard"))

    return render_template("admin_login.html", next=request.args.get("next", ""))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        student_id = (f.get("student_id") or "").strip()
        first_name = (f.get("first_name") or "").strip()
        last_name = (f.get("last_name") or "").strip()
        phone = (f.get("phone") or "").strip()
        password = f.get("password") or ""
        confirm = f.get("confirm_password") or ""

        errors = []
        if not re.match(r"^[A-Za-z0-9._-]{3,20}$", student_id):
            errors.append("รหัสนิสิต ต้องเป็นตัวอักษรหรือตัวเลข 3-20 ตัว (เช่น 65012345)")
        if len(first_name) < 2:
            errors.append("กรุณากรอกชื่อ")
        if len(last_name) < 2:
            errors.append("กรุณากรอกนามสกุล")
        if not PHONE_RE.match(phone):
            errors.append("กรุณากรอกเบอร์โทรศัพท์ให้ถูกต้อง (เช่น 0812345678)")
        if len(password) < 8:
            errors.append("รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร")
        if password != confirm:
            errors.append("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
        if db.query("SELECT id FROM users WHERE student_id = ?", (student_id,), one=True):
            errors.append(f"รหัสนิสิต {student_id} ถูกใช้สมัครไปแล้ว")

        if errors:
            for e in errors:
                flash(e, "bad")
            return render_template("register.html", form=f)

        db.execute(
            """INSERT INTO users (student_id, first_name, last_name, phone, password_hash, role)
               VALUES (?, ?, ?, ?, ?, 'student')""",
            (student_id, first_name, last_name, phone, generate_password_hash(password)),
        )
        flash("สมัครสมาชิกสำเร็จแล้ว กรุณาเข้าสู่ระบบ", "ok")
        return redirect(url_for("login"))

    return render_template("register.html", form={})


@app.route("/logout")
def logout():
    user = current_user()
    was_admin = bool(user and user["role"] == "admin")
    session.clear()
    flash("ออกจากระบบเรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_login" if was_admin else "login"))


# ======================================================================
# ส่วนที่ 3 : หน้าของนิสิต
# ======================================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user["role"] == "admin":
        return redirect(url_for("admin_dashboard"))

    stats = db.query(
        """SELECT
             SUM(status = 'pending')   AS pending,
             SUM(status = 'approved')  AS approved,
             SUM(status = 'rejected')  AS rejected,
             SUM(status = 'cancelled') AS cancelled,
             COUNT(*)                  AS total
           FROM bookings WHERE user_id = ?""",
        (user["id"],),
        one=True,
    )
    recent = db.query(
        BOOKING_SELECT + " WHERE b.user_id = ? ORDER BY b.id DESC LIMIT 6",
        (user["id"],),
    )
    counts = db.query(
        """SELECT
             (SELECT COUNT(*) FROM attachments a JOIN bookings b ON b.id = a.booking_id
               WHERE b.user_id = ? AND a.kind = 'resume') AS resume_files,
           (SELECT COUNT(DISTINCT b.venue_id) FROM bookings b WHERE b.user_id = ?) AS places,
           (SELECT COUNT(DISTINCT v.type_id) FROM bookings b JOIN venues v ON v.id = b.venue_id
              WHERE b.user_id = ?) AS types""",
        (user["id"], user["id"], user["id"]),
        one=True,
    )
    return render_template("student_dashboard.html", stats=stats, recent=recent, counts=counts)


@app.route("/bookings")
@login_required
def my_bookings():
    user = current_user()
    if user["role"] == "admin":
        return redirect(url_for("admin_bookings"))

    status = request.args.get("status", "")
    sql = BOOKING_SELECT + " WHERE b.user_id = ?"
    args = [user["id"]]
    if status in STATUS_LABELS:
        sql += " AND b.status = ?"
        args.append(status)
    sql += " ORDER BY b.id DESC"

    rows = db.query(sql, args)
    attachment_counts = {
        r["booking_id"]: r["c"]
        for r in db.query(
            """SELECT a.booking_id, COUNT(*) AS c FROM attachments a
               JOIN bookings b ON b.id = a.booking_id
               WHERE b.user_id = ? GROUP BY a.booking_id""",
            (user["id"],),
        )
    }
    return render_template(
        "my_bookings.html", bookings=rows, status=status, attachment_counts=attachment_counts
    )


@app.route("/bookings/new", methods=["GET", "POST"])
@login_required
def create_booking():
    user = current_user()
    if user["role"] == "admin":
        flash("บัญชีเจ้าหน้าที่ไม่สามารถยื่นคำขอได้", "warn")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        f = request.form
        new_type_name = " ".join((f.get("new_type_name") or "").split())
        type_id = f.get("type_id", type=int)
        venue_id = f.get("venue_id", type=int)
        new_venue_name = " ".join((f.get("new_venue_name") or "").split())
        first_name = (f.get("first_name") or "").strip()
        last_name = (f.get("last_name") or "").strip()
        phone = (f.get("phone") or "").strip()

        errors = []

        # ----- ประเภทสถานที่: เลือกของเดิม หรือพิมพ์ประเภทใหม่เอง -----
        venue_type = None
        if new_type_name:
            if len(new_type_name) < 2:
                errors.append("ชื่อประเภทสถานที่ใหม่สั้นเกินไป")
            elif len(new_type_name) > 60:
                errors.append("ชื่อประเภทสถานที่ใหม่ยาวเกินไป (ไม่เกิน 60 ตัวอักษร)")
        else:
            venue_type = db.query(
                "SELECT * FROM venue_types WHERE id = ? AND is_active = 1", (type_id,), one=True
            )
            if not venue_type:
                errors.append("กรุณาเลือกประเภทสถานที่ฝึกงาน")

        if len(first_name) < 2:
            errors.append("กรุณากรอกชื่อ")
        if len(last_name) < 2:
            errors.append("กรุณากรอกนามสกุล")
        if not PHONE_RE.match(phone):
            errors.append("กรุณากรอกเบอร์โทรศัพท์ให้ถูกต้อง (เช่น 0812345678)")

        # ตรวจชื่อสถานที่: เลือกจากรายการเดิม หรือพิมพ์ชื่อใหม่
        venue = None
        if new_venue_name:
            if len(new_venue_name) < 2:
                errors.append("ชื่อสถานที่ฝึกงานสั้นเกินไป")
            elif len(new_venue_name) > 120:
                errors.append("ชื่อสถานที่ฝึกงานยาวเกินไป (ไม่เกิน 120 ตัวอักษร)")
        elif venue_id:
            if new_type_name:
                errors.append("ประเภทใหม่ยังไม่มีรายชื่อสถานที่ กรุณาพิมพ์ชื่อสถานที่ฝึกงาน")
            else:
                venue = db.query(
                    """SELECT v.* FROM venues v JOIN venue_types t ON t.id = v.type_id
                       WHERE v.id = ? AND v.is_active = 1""",
                    (venue_id,),
                    one=True,
                )
                if not venue:
                    errors.append("ไม่พบสถานที่ที่เลือก กรุณาเลือกใหม่")
                elif type_id and venue["type_id"] != type_id:
                    errors.append("สถานที่ที่เลือกไม่ตรงกับประเภทที่เลือกไว้ กรุณาเลือกใหม่")
        elif new_type_name:
            errors.append("กรุณาพิมพ์ชื่อสถานที่ฝึกงาน (ประเภทใหม่ยังไม่มีรายชื่อสถานที่)")
        else:
            errors.append("กรุณาเลือกสถานที่เดิม หรือพิมพ์ชื่อสถานที่ฝึกงานใหม่")

        # ตรวจไฟล์แนบ: ต้องมี Resume 1 ไฟล์
        resume_file = request.files.get("resume")
        extra_files = [x for x in request.files.getlist("documents") if x and x.filename]
        if not resume_file or not resume_file.filename:
            errors.append("กรุณาแนบไฟล์ Resume (PDF หรือ Word)")
        else:
            if file_ext(resume_file.filename) not in ALLOWED_EXT:
                errors.append("ไฟล์ Resume ต้องเป็น PDF, DOC หรือ DOCX เท่านั้น")
            if resume_file.content_length and resume_file.content_length > MAX_FILE_SIZE:
                errors.append(f"ไฟล์ Resume ต้องมีขนาดไม่เกิน {MAX_FILE_SIZE_MB} MB")
        if len(extra_files) > MAX_EXTRA_FILES:
            errors.append(f"แนบเอกสารประกอบได้ไม่เกิน {MAX_EXTRA_FILES} ไฟล์")

        if errors:
            for e in errors:
                flash(e, "bad")
            return render_template("booking_form.html", form=f)

        # อัปเดตข้อมูลส่วนตัวของนิสิตให้ตรงกับที่กรอกล่าสุด
        db.execute(
            "UPDATE users SET first_name = ?, last_name = ?, phone = ? WHERE id = ?",
            (first_name, last_name, phone, user["id"]),
        )

        if new_venue_name and not venue:
            if new_type_name:
                # ประเภทใหม่: สร้างประเภทให้ก่อน แล้วจึงสร้างชื่อสถานที่ภายใต้ประเภทนั้น
                type_id = db.get_or_create_venue_type(new_type_name, created_by=user["id"])
            new_venue_id = db.get_or_create_venue(type_id, new_venue_name, created_by=user["id"])
        else:
            new_venue_id = venue["id"]

        booking_code = generate_booking_code()
        booking_id = db.execute(
            """INSERT INTO bookings (booking_code, user_id, venue_id, status)
               VALUES (?, ?, ?, 'pending')""",
            (booking_code, user["id"], new_venue_id),
        )

        try:
            insert_attachment(save_upload(resume_file, booking_id, "resume"))
            for fs in extra_files:
                insert_attachment(save_upload(fs, booking_id, "document"))
        except ValueError as ex:
            # ถ้าไฟล์ผิดพลาด ให้ยกเลิกคำขอนี้ทิ้งเพื่อไม่ให้เหลือข้อมูลครึ่ง ๆ กลาง ๆ
            for a in get_attachments(booking_id):
                p = os.path.join(UPLOAD_DIR, a["stored_name"])
                if os.path.exists(p):
                    os.remove(p)
            db.execute("DELETE FROM attachments WHERE booking_id = ?", (booking_id,))
            db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            flash(str(ex), "bad")
            return redirect(url_for("create_booking"))

        flash(f"ส่งคำขอสำเร็จ เลขที่ {booking_code} (รอเจ้าหน้าที่ตรวจสอบ)", "ok")
        return redirect(url_for("booking_detail", booking_id=booking_id))

    # GET: แสดงฟอร์ม โดยดึงข้อมูลส่วนตัวของนิสิตมาเติมให้
    form = {
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "phone": user["phone"] or "",
    }
    return render_template("booking_form.html", form=form)


@app.route("/bookings/<int:booking_id>")
@login_required
def booking_detail(booking_id):
    user = current_user()
    booking = get_booking(booking_id)
    if not booking:
        abort(404)
    if user["role"] != "admin" and booking["user_id"] != user["id"]:
        abort(403)
    return render_template(
        "booking_detail.html",
        booking=booking,
        attachments=get_attachments(booking_id),
        human_size=human_size,
    )


@app.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    user = current_user()
    booking = get_booking(booking_id)
    if not booking:
        abort(404)
    if user["role"] != "admin" and booking["user_id"] != user["id"]:
        abort(403)
    if booking["status"] not in ("pending", "approved"):
        flash("ยกเลิกได้เฉพาะคำขอที่รออนุมัติหรืออนุมัติแล้วเท่านั้น", "warn")
    else:
        db.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        flash(f"ยกเลิกคำขอ {booking['booking_code']} เรียบร้อยแล้ว", "ok")
    return redirect(url_for("booking_detail", booking_id=booking_id))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action")

        if action == "info":
            first_name = (request.form.get("first_name") or "").strip()
            last_name = (request.form.get("last_name") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            if len(first_name) < 2 or len(last_name) < 2:
                flash("กรุณากรอกชื่อและนามสกุลให้ครบถ้วน", "bad")
            elif user["role"] == "student" and not PHONE_RE.match(phone):
                flash("กรุณากรอกเบอร์โทรศัพท์ให้ถูกต้อง", "bad")
            else:
                db.execute(
                    "UPDATE users SET first_name = ?, last_name = ?, phone = ? WHERE id = ?",
                    (first_name, last_name, phone, user["id"]),
                )
                flash("บันทึกข้อมูลส่วนตัวเรียบร้อยแล้ว", "ok")

        elif action == "password":
            old = request.form.get("old_password") or ""
            new = request.form.get("new_password") or ""
            confirm = request.form.get("confirm_password") or ""
            if not check_password_hash(user["password_hash"], old):
                flash("รหัสผ่านเดิมไม่ถูกต้อง", "bad")
            elif len(new) < 8:
                flash("รหัสผ่านใหม่ต้องมีอย่างน้อย 8 ตัวอักษร", "bad")
            elif new != confirm:
                flash("รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน", "bad")
            else:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new), user["id"]),
                )
                flash("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว", "ok")
        return redirect(url_for("profile"))

    return render_template("profile.html")


# ======================================================================
# ส่วนที่ 4 : หน้าของเจ้าหน้าที่ (admin)
# ======================================================================
@app.route("/admin")
@reviewer_required
def admin_dashboard():
    stats = db.query(
        """SELECT
             SUM(status = 'pending')   AS pending,
             SUM(status = 'approved')  AS approved,
             SUM(status = 'rejected')  AS rejected,
             SUM(status = 'cancelled') AS cancelled,
             COUNT(*)                  AS total
           FROM bookings""",
        one=True,
    )
    students = db.query("SELECT COUNT(*) AS c FROM users WHERE role = 'student'", one=True)["c"]
    attachments = db.query("SELECT COUNT(*) AS c FROM attachments", one=True)["c"]
    places = db.query("SELECT COUNT(*) AS c FROM venues WHERE is_active = 1", one=True)["c"]

    pending = db.query(
        BOOKING_SELECT + " WHERE b.status = 'pending' ORDER BY b.id LIMIT 10"
    )
    by_venue = db.query(
        """SELECT v.name AS venue_name, t.name AS type_name, COUNT(b.id) AS c
           FROM venues v
           JOIN venue_types t ON t.id = v.type_id
           LEFT JOIN bookings b ON b.venue_id = v.id AND b.status IN ('pending', 'approved')
           GROUP BY v.id ORDER BY c DESC, v.name LIMIT 8"""
    )
    return render_template(
        "admin_dashboard.html",
        stats=stats, students=students, attachment_count=attachments,
        place_count=places, pending=pending, by_venue=by_venue,
        type_counts=venue_type_counts(),
    )


@app.route("/admin/bookings")
@reviewer_required
def admin_bookings():
    status = request.args.get("status", "")
    keyword = (request.args.get("q") or "").strip()
    type_id = request.args.get("type_id", type=int)
    venue_id = request.args.get("venue_id", type=int)
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = 15

    where, args = "WHERE 1 = 1", []
    if status in STATUS_LABELS:
        where += " AND b.status = ?"
        args.append(status)
    if type_id:
        where += " AND t.id = ?"
        args.append(type_id)
    if venue_id:
        where += " AND b.venue_id = ?"
        args.append(venue_id)
    if keyword:
        where += """ AND (u.first_name LIKE ? OR u.last_name LIKE ? OR u.student_id LIKE ?
                          OR u.phone LIKE ? OR v.name LIKE ? OR b.booking_code LIKE ?)"""
        kw = f"%{keyword}%"
        args += [kw] * 6

    total = db.query(
        f"""SELECT COUNT(*) AS c FROM bookings b
            JOIN users u ON u.id = b.user_id
            JOIN venues v ON v.id = b.venue_id
            JOIN venue_types t ON t.id = v.type_id {where}""",
        args,
        one=True,
    )["c"]

    rows = db.query(
        BOOKING_SELECT + f" {where} ORDER BY b.id DESC LIMIT ? OFFSET ?",
        args + [per_page, (page - 1) * per_page],
    )
    resume_map = {
        r["booking_id"]: r["c"]
        for r in db.query(
            "SELECT booking_id, COUNT(*) AS c FROM attachments WHERE kind = 'resume' GROUP BY booking_id"
        )
    }
    return render_template(
        "admin_bookings.html",
        bookings=rows, status=status, keyword=keyword, type_id=type_id, venue_id=venue_id,
        page=page, total=total, per_page=per_page,
        total_pages=max((total + per_page - 1) // per_page, 1),
        resume_map=resume_map,
    )


@app.route("/admin/bookings/<int:booking_id>")
@reviewer_required
def admin_booking_detail(booking_id):
    booking = get_booking(booking_id)
    if not booking:
        abort(404)
    others = db.query(
        """SELECT b.booking_code, b.status, b.created_at,
                  u.first_name AS student_first, u.last_name AS student_last, u.student_id AS student_code
           FROM bookings b JOIN users u ON u.id = b.user_id
           WHERE b.venue_id = ? AND b.id <> ? ORDER BY b.id DESC LIMIT 10""",
        (booking["venue_id"], booking_id),
    )
    return render_template(
        "admin_booking_detail.html",
        booking=booking,
        attachments=get_attachments(booking_id),
        human_size=human_size,
        other_bookings=others,
    )


@app.route("/admin/bookings/<int:booking_id>/review", methods=["POST"])
@reviewer_required
def admin_review(booking_id):
    reviewer = current_user()
    booking = get_booking(booking_id)
    if not booking:
        abort(404)

    action = request.form.get("action")
    note = (request.form.get("admin_note") or "").strip()

    if action not in ("approve", "reject"):
        flash("คำสั่งไม่ถูกต้อง", "bad")
        return redirect(url_for("admin_booking_detail", booking_id=booking_id))

    if booking["status"] not in ("pending", "approved"):
        flash("คำขอนี้ถูกยกเลิกหรือตรวจสอบไปแล้ว ไม่สามารถเปลี่ยนสถานะได้", "warn")
        return redirect(url_for("admin_booking_detail", booking_id=booking_id))

    new_status = "approved" if action == "approve" else "rejected"
    db.execute(
        """UPDATE bookings SET status = ?, admin_note = ?, reviewed_by = ?,
                  reviewed_at = datetime('now', 'localtime')
           WHERE id = ?""",
        (new_status, note, reviewer["id"], booking_id),
    )
    flash(f"คำขอ {booking['booking_code']} -> {STATUS_LABELS[new_status]} เรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_booking_detail", booking_id=booking_id))


@app.route("/admin/students")
@admin_required
def admin_students():
    keyword = (request.args.get("q") or "").strip()
    where, args = "WHERE u.role = 'student'", []
    if keyword:
        where += " AND (u.first_name LIKE ? OR u.last_name LIKE ? OR u.student_id LIKE ? OR u.phone LIKE ?)"
        kw = f"%{keyword}%"
        args += [kw] * 4
    students = db.query(
        f"""SELECT u.*,
                  (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id) AS booking_count,
                  (SELECT COUNT(*) FROM bookings b WHERE b.user_id = u.id AND b.status = 'approved') AS approved_count
           FROM users u {where} ORDER BY u.student_id""",
        args,
    )
    return render_template("admin_students.html", students=students, keyword=keyword)


@app.route("/admin/students/<int:user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_student(user_id):
    user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not user or user["role"] == "admin":
        abort(404)
    db.execute("UPDATE users SET is_active = ? WHERE id = ?", (0 if user["is_active"] else 1, user_id))
    state = "ระงับ" if user["is_active"] else "เปิดใช้งาน"
    flash(f"{state}บัญชี {user['first_name']} {user['last_name']} เรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_students"))


@app.route("/admin/students/<int:user_id>/appoint", methods=["POST"])
@admin_required
def admin_appoint_student(user_id):
    """แต่งตั้ง/ถอดถอน 'ผู้ดูแล' — นิสิตที่ช่วยตรวจสอบและอนุมัติคำขอได้"""
    user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not user or user["role"] == "admin":
        abort(404)
    make_staff = not user["can_review"]
    db.execute("UPDATE users SET can_review = ? WHERE id = ?", (1 if make_staff else 0, user_id))
    name = f"{user['first_name']} {user['last_name']}".strip()
    if make_staff:
        flash(f"แต่งตั้ง {name} เป็นผู้ดูแลแล้ว — เข้าสู่ระบบเพื่อตรวจสอบ/อนุมัติคำขอได้", "ok")
    else:
        flash(f"ถอด {name} จากตำแหน่งผู้ดูแลแล้ว", "ok")
    return redirect(url_for("admin_students"))


@app.route("/admin/venues")
@admin_required
def admin_venues():
    types = db.query(
        """SELECT t.*, u.first_name AS creator_first, u.last_name AS creator_last, u.role AS creator_role
           FROM venue_types t LEFT JOIN users u ON u.id = t.created_by
           ORDER BY t.sort_order, t.name"""
    )
    venues = db.query(
        """SELECT v.*, t.name AS type_name,
                  (SELECT COUNT(*) FROM bookings b WHERE b.venue_id = v.id) AS booking_count,
                  u.first_name AS creator_first, u.last_name AS creator_last
           FROM venues v
           JOIN venue_types t ON t.id = v.type_id
           LEFT JOIN users u ON u.id = v.created_by
           ORDER BY t.sort_order, t.name, v.name"""
    )
    grouped = {}
    for v in venues:
        grouped.setdefault(v["type_name"], []).append(v)
    return render_template("admin_venues.html", types=types, grouped=grouped)


@app.route("/admin/venues/add", methods=["POST"])
@admin_required
def admin_add_venue():
    type_id = request.form.get("type_id", type=int)
    name = " ".join((request.form.get("name") or "").split())
    venue_type = db.query("SELECT * FROM venue_types WHERE id = ?", (type_id,), one=True)
    if not venue_type:
        flash("กรุณาเลือกประเภทสถานที่", "bad")
    elif len(name) < 2:
        flash("กรุณากรอกชื่อสถานที่ฝึกงาน", "bad")
    else:
        db.get_or_create_venue(type_id, name)
        flash(f"เพิ่มสถานที่ '{name}' ในประเภท {venue_type['name']} เรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_venues"))


@app.route("/admin/venue-types/add", methods=["POST"])
@admin_required
def admin_add_venue_type():
    admin = current_user()
    name = " ".join((request.form.get("name") or "").split())
    if len(name) < 2:
        flash("กรุณากรอกชื่อประเภทสถานที่", "bad")
    elif len(name) > 60:
        flash("ชื่อประเภทสถานที่ยาวเกินไป (ไม่เกิน 60 ตัวอักษร)", "bad")
    elif db.query("SELECT id FROM venue_types WHERE name = ? COLLATE NOCASE", (name,), one=True):
        flash(f"มีประเภท '{name}' อยู่แล้ว ไม่สร้างซ้ำ", "warn")
    else:
        db.get_or_create_venue_type(name, created_by=admin["id"])
        flash(f"เพิ่มประเภทสถานที่ '{name}' เรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_venues"))


@app.route("/admin/venues/<int:venue_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_venue(venue_id):
    venue = db.query("SELECT * FROM venues WHERE id = ?", (venue_id,), one=True)
    if not venue:
        abort(404)
    db.execute("UPDATE venues SET is_active = ? WHERE id = ?", (0 if venue["is_active"] else 1, venue_id))
    state = "ซ่อน" if venue["is_active"] else "เปิดใช้งาน"
    flash(f"{state}สถานที่ '{venue['name']}' เรียบร้อยแล้ว", "ok")
    return redirect(url_for("admin_venues"))


# ======================================================================
# ส่วนที่ 5 : ดาวน์โหลดไฟล์แนบ
# ======================================================================
@app.route("/uploads/<stored_name>")
@login_required
def download_file(stored_name):
    att = db.query(
        """SELECT a.*, b.user_id AS owner_id FROM attachments a
           JOIN bookings b ON b.id = a.booking_id WHERE a.stored_name = ?""",
        (stored_name,),
        one=True,
    )
    if not att:
        abort(404)
    user = current_user()
    if not is_reviewer(user) and att["owner_id"] != user["id"]:
        abort(403)
    path = os.path.join(UPLOAD_DIR, stored_name)
    if not os.path.exists(path):
        abort(404)
    return send_from_directory(
        UPLOAD_DIR, stored_name, as_attachment=True, download_name=att["original_name"]
    )


# ======================================================================
# เริ่มทำงาน
# ======================================================================
def local_ip_hint():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    db.init_db()
    # Render ส่ง PORT ผ่าน environment variable
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    print("=" * 68)
    print("  ระบบจองสถานที่ฝึกงาน กำลังทำงานอยู่")
    print("=" * 68)
    print(f"  หน้าแรก (เลือกทางเข้า)        : http://127.0.0.1:{port}")
    print(f"  สำหรับนิสิต                    : http://127.0.0.1:{port}/login")
    print(f"  สำหรับเจ้าหน้าที่ (admin)       : http://127.0.0.1:{port}/admin/login")
    print(f"  ให้เครื่องอื่นใน WiFi เดียวกัน  : http://{local_ip_hint()}:{port}")
    print(f"  ไฟล์ฐานข้อมูล (SQLite)         : {db.DB_PATH}")
    print(f"  โฟลเดอร์เก็บ Resume            : {UPLOAD_DIR}")
    print("  บัญชีเจ้าหน้าที่เริ่มต้น        : admin / Admin@1234  (กรุณาเปลี่ยนรหัสผ่าน)")
    print("  ปิดโปรแกรม: กด Ctrl + C ในหน้าต่างนี้")
    print("=" * 68)

    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, debug=False)
