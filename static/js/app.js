/* =====================================================================
   app.js — พฤติกรรมเล็ก ๆ ที่ทำให้ใช้งานลื่นขึ้น
     1) ปิดข้อความแจ้งเตือนได้ + หายเองใน 6 วินาที
     2) เปิด/ปิดเมนูบนจอมือถือ
     3) ปุ่มส่งฟอร์มแสดงสถานะ "กำลังบันทึก..." กันกดซ้ำ
   ===================================================================== */
document.addEventListener("DOMContentLoaded", function () {
  /* ---------- 1) ข้อความแจ้งเตือน ---------- */
  function hideFlash(el) {
    if (!el || el.classList.contains("is-hiding")) return;
    el.classList.add("is-hiding");
    window.setTimeout(function () { el.remove(); }, 320);
  }

  document.querySelectorAll("[data-flash-close]").forEach(function (btn) {
    btn.addEventListener("click", function () { hideFlash(btn.closest(".flash")); });
  });

  window.setTimeout(function () {
    document.querySelectorAll(".flash").forEach(function (el, i) {
      window.setTimeout(function () { hideFlash(el); }, i * 120);
    });
  }, 6000);

  /* ---------- 2) เมนูมือถือ ---------- */
  var toggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", nav.classList.contains("open") ? "true" : "false");
    });
  }

  /* ---------- 3) ปุ่มส่งฟอร์ม ---------- */
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var btn = event.submitter || form.querySelector('button[type="submit"], button:not([type])');
      if (!btn) return;
      window.setTimeout(function () {
        if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent.trim();
        btn.classList.add("is-busy");
        btn.setAttribute("aria-busy", "true");
        if (btn.dataset.originalText.length <= 28) btn.textContent = "กำลังบันทึก...";
      }, 0);
    });
  });
});
