# -*- coding: utf-8 -*-
"""Sel, aşırı sıcak ve deprem kırılganlık ön ayarları.

Eşikler öğrencinin stüdyo çalışmasındaki (DEÜ ŞBP PLN 3113, Tire) puanlama
kurallarından birebir aktarılmıştır. Hepsi arayüzde düzenlenebilir; başka bir
yerleşimde kullanılmadan önce yerel veriye göre gözden geçirilmelidir.

Ölçüm (measure) türleri — ``gis/extract.py`` bunları hesaplar:

  area_ha            bölge alanı (ha)
  field              bölge (ya da mahalle) katmanındaki sayısal alan
  field_text         bölge (ya da mahalle) katmanındaki metin alanı
  field_ratio        alan1 / alan2 × 100 (ör. 65+ nüfus / toplam nüfus)
  cover_ratio        yapı katmanının bölgeyi kaplama oranı (TAKS, 0-1)
  floor_area_ratio   Σ(taban alanı × kat) / bölge alanı (KAKS)
  open_ratio         100 − TAKS × 100 (açık / geçirimli yüzey yüzdesi)
  area_mean          yapı katmanında alan ağırlıklı sayısal ortalama
  area_category      yapı katmanında alan ağırlıklı kategori puanı ortalaması
  area_share         yapı katmanında anahtar sözcüğe uyan alanın yüzdesi
  length_mean        yol katmanında uzunluk ağırlıklı sayısal ortalama
  length_share       yol katmanında koşula uyan uzunluğun yüzdesi
  distance           bölgeden en yakın öğeye uzaklık (m; kesişiyorsa 0)
  raster_mean        rasterin bölge içindeki ortalaması
  raster_aspect      bakı rasterinin dairesel ortalaması (derece)
"""

from .vulnerability import Indicator

ROLES = [
    # (anahtar, etiket, tür, ad ipuçları)
    ("mahalle", "Mahalle (TÜİK, ops.)", "polygon",
     ["mahalle", "tuik", "nufus", "adnks"]),
    ("yapi", "Yapı / mevcut durum", "polygon",
     ["mevcut", "bina", "yapi", "building", "parsel"]),
    ("yol", "Yol ağı", "line", ["yol", "road", "sokak", "cadde", "street"]),
    ("dere", "Dere / akarsu", "line", ["dere", "akarsu", "stream", "river", "su"]),
    ("fay", "Diri fay", "line", ["fay", "fault"]),
    ("toplanma", "Toplanma alanları", "any", ["toplanma", "afet", "assembly"]),
    ("itfaiye", "İtfaiye", "any", ["itfaiye", "fire"]),
    ("hastane", "Hastane / sağlık", "any", ["hastane", "saglik", "sağlık", "hospital"]),
    ("dem", "DEM (yükseklik)", "raster", ["dem", "rakim", "yukseklik", "elev"]),
    ("egim", "Eğim (%) rasteri", "raster", ["egim", "eğim", "slope"]),
    ("lst", "LST (yüzey sıcaklığı)", "raster", ["lst", "sicaklik", "sıcaklık", "temp"]),
    ("baki", "Bakı (derece)", "raster", ["baki", "bakı", "aspect"]),
]
ROLE_LABELS = {r[0]: r[1] for r in ROLES}

POP_HINTS = ["nufus_2025", "nufus", "toplam_nufus", "nüfus", "population", "pop"]
CHILD_HINTS = ["yas_0_14_toplam", "cocuk", "çocuk", "0_14", "age_0_14"]
OLD_HINTS = ["yas_64_ustu_toplam", "yas_65_ustu_toplam", "yasli", "yaşlı", "65", "64_ustu"]
FLOOR_HINTS = ["ortalama_kat", "kat_sayisi", "katsayisi", "kat_adedi", "bina_kat_adedi",
               "katadedi", "kat", "floors", "building_levels", "levels"]
LAYOUT_HINTS = ["yapilasma_duzeni", "yapi_duzeni", "duzen", "nizam"]
MATERIAL_HINTS = ["baskin_yapi_tipi", "yapi_malzemesi", "malzeme", "tasiyici", "doku_ozelligi"]
LANDUSE_HINTS = ["arazi_kullanim_tanimi", "arazi_kull", "arazi_kullanimi", "fonksiyon",
                 "kullanim", "landuse"]
