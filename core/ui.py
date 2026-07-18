# -*- coding: utf-8 -*-
"""
ui.py — RuntimeFix v2.0 — "Sakin Modern" koyu tema
Tasarım ilkeleri:
  - Tek vurgu rengi (#8ab4f8), yalnızca ana eylem butonunda
  - Üstte sağlık halkası + tek cümlelik durum + tek buton
  - Eksikler üstte ve net, kurulular sönük — göz sadece işine bakar
  - Kategori kutuları / çerçeve içinde çerçeve yok; ayrım boşluk ve ince çizgilerle
Eski arayüz yedeği: ui_legacy.py.bak
"""

import logging
import os
import subprocess
from typing import List, Optional

try:
    import winsound
    _WINSOUND = True
except ImportError:
    _WINSOUND = False

from PyQt6.QtCore import (Qt, QThread, QTimer, pyqtSignal, QObject, QRectF,
                          QPointF, QVariantAnimation, QEasingCurve)
from PyQt6.QtGui import QColor, QPixmap, QIcon, QPainter, QBrush, QPen, QFont, QPolygonF
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget, QLineEdit, QTextEdit, QDialog,
    QApplication, QMenu,
)

from worker import DownloadInstallWorker, WorkerSignals
from security import SecurityManager
from utils import is_component_installed
from languages import LANGUAGES, LANG_ORDER, get as T

logger = logging.getLogger("RuntimeFix.ui")

# ── GitHub / güncelleme sabitleri ───────────────────────────────────────────
GITHUB_REPO  = "IzzmooPro/RuntimeFix"
VERSION_URL  = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/version.txt"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

# ── Palet — monokrom zemin + tek turkuaz vurgu ──────────────────────────────
C_BG       = "#17181c"   # pencere zemini (yumuşak antrasit)
C_SURFACE  = "#1e2025"   # hover / girdi zemini
C_BORDER   = "#25272d"   # ince ayraç
C_BORDER2  = "#2e3138"   # vurgulu ayraç
C_TEXT     = "#ececee"   # ana metin (kırık beyaz)
C_MUTED    = "#8a8f98"   # ikincil metin
C_DIM      = "#585d66"   # sönük (kurulu satırlar)
C_DIMMER   = "#41454d"   # en sönük (kurulu etiketi)
C_ACCENT   = "#2dd4bf"   # tek vurgu — sakin turkuaz (halka, seçim, odak)
C_ACCENT_H = "#4ae0cd"   # vurgu hover
C_ON_ACC   = "#062e29"   # vurgu üstü metin
C_PRIM_BG  = "#ececee"   # birincil buton zemini (kırık beyaz)
C_PRIM_FG  = "#141519"   # birincil buton yazısı
C_PRIM_H   = "#ffffff"   # birincil hover
C_PRIM_P   = "#d7d8dc"   # birincil pressed
C_OK       = "#7fd39a"   # yumuşak yeşil (başarı / onarım açık)
C_ERR      = "#f28b82"   # yumuşak kırmızı (yalnızca gerçek hatalar)

# ── Bileşen açıklamaları (tooltip) ──────────────────────────────────────────
COMPONENT_DESCRIPTIONS = {
    "VC++ Redist 2005":      "Eski oyunlar ve uygulamalar için gerekli C++ 2005 çalışma zamanı.",
    "VC++ Redist 2008":      "Birçok eski uygulama ve oyun motoru için gerekli C++ 2008 çalışma zamanı.",
    "VC++ Redist 2010":      "Bazı oyunlar ve yazılımların bağımlılığı olan C++ 2010 çalışma zamanı.",
    "VC++ Redist 2012":      "Visual Studio 2012 ile derlenen uygulamalar için C++ çalışma zamanı.",
    "VC++ Redist 2013":      "Visual Studio 2013 ile derlenen uygulamalar için C++ çalışma zamanı.",
    "VC++ Redist 2015-2022": "En yaygın C++ çalışma zamanı. Modern oyunların ve uygulamaların büyük bölümü bunu gerektirir.",
    ".NET Desktop Runtime 6.0": ".NET 6 ile yazılmış masaüstü uygulamaları için çalışma zamanı (LTS).",
    ".NET Desktop Runtime 7.0": ".NET 7 ile yazılmış masaüstü uygulamaları için çalışma zamanı.",
    ".NET Desktop Runtime 8.0": ".NET 8 ile yazılmış masaüstü uygulamaları için çalışma zamanı (LTS).",
    ".NET Desktop Runtime 9.0": ".NET 9 ile yazılmış masaüstü uygulamaları için çalışma zamanı.",
    ".NET Desktop Runtime 10.0": ".NET 10 ile yazılmış masaüstü uygulamaları için çalışma zamanı (LTS, güncel).",
    "ASP.NET Core Runtime":  "Web tabanlı .NET uygulamaları için ASP.NET Core çalışma zamanı.",
    ".NET SDK 6.0":          ".NET 6 uygulamaları geliştirmek ve derlemek için SDK (geliştirici aracı).",
    ".NET SDK 8.0":          ".NET 8 uygulamaları geliştirmek ve derlemek için SDK (LTS, geliştirici aracı).",
    ".NET SDK 9.0":          ".NET 9 uygulamaları geliştirmek ve derlemek için SDK (geliştirici aracı).",
    ".NET SDK 10.0":         ".NET 10 uygulamaları geliştirmek ve derlemek için SDK (LTS, geliştirici aracı).",
    "DirectX End-User Runtime Web Installer": "Eski oyunların gerektirdiği D3DX9/D3DX10/D3DX11 bileşenlerini yükler.",
    "DirectX Offline Redistributable": "İnternet bağlantısı olmadan DirectX eski bileşenlerini kurar (~100 MB).",
    "XNA Framework Redistributable 4.0": "Microsoft XNA oyun motoru ile geliştirilmiş oyunlar için çalışma zamanı.",
    "XNA Framework Redistributable 3.1": "Eski XNA oyunları (Terraria ilk sürümleri, Magicka vb.) için gerekli 3.1 çalışma zamanı.",
    "Vulkan Runtime":        "Modern oyunların kullandığı Vulkan grafik API çalışma zamanı.",
    "DirectPlay":            "2000'ler dönemi oyunların çoklu oyuncu/ağ bileşeni. Windows özelliği olarak etkinleştirilir.",
    "Java 8 Runtime":        "Eski oyun ve uygulamaların gerektirdiği Java 8 çalışma ortamı (JRE).",
    "OpenAL":                "3D ses işleme kütüphanesi. Bazı oyunlar ve ses uygulamaları bunu gerektirir.",
    "WebView2 Runtime":      "Microsoft Edge tabanlı web görüntüleyici bileşeni.",
    "VS 2010 Tools for Office Runtime": "VS 2010 ile geliştirilmiş Office eklentileri için çalışma zamanı.",
    "NVIDIA PhysX System Software": "NVIDIA PhysX fizik motoru. PhysX destekli oyunlar için gereklidir.",
    "Java SE Development Kit 21": "Java uygulama ve araçları çalıştırmak için JDK 21 (LTS).",
    "MSXML 4.0 SP3 Parser":  "XML işleme kütüphanesi. Bazı eski uygulamalar bunu gerektirir.",
    ".NET Framework 3.5":    "Windows'un isteğe bağlı özelliği. Eski .NET 2.0/3.5 uygulamaları için gerekli.",
    ".NET Framework 4.8.1":  "En güncel .NET Framework sürümü. .NET 4.x tabanlı uygulamalar için gerekli.",
}


