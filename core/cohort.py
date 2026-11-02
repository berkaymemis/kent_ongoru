# -*- coding: utf-8 -*-
"""Kuşak-bileşen (cohort-component) nüfus projeksiyonu.

Saf Python; QGIS gerektirmez. 17 beş yaşlık grup (0-4 ... 80+), iki cinsiyet,
beşer yıllık adımlar.

Bir adım (t -> t+5):
  1. Yaşlanma: P[i+1](t+5) = P[i](t) * Sx[i];  açık grup 80+ kendi Sx'i ile kalır.
  2. Doğumlar: B = 5 * Σ ASFR[i] * (K[i](t) + K[i](t+5)) / 2   (15-49 yaş kadın)
     0-4 grubu = B * cinsiyet payı * Sx[0]  (doğumdan 0-4'e yaşama yaklaşımı).
  3. Göç: dönemlik net göçmen sayısı yaş profiline göre dağıtılır.

Öğrenci sürümündeki iki hata burada düzeltildi:
  * "Yıllık" net göç hızı 5 yıllık adımda tek bir kez uygulanıyordu; artık
    (1 + r)^5 ile bileşiklenir ve doğan çocuklara da (yaş profiline göre) yansır.
  * Göç yalnızca hayatta kalanlara çarpan olarak uygulanıyordu; artık mutlak
    göçmen sayısı olarak modellenir, böylece hem oran hem kişi/yıl girilebilir.
"""

import math

AGE_GROUPS = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39",
    "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+",
]
N_GROUPS = len(AGE_GROUPS)
FERTILE_GROUPS = ["15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49"]

# Öğrenci çalışmasındaki TÜİK hayat tablosu yaşama oranları (Sx); düzenlenebilir.
DEFAULT_SX_FEMALE = [
    0.9990876499, 0.9988642081, 0.9987452872, 0.9980233098, 0.99750964,
    0.9973624311, 0.9965801067, 0.9933525170, 0.9897364233, 0.9820347706,
    0.9696346681, 0.9481336409, 0.9079311651, 0.8358106550, 0.6729064922,
    0.3909319360, 0.7128154371,
]
DEFAULT_SX_MALE = [
    0.998506744, 0.997440219, 0.996469676, 0.996036476, 0.996015267,
    0.994961042, 0.992460875, 0.987267714, 0.977526232, 0.961258106,
    0.936199346, 0.898950262, 0.843522245, 0.732330858, 0.577969832,
    0.206646854, 0.569264213,
]
# Yaşa özel doğurganlık hızları (yıllık, kadın başına).  TFR = 5 * Σ = 1.545
DEFAULT_ASFR = {
    "15-19": 0.012, "20-24": 0.055, "25-29": 0.095, "30-34": 0.085,
    "35-39": 0.045, "40-44": 0.015, "45-49": 0.002,
}
# Net göçün yaş dağılımı: Rogers-Castro biçimli basit bir model profil
# (genç yetişkin tepe noktası + onlara eşlik eden çocuklar). Toplamı 1'e ölçeklenir.
DEFAULT_MIGRATION_PROFILE = [
    0.070, 0.050, 0.040, 0.070, 0.140, 0.150, 0.120, 0.090, 0.070,
    0.050, 0.040, 0.030, 0.025, 0.020, 0.015, 0.010, 0.010,
]
# Geniş gruplardan (0-14, 15-64, 65+) 5'li gruplara dağıtım ağırlıkları.
BROAD_WEIGHTS = {
    "0-14": [0.31, 0.34, 0.35],
    "15-64": [0.095, 0.098, 0.105, 0.110, 0.115, 0.118, 0.112, 0.098, 0.082, 0.067],
    "65+": [0.36, 0.28, 0.20, 0.16],
}


def tfr(asfr):
    """Toplam doğurganlık hızı = 5 * Σ ASFR."""
    return 5.0 * sum(float(v) for v in asfr.values())


def _normalised(weights):
    total = float(sum(weights))
    if total <= 0:
        return [1.0 / len(weights)] * len(weights)
    return [w / total for w in weights]