WIDTH_HINTS = ["genislik_m", "genislik", "y_genislik", "width"]
SURFACE_HINTS = ["kaplama_turu", "y_kaplama", "kaplama", "kaplama_tipi", "surface"]
SIDEWALK_HINTS = ["kaldirim_durumu", "y_kaldirim", "kaldirim", "kaldirim_tipi"]
EDU_HINTS = ["egitim", "eğitim", "universite", "lisans", "education"]
INCOME_HINTS = ["gelir", "ses", "income"]


def _r(ranges, else_score, strict=False):
    return {"method": "ranges", "ranges": [list(x) for x in ranges],
            "else": else_score, "strict": strict}


def _cat(mapping, else_score=3):
    return {"method": "categories", "map": [[list(k), s] for k, s in mapping],
            "else": else_score}


LANDUSE_MAP = [
    (("boş", "bos", "açık", "acik"), 1),
    (("yeşil", "yesil", "park", "rekreasyon"), 2),
    (("tarım", "tarim", "bahçe", "bahce"), 3),
    (("sanayi", "depolama", "imalat"), 4),
    (("ticaret", "konut", "mesken", "kamu"), 5),
]
LAYOUT_MAP = [
    (("ayrık", "ayrik", "bahçeli", "bahceli"), 5),
    (("blok", "ikiz"), 3),
    (("bitişik", "bitisik", "nizamsız", "nizamsiz"), 1),
]
SIDEWALK_MAP = [
    (("engelli", "çok iyi", "cok iyi"), 5),
    (("standart", "iyi"), 4),
    (("orta", "tek"), 3),
    (("dar", "yetersiz"), 2),
    (("yok",), 1),
]
ASPHALT = ["asfalt", "beton", "bsk", "sathi"]


def _pop(label_key="SN", component="maruziyet", ranges=None, strict=False):
    fallback = {"type": "residential_pop", "role": "yapi", "field": None,
                "hints": FLOOR_HINTS, "landuse_hints": LANDUSE_HINTS, "m2_per_person": 35.0}
    return Indicator(label_key, "Nüfus", component,
                     {"type": "field", "role": "bolge", "field": None, "hints": POP_HINTS,
                      "fallback": fallback},
                     _r(*ranges, strict=strict),
                     note="Nüfus alanı yoksa konut inşaat alanı / 35 m² ile kestirilir.")


def _elderly(ranges, strict=False):
    return Indicator("SY", "Yaşlı nüfus oranı (65+, %)", "hassasiyet",
                     {"type": "field_ratio", "role": "bolge", "field": None,
                      "field2": None, "hints": OLD_HINTS, "hints2": POP_HINTS},
                     _r(*ranges, strict=strict))


def _children(ranges, strict=False):
    return Indicator("SC", "Çocuk nüfus oranı (0-14, %)", "hassasiyet",
                     {"type": "field_ratio", "role": "bolge", "field": None,
                      "field2": None, "hints": CHILD_HINTS, "hints2": POP_HINTS},
                     _r(*ranges, strict=strict))


def _optional_field(key, label, hints):
    return Indicator(key, label, "uyum",
                     {"type": "field", "role": "bolge", "field": None, "hints": hints},
                     {"method": "quantile", "reverse": False}, enabled=False,
                     note="Kendi verinizle açın (ör. üniversite mezunu oranı, gelir).")


