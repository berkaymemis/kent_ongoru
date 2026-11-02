# Değişiklik günlüğü

Biçim: [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/), sürümleme: SemVer.

## [1.1.0] - 2026-11-02

### Eklendi
- **Modüller Arası Nüfus × Kırılganlık Müdahale Öncelik Matrisi (`core/priority.py`)**:
  Kırılganlık endeksi ile mahalle nüfusunu (ve artış baskısını) 0–100 ölçeğinde birleştiren
  müdahale öncelik skoru (`ONCELIK_SKOR` / `BIL_Oncelik`), 1–5 öncelik derecesi, risk altındaki
  eşdeğer nüfus (`RISK_NUFUS`) ve 5 kademeli mekansal planlama müdahale kararı (`PLAN_KARARI` /
  `BIL_Karar`) üretimi.
- **Kırılganlık Duyarlı Güvenli Nüfus Dağıtımı (`kirilganlik_duyarli`)**:
  1. ve 2. derece yüksek kırılganlık bölgelerine yeni nüfus yüklenmesini sınırlayıp büyümeyi
  güvenli gelişme alanlarına yönlendiren dördüncü mahalle dağıtım yöntemi (`core/allocation.py`
  ve `ui/population_page.py`).
- **Trend Doğruluk Metrikleri (`core/trends.py`)**:
  Tüm 7 trend modeline Ortalama Mutlak Yüzde Hata (`MAPE %`), Kök Ortalama Kare Hata (`RMSE`),
  bileşik yıllık büyüme hızı (`cagr`) ve nüfus ikiye katlanma süresi (`doubling_time`) hesapları.
- **Yeni Processing Algoritmaları (`processing_provider/algorithms.py`)**:
  Model Oluşturucu (Graphical Modeler) ve toplu işlem için iki yeni algoritma eklendi (toplam 4 algoritma):
  - `Nüfus × Kırılganlık müdahale öncelik matrisi` (`kent_ongoru:nufus_kirilganlik_oncelik`)
  - `Hedef nüfus mahalle dağıtımı ve donatı ihtiyacı` (`kent_ongoru:nufus_mahalle_dagitimi`)
- **Bileşik Katman Stili**: Bileşik analiz çıktısına `"Bileşik"` stilinin yanı sıra tek tıkla
  geçilebilen `"Müdahale Önceliği"` adlandırılmış katman stili eklendi.
- **Çift Çalışma Zamanı (QGIS 3.44 LTR Qt5 + QGIS 4.2 Qt6) E2E Test Paketi**:
  `tests/test_core.py` ve `tests/qgis_smoke.py` ile otomatik birim ve headless PyQGIS E2E testleri.

## [1.0.0] - 2026-10-28

### Eklendi
- İlk sürüm. Öğrenci araçları (`Tire_Nufus_Projeksiyon_Eklentisi`, sel, aşırı sıcak, deprem,
  bileşik afet ve kentsel kırılganlık paketi) tek eklentide iki modül olarak birleştirildi.
- Nüfus: 7 trend yöntemi ve geriye dönük sınama, hedef TFR geçişi, yaş profilli göç, temel sektör
  × baz çarpanı, yerel işgücü arzı düzeltmesi, senaryo seçimi, kapasite sınırlı mahalle dağıtımı,
  mahalle bazında donatı ihtiyacı, harita katmanı çıktısı.
- Kırılganlık: düzenlenebilir gösterge tablosu, özel endeks, otomatik gösterge çıkarma, Jenks /
  eşit sayılı / eşit aralık sınıflama, baskın etken teşhisi, duyarlılık analizi, logaritmik
  normalleştirme seçenekli bileşik endeks, adlandırılmış katman stilleri.
- HTML rapor (gömülü grafik ve harita), bağımlılıksız Excel çıktısı, 300 DPI PNG, iki Processing
  algoritması.

### Düzeltildi (öğrenci sürümlerine göre)
- Sabit dosya yolları, uydurma varsayılan veriler, QThread içinden katman düzenleme, kaynak
  katmanın kalıcı olarak değiştirilmesi, bileşiklenmeyen göç hızı, hesaba girmeyen baz çarpanı,
  İller Bankası hız formülü, bileşik endekste sınıfsız kalan en düşük bölge, coğrafi CRS'te alan
  hesabı, deprem TAKS'ının tapu alanından hesaplanması.