def baseline_from_broad_groups(m_0_14, m_15_64, m_65, f_0_14, f_15_64, f_65):
    """Geniş yaş gruplarından 17 gruplu erkek/kadın başlangıç vektörü üretir."""
    def spread(a, b, c):
        out = []
        for value, key in ((a, "0-14"), (b, "15-64"), (c, "65+")):
            w = _normalised(BROAD_WEIGHTS[key])
            out.extend(float(value) * x for x in w)
        return out
    return spread(m_0_14, m_15_64, m_65), spread(f_0_14, f_15_64, f_65)


class CohortParams:
    """Projeksiyon parametreleri (hepsi düzenlenebilir)."""

    def __init__(self):
        self.sx_male = list(DEFAULT_SX_MALE)
        self.sx_female = list(DEFAULT_SX_FEMALE)
        self.asfr = dict(DEFAULT_ASFR)
        self.sex_ratio_at_birth = 105.0      # 100 kız doğuma karşı erkek doğum
        self.tfr_target = None               # hedef yıla doğru doğrusal TFR geçişi
        self.migration_mode = "none"         # none | rate | absolute
        self.migration_rate = 0.0            # yıllık net göç hızı (oran, ör. 0.01)
        self.migration_annual = 0.0          # yıllık net göçmen (kişi)
        self.migration_profile = list(DEFAULT_MIGRATION_PROFILE)

    def validate(self):
        problems = []
        if len(self.sx_male) != N_GROUPS or len(self.sx_female) != N_GROUPS:
            problems.append("Sx tabloları 17 değer içermeli.")
        for s in self.sx_male + self.sx_female:
            if not 0.0 <= float(s) <= 1.0:
                problems.append("Sx değerleri 0 ile 1 arasında olmalı.")
                break
        for v in self.asfr.values():
            if float(v) < 0:
                problems.append("ASFR negatif olamaz.")
                break
        if self.sex_ratio_at_birth <= 0:
            problems.append("Doğumda cinsiyet oranı pozitif olmalı.")
        if len(self.migration_profile) != N_GROUPS:
            problems.append("Göç profili 17 değer içermeli.")
        return problems


def _asfr_scaled(params, step_index, n_steps):
    """TFR hedefi verilmişse ASFR'yi adım adım doğrusal ölçekler."""
    base_tfr = tfr(params.asfr)
    if params.tfr_target is None or base_tfr <= 0 or n_steps <= 0:
        return dict(params.asfr)
    # adımın orta noktasındaki TFR
    frac = (step_index + 0.5) / n_steps
    target = base_tfr + (float(params.tfr_target) - base_tfr) * frac
    k = target / base_tfr
    return {g: float(v) * k for g, v in params.asfr.items()}


def step(male, female, params, asfr=None):
    """Tek 5 yıllık adım. (erkek, kadın, doğum, göçmen) döndürür."""
    asfr = asfr if asfr is not None else params.asfr
    n = N_GROUPS
    nm = [0.0] * n
    nf = [0.0] * n
    for i in range(n - 1):
        nm[i + 1] = male[i] * params.sx_male[i]
        nf[i + 1] = female[i] * params.sx_female[i]
    nm[-1] += male[-1] * params.sx_male[-1]
    nf[-1] += female[-1] * params.sx_female[-1]

    births = 0.0
    for g in FERTILE_GROUPS:
        i = AGE_GROUPS.index(g)
        births += 5.0 * float(asfr.get(g, 0.0)) * (female[i] + nf[i]) / 2.0
    male_share = params.sex_ratio_at_birth / (100.0 + params.sex_ratio_at_birth)
    nm[0] = births * male_share * params.sx_male[0]
    nf[0] = births * (1.0 - male_share) * params.sx_female[0]

    migrants = 0.0
    if params.migration_mode == "rate" and params.migration_rate:
        start_total = sum(male) + sum(female)
        migrants = start_total * ((1.0 + float(params.migration_rate)) ** 5 - 1.0)
    elif params.migration_mode == "absolute" and params.migration_annual:
        migrants = float(params.migration_annual) * 5.0
    if migrants:
        prof = _normalised(params.migration_profile)
        for i in range(n):
            nm[i] += migrants * prof[i] * 0.5
            nf[i] += migrants * prof[i] * 0.5
    nm = [max(0.0, v) for v in nm]
    nf = [max(0.0, v) for v in nf]
    return nm, nf, births, migrants