def flood_preset():
    """Sel ve taşkın kırılganlığı (K_Y)."""
    return [
        Indicator("FD", "Dereye uzaklık (m)", "maruziyet",
                  {"type": "distance", "role": "dere"},
                  _r(([200, 5], [400, 4], [600, 3], [800, 2]), 1)),
        Indicator("FR", "Rakım (m)", "maruziyet",
                  {"type": "raster_mean", "role": "dem"},
                  _r(([70, 1], [120, 3], [170, 4], [210, 5]), 2),
                  note="Tire stüdyo eşiği; havzaya göre düzenleyin."),
        Indicator("MB", "Alan büyüklüğü (ha)", "maruziyet", {"type": "area_ha"},
                  _r(([40, 1], [80, 2], [120, 3], [160, 4]), 5)),
        _pop("SN", "maruziyet", (([2118, 1], [4236, 2], [6354, 3], [8472, 4]), 5)),
        Indicator("MT", "TAKS (yapı yoğunluğu)", "hassasiyet",
                  {"type": "cover_ratio", "role": "yapi"},
                  _r(([0.2, 1], [0.4, 2], [0.6, 3], [0.8, 4]), 5)),
        Indicator("MA", "Arazi kullanımı", "hassasiyet",
                  {"type": "area_category", "role": "yapi", "field": None,
                   "hints": LANDUSE_HINTS, "map": [[list(k), s] for k, s in LANDUSE_MAP]},
                  {"method": "round"}),
        _elderly((([4, 1], [8, 2], [12, 3], [16, 4]), 5)),
        _children((([10, 1], [20, 2], [30, 3], [40, 4]), 5)),
        Indicator("YM", "Yol kaplaması (asfalt %)", "hassasiyet",
                  {"type": "length_share", "role": "yol", "field": None,
                   "hints": SURFACE_HINTS, "keywords": ASPHALT},
                  _r(([20, 1], [40, 2], [60, 3], [80, 4]), 5, strict=True)),
        Indicator("YK", "Ortalama kat sayısı", "uyum",
                  {"type": "area_mean", "role": "yapi", "field": None, "hints": FLOOR_HINTS},
                  _r(([0.5, 1], [2, 2], [4, 3], [6, 4]), 5),
                  note="Çok katlı yapı düşey tahliyeye olanak verir."),
        Indicator("YD", "Yapı düzeni", "uyum",
                  {"type": "area_category", "role": "yapi", "field": None,
                   "hints": LAYOUT_HINTS, "map": [[list(k), s] for k, s in LAYOUT_MAP]},
                  _r(([2, 1], [3.5, 3]), 5, strict=False)),
        Indicator("FE", "Eğim (%)", "uyum",
                  {"type": "raster_mean", "role": "egim"},
                  _r(([5, 1], [10, 3], [15, 4], [20, 5]), 2)),
        Indicator("MY", "Geçirimli yüzey (%)", "uyum", {"type": "open_ratio", "role": "yapi"},
                  _r(([20, 1], [40, 2], [60, 3], [80, 4]), 5)),
        Indicator("YG", "Yol genişliği (m)", "uyum",
                  {"type": "length_mean", "role": "yol", "field": None, "hints": WIDTH_HINTS},
                  _r(([6, 1], [10, 3]), 5, strict=False)),
        Indicator("KD", "Kaldırım durumu", "uyum",
                  {"type": "length_category", "role": "yol", "field": None,
                   "hints": SIDEWALK_HINTS, "map": [[list(k), s] for k, s in SIDEWALK_MAP]},
                  _r(([1.5, 1], [2.2, 2], [3.0, 3], [4.0, 4]), 5, strict=True),
                  enabled=False),
    ]


HEAT_MATERIAL_MAP = [
    (("gecekondu", "karma", "sac", "çinko", "cinko", "ahşap yığma"), 5),
    (("betonarme", "karkas"), 4),
    (("tuğla", "tugla", "briket"), 3),
    (("taş", "tas", "yığma", "yigma"), 2),
    (("boş", "bos", "park", "yeşil", "yesil"), 1),
]