def _get_tooltip(component: dict) -> str:
    name = component.get("name", "")
    for key, desc in COMPONENT_DESCRIPTIONS.items():
        if key.lower() in name.lower():
            return desc
    return ""


COMPONENT_SIZES = {
    "VC++ Redist 2005": 3, "VC++ Redist 2008": 4, "VC++ Redist 2010": 5,
    "VC++ Redist 2012": 7, "VC++ Redist 2013": 7, "VC++ Redist 2015-2022": 25,
    ".NET Desktop Runtime 6.0": 55, ".NET Desktop Runtime 7.0": 55,
    ".NET Desktop Runtime 8.0": 58, ".NET Desktop Runtime 9.0": 60,
    ".NET Desktop Runtime 10.0": 57,
    "ASP.NET Core Runtime 6.0": 10, "ASP.NET Core Runtime 8.0": 10,
    "ASP.NET Core Runtime 9.0": 10, "ASP.NET Core Runtime 10.0": 11,
    "DirectX End-User": 1, "DirectX Offline": 100,
    "XNA Framework": 8, "OpenAL": 1,
    "WebView2": 2, "VS 2010 Tools": 38,
    "MSXML": 3, "NVIDIA PhysX": 30, "Java SE": 160,
    "Java 8 Runtime": 70, "Vulkan": 25, "DirectPlay": 10,
    "XNA Framework Redistributable 3.1": 7,
    ".NET SDK 6.0": 200, ".NET SDK 8.0": 210, ".NET SDK 9.0": 215,
    ".NET SDK 10.0": 204,
    ".NET Framework 4.8.1": 70,
}


def estimate_size_mb(component: dict) -> int:
    name = component.get("name", "")
    for key, mb in COMPONENT_SIZES.items():
        if key.lower() in name.lower():
            return mb
    return 20


def make_app_icon(size: int = 32) -> QIcon:
    """Kod içi vektörel uygulama ikonu: koyu daire + kalkan + şimşek."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    p.setBrush(QBrush(QColor("#16213e")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, s, s)
    p.setBrush(QBrush(QColor(C_ACCENT)))
    shield = QPolygonF([QPointF(x, y) for x, y in [
        (s * 0.5, s * 0.10), (s * 0.88, s * 0.25), (s * 0.88, s * 0.55),
        (s * 0.5, s * 0.92), (s * 0.12, s * 0.55), (s * 0.12, s * 0.25),
    ]])
    p.drawPolygon(shield)
    p.setBrush(QBrush(QColor("#ffffff")))
    bolt = QPolygonF([QPointF(x, y) for x, y in [
        (s * 0.57, s * 0.22), (s * 0.38, s * 0.52), (s * 0.52, s * 0.52),
        (s * 0.43, s * 0.78), (s * 0.64, s * 0.45), (s * 0.50, s * 0.45),
    ]])
    p.drawPolygon(bolt)
    p.end()
    return QIcon(px)


def _beep(kind: str):
    if not _WINSOUND:
        return
    try:
        flag = winsound.MB_ICONHAND if kind == "error" else winsound.MB_ICONASTERISK
        winsound.MessageBeep(flag)
    except Exception:
        pass


# ── Global stil ─────────────────────────────────────────────────────────────
STYLE = f"""
QWidget {{
    font-family: "Segoe UI Variable Display", "Segoe UI", Arial, sans-serif;
    background-color: {C_BG};
    color: {C_TEXT};
    font-size: 10pt;
}}
QLabel {{ background: transparent; }}

QPushButton#primaryBtn {{
    background-color: {C_PRIM_BG};
    color: {C_PRIM_FG};
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 10pt;
    font-weight: 600;
}}
QPushButton#primaryBtn:hover    {{ background-color: {C_PRIM_H}; }}
QPushButton#primaryBtn:pressed  {{ background-color: {C_PRIM_P}; }}
QPushButton#primaryBtn:disabled {{ background-color: {C_SURFACE}; color: {C_DIM}; }}

QPushButton#ghostBtn {{
    background: transparent;
    color: {C_MUTED};
    border: 1px solid {C_BORDER2};
    border-radius: 8px;
    padding: 8px 18px;
}}
QPushButton#ghostBtn:hover    {{ color: {C_ERR}; border-color: {C_ERR}; }}
QPushButton#ghostBtn:disabled {{ color: {C_DIMMER}; border-color: {C_BORDER}; }}

QPushButton#flatBtn {{
    background: transparent;
    color: {C_MUTED};
    border: none;
    padding: 4px 8px;
    font-size: 9pt;
}}
QPushButton#flatBtn:hover {{ color: {C_TEXT}; }}

QPushButton#linkBtn {{
    background: transparent;
    color: {C_MUTED};
    border: none;
    padding: 2px 4px;
    font-size: 8.5pt;
}}
QPushButton#linkBtn:hover {{ color: {C_ACCENT}; }}

QPushButton#repairBtn {{
    background: transparent;
    color: #9aa1ab;
    border: 1px solid {C_BORDER2};
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 10pt;
    font-weight: 600;
}}
QPushButton#repairBtn:hover {{ color: {C_TEXT}; border-color: {C_DIM}; }}
QPushButton#repairBtn:disabled {{ color: {C_DIMMER}; border-color: {C_BORDER}; }}

QPushButton#infoDot {{
    background: transparent;
    color: {C_MUTED};
    border: 1px solid {C_BORDER2};
    border-radius: 11px;
    min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px;
    padding: 0;
    font-size: 10pt;
    font-weight: 600;
}}
QPushButton#infoDot:hover {{ color: {C_ACCENT}; border-color: {C_ACCENT}; }}
QPushButton#infoDot:disabled {{ color: {C_DIMMER}; border-color: {C_BORDER}; }}

