/* =====================================================================
   booking.js — ช่วยกรอกฟอร์มยื่นคำขอให้ง่ายขึ้น
     1) เลือกประเภท -> กรองรายชื่อสถานที่เดิมให้เหลือเฉพาะประเภทนั้น
     2) เลือก "➕ เพิ่มประเภทใหม่" -> เปิดช่องพิมพ์ชื่อประเภทเอง
     3) เลือกสถานที่เดิม <-> พิมพ์ชื่อใหม่ ไม่ให้กรอกชนกัน
   (ถ้าปิด JavaScript ฟอร์มยังส่งได้ แต่จะไม่มีการกรองให้)
   ===================================================================== */
document.addEventListener("DOMContentLoaded", function () {
  var typeSel = document.getElementById("type_id");
  var venueSel = document.getElementById("venue_id");
  var newName = document.getElementById("new_venue_name");
  var newTypeWrap = document.getElementById("new_type_wrap");
  var newTypeInput = document.getElementById("new_type_name");
  if (!typeSel || !venueSel) return;

  // เก็บรายการตัวเลือกสถานที่ทั้งหมดไว้ในหน่วยความจำก่อน
  var allOptions = Array.prototype.map.call(venueSel.options, function (opt) {
    return { value: opt.value, text: opt.textContent, type: opt.getAttribute("data-type") || "" };
  });

  function isNewType() {
    return typeSel.value === "__new__";
  }

  function refreshVenueOptions() {
    var type = typeSel.value;
    var previous = venueSel.value;
    venueSel.innerHTML = "";
    venueSel.add(new Option("-- เลือกจากรายการเดิม --", ""));

    if (!isNewType()) {
      allOptions.forEach(function (opt) {
        if (!opt.value) return;                              // ข้ามตัวเลือกว่าง
        if (type && opt.type && opt.type !== type) return;   // กรองตามประเภท
        var el = new Option(opt.text, opt.value);
        if (opt.type) el.setAttribute("data-type", opt.type);
        venueSel.add(el);
      });
    }

    var stillExists = Array.prototype.some.call(venueSel.options, function (o) {
      return o.value === previous;
    });
    venueSel.value = stillExists ? previous : "";
  }

  function syncNewTypePanel() {
    if (!newTypeWrap) return;
    var show = isNewType();
    newTypeWrap.classList.toggle("hidden", !show);

    // ปิดช่องเลือกสถานที่เดิมเมื่อสร้างประเภทใหม่ (ยังไม่มีรายชื่อสถานที่ในประเภทนั้น)
    venueSel.disabled = show;
    if (show) venueSel.value = "";

    if (newTypeInput) {
      // ถ้าซ่อนอยู่ต้อง disable เพื่อไม่ให้ค่าที่ค้างอยู่ถูกส่งไปด้วย
      newTypeInput.disabled = !show;
      newTypeInput.required = show;
      if (show) newTypeInput.focus();
    }
  }

  typeSel.addEventListener("change", function () {
    refreshVenueOptions();
    syncNewTypePanel();
  });

  // พิมพ์ชื่อสถานที่ใหม่ -> ล้างรายการเดิมที่เลือกไว้ และกลับกัน
  if (newName) {
    newName.addEventListener("input", function () {
      if (newName.value.trim() !== "") venueSel.value = "";
    });
    venueSel.addEventListener("change", function () {
      if (venueSel.value) newName.value = "";
    });
  }

  refreshVenueOptions();
  syncNewTypePanel();
});