def heat_preset():
    """Aşırı sıcak / kentsel ısı adası kırılganlığı (K_S)."""
    return [
        Indicator("LST", "Yüzey sıcaklığı (°C)", "maruziyet",
                  {"type": "raster_mean", "role": "lst"},
                  _r(([42, 1], [45, 2], [48, 3], [51, 4]), 5, strict=True)),
        Indicator("BK", "Bakı (güneşlenme)", "maruziyet",
                  {"type": "raster_aspect", "role": "baki"},
                  _r(([22.5, 1], [112.5, 2], [157.5, 4], [202.5, 5], [247.5, 4],
                      [337.5, 3]), 1, strict=True),
                  note="Kuzey 1 … Güney 5."),
        Indicator("FR", "Rakım (m)", "maruziyet",
                  {"type": "raster_mean", "role": "dem"},
                  _r(([50, 5], [80, 4], [120, 3], [160, 2]), 1, strict=True),
                  note="Çanak tabanı (düşük kot) sıcak havayı tutar."),
        Indicator("MT", "TAKS", "hassasiyet", {"type": "cover_ratio", "role": "yapi"},
                  _r(([0.2, 1], [0.4, 2], [0.6, 3], [0.8, 4]), 5, strict=True)),
        Indicator("KAKS", "KAKS (emsal)", "hassasiyet",
                  {"type": "floor_area_ratio", "role": "yapi", "field": None,
                   "hints": FLOOR_HINTS},
                  _r(([1.0, 1], [1.5, 2], [2.0, 3], [2.5, 4]), 5, strict=True)),
        Indicator("YK", "Ortalama kat sayısı", "hassasiyet",
                  {"type": "area_mean", "role": "yapi", "field": None, "hints": FLOOR_HINTS},
                  _r(([1.5, 5], [3, 4], [5, 3], [7, 2]), 1, strict=True),
                  note="Alçak, çatısı güneşe açık yapı daha çok ısınır."),
        Indicator("YMZ", "Yapı malzemesi", "hassasiyet",
                  {"type": "area_category", "role": "yapi", "field": None,
                   "hints": MATERIAL_HINTS, "map": [[list(k), s] for k, s in HEAT_MATERIAL_MAP]},
                  {"method": "round"}),
        _pop("SN", "hassasiyet", (([1000, 1], [2500, 2], [4500, 3], [7000, 4]), 5), strict=True),
        _elderly((([8, 1], [12, 2], [16, 3], [20, 4]), 5), strict=True),
        _children((([12, 1], [16, 2], [20, 3], [25, 4]), 5), strict=True),
        Indicator("YM", "Yol kaplaması (asfalt %)", "hassasiyet",
                  {"type": "length_share", "role": "yol", "field": None,
                   "hints": SURFACE_HINTS, "keywords": ASPHALT},
                  _r(([30, 1], [50, 2], [70, 3], [85, 4]), 5, strict=True)),
        Indicator("YG", "Yol genişliği (m)", "hassasiyet",
                  {"type": "length_mean", "role": "yol", "field": None, "hints": WIDTH_HINTS},
                  _r(([7, 5], [10, 4], [14, 3], [18, 2]), 1, strict=True),
                  note="Dar sokak hava akışını keser."),
        Indicator("FE", "Eğim (%)", "uyum", {"type": "raster_mean", "role": "egim"},
                  _r(([2, 1], [4, 2], [8, 3], [12, 4]), 5, strict=True),
                  note="Eğim katabatik esinti ve havalanma sağlar."),
        Indicator("MY", "Geçirimli yüzey (%)", "uyum", {"type": "open_ratio", "role": "yapi"},
                  _r(([10, 1], [20, 2], [35, 3], [50, 4]), 5, strict=True)),
        _optional_field("EG", "Eğitim düzeyi", EDU_HINTS),
        _optional_field("GL", "Gelir düzeyi", INCOME_HINTS),
    ]


EQ_MATERIAL_MAP = [
    (("gecekondu", "kerpiç", "kerpic", "ahşap yığma", "sac", "çinko", "cinko"), 5),
    (("taş", "tas", "yığma", "yigma", "karma"), 4),
    (("tuğla", "tugla", "briket", "karkas"), 3),
    (("betonarme",), 2),
    (("çelik", "celik", "prefabrik"), 1),
]


