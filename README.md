<p align="center"><img src="icons/icon_512.png" width="160" alt="Kent Öngörü"></p>

# Kent Öngörü

**Nüfus projeksiyonu ve kentsel kırılganlık için iki modüllü QGIS eklentisi.**
Şehir ve bölge planlama stüdyosunun iki temel sorusunu (*kaç kişi olacağız?* ve
*nerede, neye karşı kırılganız?*) aynı veri üzerinde, tek pencerede yanıtlar.

Geliştirici: **Berkay Memiş**, DEÜ Şehir ve Bölge Planlama · Lisans: GPL-2.0-or-later
QGIS 3.28 – 4.x · Ek Python kitaplığı gerekmez (pandas, matplotlib, openpyxl kullanılmaz)

---

## Modül 1: Nüfus projeksiyonu

| Sekme | Ne yapar |
|---|---|
| **1 · Veri** | Mahalle katmanından toplam nüfus, mahalle listesi ve (varsa) yaş-cinsiyet yapısını okur. 17 yaş grubu tablosu elle ya da Excel'den yapıştırılarak düzenlenebilir; geniş gruplardan (0-14 / 15-64 / 65+) 5'li gruplara dağıtılabilir. Geçmiş TÜİK ADNKS serisi panodan yapıştırılabilir. |
| **2 · Trend yöntemleri** | Aritmetik, geometrik, üstel, İller Bankası (%1–%3), doğrusal regresyon (EKK), 2. derece polinom ve lojistik (doyumlu). Her yöntem için R² ve **geriye dönük sınama hatası** (son gözlem dışarıda bırakılıp tahmin edilir). |
| **3 · Kuşak-bileşen** | Cinsiyete göre Sx yaşama oranları, ASFR, doğumda cinsiyet oranı, hedef yıla doğru TFR geçişi, yaş profilli net göç (yıllık oran ya da kişi/yıl). Yaş piramidi, bağımlılık oranı, yaşlanma endeksi, medyan yaş. |
| **4 · İstihdam ve göç** | İktisadi temel: toplam istihdam artışı ya da *temel sektör işi × baz çarpanı*; bağımlılık oranı; isteğe bağlı olarak doğal çalışma çağı artışının karşıladığı işler düşülür. |
| **5 · Senaryolar** | Düşük / orta / yüksek senaryo için kaynak seçimi; plan nüfusu. |
| **6 · Donatı ihtiyacı** | Düzenlenebilir kişi başı standart tablosuyla net ek alan (m², ha). |
| **7 · Mahalle dağıtımı** | Oransal, planlama bölgesi payı ya da plan kapasitesiyle sınırlı dağıtım; mahalle toplamı hedefe birebir eşittir; sonuç yeni, renklendirilmiş bir katman olarak eklenir. |
| **8 · Rapor** | Tek dosya HTML rapor (gömülü grafikler), çok sayfalı Excel, 300 DPI PNG grafikler. |

## Modül 2: Kentsel kırılganlık

Stüdyoda kullanılan **pay / payda yöntemi**: her gösterge 1–5 puanlanır.
Kırılganlığı **artıran** (kötü yönlü: *maruziyet*, *hassasiyet*) göstergeler paya,
**azaltan** (iyi yönlü: *uyum kapasitesi*) göstergeler paydaya çarpılır.

```
K = Π(kötü yönlü puanlar) / Π(iyi yönlü puanlar)
```

Sonuç 5 dereceye ayrılır (1. derece = çok yüksek kırılganlık).

* **Ön ayarlar:** Sel ve taşkın (K_Y), aşırı sıcak (K_S), deprem ve tahliye (K_D) ve
  boş bir **özel endeks** (K_O). Her gösterge açılıp kapatılabilir; bileşeni (yönü), kaynak
  alanı ve eşikleri tablodan düzenlenebilir; tanımlar JSON olarak kaydedilip yüklenebilir.
