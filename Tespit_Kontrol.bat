@echo off
title RuntimeFix - Tespit Denetimi
:: Nereden calistirilirsa calistirilsin proje klasorune gecer
cd /d "%~dp0"

where python >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [HATA] Python bulunamadi.
    pause
    exit /b 1
)

set PYTHONUTF8=1
python debug\detection_audit.py

echo.
pause
