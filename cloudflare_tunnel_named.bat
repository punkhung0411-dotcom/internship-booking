@echo off
chcp 65001 >nul
title Cloudflare Named Tunnel - ระบบจองสถานที่ฝึกงาน

echo ============================================================
echo  รัน Named Tunnel: internship-booking
echo  ใช้ config จาก %USERPROFILE%\.cloudflared\config.yml
echo ============================================================
echo.

where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] ไม่พบ cloudflared
    pause
    exit /b 1
)

:: ตรวจสอบ config
if not exist "%USERPROFILE%\.cloudflared\config.yml" (
    echo [ERROR] ไม่พบ config.yml
    echo รัน cloudflare_tunnel_setup.bat ก่อน เพื่อตั้งค่า Named Tunnel
    pause
    exit /b 1
)

:: ตรวจสอบว่าแอปกำลังรัน
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %errorlevel% neq 0 (
    echo [WARNING] ไม่พบเซิร์ฟเวอร์ที่พอร์ต 8000
    echo โปรดเปิด run.bat ก่อน
    echo.
    pause
)

echo.
echo [INFO] เริ่ม Named Tunnel ... (Ctrl+C เพื่อหยุด)
echo.

cloudflared tunnel run --config "%USERPROFILE%\.cloudflared\config.yml" internship-booking

echo.
echo Tunnel หยุดแล้ว
pause