* **Ham değerler katmanlardan otomatik çıkarılır:** yapı kaplaması (TAKS), KAKS, alan
  ağırlıklı kat sayısı, kategori puanı ve payı (malzeme, düzen, arazi kullanımı), yol uzunluğu
  payları (asfalt, dar sokak, geniş tahliye yolu), en yakın uzaklık (dere, fay, toplanma alanı,
  itfaiye, hastane), raster bölgesel ortalaması (DEM, eğim, LST) ve bakının dairesel ortalaması.
* **Sınıflama:** geometrik aralık, doğal kırılmalar (Jenks), eşit sayılı, eşit aralık.
* **Teşhis:** her bölge için baskın kötü etkenler (puan ≥ 4) ve zayıf uyum kapasitesi (puan ≤ 2).
* **Duyarlılık:** her gösterge tek tek çıkarıldığında derecesi değişen bölge oranı ve Spearman ρ,
  yani haritayı hangi verinin belirlediği.
* **Bileşik endeks:** normalize K'ların ağırlıklı ortalaması (doğrusal ya da logaritmik),
  yüksek tehlike sayısı ve çoklu tehlike teşhisi.
* Kaynak katmanlar **hiç değiştirilmez**. Sonuçlar ayrı bir katmana yazılır; her tehlike için
  ayrı adlandırılmış stil kaydedilir (Katman Stilleri panelinden geçilebilir).

### Puanlama sözdizimi (tablodaki "Puanlama" sütunu)

| Yazım | Anlamı |
|---|---|
| `<=200:5; <=400:4; <=600:3; <=800:2; *:1` | eşik (ilk sağlanan aralığın puanı; `<` da kullanılabilir) |
| `asfalt,beton=5; parke,taş=3; toprak=1; *=3` | kategori (anahtar sözcük içeren değer) |
| `dilim` / `dilim ters` | veriye göre eşit sayılı 5 dilim |
| `esit` / `esit ters` | eşit aralık |
| `yuvarla` | ham değer zaten 1–5 ise |

### Veri hazırlığı

| Rol | Beklenen | Otomatik tanınan alan adları (örnek) |
|---|---|---|
| Analiz bölgeleri | poligon | `alt_bolge_no`, `mahalle_adi`, `nufus_2025`, `yas_0_14_toplam`, `yas_64_ustu_toplam` |
| Yapı / mevcut durum | poligon | `ortalama_kat`, `baskin_yapi_tipi`, `yapilasma_duzeni`, `arazi_kullanim_tanimi` |
| Yol ağı | çizgi | `genislik_m`, `kaplama_turu`, `kaldirim_durumu` |
| Dere, diri fay | çizgi | — |
| Toplanma, itfaiye, hastane | nokta ya da poligon | — |
| DEM, eğim (%), LST (°C), bakı (°) | raster | — |

Alan adları farklıysa tablodaki **Alan** sütunundan seçilir. "Katman adlarından otomatik eşle"
düğmesi proje katmanlarını adlarına göre rollere yerleştirir. Gerekli katmanı ya da alanı
olmayan gösterge çalıştırmada atlanır ve raporda belirtilir.

**Eksik veri ilkesi:** bir bölgede bir göstergenin ham değeri hesaplanamazsa puanı ölçeğin orta
değeri (3) alınır ve bölgenin `X_Eksik` alanına yazılır. Uydurma bir sayı konmaz.

### Sonuç alanları

`K_Y`, `K_S`, `K_D`, `K_O` (endeks) · `Y_Pay`, `Y_Payda` · `Y_Derece` (1–5) · `Y_Sinif` ·
`Y_Etken` (baskın kötü etkenler) · `Y_ZayifUyum` · `Y_Eksik` · `Y_R_<kod>` (ham değer) ·
`Y_P_<kod>` (puan). Bileşik: `K_BIL`, `BIL_Derece`, `BIL_Sinif`, `BIL_Teshis`,
`BIL_TehlikeSay`, `N_K_*`.

## Processing araçları

*Kent Öngörü → Kentsel kırılganlık* grubunda, model oluşturucu ve toplu işlem için:

