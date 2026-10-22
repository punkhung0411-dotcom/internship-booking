"""
smoke_test.py — ทดสอบระบบอัตโนมัติแบบครบวงจร (ไม่กระทบข้อมูลจริง)

วิธีรัน (ในโฟลเดอร์โปรเจกต์):
    .venv\\Scripts\\python.exe tests\\smoke_test.py

สิ่งที่ทดสอบ (ระบบแบบใหม่: แยกประเภทสถานที่ + ไม่มีวันที่/เวลา + พิมพ์ชื่อสถานที่เองได้)
  1) หน้าเข้าสู่ระบบเปิดได้
  2) นิสิตสมัครสมาชิก (ชื่อ/นามสกุล/รหัสนิสิต/เบอร์โทร) + ล็อกอินได้
  3) นิสิตยื่นคำขอพร้อมพิมพ์ชื่อสถานที่ใหม่ + แนบ Resume ได้
  4) ระบบจำชื่อสถานที่ใหม่ไว้ให้ใช้ครั้งต่อไป (ไม่สร้างซ้ำ)
  5) ตรวจการแนบไฟล์ผิดชนิด / ไม่แนบ Resume
  6) กันการเข้าถึงข้อมูลของนิสิตคนอื่น (403)
  7) เจ้าหน้าที่อนุมัติได้ + ดาวน์โหลด Resume ได้
  8) เจ้าหน้าที่เพิ่มสถานที่/ประเภทสถานที่ได้
  9) หน้าจอทั้งหมดเปิดได้ (200)
"""
import io
import os
import shutil
import sys
import tempfile

# --- บังคับให้ใช้ฐานข้อมูล/โฟลเดอร์ไฟล์แนบชั่วคราว เพื่อไม่ให้กระทบข้อมูลจริง ---
TMP = tempfile.mkdtemp(prefix="booking_smoke_")
os.environ["BOOKING_DB_PATH"] = os.path.join(TMP, "test.db")
os.environ["BOOKING_UPLOAD_DIR"] = os.path.join(TMP, "uploads")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db          # noqa: E402
import app as app_module       # noqa: E402

passed, failed = [], []
PDF = b"%PDF-1.4\n% smoke test resume\n%%EOF\n"


def check(name, condition, extra=""):
    if condition:
        passed.append(name)
        print(f"  [PASS] {name}")
    else:
        failed.append(name)
        print(f"  [FAIL] {name} {extra}")


def csrf(client, url):
    client.get(url)
    with client.session_transaction() as sess:
        return sess.get("_csrf")


def flashes(html_text):
    import re
    return [re.sub(r"\s+", " ", m).strip()
            for m in re.findall(r'<div class="flash[^"]*">(.*?)</div>', html_text, re.S)]


def register(client, student_id, first, last, phone, password):
    token = csrf(client, "/register")
    return client.post("/register", data={
        "_csrf": token, "student_id": student_id, "first_name": first, "last_name": last,
        "phone": phone, "password": password, "confirm_password": password,
    }, follow_redirects=True)


def login(client, username, password):
    token = csrf(client, "/login")
    return client.post("/login", data={"_csrf": token, "username": username, "password": password},
                       follow_redirects=True)


def login_admin(client, username="admin", password="Admin@1234"):
    token = csrf(client, "/admin/login")
    return client.post("/admin/login", data={"_csrf": token, "username": username, "password": password},
                       follow_redirects=True)


def submit_booking(client, form_extra=None, resume=True):
    token = csrf(client, "/bookings/new")
    data = {"_csrf": token, "type_id": "1", "venue_id": "",
            "new_venue_name": "ฟิตเนส บ้านสวน", "first_name": "สมชาย",
            "last_name": "ใจดี", "phone": "0812345678"}
    data.update(form_extra or {})
    if resume is True:
        data["resume"] = (io.BytesIO(PDF), "resume.pdf")
    elif resume:
        data["resume"] = resume
    return client.post("/bookings/new", data=data, content_type="multipart/form-data",
                       follow_redirects=True)