def earthquake_preset():
    """Deprem ve acil durum tahliyesi kırılganlığı (K_D)."""
    return [
        Indicator("FAY", "Diri faya uzaklık (m)", "maruziyet",
                  {"type": "distance", "role": "fay"},
                  _r(([500, 5], [1500, 4], [3000, 3], [5000, 2]), 1, strict=True)),
        Indicator("YMZ", "Yapı malzemesi / taşıyıcı sistem", "hassasiyet",
                  {"type": "area_category", "role": "yapi", "field": None,
                   "hints": MATERIAL_HINTS, "map": [[list(k), s] for k, s in EQ_MATERIAL_MAP]},
                  {"method": "round"}),
        Indicator("YK", "Ortalama kat sayısı", "hassasiyet",
                  {"type": "area_mean", "role": "yapi", "field": None, "hints": FLOOR_HINTS},
                  _r(([1.5, 1], [3, 2], [4.5, 3], [6, 4]), 5, strict=True)),
        Indicator("YD", "Bitişik / blok nizam payı (%)", "hassasiyet",
                  {"type": "area_share", "role": "yapi", "field": None, "hints": LAYOUT_HINTS,
                   "keywords": ["bitişik", "bitisik", "blok"]},
                  _r(([10, 1], [25, 2], [50, 3], [75, 4]), 5, strict=True),
                  note="Çekiçleme riski."),
        Indicator("MT", "TAKS", "hassasiyet", {"type": "cover_ratio", "role": "yapi"},
                  _r(([0.2, 1], [0.35, 2], [0.5, 3], [0.7, 4]), 5, strict=True)),
        Indicator("ENK", "Dar sokak payı (<7 m, %)", "hassasiyet",
                  {"type": "length_share", "role": "yol", "field": None, "hints": WIDTH_HINTS,
                   "lt": 7.0},
                  _r(([10, 1], [25, 2], [40, 3], [60, 4]), 5, strict=True),
                  note="Enkaz ile yol tıkanması."),
        _pop("SN", "maruziyet", (([1000, 1], [2500, 2], [4500, 3], [7000, 4]), 5), strict=True),
        _elderly((([8, 1], [12, 2], [16, 3], [20, 4]), 5), strict=True),
        _children((([12, 1], [16, 2], [20, 3], [25, 4]), 5), strict=True),
        Indicator("TOP", "Toplanma alanına uzaklık (m)", "uyum",
                  {"type": "distance", "role": "toplanma"},
                  _r(([0, 5], [300, 4], [600, 3], [1000, 2]), 1, strict=False),
                  note="Bölge içinde toplanma alanı varsa 5."),
        Indicator("ITF", "İtfaiyeye uzaklık (m)", "uyum",
                  {"type": "distance", "role": "itfaiye"},
                  _r(([1000, 5], [2000, 4], [3500, 3], [5000, 2]), 1, strict=True)),
        Indicator("HST", "Hastaneye uzaklık (m)", "uyum",
                  {"type": "distance", "role": "hastane"},
                  _r(([1200, 5], [2500, 4], [4000, 3], [6000, 2]), 1, strict=True)),
        Indicator("TYL", "Geniş tahliye yolu payı (≥12 m, %)", "uyum",
                  {"type": "length_share", "role": "yol", "field": None, "hints": WIDTH_HINTS,
                   "ge": 12.0},
                  _r(([5, 1], [10, 2], [20, 3], [35, 4]), 5, strict=True)),
        _optional_field("EG", "Eğitim düzeyi", EDU_HINTS),
        _optional_field("GL", "Gelir düzeyi", INCOME_HINTS),
    ]


HAZARDS = {
    "sel": {"ad": "Sel ve taşkın", "kod": "K_Y", "preset": flood_preset, "palet": "mavi"},
    "sicak": {"ad": "Aşırı sıcak", "kod": "K_S", "preset": heat_preset, "palet": "sicak"},
    "deprem": {"ad": "Deprem ve tahliye", "kod": "K_D", "preset": earthquake_preset,
               "palet": "deprem"},
    "ozel": {"ad": "Özel endeks", "kod": "K_O", "preset": lambda: [], "palet": "mor"},
}

# Öğrenci çalışmasındaki bileşik ağırlıklar
COMPOSITE_WEIGHTS = {"K_D": 0.40, "K_Y": 0.35, "K_S": 0.25}

PALETTES = {
    # 1. derece (çok yüksek) → 5. derece (çok düşük) sırasıyla
    "mavi": ["#08306b", "#2171b5", "#6baed6", "#bdd7e7", "#eaf2fb"],
    "sicak": ["#bd0026", "#f03b20", "#fd8d3c", "#fecc5c", "#ffffb2"],
    "deprem": ["#67000d", "#cb181d", "#fb6a4a", "#fcbba1", "#fff5f0"],
    "mor": ["#3f007d", "#6a51a3", "#9e9ac8", "#cbc9e2", "#f2f0f7"],
    "bilesik": ["#880e4f", "#ff5722", "#ffc107", "#8bc34a", "#2e7d32"],
}
