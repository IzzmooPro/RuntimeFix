@echo off
setlocal enabledelayedexpansion
title RuntimeFix v1.0

:: Yonetici kontrolu
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

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

:: Bagimlilik kontrolu
python -c "import PyQt6, requests, urllib3" >nul 2>&1
if %errorLevel% NEQ 0 (
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install -r requirements.txt >nul 2>&1
    if !errorLevel! NEQ 0 (
        echo [HATA] Bagimliliklar kurulamadi!
        echo        Lutfen manuel olarak calistirin: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

:: pythonw varsa sessiz baslat, yoksa python ile baslat
where pythonw >nul 2>&1
if %errorLevel% EQU 0 (
    pythonw main.py
) else (
    python main.py
)
exit /b %errorlevel%

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
echo [BILGI] Python sessiz modda kuruluyor, lutfen bekleyin...
"%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
if %errorLevel% NEQ 0 (
    echo [HATA] Python kurulumu basarisiz oldu!
    pause
    exit /b 1
)
set "PATH=%ProgramFiles%\Python311\Scripts\;%ProgramFiles%\Python311\;%PATH%"
set "PATH=%LocalAppData%\Programs\Python\Python311\Scripts\;%LocalAppData%\Programs\Python\Python311\;%PATH%"
exit /b 0
