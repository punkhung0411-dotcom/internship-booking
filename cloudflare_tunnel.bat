@echo off
chcp 65001 >nul
title Cloudflare Tunnel - ระบบจองสถานที่ฝึกงาน

echo ============================================================
echo  Cloudflare Tunnel สำหรับ ระบบจองสถานที่ฝึกงาน
echo  จะสร้างลิงก์ https://xxx.trycloudflare.com ชี้ไปที่ localhost:8000
echo ============================================================
echo.

:: ตรวจสอบ cloudflared
where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] ไม่พบ cloudflared ใน PATH
    echo.
    echo กรุณาติดตั้งก่อน:
    echo   winget install Cloudflare.cloudflared
    echo.
    echo หรือดาวน์โหลดจาก: https://github.com/cloudflare/cloudflared/releases
    echo.
    pause
    exit /b 1
)

:: ตรวจสอบว่าแอปกำลังรันอยู่ที่พอร์ต 8000 หรือไม่
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [WARNING] ไม่พบเซิร์ฟเวอร์รันที่พอร์ต 8000
    echo โปรดเปิด run.bat ก่อน (หรือรัน .venv\Scripts\python.exe app.py)
    echo.
    echo กด Enter เพื่อลองต่อไปอยู่ดี... (ถ้าแอปยังไม่พร้อม Tunnel จะล้มเหลว)
    pause
)

echo.
echo [INFO] เริ่ม Tunnel ... (กด Ctrl+C เพื่อหยุด)
echo.

:: รัน Tunnel แบบ Quick (ไม่ต้อง login, ใช้ trycloudflare.com)
:: จะได้ URL แบบ https://random-name.trycloudflare.com
cloudflared tunnel --url http://localhost:8000 --no-autoupdate

echo.
echo Tunnel หยุดทำงานแล้ว
pause