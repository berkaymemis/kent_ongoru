# Değişiklik günlüğü

Biçim: [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/), sürümleme: SemVer.

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
