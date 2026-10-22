"""
database.py — ส่วนจัดการฐานข้อมูล SQLite
--------------------------------------------------------------------
หน้าที่ของไฟล์นี้
  1) บอกว่าไฟล์ฐานข้อมูลอยู่ที่ไหน  ->  data/booking.db
  2) สร้างตารางทั้งหมดให้อัตโนมัติในครั้งแรกที่เปิดโปรแกรม
  3) ใส่ข้อมูลตั้งต้น (บัญชีผู้ดูแลระบบ + ประเภทสถานที่ฝึกงาน)
  4) มีฟังก์ชัน query() / execute() ให้ไฟล์ app.py เรียกใช้

หมายเหตุ: ถ้าเจอฐานข้อมูลเวอร์ชันเก่า (แบบที่มีวันที่/เวลา)
ระบบจะสำรองไฟล์เก่าไว้ชื่อ booking.db.backup-... แล้วสร้างใหม่ให้อัตโนมัติ

ไฟล์ฐานข้อมูลเป็น SQLite ธรรมดา สามารถเปิดดูด้วยโปรแกรม
"DB Browser for SQLite" ได้เลย
"""
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
# เผื่อกรณีต้องการย้ายที่เก็บไฟล์ (เช่นตอนทดสอบ) โดยไม่ต้องแก้โค้ด
DB_PATH = os.environ.get("BOOKING_DB_PATH") or os.path.join(DATA_DIR, "booking.db")
SECRET_FILE = os.path.join(DATA_DIR, "secret_key.txt")

# ----------------------------------------------------------------------
# โครงสร้างตาราง (Schema)
# ----------------------------------------------------------------------
SCHEMA = """
-- 1) ผู้ใช้งาน: นิสิต และ เจ้าหน้าที่ (admin)
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT    NOT NULL UNIQUE,          -- รหัสนิสิต / ชื่อผู้ใช้ของแอดมิน
    first_name    TEXT    NOT NULL DEFAULT '',      -- ชื่อ
    last_name     TEXT    NOT NULL DEFAULT '',      -- นามสกุล
    phone         TEXT,                             -- เบอร์โทรศัพท์
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'student'
                  CHECK (role IN ('student', 'admin')),
    can_review    INTEGER NOT NULL DEFAULT 0,       -- 1 = ได้รับแต่งตั้งเป็น "ผู้ดูแล" (อนุมัติ/ตรวจสอบคำขอได้)
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 2) ประเภทของสถานที่ฝึกงาน เช่น ฟิตเนส / อคาเดมี่ / โรงเรียน / สถานที่ราชการ
CREATE TABLE IF NOT EXISTS venue_types (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id),        -- ใครเป็นคนเพิ่ม (NULL = ข้อมูลเริ่มต้น/เจ้าหน้าที่)
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 3) ชื่อสถานที่ฝึกงาน (นิสิตพิมพ์เพิ่มเองได้ ระบบจะจำไว้ให้ใช้ครั้งต่อไป)
CREATE TABLE IF NOT EXISTS venues (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id    INTEGER NOT NULL REFERENCES venue_types(id),
    name       TEXT    NOT NULL,
    created_by INTEGER REFERENCES users(id),        -- ใครเป็นคนเพิ่มชื่อนี้ (NULL = เจ้าหน้าที่เพิ่ม)
    is_active  INTEGER NOT NULL DEFAULT 1,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (type_id, name)
);

-- 4) คำขอลงทะเบียนสถานที่ฝึกงาน (ไม่เก็บวันที่/เวลา)
CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_code TEXT    NOT NULL UNIQUE,            -- เลขที่คำขอ เช่น BK2611-0001
    user_id      INTEGER NOT NULL REFERENCES users(id),
    venue_id     INTEGER NOT NULL REFERENCES venues(id),
    status       TEXT    NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    admin_note   TEXT,                               -- หมายเหตุจากเจ้าหน้าที่
    reviewed_by  INTEGER REFERENCES users(id),
    reviewed_at  TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 5) ไฟล์แนบ (Resume ของนิสิต และเอกสารประกอบอื่น)
CREATE TABLE IF NOT EXISTS attachments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id    INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    kind          TEXT    NOT NULL DEFAULT 'resume',  -- resume = ไฟล์ Resume, document = เอกสารอื่น
    original_name TEXT    NOT NULL,                   -- ชื่อไฟล์เดิมที่นิสิตอัปโหลด
    stored_name   TEXT    NOT NULL,                   -- ชื่อไฟล์ที่เก็บจริงในโฟลเดอร์ uploads
    size_bytes    INTEGER,
    mime_type     TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_bookings_user   ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_venue  ON bookings(venue_id);
CREATE INDEX IF NOT EXISTS idx_venues_type     ON venues(type_id);
CREATE INDEX IF NOT EXISTS idx_attach_booking  ON attachments(booking_id);

-- 6) นับความพยายามเข้าสู่ระบบผิดจากแต่ละ IP (ป้องกันการเดารหัสผ่าน brute force)
CREATE TABLE IF NOT EXISTS login_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_address    TEXT    NOT NULL,
    failed_count  INTEGER NOT NULL DEFAULT 0,
    locked_until  TEXT,
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip_address);

-- 7) บันทึกประวัติการเข้าสู่ระบบ (ไว้ตรวจสอบย้อนหลังว่าใครเข้าเมื่อไร สำเร็จหรือไม่)
CREATE TABLE IF NOT EXISTS login_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     TEXT,
    ip_address     TEXT,
    success        INTEGER NOT NULL DEFAULT 0,
    attempted_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_login_logs_student ON login_logs(student_id);
CREATE INDEX IF NOT EXISTS idx_login_logs_time ON login_logs(attempted_at);
"""