QLineEdit {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 7px;
    padding: 5px 10px;
    color: {C_TEXT};
    font-size: 9pt;
}}
QLineEdit:focus {{ border-color: {C_ACCENT}; }}

QProgressBar {{
    background: {C_BORDER};
    border: none;
    border-radius: 2px;
    max-height: 4px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {C_ACCENT}; border-radius: 2px; }}

QWidget#updateBar {{
    background: #14302b;
    border-bottom: 1px solid #1e4a41;
}}

QWidget#heroCard {{
    background: #1c1e23;
    border: 1px solid #292c33;
    border-radius: 12px;
}}
QWidget#heroRow, QWidget#progRow {{ background: transparent; }}
QWidget#heroCard QLabel {{ background: transparent; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER2}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {C_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QMenu {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER2};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; color: {C_TEXT}; }}
QMenu::item:selected {{ background: {C_BORDER2}; }}

QToolTip {{
    background: {C_SURFACE};
    color: {C_TEXT};
    border: 1px solid {C_BORDER2};
    padding: 5px 8px;
}}
"""


# ── Sağlık halkası ──────────────────────────────────────────────────────────
class HealthRing(QWidget):
    """Dairesel yüzde göstergesi — yumuşak süpürme animasyonlu.

    %100'e ulaşınca vurgu rengi sessizce yumuşak yeşile döner.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pct: Optional[int] = None      # hedef değer (None = taranmadı)
        self._display: Optional[float] = None  # ekranda çizilen (animasyonlu)
        self._busy = False
        self._anim: Optional[QVariantAnimation] = None
        self.setFixedSize(56, 56)

    def set_percent(self, pct: Optional[int], animate: bool = True):
        self._busy = False
        if self._anim:
            self._anim.stop()
            self._anim = None
        if pct is None:
            self._pct = None
            self._display = None
            self.update()
            return
        pct = max(0, min(100, pct))
        start = self._display if self._display is not None else 0.0
        self._pct = pct
        if not animate or abs(start - pct) < 1:
            self._display = float(pct)
            self.update()
            return
        anim = QVariantAnimation(self)
        anim.setStartValue(float(start))
        anim.setEndValue(float(pct))
        anim.setDuration(700)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_anim_step)
        self._anim = anim
        anim.start()

    def _on_anim_step(self, value):
        self._display = float(value)
        self.update()

    def set_busy(self):
        self._busy = True
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)

        pen = QPen(QColor(C_BORDER2), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        shown = self._display
        complete = (self._pct == 100 and shown is not None and shown >= 99.5)
        if shown is not None and not self._busy:
            pen.setColor(QColor(C_OK if complete else C_ACCENT))
            p.setPen(pen)
            span = int(-360 * 16 * (shown / 100))
            p.drawArc(rect, 90 * 16, span)

        p.setPen(QPen(QColor(C_OK if complete else C_TEXT)))
        f = QFont(self.font())
        f.setPointSize(11)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        if self._busy:
            text = "…"
        elif shown is None:
            text = "—"
        else:
            text = f"%{round(shown)}"
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


# ── Bileşen satırı ──────────────────────────────────────────────────────────
class ComponentRow(QWidget):
    toggled = pyqtSignal(str, bool)

    ST_MISSING, ST_INSTALLED, ST_DONE, ST_FAILED = range(4)

    def __init__(self, component: dict, installed: bool, lang: str, parent=None):
        super().__init__(parent)
        self.component = component
        self._lang = lang
        self._state = self.ST_INSTALLED if installed else self.ST_MISSING
        self._checked = False   # seçim kullanıcıya ait — hiçbir şey önceden seçili gelmez
        self._interactive = True
        self._repair = False   # Onarım modu: kurulu satırlar da seçilebilir
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(31)
        tip = _get_tooltip(component)
        if tip:
            self.setToolTip(tip)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)

        self._mark = QLabel()
        self._mark.setFixedWidth(26)
        self._mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._mark)

        self._name = QLabel(component.get("name", "?"))
        lay.addWidget(self._name)
        lay.addStretch(1)

        self._right = QLabel()
        lay.addWidget(self._right)

        self._render()

    # ── görünüm ──
    def _render(self):
        if self._state == self.ST_MISSING:
            self.setStyleSheet(
                f"ComponentRow {{ border-radius:7px; background:transparent; }}"
                f"ComponentRow:hover {{ background:{C_SURFACE}; }}"
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if self._checked:
                self._mark.setText("●")
                self._mark.setStyleSheet(f"color:{C_ACCENT};font-size:15pt;")
            else:
                self._mark.setText("○")
                self._mark.setStyleSheet(f"color:{C_MUTED};font-size:15pt;")
            self._name.setStyleSheet(f"color:{C_TEXT};font-size:10pt;")
            self._right.setText(f"{estimate_size_mb(self.component)} MB")
            self._right.setStyleSheet(f"color:{C_MUTED};font-size:8.5pt;")
        elif self._state == self.ST_DONE:
            self.setStyleSheet("ComponentRow { background:transparent; }")
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._mark.setText("●")
            self._mark.setStyleSheet(f"color:{C_OK};font-size:15pt;")
            self._name.setStyleSheet(f"color:{C_TEXT};font-size:10pt;")
            self._right.setText(T(self._lang, "row_done"))
            self._right.setStyleSheet(f"color:{C_OK};font-size:8.5pt;")
        elif self._state == self.ST_FAILED:
            self.setStyleSheet("ComponentRow { background:transparent; }")
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._mark.setText("✕")
            self._mark.setStyleSheet(f"color:{C_ERR};font-size:13pt;")
            self._name.setStyleSheet(f"color:{C_TEXT};font-size:10pt;")
            self._right.setText(T(self._lang, "row_failed"))
            self._right.setStyleSheet(f"color:{C_ERR};font-size:8.5pt;")
        elif self._state == self.ST_INSTALLED and self._repair:
            # Onarım modu: kurulu satır seçilebilir hale gelir
            self.setStyleSheet(
                f"ComponentRow {{ border-radius:7px; background:transparent; }}"
                f"ComponentRow:hover {{ background:{C_SURFACE}; }}"
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if self._checked:
                self._mark.setText("●")
                self._mark.setStyleSheet(f"color:{C_ACCENT};font-size:15pt;")
                self._name.setStyleSheet(f"color:{C_TEXT};font-size:10pt;")
                self._right.setText(T(self._lang, "row_reinstall"))
                self._right.setStyleSheet(f"color:{C_ACCENT};font-size:8.5pt;")
            else:
                self._mark.setText("○")
                self._mark.setStyleSheet(f"color:{C_MUTED};font-size:15pt;")
                self._name.setStyleSheet(f"color:{C_MUTED};font-size:10pt;")
                self._right.setText(T(self._lang, "row_installed"))
                self._right.setStyleSheet(f"color:{C_DIMMER};font-size:8.5pt;")
        else:  # ST_INSTALLED — sönük, ikonsuz (durumu isim + etiket anlatır)
            self.setStyleSheet("ComponentRow { background:transparent; }")
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._mark.setText("")
            self._name.setStyleSheet(f"color:{C_DIM};font-size:10pt;")
            self._right.setText(T(self._lang, "row_installed"))
            self._right.setStyleSheet(f"color:{C_DIMMER};font-size:8.5pt;")

    def update_lang(self, lang: str):
        self._lang = lang
        self._render()

    # ── etkileşim ──
    def _selectable(self) -> bool:
        return (self._state == self.ST_MISSING
                or (self._state == self.ST_INSTALLED and self._repair))

    def mousePressEvent(self, event):
        if (self._selectable() and self._interactive
                and event.button() == Qt.MouseButton.LeftButton):
            self.set_checked(not self._checked)
        super().mousePressEvent(event)

    def set_checked(self, val: bool):
        if not self._selectable() or self._checked == val:
            return
        self._checked = val
        self._render()
        self.toggled.emit(self.component.get("name", ""), val)

    def set_repair_mode(self, on: bool):
        if self._repair == on:
            return
        self._repair = on
        if self._state == self.ST_INSTALLED and not on:
            self._checked = False   # mod kapanınca onarım seçimleri temizlenir
        self._render()

    def set_interactive(self, enabled: bool):
        self._interactive = enabled

    def mark_installed(self):
        self._state = self.ST_DONE
        self._checked = False
        self._render()

    def mark_failed(self):
        self._state = self.ST_FAILED
        self._render()

    @property
    def is_missing(self) -> bool:
        return self._state in (self.ST_MISSING, self.ST_FAILED)

    @property
    def is_selected(self) -> bool:
        return self._selectable() and self._checked

    def matches(self, query: str) -> bool:
        return query.lower() in self.component.get("name", "").lower()


# ── Bölüm başlığı ───────────────────────────────────────────────────────────
class SectionHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 2)
        lay.setSpacing(8)
        self.label = QLabel()
        self.label.setStyleSheet(
            f"color:{C_MUTED};font-size:8pt;font-weight:600;letter-spacing:1px;"
        )
        lay.addWidget(self.label)
        lay.addStretch(1)
        self.action = QPushButton()
        self.action.setObjectName("linkBtn")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.setVisible(False)
        lay.addWidget(self.action)


# ── Günlük görüntüleyici ────────────────────────────────────────────────────
class LogViewerDialog(QDialog):
    def __init__(self, log_path: str, lang: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T(lang, "hdr_log"))
        self.resize(680, 460)
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            f"background:{C_SURFACE};border:1px solid {C_BORDER};"
            f"border-radius:8px;color:{C_MUTED};"
            f"font-family:Consolas,monospace;font-size:8.5pt;"
        )
        lay.addWidget(self._text)
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            self._text.setPlainText("".join(lines[-500:]))
            self._text.moveCursor(self._text.textCursor().MoveOperation.End)
        except OSError as exc:
            self._text.setPlainText(f"Log okunamadı: {exc}")


