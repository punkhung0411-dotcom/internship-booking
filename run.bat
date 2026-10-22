@echo off
REM ============================================================
REM  run.bat  -  เปิดระบบจองสถานที่ฝึกงาน
REM  (ถ้าเปิดครั้งแรกแล้วขึ้นข้อความให้รัน setup.bat ก่อน)
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"
title Internship Venue Booking System

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo *** System not installed yet. Please run  setup.bat  first. ***
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" app.py

echo.
echo System stopped.
pause