* **Pay / payda kırılganlık endeksi:** puanları zaten alanlarda olan katmandan K ve derece.
* **Bileşik (çoklu tehlike) endeksi:** alanlar + ağırlıklar (`40,35,25`) ile K_BIL.

---

## Öğrenci sürümlerinden neler değişti?

Bu eklenti, altı ayrı aracı (`Tire_Nufus_Projeksiyon_Eklentisi`, `sel_`, `asiri_sicak_`,
`deprem_kirilganlik_analizi`, `bilesik_afet_direnclilik_analizi`, `kentsel_kirilganlik_paketi`)
tek bir eklentide iki modül olarak birleştirir. Hesap mantığı (pay/payda, eşikler, Sx/ASFR,
iktisadi temel, donatı standartları) korunmuş, şu hatalar düzeltilmiştir:

* `C:\Users\berka\...` sabit dosya yolları kaldırıldı; her ilçe/katmanla çalışır.
* Uydurma veri kaldırıldı: Tire mahallelerine elle yazılmış eğitim/gelir eşlemesi, eksik
  nüfusa "2500", eksik yaşlı oranına "%14" gibi değerler. Eksik veri artık görünürdür.
* Analizler `QThread` içinden katman düzenliyordu (QGIS'i çökertebilir) ve kaynak katmanı
  kalıcı olarak değiştiriyordu; artık ana iş parçacığında, ayrı sonuç katmanına yazılır.
* Yıllık net göç hızı 5 yıllık adımda tek kez uygulanıyordu; artık (1 + r)⁵ ile bileşiklenir.
* Baz çarpanı ekranda görünüp hesaba girmiyordu; "temel sektör × baz çarpanı" biçimi eklendi.
* İller Bankası artış hızı aritmetik formülle hesaplanıp bileşik uygulanıyordu; geometrik hıza
  çevrildi.
* Bileşik endekste en düşük bölgenin normalize değeri 0 olduğu için geometrik aralık onu hiçbir
  sınıfa koymuyordu; tüm bölgeler artık sınıflanır.
* Coğrafi CRS'te (EPSG:4326) alanlar derece² olarak hesaplanıyordu; artık metrik UTM dilimine
  dönüştürülür. Raster değeri yalnızca centroid'den değil, bölge içindeki tüm hücrelerden alınır.
* Deprem modülünde TAKS, yapı taban alanı yerine tapu alanından hesaplanıyordu; artık geometri
  kesişiminden hesaplanır.
* pandas / matplotlib / openpyxl bağımlılığı kaldırıldı (grafikler Qt ile çizilir, Excel
  standart kitaplıkla yazılır); eklenti her QGIS kurulumunda açılır.

## Testler

```
py -3 tests/test_core.py                                  # saf Python çekirdek testleri
C:\OSGeo4W\bin\python-qgis-ltr.bat tests\qgis_smoke.py    # QGIS 3.44 LTR, 47 kontrol
C:\OSGeo4W\bin\python-qgis.bat     tests\qgis_smoke.py    # QGIS 4.x
```

Testler elle hesaplanmış değerlerle karşılaştırır (örn. sentetik A bölgesi için
K_Y = 7500 / 12 = 625).

## Sorumluluk notu

Ön ayar eşikleri, Sx/ASFR değerleri ve donatı standartları Tire (İzmir) stüdyo çalışmasından
aktarılmıştır. Başka bir yerleşimde kullanmadan önce yerel veriye ve yürürlükteki mevzuata göre
gözden geçirin.

---

*English summary:* Kent Öngörü ("urban foresight") is a two-module QGIS plugin for planning
studios: cohort-component and trend population projection with economic-base migration,
scenarios, facility needs and neighbourhood allocation; and indicator-based flood, heat and
earthquake vulnerability using a bad-over-good index K = Π(bad) / Π(good), with automatic
indicator extraction from layers, sensitivity analysis and a composite multi-hazard index.
The interface is in Turkish.