class CohortResult:
    def __init__(self, years, male, female, births, migrants):
        self.years = years          # [2025, 2030, ...]
        self.male = male            # {yıl: [17]}
        self.female = female
        self.births = births        # {bitiş yılı: dönem doğumu}
        self.migrants = migrants    # {bitiş yılı: dönem net göçü}

    def total(self, year):
        return sum(self.male[year]) + sum(self.female[year])

    def totals(self):
        return [(y, self.total(y)) for y in self.years]

    def total_at(self, year):
        """5'in katı olmayan yıllar için iki adım arası geometrik enterpolasyon."""
        if year in self.male:
            return self.total(year)
        ys = self.years
        if year <= ys[0]:
            return self.total(ys[0])
        if year >= ys[-1]:
            return self.total(ys[-1])
        for a, b in zip(ys, ys[1:]):
            if a < year < b:
                pa, pb = self.total(a), self.total(b)
                if pa <= 0 or pb <= 0:
                    return pa + (pb - pa) * (year - a) / (b - a)
                return pa * (pb / pa) ** ((year - a) / (b - a))
        return self.total(ys[-1])

    def indicators(self, year):
        return demographic_indicators(self.male[year], self.female[year])


def project(male0, female0, base_year, target_year, params):
    """Başlangıç yılından hedef yıla (5'er yıl) projeksiyon."""
    problems = params.validate()
    if problems:
        raise ValueError(" ".join(problems))
    if len(male0) != N_GROUPS or len(female0) != N_GROUPS:
        raise ValueError("Başlangıç nüfusu 17 yaş grubu içermeli.")
    n_steps = max(0, int(math.ceil((target_year - base_year) / 5.0)))
    years = [base_year + 5 * k for k in range(n_steps + 1)]
    male = {base_year: [float(v) for v in male0]}
    female = {base_year: [float(v) for v in female0]}
    births, migrants = {}, {}
    m, f = male[base_year], female[base_year]
    for k in range(n_steps):
        asfr = _asfr_scaled(params, k, n_steps)
        m, f, b, mig = step(m, f, params, asfr)
        y = years[k + 1]
        male[y], female[y] = m, f
        births[y], migrants[y] = b, mig
    return CohortResult(years, male, female, births, migrants)


def demographic_indicators(male, female):
    """Bağımlılık oranları, yaşlanma endeksi, medyan yaş, cinsiyet oranı."""
    tot = [m + f for m, f in zip(male, female)]
    p = sum(tot)
    child = sum(tot[0:3])
    work = sum(tot[3:13])
    old = sum(tot[13:])
    out = {
        "toplam": p,
        "erkek": sum(male),
        "kadin": sum(female),
        "cocuk_0_14": child,
        "calisma_15_64": work,
        "yasli_65": old,
        "cocuk_orani": 100.0 * child / p if p else 0.0,
        "yasli_orani": 100.0 * old / p if p else 0.0,
        "toplam_bagimlilik": 100.0 * (child + old) / work if work else 0.0,
        "genc_bagimlilik": 100.0 * child / work if work else 0.0,
        "yasli_bagimlilik": 100.0 * old / work if work else 0.0,
        "yaslanma_endeksi": 100.0 * old / child if child else 0.0,
        "cinsiyet_orani": 100.0 * sum(male) / sum(female) if sum(female) else 0.0,
        "medyan_yas": median_age(tot),
    }
    return out


def median_age(tot):
    """Gruplanmış veriden medyan yaş (grup içi doğrusal enterpolasyon)."""
    p = sum(tot)
    if p <= 0:
        return 0.0
    half = p / 2.0
    cum = 0.0
    for i, v in enumerate(tot):
        if cum + v >= half and v > 0:
            lower = 5.0 * i
            return lower + 5.0 * (half - cum) / v
        cum += v
    return 80.0