# ประเภทสถานที่ฝึกงานเริ่มต้น (เพิ่ม/แก้ไขได้ในฐานข้อมูล หรือให้เจ้าหน้าที่เพิ่มผ่านหน้าเว็บ)
DEFAULT_VENUE_TYPES = [
    ("ฟิตเนส", 1),
    ("อคาเดมี่", 2),
    ("โรงเรียน", 3),
    ("สถานที่ราชการ", 4),
]

# ตัวอย่างชื่อสถานที่ (ให้เห็นว่ารายการทำงานอย่างไร — ลบได้ และนิสิตเพิ่มของตัวเองได้)
DEFAULT_VENUES = [
    ("ฟิตเนส", "ฟิตเนส เฮลท์ตี้ ซิตี้"),
    ("ฟิตเนส", "ฟิตเนส ดีฟิต สปอร์ตคลับ"),
    ("อคาเดมี่", "อคาเดมี่ฟุตบอลเยาวชน ABC"),
    ("อคาเดมี่", "อคาเดมี่สอนว่ายน้ำ สไมล์"),
    ("โรงเรียน", "โรงเรียนสาธิตวิทยา"),
    ("โรงเรียน", "โรงเรียนบ้านหนองหญ้า"),
    ("สถานที่ราชการ", "สำนักงานเขตบางกะปิ"),
    ("สถานที่ราชการ", "เทศบาลนครนนทบุรี"),
]


# ----------------------------------------------------------------------
# ฟังก์ชันเชื่อมต่อ / สั่งงานฐานข้อมูล
# ----------------------------------------------------------------------
def connect():
    """เปิดการเชื่อมต่อฐานข้อมูล (สร้างโฟลเดอร์ให้ถ้ายังไม่มี)"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # ให้อ่านค่าด้วยชื่อคอลัมน์ได้ เช่น row["first_name"]
    conn.execute("PRAGMA foreign_keys = ON")  # บังคับใช้ foreign key
    return conn


def query(sql, args=(), one=False):
    """อ่านข้อมูล (SELECT) -> คืนค่าเป็นลิสต์ หรือ แถวเดียวถ้า one=True"""
    conn = connect()
    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    """เขียนข้อมูล (INSERT/UPDATE/DELETE) -> คืนค่า id ของแถวที่เพิ่งเพิ่ม"""
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_secret_key():
    """
    คีย์ลับของ session (ใช้จำว่าใครล็อกอินอยู่)
    สุ่มครั้งแรกแล้วเก็บไว้ใน data/secret_key.txt เพื่อให้ผู้ใช้ไม่ต้องล็อกอินใหม่ทุกครั้งที่รีสตาร์ท
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    key = secrets.token_hex(32)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def _is_legacy_database(conn):
    """ตรวจว่าเป็นฐานข้อมูลเวอร์ชันเก่า (มีวันที่/เวลา) หรือไม่"""
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(bookings)").fetchall()}
    except sqlite3.DatabaseError:
        return False
    return bool(cols) and ("booking_date" in cols or "start_time" in cols)


