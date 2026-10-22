@echo off
REM ============================================================
REM  reset_database.bat - ล้างข้อมูลทั้งหมด เริ่มระบบใหม่แบบว่างเปล่า
REM  (ลบไฟล์ฐานข้อมูล และไฟล์ Resume ที่เคยอัปโหลด)
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  *** คําเตือน: การทํางานนี้จะลบข้อมูลการจอง นิสิต และไฟล์ Resume ทั้งหมด ***
echo.
set /p ANSWER= พิมพ์ YES เพื่อยืนยันการล้างข้อมูล: 
if /I not "%ANSWER%"=="YES" (
    echo ยกเลิกการล้างข้อมูล
    pause
    exit /b 0
)

if exist "data\booking.db" del /q "data\booking.db"
if exist "uploads\*" del /q "uploads\*"
echo.
echo ล้างข้อมูลเรียบร้อยแล้ว - เปิดระบบใหม่ด้วย run.bat (ระบบจะสร้างฐานข้อมูลใหม่ให้อัตโนมัติ)
pause
