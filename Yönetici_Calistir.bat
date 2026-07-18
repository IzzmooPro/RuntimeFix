@echo off
setlocal enabledelayedexpansion
title RuntimeFix v1.0 - Konsol

:: Yonetici kontrolu
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [BILGI] Yonetici yetkisi gerekiyor, UAC penceresi acilacak...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo.
echo ============================================================
echo   RuntimeFix v1.0
echo   Yonetici olarak calistirildi: %date% %time%
echo ============================================================
echo.

:: Python kontrolu
where python >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [BILGI] Python sistemde bulunamadi.
    call :INSTALL_PYTHON
    if !errorLevel! NEQ 0 exit /b 1
)

:: Python versiyon kontrolu (3.11+ gerekli)
python -c "import sys; exit(0) if sys.version_info >= (3,11) else exit(1)" >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [BILGI] Mevcut Python surumu eski. Python 3.11+ gerekli.
    call :INSTALL_PYTHON
    if !errorLevel! NEQ 0 exit /b 1
)

echo [OK] Python bulundu:
python --version
echo.

:: Bagimlilik kontrolu
echo [BILGI] Bagimliliklar kontrol ediliyor...
python -c "import PyQt6, requests, urllib3" >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [YUKLE] Eksik bilesenler yukleniyor...
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install -r requirements.txt
    if !errorLevel! NEQ 0 (
        echo [HATA] pip install basarisiz oldu!
        pause
        exit /b 1
    )
) else (
    echo [OK] Tum bagimliliklar mevcut.
)

echo.
echo ============================================================
echo   Uygulama baslatiliyor...
echo ============================================================
echo.

python main.py
set _EXIT=%errorlevel%

echo.
echo ============================================================
echo   Uygulama sonlandi. Cikis kodu: !_EXIT!
echo ============================================================
echo.
pause
exit /b !_EXIT!

:INSTALL_PYTHON
echo.
echo [ONAY] Bu program icin Python 3.11+ gerekli.
echo        Python 3.11.9 python.org adresinden indirilip sisteme kurulacak.
choice /C EH /M "Python kurulsun mu? (E=Evet, H=Hayir)"
if errorlevel 2 (
    echo [IPTAL] Python kurulumu reddedildi. Python'u manuel kurup tekrar deneyin.
    pause
    exit /b 1
)
echo [BILGI] Python 3.11.9 indiriliyor...
curl -L -o "%TEMP%\python_installer.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if %errorLevel% NEQ 0 (
    echo [HATA] Python indirilemedi! Lutfen internet baglantinizi kontrol ediniz.
    pause
    exit /b 1
)
echo [BILGI] Python sessiz modda kuruluyor, lutfen bekleyin (Bu islem 1-2 dakika surebilir)...
"%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
if %errorLevel% NEQ 0 (
    echo [HATA] Python kurulumu basarisiz oldu!
    pause
    exit /b 1
)
echo [OK] Python basariyla kuruldu!
:: PATH degiskenini komut satirina manuel olarak ekleyelim
set "PATH=%ProgramFiles%\Python311\Scripts\;%ProgramFiles%\Python311\;%PATH%"
set "PATH=%LocalAppData%\Programs\Python\Python311\Scripts\;%LocalAppData%\Programs\Python\Python311\;%PATH%"

python --version >nul 2>&1
if %errorLevel% NEQ 0 (
    echo [HATA] Python kuruldu ancak erisilemiyor! PATH degiskenini guncellemek icin sistemi yeniden baslatiniz.
    pause
    exit /b 1
)
exit /b 0