def _backup_legacy_database():
    """สำรองฐานข้อมูลเวอร์ชันเก่าไว้ แล้วสร้างใหม่ในที่เดิม"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{DB_PATH}.backup-{stamp}"
    try:
        shutil.move(DB_PATH, backup)
        print(f"[i] พบฐานข้อมูลเวอร์ชันเก่า (มีวันที่/เวลา) -> สำรองไว้ที่ {os.path.basename(backup)}")
    except OSError:
        os.remove(DB_PATH)


def init_db():
    """
    สร้างตารางทั้งหมด + ข้อมูลตั้งต้น ถ้ายังไม่มี
    จะถูกเรียกทุกครั้งที่เปิดโปรแกรม (ถ้ามีอยู่แล้วก็ข้ามไป)
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    if os.path.exists(DB_PATH):
        try:
            conn = connect()
            legacy = _is_legacy_database(conn)
            conn.close()
        except sqlite3.DatabaseError:
            legacy = True
        if legacy:
            _backup_legacy_database()

    conn = connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()

        # อัปเกรดฐานข้อมูลรุ่นก่อน: เพิ่มคอลัมน์ created_by ให้ตาราง venue_types
        type_cols = {r["name"] for r in conn.execute("PRAGMA table_info(venue_types)").fetchall()}
        if "created_by" not in type_cols:
            conn.execute("ALTER TABLE venue_types ADD COLUMN created_by INTEGER REFERENCES users(id)")
            conn.commit()

        # อัปเกรดฐานข้อมูลรุ่นก่อน: เพิ่มคอลัมน์ can_review (สิทธิ์ "ผู้ดูแล") ให้ตาราง users
        user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "can_review" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN can_review INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "failed_login_attempts" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "locked_until" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN locked_until TEXT")
            conn.commit()

        # 1) สร้างบัญชีผู้ดูแลระบบ (เจ้าหน้าที่) ถ้ายังไม่มี
        if not conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone():
            from werkzeug.security import generate_password_hash
            conn.execute(
                """INSERT INTO users (student_id, first_name, last_name, phone, password_hash, role)
                   VALUES (?, ?, ?, ?, ?, 'admin')""",
                ("admin", "เจ้าหน้าที่", "ดูแลระบบ", "", generate_password_hash("Admin@1234")),
            )
            conn.commit()

        # 2) ประเภทสถานที่เริ่มต้น
        if not conn.execute("SELECT id FROM venue_types LIMIT 1").fetchone():
            conn.executemany(
                "INSERT INTO venue_types (name, sort_order) VALUES (?, ?)",
                DEFAULT_VENUE_TYPES,
            )
            conn.commit()

        # 3) ตัวอย่างชื่อสถานที่ (เฉพาะครั้งแรกที่สร้างฐานข้อมูล)
        if not conn.execute("SELECT id FROM venues LIMIT 1").fetchone():
            for type_name, venue_name in DEFAULT_VENUES:
                type_row = conn.execute(
                    "SELECT id FROM venue_types WHERE name = ?", (type_name,)
                ).fetchone()
                if type_row:
                    conn.execute(
                        "INSERT OR IGNORE INTO venues (type_id, name) VALUES (?, ?)",
                        (type_row["id"], venue_name),
                    )
            conn.commit()
    finally:
        conn.close()