def main():
    app_module.app.config["TESTING"] = True
    db.init_db()
    client = app_module.app.test_client()

    print("\n=== 1) หน้าแรกและการแยกทางเข้านิสิต/เจ้าหน้าที่ ===")
    r = client.get("/")
    body = r.get_data(as_text=True)
    check("หน้าแรกเปิดได้ (200)", r.status_code == 200, f"-> {r.status_code}")
    check("หน้าแรกมีทางเข้า 2 ทาง (/login และ /admin/login)",
          'href="/login"' in body and 'href="/admin/login"' in body)
    check("หน้าแรกมีข้อความ 'สำหรับนิสิต' และ 'สำหรับเจ้าหน้าที่'",
          "สำหรับนิสิต" in body and "สำหรับเจ้าหน้าที่" in body)
    check("หน้า /login เปิดได้", client.get("/login").status_code == 200)
    check("หน้า /admin/login เปิดได้", client.get("/admin/login").status_code == 200)

    r = client.get("/admin")
    check("ยังไม่ล็อกอิน เข้า /admin ไม่ได้ และถูกพาไปหน้าเจ้าหน้าที่",
          r.status_code == 302 and "/admin/login" in r.headers["Location"],
          f"-> {r.status_code} {r.headers.get('Location')}")
    check("หน้า login ของนิสิตมีลิงก์ไปหน้าของเจ้าหน้าที่",
          "/admin/login" in client.get("/login").get_data(as_text=True))
    check("หน้า login ของเจ้าหน้าที่มีลิงก์กลับไปหน้าของนิสิต",
          'href="/login"' in client.get("/admin/login").get_data(as_text=True))

    print("\n=== 2) ประเภทสถานที่ 4 ประเภทตามที่ต้องการ ===")
    types = [t["name"] for t in db.query("SELECT name FROM venue_types ORDER BY sort_order")]
    for expected in ("ฟิตเนส", "อคาเดมี่", "โรงเรียน", "สถานที่ราชการ"):
        check(f"มีประเภท '{expected}'", expected in types, str(types))

    print("\n=== 3) นิสิตสมัครสมาชิก + ล็อกอิน ===")
    r = register(client, "65012345", "สมชาย", "ใจดี", "0812345678", "Student@123")
    check("สมัครสมาชิกสำเร็จ", "สมัครสมาชิกสำเร็จ" in r.get_data(as_text=True), str(flashes(r.get_data(as_text=True))))
    student = db.query("SELECT * FROM users WHERE student_id = '65012345'", one=True)
    check("บันทึกชื่อ/นามสกุล/เบอร์โทร ถูกต้อง",
          student and student["first_name"] == "สมชาย" and student["last_name"] == "ใจดี"
          and student["phone"] == "0812345678")
    check("รหัสผ่านถูกเข้ารหัส", student and student["password_hash"] != "Student@123")

    r = login(client, "65012345", "Student@123")
    body = r.get_data(as_text=True)
    check("ล็อกอินนิสิตสำเร็จ", "สวัสดีครับ/ค่ะ" in body)
    check("หน้าหลักนิสิตใช้ธีมของนิสิต (role-student)", 'class="role-student"' in body)
    check("นิสิตที่ล็อกอินแล้วเข้า /admin ไม่ได้ (403)", client.get("/admin").status_code == 403)

    # บัญชีนิสิตพยายามเข้าหน้าล็อกอินของเจ้าหน้าที่
    sneak = app_module.app.test_client()
    token = csrf(sneak, "/admin/login")
    r = sneak.post("/admin/login",
                   data={"_csrf": token, "username": "65012345", "password": "Student@123"},
                   follow_redirects=True)
    check("นิสิตล็อกอินที่หน้าของเจ้าหน้าที่ไม่ได้",
          "บัญชีนี้เป็นของนิสิต" in r.get_data(as_text=True))

    # บัญชีเจ้าหน้าที่พยายามเข้าหน้าล็อกอินของนิสิต
    sneak2 = app_module.app.test_client()
    token = csrf(sneak2, "/login")
    r = sneak2.post("/login",
                    data={"_csrf": token, "username": "admin", "password": "Admin@1234"},
                    follow_redirects=True)
    body2 = r.get_data(as_text=True)
    check("เจ้าหน้าที่ล็อกอินที่หน้าของนิสิตไม่ได้ (ถูกพาไปหน้าของเจ้าหน้าที่)",
          "เข้าสู่ระบบเจ้าหน้าที่" in body2 and "บัญชีนี้เป็นของเจ้าหน้าที่" in body2)

    print("\n=== 4) ยื่นคำขอ + พิมพ์ชื่อสถานที่ใหม่ + แนบ Resume ===")
    form_html = client.get("/bookings/new").get_data(as_text=True)
    check("ฟอร์มไม่มีช่องวันที่/เวลาแล้ว", "booking_date" not in form_html and "start_time" not in form_html)
    check("ฟอร์มมีช่องชื่อ/นามสกุล/เบอร์โทร",
          'name="first_name"' in form_html and 'name="last_name"' in form_html and 'name="phone"' in form_html)

    r = submit_booking(client)
    body = r.get_data(as_text=True)
    check("ส่งคำขอสำเร็จ", "ส่งคำขอสำเร็จ" in body, str(flashes(body)))
    booking = db.query("SELECT * FROM bookings ORDER BY id DESC LIMIT 1", one=True)
    check("บันทึกคำขอสถานะ pending", booking and booking["status"] == "pending")
    check("สร้างเลขที่คำขออัตโนมัติ", booking and booking["booking_code"].startswith("BK"))
    venue = db.query("""SELECT v.*, t.name AS type_name FROM venues v
                        JOIN venue_types t ON t.id = v.type_id
                        WHERE v.id = ?""", (booking["venue_id"],), one=True)
    check("สร้างสถานที่ใหม่ชื่อ 'ฟิตเนส บ้านสวน' สำเร็จ", venue and venue["name"] == "ฟิตเนส บ้านสวน")
    check("สถานที่ใหม่อยู่ในประเภทที่เลือก (ฟิตเนส)", venue and venue["type_name"] == "ฟิตเนส")
    check("บันทึกว่าใครเป็นคนเพิ่มสถานที่", venue and venue["created_by"] == student["id"])
    att = db.query("SELECT * FROM attachments WHERE booking_id = ?", (booking["id"],), one=True)
    check("ไฟล์ Resume ถูกบันทึกและเก็บลงดิสก์จริง",
          att and os.path.exists(os.path.join(app_module.UPLOAD_DIR, att["stored_name"])))

    print("\n=== 5) ระบบจำชื่อสถานที่เดิม (ไม่สร้างซ้ำ) ===")
    venue_count_before = db.query("SELECT COUNT(*) AS c FROM venues", one=True)["c"]
    r = submit_booking(client, {"venue_id": str(venue["id"]), "new_venue_name": ""})
    check("เลือกสถานที่เดิมแล้วส่งคำขอได้", "ส่งคำขอสำเร็จ" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))
    venue_count_after = db.query("SELECT COUNT(*) AS c FROM venues", one=True)["c"]
    check("ไม่สร้างสถานที่ซ้ำ", venue_count_before == venue_count_after,
          f"{venue_count_before} -> {venue_count_after}")

    print("\n=== 5.5) นิสิตเพิ่ม \"ประเภทสถานที่\" ใหม่ได้เอง ===")
    before_types = db.query("SELECT COUNT(*) AS c FROM venue_types", one=True)["c"]
    r = submit_booking(client, {"type_id": "__new__", "new_type_name": "โรงพยาบาล",
                                "new_venue_name": "โรงพยาบาลศรีนครินทร์"})
    check("ส่งคำขอพร้อมพิมพ์ประเภทใหม่สำเร็จ", "ส่งคำขอสำเร็จ" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))
    new_type = db.query("SELECT * FROM venue_types WHERE name = 'โรงพยาบาล'", one=True)
    check("สร้างประเภทใหม่ในฐานข้อมูล", new_type is not None)
    check("บันทึกว่าใครเป็นคนเพิ่มประเภท", new_type and new_type["created_by"] == student["id"])
    check("ประเภทใหม่เปิดใช้งานทันที", new_type and new_type["is_active"] == 1)

    latest = db.query("SELECT * FROM bookings ORDER BY id DESC LIMIT 1", one=True)
    latest_venue = db.query("SELECT * FROM venues WHERE id = ?", (latest["venue_id"],), one=True)
    check("สร้างชื่อสถานที่ภายใต้ประเภทใหม่ถูกต้อง",
          latest_venue and new_type and latest_venue["type_id"] == new_type["id"]
          and latest_venue["name"] == "โรงพยาบาลศรีนครินทร์")

    # พิมพ์ชื่อประเภทซ้ำ (มีช่องว่างเกิน) ต้องใช้ของเดิม ไม่สร้างซ้ำ
    r = submit_booking(client, {"type_id": "__new__", "new_type_name": "  โรงพยาบาล  ",
                                "new_venue_name": "โรงพยาบาลอีกแห่ง"})
    check("ส่งคำขอโดยพิมพ์ประเภทชื่อเดิมได้", "ส่งคำขอสำเร็จ" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))
    after_types = db.query("SELECT COUNT(*) AS c FROM venue_types", one=True)["c"]
    check("ชื่อประเภทซ้ำไม่ถูกสร้างใหม่", after_types == before_types + 1,
          f"{before_types} -> {after_types}")

    # เลือกประเภทใหม่แต่ไม่พิมพ์ชื่อสถานที่ -> ต้องแจ้งเตือน และไม่ทิ้งประเภทค้างไว้
    r = submit_booking(client, {"type_id": "__new__", "new_type_name": "มูลนิธิ",
                                "new_venue_name": ""})
    body = r.get_data(as_text=True)
    check("ประเภทใหม่ต้องพิมพ์ชื่อสถานที่ด้วย", "กรุณาพิมพ์ชื่อสถานที่ฝึกงาน" in body,
          str(flashes(body)))
    check("ฟอร์มไม่ผ่าน = ไม่สร้างประเภทค้างไว้",
          db.query("SELECT id FROM venue_types WHERE name = 'มูลนิธิ'", one=True) is None)

    print("\n=== 6) ตรวจไฟล์แนบผิดเงื่อนไข ===")
    r = submit_booking(client, {"new_venue_name": "ฟิตเนส ทดสอบไฟล์ผิด"},
                       resume=(io.BytesIO(b"hello"), "resume.txt"))
    check("ปฏิเสธไฟล์ที่ไม่ใช่ PDF/DOC/DOCX", "ต้องเป็น PDF, DOC หรือ DOCX" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))
    r = submit_booking(client, {"new_venue_name": "ฟิตเนส ไม่มีไฟล์"}, resume=False)
    check("บังคับให้แนบ Resume", "กรุณาแนบไฟล์ Resume" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))

    print("\n=== 7) กันการเข้าถึงข้อมูลนิสิตคนอื่น ===")
    other = app_module.app.test_client()
    register(other, "65099999", "นิสิต", "คนอื่น", "0899999999", "Other@1234")
    login(other, "65099999", "Other@1234")
    check("นิสิตคนอื่นเปิดคำขอเราไม่ได้ (403)", other.get(f"/bookings/{booking['id']}").status_code == 403)
    check("นิสิตคนอื่นดาวน์โหลด Resume เราไม่ได้ (403)",
          other.get(f"/uploads/{att['stored_name']}").status_code == 403)

    print("\n=== 8) เจ้าหน้าที่อนุมัติ + ดาวน์โหลด Resume ===")
    admin = app_module.app.test_client()
    r = login_admin(admin)
    body = r.get_data(as_text=True)
    check("ล็อกอินเจ้าหน้าที่สำเร็จ", "หน้าหลักเจ้าหน้าที่" in body)
    check("หน้าของเจ้าหน้าที่ใช้ธีมเจ้าหน้าที่ (role-admin)", 'class="role-admin"' in body)
    check("หน้าของเจ้าหน้าที่แสดงแถบ 'โหมดเจ้าหน้าที่'", "โหมดเจ้าหน้าที่" in body)
    check("เจ้าหน้าที่เปิดดูคำขอได้", admin.get(f"/admin/bookings/{booking['id']}").status_code == 200)
    token = csrf(admin, "/admin")
    r = admin.post(f"/admin/bookings/{booking['id']}/review",
                   data={"_csrf": token, "action": "approve", "admin_note": "อนุมัติแล้ว"},
                   follow_redirects=True)
    check("กดอนุมัติสำเร็จ", "อนุมัติแล้ว" in r.get_data(as_text=True))
    after = db.query("SELECT * FROM bookings WHERE id = ?", (booking["id"],), one=True)
    check("สถานะเปลี่ยนเป็น approved และบันทึกผู้พิจารณา",
          after["status"] == "approved" and after["reviewed_by"] and after["reviewed_at"])
    r = admin.get(f"/uploads/{att['stored_name']}")
    check("เจ้าหน้าที่ดาวน์โหลด Resume ได้", r.status_code == 200 and b"%PDF" in r.data)

    print("\n=== 9) เจ้าหน้าที่เพิ่มสถานที่/ประเภท ===")
    token = csrf(admin, "/admin/venues")
    r = admin.post("/admin/venues/add",
                   data={"_csrf": token, "type_id": "3", "name": "โรงเรียนทดสอบใหม่"},
                   follow_redirects=True)
    check("เพิ่มชื่อสถานที่ใหม่ได้", "เรียบร้อยแล้ว" in r.get_data(as_text=True))
    check("สถานที่ใหม่ปรากฏในฐานข้อมูล",
          db.query("SELECT id FROM venues WHERE name = 'โรงเรียนทดสอบใหม่'", one=True) is not None)
    token = csrf(admin, "/admin/venues")
    r = admin.post("/admin/venue-types/add",
                   data={"_csrf": token, "name": "บริษัทเอกชน"}, follow_redirects=True)
    check("เพิ่มประเภทสถานที่ใหม่ได้",
          db.query("SELECT id FROM venue_types WHERE name = 'บริษัทเอกชน'", one=True) is not None)

    print("\n=== 10) หน้าจอทั้งหมดเปิดได้ ===")
    for url, name in [("/admin", "แดชบอร์ดเจ้าหน้าที่"),
                      ("/admin/bookings", "คำขอทั้งหมด"),
                      ("/admin/venues", "สถานที่ฝึกงาน"),
                      ("/admin/students", "รายชื่อนิสิต"),
                      ("/admin/bookings?status=pending", "กรองสถานะรออนุมัติ"),
                      ("/bookings", "คำขอของฉัน"),
                      ("/profile", "โปรไฟล์")]:
        cli = admin if url.startswith("/admin") else client
        r = cli.get(url)
        check(f"เปิดหน้า {name} ได้ (200)", r.status_code == 200, f"-> {r.status_code}")

    print("\n=== 11) เจ้าหน้าที่แต่งตั้งนิสิตเป็น \"ผู้ดูแล\" (อนุมัติ/ตรวจสอบได้) ===")
    target = db.query("SELECT * FROM users WHERE student_id = '65012345'", one=True)
    token = csrf(admin, "/admin/students")
    r = admin.post(f"/admin/students/{target['id']}/appoint",
                   data={"_csrf": token}, follow_redirects=True)
    body = r.get_data(as_text=True)
    check("แต่งตั้งนิสิตเป็นผู้ดูแลสำเร็จ", "เป็นผู้ดูแลแล้ว" in body, str(flashes(body)))
    target = db.query("SELECT * FROM users WHERE id = ?", (target["id"],), one=True)
    check("บันทึกสิทธิ์ can_review = 1", target["can_review"] == 1)
    check("หน้าจอแสดงป้าย 'ผู้ดูแล'", "🛡️ ผู้ดูแล" in body)

    reviewer = app_module.app.test_client()
    r = login_admin(reviewer, "65012345", "Student@123")
    body = r.get_data(as_text=True)
    check("ผู้ดูแลล็อกอินที่หน้า /admin/login ได้", "หน้าหลักเจ้าหน้าที่" in body, str(flashes(body)))
    check("หน้าโหมดผู้ดูแลใช้ธีมเจ้าหน้าที่ (role-admin)", 'class="role-admin"' in body)
    check("แสดงแถบ 'โหมดผู้ดูแล'", "โหมดผู้ดูแล" in body)
    check("ผู้ดูแลเห็นเมนูคำขอทั้งหมด", "/admin/bookings" in body)
    check("ผู้ดูแลไม่เห็นเมนูจัดการสถานที่", "/admin/venues" not in body)

    # สร้างคำขอใหม่ของนิสิตอีกคน เพื่อให้ผู้ดูแลกดอนุมัติ
    other_user = db.query("SELECT * FROM users WHERE student_id = '65099999'", one=True)
    submit_booking(other, {"new_venue_name": "ฟิตเนส ทดสอบผู้ดูแล"})
    pending_bk = db.query("SELECT * FROM bookings ORDER BY id DESC LIMIT 1", one=True)
    check("มีคำขอใหม่สถานะรออนุมัติให้ทดสอบ", pending_bk["status"] == "pending")

    check("ผู้ดูแลเปิดรายการคำขอได้", reviewer.get("/admin/bookings").status_code == 200)
    check("ผู้ดูแลเปิดรายละเอียดคำขอได้",
          reviewer.get(f"/admin/bookings/{pending_bk['id']}").status_code == 200)
    token = csrf(reviewer, "/admin")
    r = reviewer.post(f"/admin/bookings/{pending_bk['id']}/review",
                      data={"_csrf": token, "action": "approve",
                            "admin_note": "อนุมัติโดยผู้ดูแล"},
                      follow_redirects=True)
    check("ผู้ดูแลกดอนุมัติได้", "อนุมัติโดยผู้ดูแล" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))
    after = db.query("SELECT * FROM bookings WHERE id = ?", (pending_bk["id"],), one=True)
    check("สถานะเปลี่ยนเป็น approved และบันทึกผู้พิจารณาเป็นผู้ดูแล",
          after["status"] == "approved" and after["reviewed_by"] == target["id"])

    att2 = db.query("SELECT * FROM attachments WHERE booking_id = ?", (pending_bk["id"],), one=True)
    r = reviewer.get(f"/uploads/{att2['stored_name']}")
    check("ผู้ดูแลดาวน์โหลด Resume ของนิสิตคนอื่นได้", r.status_code == 200 and b"%PDF" in r.data)

    # สิทธิ์ที่ผู้ดูแลยังไม่มี (เฉพาะผู้ดูแลระบบ)
    check("ผู้ดูแลเข้าหน้าจัดการสถานที่ไม่ได้ (403)",
          reviewer.get("/admin/venues").status_code == 403)
    check("ผู้ดูแลเข้าหน้ารายชื่อนิสิตไม่ได้ (403)",
          reviewer.get("/admin/students").status_code == 403)
    token = csrf(reviewer, "/admin")
    r = reviewer.post(f"/admin/students/{other_user['id']}/appoint", data={"_csrf": token})
    check("ผู้ดูแลแต่งตั้งคนอื่นเป็นผู้ดูแลไม่ได้ (403)", r.status_code == 403)
    token = csrf(reviewer, "/admin")
    r = reviewer.post("/admin/venue-types/add", data={"_csrf": token, "name": "ทดสอบสิทธิ์"})
    check("ผู้ดูแลเพิ่มประเภทสถานที่ไม่ได้ (403)", r.status_code == 403)

    body = reviewer.get("/dashboard").get_data(as_text=True)
    check("หน้าหลักนิสิตแสดงแบนเนอร์ 'โหมดผู้ดูแล'", "โหมดผู้ดูแล" in body)

    # ถอดถอนสิทธิ์
    token = csrf(admin, "/admin/students")
    r = admin.post(f"/admin/students/{target['id']}/appoint",
                   data={"_csrf": token}, follow_redirects=True)
    check("ถอดจากตำแหน่งผู้ดูแลสำเร็จ", "ถอด" in r.get_data(as_text=True),
          str(flashes(r.get_data(as_text=True))))
    target = db.query("SELECT * FROM users WHERE id = ?", (target["id"],), one=True)
    check("สิทธิ์ can_review กลับเป็น 0", target["can_review"] == 0)
    check("หลังถูกถอด เข้า /admin/bookings ไม่ได้ (403)",
          reviewer.get("/admin/bookings").status_code == 403)
    r = login_admin(app_module.app.test_client(), "65012345", "Student@123")
    check("หลังถูกถอด ล็อกอินหน้า /admin/login ไม่ได้",
          "บัญชีนี้เป็นของนิสิต" in r.get_data(as_text=True))

    print("\n" + "=" * 60)
    print(f"  ผลการทดสอบ: ผ่าน {len(passed)} รายการ, ไม่ผ่าน {len(failed)} รายการ")
    print("=" * 60)
    if failed:
        print("  รายการที่ไม่ผ่าน:")
        for f in failed:
            print(f"   - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
