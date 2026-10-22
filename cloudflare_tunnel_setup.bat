@echo off
chcp 65001 >nul
title Cloudflare Tunnel Setup - Named Tunnel (ถาวร/ใช้โดเมนตัวเอง)

echo ============================================================
echo  ตั้งค่า Cloudflare Named Tunnel (ถาวร)
echo  - ต้องมี Cloudflare account + domain อยู่แล้ว
echo  - สร้าง tunnel ถาวร ใช้ได้หลายครั้ง ไม่เปลี่ยน URL
echo ============================================================
echo.

where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] ไม่พบ cloudflared
    echo ติดตั้ง: winget install Cloudflare.cloudflared
    pause
    exit /b 1
)

echo ขั้นตอน:
echo 1. Login Cloudflare (จะเปิดเบราว์เซอร์ให้กด Authorize)
echo 2. สร้าง tunnel ชื่อ internship-booking
echo 3. สร้าง config file
echo 4. สร้าง DNS record (ถ้ามี domain)
echo.

set /p confirm=ทำต่อไหม? (y/N): 
if /i not "%confirm%"=="y" (
    echo ยกเลิก
    pause
    exit /b
)

echo.
echo [1/4] Login Cloudflare...
cloudflared tunnel login
if %errorlevel% neq 0 (
    echo Login ล้มเหลว
    pause
    exit /b 1
)

echo.
echo [2/4] สร้าง tunnel...
cloudflared tunnel create internship-booking
if %errorlevel% neq 0 (
    echo สร้าง tunnel ล้มเหลว (อาจมีอยู่แล้ว)
)

echo.
echo [3/4] สร้าง config.yml ...
set CONFIG_DIR=%USERPROFILE%\.cloudflared
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

:: หา tunnel ID
for /f "tokens=*" %%a in ('cloudflared tunnel list ^| findstr "internship-booking"') do set TUNNEL_LINE=%%a
for /f "tokens=1" %%a in ('echo %TUNNEL_LINE%') do set TUNNEL_ID=%%a

if not defined TUNNEL_ID (
    echo ไม่หา tunnel ID ได้ ลองดูด้วย: cloudflared tunnel list
    pause
    exit /b 1
)

echo Tunnel ID: %TUNNEL_ID%

(
    echo tunnel: %TUNNEL_ID%
    echo credentials-file: %CONFIG_DIR%\%TUNNEL_ID%.json
    echo ingress:
    echo   - hostname: booking.yourdomain.com
    echo     service: http://localhost:8000
    echo   - service: http_status:404
) > "%CONFIG_DIR%\config.yml"

echo สร้าง config.yml ที่ %CONFIG_DIR%\config.yml
echo.
echo ============================================================
echo  สำคัญ: ต้องแก้ hostname ใน config.yml ให้เป็น domain จริงของคุณ
echo  เช่น: booking.example.com
echo  แล้วรัน DNS record:
echo    cloudflared tunnel route dns internship-booking booking.example.com
echo ============================================================
echo.

echo [4/4] เสร็จสิ้น
echo.
echo วิธีใช้งาน:
echo   cloudflared tunnel run internship-booking
echo.
echo หรือใช้ไฟล์ cloudflare_tunnel_named.bat ที่สร้างไว้ให้
pause