# ── Hakkında ────────────────────────────────────────────────────────────────
class AboutDialog(QDialog):
    def __init__(self, version: str, lang: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T(lang, "about_btn"))
        self.setFixedWidth(360)
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(6)

        icon = QLabel()
        icon.setPixmap(make_app_icon(56).pixmap(56, 56))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)

        title = QLabel(f"RuntimeFix v{version}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{C_TEXT};font-size:13pt;font-weight:600;")
        lay.addWidget(title)

        info = QLabel(T(lang, "trust_line").replace("✔", "•").replace("\n", "<br>"))
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet(f"color:{C_MUTED};font-size:9pt;")
        lay.addWidget(info)

        dev = QLabel("IzzmooPro — IzzmooPro@gmail.com")
        dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev.setStyleSheet(f"color:{C_DIM};font-size:8pt;")
        lay.addWidget(dev)

        lay.addSpacing(8)
        ok = QPushButton("Tamam" if lang == "tr" else "OK")
        ok.setObjectName("primaryBtn")
        ok.clicked.connect(self.accept)
        lay.addWidget(ok, alignment=Qt.AlignmentFlag.AlignCenter)


# ── Onarım modu bilgi ekranı ────────────────────────────────────────────────
class RepairInfoDialog(QDialog):
    """'Onarım modu nedir?' bilgi ekranı — yalnızca açıklama, onay istemez."""

    def __init__(self, lang: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T(lang, "repair_mode"))
        self.setFixedWidth(420)
        self.setStyleSheet(STYLE)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(12)

        title = QLabel("🔧  " + T(lang, "repair_mode"))
        title.setStyleSheet(f"color:{C_TEXT};font-size:13pt;font-weight:600;")
        lay.addWidget(title)

        body = QLabel(T(lang, "repair_dlg_text"))
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{C_MUTED};font-size:9.5pt;")
        lay.addWidget(body)

        lay.addSpacing(6)
        ok = QPushButton("Tamam" if lang == "tr" else "OK")
        ok.setObjectName("primaryBtn")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept)
        lay.addWidget(ok, alignment=Qt.AlignmentFlag.AlignRight)


# ── Güncelleme denetimi ─────────────────────────────────────────────────────
class UpdateSignals(QObject):
    result = pyqtSignal(str)   # yeni sürüm no; "" = güncel ya da erişilemedi