def get_or_create_venue(type_id, name, created_by=None):
    """
    หาสถานที่จาก (ประเภท + ชื่อ) ถ้ายังไม่มีก็สร้างใหม่
    -> คืนค่า id ของสถานที่ (ใช้ตอนนิสิตพิมพ์ชื่อสถานที่ใหม่ของตัวเอง)
    """
    clean = " ".join((name or "").split())
    type_id = int(type_id)
    if not clean:
        raise ValueError("กรุณาระบุชื่อสถานที่ฝึกงาน")

    conn = connect()
    try:
        row = conn.execute(
            "SELECT id FROM venues WHERE type_id = ? AND name = ? COLLATE NOCASE",
            (type_id, clean),
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO venues (type_id, name, created_by) VALUES (?, ?, ?)",
            (type_id, clean, created_by),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_or_create_venue_type(name, created_by=None):
    """
    หาประเภทสถานที่จากชื่อ ถ้ายังไม่มีก็สร้างใหม่
    -> คืนค่า id ของประเภท (ใช้ตอนนิสิต/เจ้าหน้าที่พิมพ์ประเภทใหม่เอง)
    ชื่อซ้ำ (ไม่สนตัวพิมพ์เล็ก/ใหญ่) จะใช้รายการเดิมและเปิดใช้งานให้
    """
    clean = " ".join((name or "").split())
    if not clean:
        raise ValueError("กรุณาระบุชื่อประเภทสถานที่")

    conn = connect()
    try:
        row = conn.execute(
            "SELECT id FROM venue_types WHERE name = ? COLLATE NOCASE", (clean,)
        ).fetchone()
        if row:
            conn.execute("UPDATE venue_types SET is_active = 1 WHERE id = ?", (row["id"],))
            conn.commit()
            return row["id"]

        order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS m FROM venue_types"
        ).fetchone()["m"]
        cur = conn.execute(
            "INSERT INTO venue_types (name, sort_order, created_by) VALUES (?, ?, ?)",
            (clean, order + 1, created_by),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------------
# ป้องกันการเดารหัสผ่าน (brute force) + บันทึกประวัติการล็อกอิน
# ----------------------------------------------------------------------
FAILED_LOGIN_LIMIT = 5          # ผิดกี่ครั้งถึงล็อก
LOCKOUT_MINUTES = 15            # ล็อกนานกี่นาที


def _connect_locked():
    """เปิดเชื่อมต่อฐานข้อมูลเพื่อจัดการ login_attempts / login_logs (ใช้การเชื่อมต่อเดียว)"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def record_login_attempt(ip_address, student_id, success):
    """
    บันทึกผลการพยายามล็อกอินลง login_logs และปรับ failed_count / locked_until ใน login_attempts
    success = 1 ล็อกอินสำเร็จ, 0 = ผิดรหัส
    """
    now = now_text()
    conn = _connect_locked()
    try:
        conn.execute(
            """INSERT INTO login_logs (student_id, ip_address, success, attempted_at)
               VALUES (?, ?, ?, ?)""",
            (student_id, ip_address, 1 if success else 0, now),
        )
        if success:
            # ล็อกอินสำเร็จ -> ล้างนับผิด และปลดล็อก IP นั้น
            conn.execute(
                """UPDATE login_attempts
                       SET failed_count = 0, locked_until = NULL, updated_at = ?
                     WHERE ip_address = ?""",
                (now, ip_address),
            )
            if conn.execute(
                "SELECT changes() AS c"
            ).fetchone()["c"] == 0:
                conn.execute(
                    """INSERT INTO login_attempts (ip_address, failed_count, locked_until, updated_at)
                       VALUES (?, 0, NULL, ?)""",
                    (ip_address, now),
                )
        else:
            row = conn.execute(
                "SELECT failed_count, locked_until FROM login_attempts WHERE ip_address = ?",
                (ip_address,),
            ).fetchone()
            if row:
                new_count = row["failed_count"] + 1
                locked_until = None
                if new_count >= FAILED_LOGIN_LIMIT:
                    locked_until = (
                        datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)
                    ).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """UPDATE login_attempts
                           SET failed_count = ?, locked_until = ?, updated_at = ?
                         WHERE ip_address = ?""",
                    (new_count, locked_until, now, ip_address),
                )
            else:
                conn.execute(
                    """INSERT INTO login_attempts (ip_address, failed_count, updated_at)
                       VALUES (?, 1, ?)""",
                    (ip_address, now),
                )
        conn.commit()
    finally:
        conn.close()


def is_ip_locked(ip_address):
    """
    ตรวจว่า IP นี้ถูกล็อกชั่วคราวหรือไม่
    -> คืนค่า (locked: bool, remaining_minutes: int)
    ถ้าหมดเวลาล็อกแล้ว จะรีเซ็ตนับผิดให้อัตโนมัติ
    """
    conn = _connect_locked()
    try:
        row = conn.execute(
            "SELECT locked_until FROM login_attempts WHERE ip_address = ?",
            (ip_address,),
        ).fetchone()
        if not row or not row["locked_until"]:
            return False, 0
        try:
            until = datetime.strptime(row["locked_until"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False, 0
        if datetime.now() < until:
            remaining = max(1, int((until - datetime.now()).total_seconds() / 60) + 1)
            return True, remaining
        # หมดเวลาล็อกแล้ว -> รีเซ็ต
        conn.execute(
            """UPDATE login_attempts
                   SET failed_count = 0, locked_until = NULL, updated_at = ?
                 WHERE ip_address = ?""",
            (now_text(), ip_address),
        )
        conn.commit()
        return False, 0
    finally:
        conn.close()


def get_recent_login_logs(limit=50):
    """ดึงประวัติการล็อกอินล่าสุด (สำหรับหน้าเจ้าหน้าที่ถ้าต้องการดูในอนาคต)"""
    return db.query(
        """SELECT * FROM login_logs ORDER BY attempted_at DESC LIMIT ?""",
        (limit,),
    )


def clear_login_attempts_for_ip(ip_address):
    """รีเซ็ตนับผิดของ IP นี้ (เจ้าหน้าที่ใช้ปลดล็อกได้ถ้าจำเป็น)"""
    conn = _connect_locked()
    try:
        conn.execute(
            "UPDATE login_attempts SET failed_count = 0, locked_until = NULL WHERE ip_address = ?",
            (ip_address,),
        )
        conn.commit()
    finally:
        conn.close()

