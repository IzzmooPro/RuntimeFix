# 🛠️ RuntimeFix v1.10

<p align="center">
  <img src="assets/runtimefix-logo.png" width="128" alt="RuntimeFix logosu">
</p>

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows)
![CI](https://github.com/IzzmooPro/RuntimeFix/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/License-MIT-green)
![Components](https://img.shields.io/badge/Components-45-orange)

**RuntimeFix v1.10**, sisteminizde eksik olan runtime bileşenlerini otomatik olarak tespit edip tek tıkla kuran modern bir araçtır. Oyun oynamadan önce veya bir uygulama çalıştırırken karşılaşılan "Visual C++ bulunamadı", ".NET Runtime eksik" gibi hata mesajlarına son verir.

---

## ✨ Özellikler

| Özellik | Açıklama |
|---|---|
| 🔍 Akıllı Tarama | Açılışta sistemi otomatik tarar, eksik bileşenleri işaretler |
| ⚡ Tek Tık Kurulum | Seçili bileşenlerin tamamını sırayla sessizce kurar |
| 🔒 SHA-256 Doğrulama | Her dosya kurulmadan önce güvenlik kontrolünden geçer |
| 📦 Offline Cache | Kaynak çalıştırmada `downloads/`, kurulu EXE'de `%TEMP%\RuntimeFix_downloads` kullanılır |
| 💬 Anlaşılır Hata Mesajları | Teknik kodlar yerine kullanıcı dostu açıklamalar |
| 🔄 Restart Yönetimi | Yeniden başlatma gerektiren kurulumlar için uyarı |
| 🌐 5 Dil | Türkçe, English, Deutsch, Français, Español |
| 🛡️ Güvenli İndirme | Sadece HTTPS ve whitelist'teki resmî sağlayıcı alan adları kullanılır |
| 🔄 Uygulama Güncellemesi | Açılışta arka planda yeni sürümü denetler; tek onayla indirir, doğrular ve kurulumu başlatır |

---

## 📦 Desteklenen Bileşenler (45 adet)

<details>
<summary><b>Visual C++ Redistributables (10 adet)</b></summary>

- VC++ 2005 (x86 / x64)
- VC++ 2008 (x86 / x64)
- VC++ 2010 (x86 / x64)
- VC++ 2012 (x86 / x64)
- VC++ 2013 (x86 / x64)
- VC++ 2015-2022 (x86 / x64)

</details>

<details>
<summary><b>.NET Desktop Runtime (10 adet)</b></summary>

- .NET Desktop Runtime 6.0 (x86 / x64)
- .NET Desktop Runtime 7.0 (x86 / x64)
- .NET Desktop Runtime 8.0 (x86 / x64)
- .NET Desktop Runtime 9.0 (x86 / x64)
- .NET Desktop Runtime 10.0 (x86 / x64)

</details>

<details>
<summary><b>.NET SDK (4 adet)</b></summary>

- .NET SDK 6.0 (x64)
- .NET SDK 8.0 (x64)
- .NET SDK 9.0 (x64)
- .NET SDK 10.0 (x64)

</details>

<details>
<summary><b>ASP.NET Core Runtime (4 adet)</b></summary>

- ASP.NET Core Runtime 6.0 (x64)
- ASP.NET Core Runtime 8.0 (x64)
- ASP.NET Core Runtime 9.0 (x64)
- ASP.NET Core Runtime 10.0 (x64)

</details>

<details>
<summary><b>Diğer Bileşenler (17 adet)</b></summary>

- DirectX Offline Redistributable (Jun 2010)
- DirectPlay — Eski Oyun Desteği (Windows özelliği)
- XNA Framework Redistributable 3.1
- XNA Framework Redistributable 4.0
- Vulkan Runtime
- OpenAL
- WebView2 Runtime
- VS 2010 Tools for Office Runtime
- NVIDIA PhysX System Software 9.23
- Java 8 Runtime — JRE (x86 / x64)
- Java SE Development Kit 21
- MSXML 4.0 SP3 Parser
- .NET Framework 3.5 (Windows özelliği)
- .NET Framework 4.8.1

</details>

---

## 🚀 Hızlı Başlangıç

### Gereksinimler
- Windows 10 / 11
- Python 3.11 veya üzeri
- Yönetici yetkisi

### Kurulum

Hazır Windows kurulum dosyasını [GitHub Releases](https://github.com/IzzmooPro/RuntimeFix/releases/latest)
sayfasından indirebilirsiniz.

Kaynak koddan çalıştırmak için:

```bash
# Bağımlılıkları yükle
pip install -r requirements.txt
```

### Çalıştırma

Bağımlılıkları kurduktan sonra doğrudan Python ile çalıştırın:
```bash
python main.py
```

---

## 📁 Dosya Yapısı

```
RuntimeFix/
├── core/                        # Python çekirdek modülleri
│   ├── ui.py                    # PyQt6 arayüzü
│   ├── worker.py                # Arka plan indirme/kurulum motoru
│   ├── downloader.py            # HTTP indirici + offline cache
│   ├── installer.py             # Silent kurulum motoru
│   ├── security.py              # SHA-256 + domain whitelist
│   ├── utils.py                 # Sistem tespiti
│   ├── app_info.py              # Uygulama sürümü ve GitHub adresleri
│   ├── updater.py               # GitHub Releases güncelleme motoru
│   └── languages.py             # 5 dil desteği
├── data/
│   └── config.json              # Bileşen veritabanı
├── assets/                      # Uygulama logosu ve Windows ikonu
├── main.py                      # Ana giriş noktası
└── requirements.txt             # Python bağımlılıkları
```

`downloads/` ve `logs/` klasörleri çalışma sırasında gerektiğinde otomatik oluşur.

---

## 🔧 Teknik Detaylar

### Tespit Yöntemleri
Program bileşenlerin kurulu olup olmadığını şu yöntemlerle kontrol eder:
- **Disk** — .NET sürümleri `dotnet\shared` ve `dotnet\sdk` klasörlerinden okunur (en hızlı ve en güvenilir kaynak)
- **Registry** — Windows kayıt defteri kontrolü (VC++, XNA, MSXML, .NET sürüm kayıtları vb.)
- **Dosya kontrolü** — Kritik DLL varlığı (DirectX, Vulkan vb.)
- **Windows özellikleri** — DirectPlay gibi bileşenlerin durumu, RuntimeFix onları etkinleştirdiğinde kaydedilir
- Tespit hiçbir aşamada alt süreç (komut satırı aracı) çalıştırmaz

Tarama hiçbir alt süreç açmaz: 45 bileşenin tamamı disk ve kayıt defteri
üzerinden, saniyenin altında tespit edilir.

### Güvenlik
- Tüm indirmeler yalnızca HTTPS üzerinden yapılır
- İzin verilen domain listesi: Microsoft, Oracle, NVIDIA, OpenAL, LunarG
- SHA-256 hash doğrulaması her dosya için zorunludur
- Uygulama güncellemelerinde yalnızca sürümle birebir eşleşen setup asset'i kabul edilir

### Sessiz Kurulum
Her bileşen arka planda, kullanıcıya kurulum ekranı göstermeden yüklenir. Eski InstallShield tabanlı installer'lar (VC++ 2005-2010) için otomatik argüman deneme zinciri uygulanır.

---

## 📋 Bağımlılıklar

```
PyQt6>=6.6.0,<7
requests>=2.31.0,<3
urllib3>=2.0.0,<3
```

---

## ✅ Testler

```bash
python -m compileall -q main.py core tests
python -m unittest discover -s tests -v
```

---

## 🔢 Sürümleme

RuntimeFix sürümleri iki basamaklı artış düzenini kullanır: `1.00`, `1.05`,
`1.10`, `1.15` şeklinde ilerler. Ana seri değiştiğinde ilk sürüm `2.00` olur.

---

## 👤 Geliştirici

**IzzmooPro** — [IzzmooPro@gmail.com](mailto:IzzmooPro@gmail.com)

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) altında dağıtılmaktadır.