class UpdateChecker(QObject):
    """GitHub'daki version.txt'yi okur, daha yeni sürüm varsa bildirir.

    Güvenlik notu: yalnızca sürüm NUMARASI okunur ve karşılaştırılır;
    hiçbir şey otomatik indirilmez/çalıştırılmaz. "Güncelle" butonu
    kullanıcıyı GitHub sürüm sayfasına (tarayıcıya) götürür.
    """

    def __init__(self, current: str):
        super().__init__()
        self.current = current
        self.signals = UpdateSignals()

    @staticmethod
    def _ver(s: str):
        try:
            return tuple(int(x) for x in s.strip().split("."))
        except ValueError:
            return (0,)

    def run(self):
        try:
            import requests
            resp = requests.get(VERSION_URL, timeout=8,
                                headers={"User-Agent": "RuntimeFix-UpdateCheck"})
            resp.raise_for_status()
            remote = resp.text.strip().splitlines()[0].strip()
            if self._ver(remote) > self._ver(self.current):
                logger.info(f"[GÜNCELLEME] Yeni sürüm bulundu: v{remote} (yerel v{self.current})")
                self.signals.result.emit(remote)
                return
            logger.info(f"[GÜNCELLEME] Sürüm güncel (v{self.current})")
        except Exception as exc:
            logger.debug(f"[GÜNCELLEME] Denetim atlandı: {exc}")
        self.signals.result.emit("")


# ── Tarama işçisi ───────────────────────────────────────────────────────────
class ScanSignals(QObject):
    done = pyqtSignal(list)


class ScanWorker(QObject):
    def __init__(self, components):
        super().__init__()
        self.components = components
        self.signals = ScanSignals()

    def run(self):
        log = logging.getLogger("RuntimeFix")
        results = []
        for c in self.components:
            installed = is_component_installed(c)
            log.info(f"  [{'OK  ' if installed else 'MISS'}] {c.get('name', '?')}")
            results.append((c, installed))
        self.signals.done.emit(results)


