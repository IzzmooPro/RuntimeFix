# RuntimeFix v1.0

Eksik runtime bileşenlerini otomatik tespit edip tek tıkla kuran araç.

---

## Hızlı Başlangıç

1. `CALISTIR_YONETICI.bat` → Sağ tık → **Yönetici olarak çalıştır**
2. Program açılır, sistemi otomatik tarar
3. Eksik bileşenler listelenir ve işaretlenir
4. **🔧 Yaygın Runtime Sorunlarını Düzelt** butonuna tıkla
5. Bekle — bitti.

---

## Özellikler

| Özellik | Açıklama |
|---|---|
| Smart Scan | Açılışta sistem taraması, eksikler otomatik işaretlenir |
| Tek Buton Kurulum | Seçili eksik bileşenlerin hepsini sırayla kurar |
| Offline Cache | İndirilen dosyalar `downloads/` klasöründe saklanır |
| SHA-256 Doğrulama | Her dosya kurulmadan önce güvenlik kontrolünden geçer |
| İnsani Mesajlar | Teknik hata kodları yerine anlaşılır açıklamalar |
| Restart Yönetimi | Yeniden başlatma gerektiren kurumlar için uyarı |
| Güvenli İndirme | Sadece HTTPS, sadece güvenilir kaynaklar |
| 5 Dil | Türkçe, English, Deutsch, Français, Español |

---

## Desteklenen Bileşenler (35 adet)

- **Visual C++ Redistributables** — 2005 / 2008 / 2010 / 2012 / 2013 / 2015-2022 (x86 + x64)
- **.NET Desktop Runtime** — 6.0 / 7.0 / 8.0 / 9.0 (x86 + x64)
- **ASP.NET Core Runtime** — 6.0 / 8.0 / 9.0 (x64)
- **.NET SDK** — 6.0 / 8.0 / 9.0 (x64)
- **DirectX** — End-User Web Installer + Offline Redistributable (Jun 2010)
- **XNA Framework** 4.0
- **OpenAL**
- **WebView2 Runtime**
- **VS 2010 Tools for Office Runtime**
- **NVIDIA PhysX**
- **Java SE Runtime 8** (8u451 x64)
- **MSXML 4.0 SP3**

---

## Dosya Yapısı

```
aio_runtime/
├── main.py              ← Başlangıç noktası
├── ui.py                ← Arayüz
├── worker.py            ← Arka plan indirme/kurulum motoru
├── downloader.py        ← HTTP indirici + offline cache
├── installer.py         ← Silent kurulum motoru
├── security.py          ← SHA-256 + domain whitelist
├── utils.py             ← Sistem tespiti
├── languages.py         ← 5 dil desteği
├── config.json          ← Bileşen veritabanı
├── CALISTIR_YONETICI.bat
├── requirements.txt
└── downloads/           ← Offline cache (otomatik oluşur)
```

---

## Gereksinimler

- Python 3.11+
- Windows 10/11
- Yönetici yetkisi

```bash
pip install -r requirements.txt
```

---

## Geliştirici: IzzmooPro — IzzmooPro@gmail.com
