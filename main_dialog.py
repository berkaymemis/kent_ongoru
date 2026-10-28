# -*- coding: utf-8 -*-
"""Ana pencere: sol gezinme + iki modül + yöntem notları."""

import os

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                                 QStackedWidget, QTextBrowser, QVBoxLayout, QWidget)

from .population_page import PopulationPage
from .vulnerability_page import VulnerabilityPage
from .widgets import QSS

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ABOUT_HTML = """
<h2 style='color:#0f3d5e'>Kent Öngörü</h2>
<p>Şehir ve bölge planlama stüdyoları için iki modüllü bir QGIS eklentisi:
geleceğin <b>nüfusunu</b> ve kentin <b>kırılganlığını</b> aynı veri üzerinde öngörür.</p>
<h3>1 · Nüfus projeksiyonu</h3>
<ul>
<li><b>Kuşak-bileşen</b>: 17 beş yaşlık grup, cinsiyete göre Sx yaşama oranları, yaşa özel
doğurganlık (ASFR), isteğe bağlı hedef TFR geçişi, yaş profilli net göç (oran ya da kişi/yıl).</li>
<li><b>Trend yöntemleri</b>: aritmetik, geometrik, üstel, İller Bankası (%1–%3 sınırlı),
doğrusal regresyon (EKK), 2. derece polinom, lojistik (doyumlu). Her biri için R² ve son gözlemi
dışarıda bırakan <b>geriye dönük sınama hatası</b>.</li>
<li><b>İktisadi temel</b>: toplam istihdam artışı ya da temel sektör × baz çarpanı; bağımlılık oranı;
doğal çalışma çağı artışıyla karşılanan işleri düşme seçeneği.</li>
<li><b>Senaryolar</b>: düşük / orta / yüksek için kaynak seçimi, plan nüfusu.</li>
<li><b>Donatı</b>: düzenlenebilir kişi başı standart tablosu ile net ek alan (m², ha).</li>
<li><b>Mahalle dağıtımı</b>: oransal, planlama bölgesi payı, plan kapasitesiyle sınırlı;
toplam birebir korunur, sonuç yeni harita katmanı olarak eklenir.</li>
</ul>
<h3>2 · Kentsel kırılganlık</h3>
<p>Stüdyoda kullanılan pay / payda yöntemi: göstergeler 1–5 puanlanır; kırılganlığı artıran
<b>kötü yönlü</b> göstergeler (maruziyet, hassasiyet) paya, azaltan <b>iyi yönlü</b> göstergeler
(uyum kapasitesi) paydaya çarpılır.</p>
<p style='font-size:15px'><b>K = Π kötü / Π iyi</b></p>
<ul>
<li>Sel (K_Y), aşırı sıcak (K_S), deprem ve tahliye (K_D) ön ayarları ve tamamen kullanıcı tanımlı
<b>özel endeks</b>; her gösterge açılıp kapatılabilir, yönü, alanı ve eşikleri düzenlenebilir.</li>
<li>Ham değerler katmanlardan otomatik çıkarılır: yapı kaplaması (TAKS), KAKS, alan ağırlıklı kat,
kategori puanı ve payı, yol uzunluğu payları, en yakın uzaklık, raster bölgesel ortalaması,
bakının dairesel ortalaması.</li>
<li>Sınıflama: geometrik aralık, Jenks, eşit sayılı, eşit aralık. Bölge başına baskın kötü etkenler ve
zayıf uyum kapasitesi yazılır.</li>
<li><b>Duyarlılık</b>: her gösterge çıkarıldığında derecesi değişen bölge oranı ve Spearman ρ.</li>
<li><b>Bileşik endeks</b>: normalize K'ların ağırlıklı ortalaması (doğrusal ya da logaritmik),
tehlike sayısı ve çoklu tehlike teşhisi.</li>
<li>Kaynak katmanlar hiç değiştirilmez; sonuçlar ayrı katmana yazılır ve her tehlike için ayrı
adlandırılmış stil kaydedilir (Katman Stilleri panelinden geçiş).</li>
</ul>
<h3>Çıktılar</h3>
<p>Tek dosya HTML rapor (gömülü grafik ve harita), çok sayfalı Excel (.xlsx; ek kitaplık gerekmez),
300 DPI PNG grafikler, Processing araç kutusunda iki algoritma (pay/payda endeksi, bileşik endeks).</p>
<h3>Veri ve sorumluluk</h3>
<p class='note'>Ön ayar eşikleri, Sx/ASFR değerleri ve donatı standartları öğrencinin Tire stüdyo
çalışmasından aktarılmıştır. Başka bir yerleşimde kullanmadan önce yerel veriye ve yürürlükteki
mevzuata göre gözden geçirin. Eksik veri uydurulmaz: hesaplanamayan gösterge atlanır ya da nötr
puanla işlenip raporlanır.</p>
<p>Geliştirici: <b>Berkay Memiş</b> · DEÜ Şehir ve Bölge Planlama</p>
"""


class MainDialog(QDialog):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Kent Öngörü — Nüfus projeksiyonu ve kentsel kırılganlık")
        icon = os.path.join(PLUGIN_DIR, "icons", "icon.png")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        w, h = 1480, 900
        if avail is not None:
            w, h = min(w, int(avail.width() * 0.94)), min(h, int(avail.height() * 0.92))
        self.resize(w, h)
        self.setObjectName("koRoot")
        self.setStyleSheet(QSS)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setFixedWidth(220)
        side.setStyleSheet("background:#0f3d5e;")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 14, 0, 10)
        logo = QLabel()
        if os.path.exists(icon):
            logo.setPixmap(QPixmap(icon).scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(logo)
        title = QLabel("Kent Öngörü")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:white;font-size:17px;font-weight:700;padding:4px 0 0 0;")
        sl.addWidget(title)
        sub = QLabel("nüfus · kırılganlık")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color:#9fc3d6;font-size:11px;padding-bottom:12px;")
        sl.addWidget(sub)
        self.nav = QListWidget()
        self.nav.setObjectName("koNav")
        self.nav.setIconSize(QSize(18, 18))
        for text in ("Nüfus projeksiyonu", "Kentsel kırılganlık", "Yöntem ve hakkında"):
            QListWidgetItem(text, self.nav)
        sl.addWidget(self.nav, 1)
        foot = QLabel("Berkay Memiş")
        foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        foot.setStyleSheet("color:#7fa6bb;font-size:10px;")
        sl.addWidget(foot)
        lay.addWidget(side)

        self.stack = QStackedWidget()
        self.population = PopulationPage(iface)
        self.vulnerability = VulnerabilityPage(iface)
        about = QTextBrowser()
        about.setOpenExternalLinks(True)
        about.setHtml(ABOUT_HTML)
        about.setStyleSheet("QTextBrowser{background:white;border:none;padding:18px;font-size:13px;}")
        self.stack.addWidget(self.population)
        self.stack.addWidget(self.vulnerability)
        self.stack.addWidget(about)
        lay.addWidget(self.stack, 1)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

    def show_module(self, index):
        self.nav.setCurrentRow(index)