# ── Ana pencere ─────────────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self, components: List[dict], security: SecurityManager,
                 version: str = "2.0"):
        super().__init__()
        self._version    = version
        self._components = sorted(components, key=lambda c: c.get("name", ""))
        self._security   = security
        self._lang       = "tr"
        self._state      = "idle"        # idle | scanning | ready | busy
        self._rows: List[ComponentRow] = []
        self._thread:      Optional[QThread] = None
        self._worker:      Optional[DownloadInstallWorker] = None
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._upd_thread:  Optional[QThread] = None
        self._upd_worker:  Optional[UpdateChecker] = None
        self._update_ver   = ""
        self._failed:          List[str] = []
        self._installed_names: List[str] = []
        self._ok_count   = 0
        self._miss_count = 0
        self._status_base = ""
        self._repair_mode = False

        import sys as _sys, tempfile as _tf
        if getattr(_sys, "frozen", False):
            _log_dir = os.path.join(_tf.gettempdir(), "RuntimeFix_logs")
        else:
            _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            _log_dir = os.path.join(_root, "logs")
        os.makedirs(_log_dir, exist_ok=True)
        self._log_path = os.path.join(_log_dir, "aio_runtime.log")

        self.setWindowTitle("RuntimeFix")
        # Genişlik sabit (yatay boyutlandırma kapalı), dikey serbest.
        # 530px, 5 dilin en uzun metinlerini de kırpmadan taşır (ölçülerek seçildi).
        self.setFixedWidth(530)
        self.setMinimumHeight(520)
        self.resize(530, 600)
        self.setStyleSheet(STYLE)
        self.setWindowIcon(make_app_icon(32))
        self._build_ui()
        self._apply_lang()
        # Açılışta otomatik tarama — kullanıcı ilk bakışta durumu görür
        QTimer.singleShot(400, self._do_scan)
        # Güncelleme denetimi arka planda, taramayı bekletmez
        QTimer.singleShot(2000, self._check_updates)

    # ── kurulum ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Üst çubuk: kimlik solda, arama ortada, eylemler sağda ──
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 6, 12, 6)
        hl.setSpacing(8)

        self._logo_lbl = QLabel()
        self._logo_lbl.setPixmap(make_app_icon(20).pixmap(20, 20))
        hl.addWidget(self._logo_lbl)

        self._title_lbl = QLabel("RuntimeFix")
        self._title_lbl.setStyleSheet(f"color:{C_TEXT};font-size:11pt;font-weight:600;")
        hl.addWidget(self._title_lbl)

        ver_lbl = QLabel(f"v{self._version}")
        ver_lbl.setStyleSheet(f"color:{C_DIM};font-size:8.5pt;")
        hl.addWidget(ver_lbl, alignment=Qt.AlignmentFlag.AlignBottom)

        hl.addStretch(1)
        self._search_box = QLineEdit()
        self._search_box.setFixedWidth(150)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search_box.textChanged.connect(self._on_search)
        hl.addWidget(self._search_box)
        hl.addStretch(1)

        self._log_btn = QPushButton()
        self._log_btn.setObjectName("flatBtn")
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.clicked.connect(self._open_log)
        hl.addWidget(self._log_btn)

        self._lang_btn = QPushButton()
        self._lang_btn.setObjectName("flatBtn")
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_btn.clicked.connect(self._show_lang_menu)
        hl.addWidget(self._lang_btn)

        self._about_btn = QPushButton()
        self._about_btn.setObjectName("flatBtn")
        self._about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._about_btn.clicked.connect(self._open_about)
        hl.addWidget(self._about_btn)

        root.addWidget(header)
        root.addWidget(self._hairline())

        # ── Güncelleme şeridi (yalnızca yeni sürüm varsa görünür) ──
        self._update_bar = QWidget()
        self._update_bar.setObjectName("updateBar")
        self._update_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        ub = QHBoxLayout(self._update_bar)
        ub.setContentsMargins(12, 6, 12, 6)
        ub.setSpacing(8)
        self._update_lbl = QLabel()
        self._update_lbl.setStyleSheet(f"color:{C_ACCENT};font-size:9pt;")
        ub.addWidget(self._update_lbl)
        ub.addStretch(1)
        self._update_btn = QPushButton()
        self._update_btn.setObjectName("linkBtn")
        self._update_btn.setStyleSheet(f"color:{C_ACCENT};font-weight:600;")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.clicked.connect(self._open_releases)
        ub.addWidget(self._update_btn)
        dismiss = QPushButton("✕")
        dismiss.setObjectName("flatBtn")
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.clicked.connect(lambda: self._update_bar.setVisible(False))
        ub.addWidget(dismiss)
        self._update_bar.setVisible(False)
        root.addWidget(self._update_bar)

        # ── Hero kartı: halka + durum + buton + ilerleme, tek odak ──
        hero_outer = QWidget()
        ho = QVBoxLayout(hero_outer)
        ho.setContentsMargins(10, 10, 10, 6)

        card = QWidget()
        card.setObjectName("heroCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        hero = QWidget()
        hero.setObjectName("heroRow")
        he = QHBoxLayout(hero)
        he.setContentsMargins(14, 12, 14, 10)
        he.setSpacing(12)

        self._ring = HealthRing()
        he.addWidget(self._ring)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        self._headline = QLabel()
        self._headline.setStyleSheet(
            f"color:{C_TEXT};font-size:11.5pt;font-weight:600;")
        mid.addWidget(self._headline)
        self._subline = QLabel()
        self._subline.setStyleSheet(f"color:{C_MUTED};font-size:9pt;")
        self._subline.setWordWrap(True)
        mid.addWidget(self._subline)
        he.addLayout(mid, 1)

        # Sağ sütun: ana buton + hemen altında Onarım modu anahtarı
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        self._fix_btn = QPushButton()
        self._fix_btn.setObjectName("primaryBtn")
        self._fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fix_btn.clicked.connect(self._on_main_btn)
        btn_col.addWidget(self._fix_btn)

        repair_row = QHBoxLayout()
        repair_row.setSpacing(6)
        self._repair_btn = QPushButton()
        self._repair_btn.setObjectName("repairBtn")
        self._repair_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._repair_btn.clicked.connect(lambda: self._toggle_repair_mode())
        repair_row.addWidget(self._repair_btn, 1)

        self._repair_info_btn = QPushButton("?")
        self._repair_info_btn.setObjectName("infoDot")
        self._repair_info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._repair_info_btn.clicked.connect(
            lambda: RepairInfoDialog(self._lang, self).exec())
        repair_row.addWidget(self._repair_info_btn)
        btn_col.addLayout(repair_row)

        self._cancel_btn = QPushButton()
        self._cancel_btn.setObjectName("ghostBtn")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self._cancel)
        self._cancel_btn.setVisible(False)
        btn_col.addWidget(self._cancel_btn)

        he.addLayout(btn_col)

        cv.addWidget(hero)

        # ── İnce ilerleme çubuğu (kurulumda görünür, kartın içinde) ──
        prog_wrap = QWidget()
        prog_wrap.setObjectName("progRow")
        pl = QHBoxLayout(prog_wrap)
        pl.setContentsMargins(16, 0, 16, 14)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        pl.addWidget(self._progress)
        self._prog_wrap = prog_wrap
        self._prog_wrap.setVisible(False)
        cv.addWidget(prog_wrap)

        ho.addWidget(card)
        root.addWidget(hero_outer)

        # ── Liste ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        body = QWidget()
        self._list_layout = QVBoxLayout(body)
        self._list_layout.setContentsMargins(10, 4, 10, 12)
        self._list_layout.setSpacing(1)

        self._miss_header = SectionHeader()
        self._miss_header.action.clicked.connect(self._toggle_select_all)
        self._ok_header = SectionHeader()
        self._ok_header.action.setVisible(False)   # Onarım modu hero kartına taşındı
        self._list_layout.addWidget(self._miss_header)
        self._list_layout.addWidget(self._ok_header)
        self._list_layout.addStretch(1)

        self._scroll.setWidget(body)
        root.addWidget(self._scroll, 1)

        # ── Alt bilgi: üç güven maddesi — sol / orta / sağ eşit hizada ──
        root.addWidget(self._hairline())
        footer = QWidget()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 7, 12, 7)
        self._trust_labels = []
        aligns = (Qt.AlignmentFlag.AlignLeft,
                  Qt.AlignmentFlag.AlignCenter,
                  Qt.AlignmentFlag.AlignRight)
        for a in aligns:
            lbl = QLabel()
            lbl.setStyleSheet(f"color:{C_DIM};font-size:8pt;")
            lbl.setAlignment(a | Qt.AlignmentFlag.AlignVCenter)
            fl.addWidget(lbl, 1)
            self._trust_labels.append(lbl)
        root.addWidget(footer)

    @staticmethod
    def _hairline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background:{C_BORDER};border:none;max-height:1px;")
        return line

    # ── dil ──────────────────────────────────────────────────────────────────
    def _show_lang_menu(self):
        menu = QMenu(self)
        for code in LANG_ORDER:
            act = menu.addAction(LANGUAGES[code]["name"])
            act.triggered.connect(lambda _=False, c=code: self._set_lang(c))
        menu.exec(self._lang_btn.mapToGlobal(self._lang_btn.rect().bottomLeft()))

    def _set_lang(self, code: str):
        self._lang = code
        self._apply_lang()

    def _apply_lang(self):
        lang = self._lang
        self._search_box.setPlaceholderText(T(lang, "search_ph"))
        self._log_btn.setText(T(lang, "hdr_log"))
        self._lang_btn.setText(lang.upper())
        self._about_btn.setText(T(lang, "about_btn"))
        self._cancel_btn.setText(T(lang, "cancel_btn"))
        # Güven maddeleri: sol / orta / sağ etiketlere dağıt
        parts = [p.strip().lstrip("✔").strip()
                 for p in T(lang, "trust_line").splitlines() if p.strip()]
        for i, lbl in enumerate(self._trust_labels):
            lbl.setText(parts[i] if i < len(parts) else "")
        for row in self._rows:
            row.update_lang(lang)
        self._refresh_update_bar()
        self._refresh_hero()
        self._refresh_headers()

    # ── durum yansıtma ──────────────────────────────────────────────────────
    def _refresh_hero(self):
        lang = self._lang
        total = len(self._components)
        if self._state == "idle":
            self._ring.set_percent(None)
            self._headline.setText(T(lang, "hero_ready"))
            self._subline.setText(T(lang, "sub_ready"))
            self._fix_btn.setText(T(lang, "btn_scan"))
            self._fix_btn.setEnabled(True)
            self._repair_btn.setEnabled(False)
        elif self._state == "scanning":
            self._ring.set_busy()
            self._headline.setText(T(lang, "scanning"))
            self._subline.setText(T(lang, "sub_ready"))
            self._fix_btn.setText(T(lang, "scanning"))
            self._fix_btn.setEnabled(False)
            self._repair_btn.setEnabled(False)
        elif self._state == "busy":
            self._fix_btn.setVisible(False)
            self._repair_btn.setVisible(False)
            self._repair_info_btn.setVisible(False)
            self._cancel_btn.setVisible(True)
            self._cancel_btn.setEnabled(True)
        else:  # ready
            pct = int(round((self._ok_count / total) * 100)) if total else 100
            self._ring.set_percent(pct)
            if self._miss_count == 0:
                self._headline.setText(T(lang, "hero_ok"))
            else:
                self._headline.setText(T(lang, "hero_issues"))
            self._update_subline()
            sel = sum(1 for r in self._rows if r.is_selected)
            if sel > 0:
                # Eksik ya da onarım — seçim varsa buton kurulum modunda
                self._fix_btn.setText(T(lang, "btn_fix", n=sel))
                self._fix_btn.setEnabled(True)
            elif self._miss_count == 0:
                self._fix_btn.setText(T(lang, "btn_scan"))
                self._fix_btn.setEnabled(True)
            else:
                # Seçim yokken buton kullanıcıya ne yapacağını söyler
                self._fix_btn.setText(T(lang, "btn_select"))
                self._fix_btn.setEnabled(False)
            self._fix_btn.setVisible(True)
            self._repair_btn.setVisible(True)
            self._repair_btn.setEnabled(True)
            self._repair_info_btn.setVisible(True)
            self._cancel_btn.setVisible(False)

    def _update_subline(self):
        lang = self._lang
        text = T(lang, "sub_summary", ok=self._ok_count, miss=self._miss_count)
        sel_rows = [r for r in self._rows if r.is_selected]
        if sel_rows:
            mb = sum(estimate_size_mb(r.component) for r in sel_rows)
            text += T(lang, "sub_selected", mb=mb)
        self._subline.setText(text)

    def _refresh_headers(self):
        lang = self._lang
        self._miss_header.label.setText(
            f"{T(lang, 'badge_missing').upper()} — {self._miss_count}")
        self._ok_header.label.setText(
            f"{T(lang, 'badge_installed').upper()} — {self._ok_count}")
        missing_rows = [r for r in self._rows if r.is_missing]
        all_sel = missing_rows and all(r.is_selected for r in missing_rows
                                       if r._state == ComponentRow.ST_MISSING)
        self._miss_header.action.setText(
            T(lang, "sel_none2") if all_sel else T(lang, "sel_all2"))
        self._miss_header.action.setVisible(self._miss_count > 0)
        self._miss_header.setVisible(self._miss_count > 0)
        self._ok_header.setVisible(self._ok_count > 0)
        # Onarım modu düğmesi hero kartında — durum yazıyla ve renkle net:
        # Açık = yeşil çerçeve, Kapalı = nötr gri (kırmızı yalnızca hatalar için)
        if self._repair_mode:
            self._repair_btn.setText(f"{T(lang, 'repair_mode')}: {T(lang, 'state_on')}")
            self._repair_btn.setStyleSheet(f"color:{C_OK};border-color:{C_OK};")
        else:
            self._repair_btn.setText(f"{T(lang, 'repair_mode')}: {T(lang, 'state_off')}")
            self._repair_btn.setStyleSheet("")
        self._repair_btn.setToolTip(T(lang, "repair_tip"))

    # ── güncelleme denetimi ─────────────────────────────────────────────────
    def _check_updates(self):
        self._upd_thread = QThread()
        self._upd_worker = UpdateChecker(self._version)
        self._upd_worker.moveToThread(self._upd_thread)
        self._upd_worker.signals.result.connect(
            self._on_update_result, Qt.ConnectionType.QueuedConnection)
        self._upd_worker.signals.result.connect(self._upd_thread.quit)
        self._upd_thread.started.connect(self._upd_worker.run)
        self._upd_thread.start()

    def _on_update_result(self, remote_ver: str):
        QTimer.singleShot(0, self._cleanup_update_thread)
        self._update_ver = remote_ver
        if remote_ver:
            self._refresh_update_bar()
            self._update_bar.setVisible(True)

    def _refresh_update_bar(self):
        if self._update_ver:
            self._update_lbl.setText(
                T(self._lang, "update_avail", v=self._update_ver))
            self._update_btn.setText(T(self._lang, "update_btn") + " →")

    def _open_releases(self):
        import webbrowser
        logger.info(f"[GÜNCELLEME] Sürüm sayfası açılıyor: {RELEASES_URL}")
        webbrowser.open(RELEASES_URL)

    def _cleanup_update_thread(self):
        if self._upd_thread:
            self._upd_thread.wait(3000)
        self._upd_thread = None
        self._upd_worker = None

    # ── tarama ──────────────────────────────────────────────────────────────
    def _on_main_btn(self):
        if self._state == "ready" and any(r.is_selected for r in self._rows):
            self._start_install()
        elif self._state in ("idle", "ready"):
            self._do_scan()

    def _do_scan(self):
        if self._state in ("scanning", "busy"):
            return
        logger.info(f"[TARAMA] Başladı — {len(self._components)} bileşen")
        self._state = "scanning"
        self._refresh_hero()
        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(self._components)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_worker.signals.done.connect(
            self._on_scan_done, Qt.ConnectionType.QueuedConnection)
        self._scan_worker.signals.done.connect(self._scan_thread.quit)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_thread.start()

    def _on_scan_done(self, results: list):
        QTimer.singleShot(0, self._cleanup_scan_thread)
        self._ok_count = sum(1 for _, inst in results if inst)
        self._miss_count = len(results) - self._ok_count
        logger.info(f"[TARAMA] Bitti — {self._ok_count} kurulu / {self._miss_count} eksik")

        # Eski satırları temizle
        for row in self._rows:
            self._list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        missing = [(c, i) for c, i in results if not i]
        installed = [(c, i) for c, i in results if i]

        # Eksikler üstte, kurulular altta — kategorisiz, alfabetik, sade
        idx_miss = self._list_layout.indexOf(self._miss_header) + 1
        for comp, inst in missing:
            row = ComponentRow(comp, inst, self._lang)
            row.toggled.connect(self._on_row_toggled)
            self._rows.append(row)
            self._list_layout.insertWidget(idx_miss, row)
            idx_miss += 1

        idx_ok = self._list_layout.indexOf(self._ok_header) + 1
        for comp, inst in installed:
            row = ComponentRow(comp, inst, self._lang)
            row.toggled.connect(self._on_row_toggled)
            self._rows.append(row)
            self._list_layout.insertWidget(idx_ok, row)
            idx_ok += 1

        # Onarım modu açıksa yeni satırlara da uygula
        if self._repair_mode:
            for r in self._rows:
                r.set_repair_mode(True)

        self._state = "ready"
        self._refresh_hero()
        self._refresh_headers()
        self._on_search(self._search_box.text())
        # Not: taramada ses yok — ses yalnızca yükleme bittiğinde çalar.

    def _cleanup_scan_thread(self):
        if self._scan_thread:
            self._scan_thread.wait(3000)
        self._scan_thread = None
        self._scan_worker = None

    # ── seçim / arama ───────────────────────────────────────────────────────
    def _on_row_toggled(self, name: str, checked: bool):
        logger.info(f"[SEÇİM] {name} → {'seçildi' if checked else 'kaldırıldı'}")
        self._refresh_hero()
        self._refresh_headers()

    def _toggle_repair_mode(self):
        # Buton durumu yazı+renkle zaten net; onay penceresi yok, direkt geçiş.
        # "Onarım modu nedir?" açıklaması yandaki ? düğmesinde.
        if self._state == "busy":
            return
        self._repair_mode = not self._repair_mode
        logger.info(f"[ONARIM] Onarım modu {'AÇIK' if self._repair_mode else 'kapalı'}")
        for r in self._rows:
            r.set_repair_mode(self._repair_mode)
        self._refresh_hero()
        self._refresh_headers()

    def _toggle_select_all(self):
        missing_rows = [r for r in self._rows
                        if r._state == ComponentRow.ST_MISSING]
        target = not all(r.is_selected for r in missing_rows) if missing_rows else True
        for r in missing_rows:
            r.set_checked(target)
        self._refresh_hero()
        self._refresh_headers()

    def _on_search(self, query: str):
        q = query.strip()
        for row in self._rows:
            row.setVisible(row.matches(q) if q else True)

    # ── kurulum ─────────────────────────────────────────────────────────────
    def _start_install(self):
        selected = [r.component for r in self._rows if r.is_selected]
        if not selected:
            QMessageBox.information(
                self, T(self._lang, "nothing_to_do_title"),
                T(self._lang, "nothing_to_do_msg"))
            return
        if self._thread and self._thread.isRunning():
            return

        names = [c.get("name", "?") for c in selected]
        logger.info(f"[KURULUM] Başlıyor — {len(selected)} bileşen: {', '.join(names)}")

        self._failed.clear()
        self._installed_names.clear()
        self._progress.setValue(0)
        self._prog_wrap.setVisible(True)
        self._state = "busy"
        self._set_busy(True)
        self._status_base = T(self._lang, "status_getting_ready")
        self._subline.setText(self._status_base)
        self._refresh_hero()

        self._thread = QThread()
        self._worker = DownloadInstallWorker(selected, self._security)
        self._worker.moveToThread(self._thread)
        sig: WorkerSignals = self._worker.signals
        sig.progress.connect(self._progress.setValue)
        sig.status.connect(self._on_status)
        sig.file_download_progress.connect(self._on_file_progress)
        sig.component_error.connect(self._on_component_error)
        sig.component_success.connect(self._on_component_success)
        sig.restart_required.connect(self._on_restart_required)
        sig.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        sig.finished.connect(self._thread.quit)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _cancel(self):
        logger.info("[TIKLA] İptal")
        self._cancel_btn.setEnabled(False)
        if self._worker:
            self._worker.cancel()

    def _on_status(self, text: str):
        self._status_base = text
        self._subline.setText(text)

    def _on_file_progress(self, filename: str, pct: int, speed: float):
        if speed > 0:
            self._subline.setText(f"{self._status_base}  ·  %{pct}  ·  {speed:.1f} MB/s")

    def _on_component_success(self, name: str):
        logger.info(f"[KURULUM] BAŞARILI: {name}")
        self._installed_names.append(name)
        self._ok_count += 1
        self._miss_count = max(0, self._miss_count - 1)
        for row in self._rows:
            if row.component.get("name", "").strip() == name.strip():
                row.mark_installed()
                # Satırı anında YÜKLÜ bölümünün en üstüne taşı — yeşil
                # "kuruldu" haliyle görünür kalır, EKSİK listesi küçülür.
                self._list_layout.removeWidget(row)
                idx = self._list_layout.indexOf(self._ok_header) + 1
                self._list_layout.insertWidget(idx, row)
                break
        total = len(self._components)
        self._ring.set_percent(int(round((self._ok_count / total) * 100)) if total else 100)
        self._refresh_headers()

    def _on_component_error(self, name: str, detail: str):
        logger.warning(f"[KURULUM] BAŞARISIZ: {name} — {detail}")
        self._failed.append(name)
        for row in self._rows:
            if row.component.get("name", "").strip() == name.strip():
                row.mark_failed()
                break

    def _on_restart_required(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle(T(self._lang, "restart_title"))
        dlg.setText(T(self._lang, "restart_msg"))
        dlg.setIcon(QMessageBox.Icon.Information)
        btn_now = dlg.addButton(T(self._lang, "restart_now"),
                                QMessageBox.ButtonRole.AcceptRole)
        dlg.addButton(T(self._lang, "restart_later"),
                      QMessageBox.ButtonRole.RejectRole)
        dlg.exec()
        if dlg.clickedButton() == btn_now:
            subprocess.run(["shutdown", "/r", "/t", "0"], check=False)

    def _on_finished(self, success: bool):
        n_ok, n_err = len(self._installed_names), len(self._failed)
        if success and not self._failed:
            logger.info(f"[KURULUM] Tamamlandı — {n_ok} bileşen kuruldu")
        elif self._failed:
            logger.warning(f"[KURULUM] Bitti (hatalı) — {n_ok} başarılı, "
                           f"{n_err} başarısız: {', '.join(self._failed)}")
        else:
            logger.info("[KURULUM] İptal edildi")
        QTimer.singleShot(0, self._cleanup_install_thread)
        self._set_busy(False)
        self._prog_wrap.setVisible(False)
        self._state = "ready"
        self._refresh_hero()
        self._refresh_headers()

        lang = self._lang
        if success and not self._failed:
            self._subline.setText(T(lang, "sub_summary",
                                    ok=self._ok_count, miss=self._miss_count))
            _beep("info")
        elif self._failed:
            self._subline.setText(
                T(lang, "status_error_summary", names=", ".join(self._failed)))
            _beep("error")
        else:
            self._subline.setText(T(lang, "status_cancelled"))

    def _cleanup_install_thread(self):
        if self._thread:
            self._thread.wait(3000)
        self._thread = None
        self._worker = None

    def _set_busy(self, busy: bool):
        self._search_box.setEnabled(not busy)
        self._lang_btn.setEnabled(not busy)
        self._miss_header.action.setEnabled(not busy)
        self._repair_btn.setEnabled(not busy)
        for row in self._rows:
            row.set_interactive(not busy)

    # ── yardımcılar ─────────────────────────────────────────────────────────
    def _open_log(self):
        LogViewerDialog(self._log_path, self._lang, self).exec()

    def _open_about(self):
        AboutDialog(self._version, self._lang, self).exec()

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            reply = QMessageBox.question(
                self, T(self._lang, "close_title"), T(self._lang, "close_msg"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                if self._worker:
                    self._worker.cancel()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
