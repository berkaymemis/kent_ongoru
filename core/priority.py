# -*- coding: utf-8 -*-
"""Nüfus × Kırılganlık çapraz müdahale öncelik matrisi ve güvenli nüfus dağıtımı.

Modül 1 (Nüfus Projeksiyonu ve Mahalle Dağıtımı) ile Modül 2 (Kentsel Kırılganlık)
arasındaki analitik köprüyü kurar:

1. **Müdahale Öncelik Matrisi (`compute_priority_matrix`)**:
   Bileşik veya tekil kırılganlık endeksi ile mahalle nüfusunu (ve varsa nüfus artış
   baskısını) 0-100 aralığında normalize ederek birleştirir; 1-5 öncelik derecesi,
   risk altındaki eşdeğer nüfus (`RISK_NUFUS`) ve mekansal planlama kararı
   (`PLAN_KARARI`) üretir.
2. **Kırılganlık Duyarlı Güvenli Dağıtım Ağırlıkları (`vulnerability_weights`)**:
   1. ve 2. derece yüksek kırılganlık bölgelerine yeni nüfus yüklenmesini sınırlar;
   büyüme baskısını 4. ve 5. derece güvenli gelişme alanlarına yönlendirir.
"""

from . import vulnerability as vu

ACTION_LABELS = (
    "1. Öncelik: Acil Kentsel Dönüşüm ve Yoğunluk Kısıtlama",
    "2. Öncelik: Yapısal Güçlendirme ve Altyapı İyileştirme",
    "3. Öncelik: Kontrollü Gelişme ve Donatı Takviyesi",
    "4. Öncelik: Sürdürülebilir Gelişme / Rezerv Alanı",
    "5. Öncelik: Mevcut Dokuyu Koruma ve İzleme",
)

# Kırılganlık derecesine (1=Çok Yüksek ... 5=Çok Düşük) göre risk maruziyet katsayısı
RISK_EXPOSURE_FACTORS = {
    1: 1.00,
    2: 0.75,
    3: 0.50,
    4: 0.25,
    5: 0.10,
}

# Kırılganlık derecesine göre yeni nüfus tahsis ağırlığı (1. derecede büyüme kısıtlanır)
SAFE_GROWTH_FACTORS = {
    1: 0.05,
    2: 0.25,
    3: 0.65,
    4: 1.00,
    5: 1.35,
}


def _clean_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def vulnerability_weights(pops, vuln_classes):
    """Mevcut nüfus ile kırılganlık güvenlik çarpanını birleştirerek dağıtım ağırlığı üretir."""
    weights = []
    for idx, pop in enumerate(pops):
        p = max(1.0, _clean_float(pop, 1.0))
        deg = 3
        if vuln_classes and idx < len(vuln_classes) and vuln_classes[idx] is not None:
            try:
                deg = max(1, min(5, int(round(float(vuln_classes[idx])))))
            except (TypeError, ValueError):
                deg = 3
        factor = SAFE_GROWTH_FACTORS.get(deg, 0.65)
        weights.append(p * factor)
    return weights


def compute_priority_matrix(
    populations,
    vuln_indices,
    vuln_classes=None,
    growth_rates=None,
    pop_weight=0.40,
    vuln_weight=0.60,
    break_method="geometrik",
):
    """Nüfus ve kırılganlık endeksinden müdahale öncelik matrisi hesaplar.

    Döndürür:
        dict:
            ``scores``: 0-100 arası müdahale öncelik skoru (list[float])
            ``degrees``: 1-5 arası öncelik derecesi (1 = en acil) (list[int])
            ``breaks``: sınıf kırılma noktaları (list[float])
            ``risk_pops``: ağırlıklı risk altındaki nüfus (list[int])
            ``decisions``: planlama müdahale kararı metni (list[str])
    """
    n = len(vuln_indices)
    if n == 0:
        return {"scores": [], "degrees": [], "breaks": [], "risk_pops": [], "decisions": []}

    clean_vuln = [_clean_float(v, 0.0) for v in vuln_indices]
    norm_vuln = vu.normalise(clean_vuln, log=False)

    has_pop = bool(populations) and any(p is not None and _clean_float(p, 0.0) > 0 for p in populations)
    if has_pop:
        clean_pop = [max(0.0, _clean_float(populations[i] if i < len(populations) else 0.0)) for i in range(n)]
        norm_pop = vu.normalise(clean_pop, log=False)
    else:
        clean_pop = [0.0] * n
        norm_pop = [50.0] * n

    if growth_rates and any(g is not None for g in growth_rates):
        clean_growth = [_clean_float(growth_rates[i] if i < len(growth_rates) else 0.0) for i in range(n)]
        norm_growth = vu.normalise(clean_growth, log=False)
    else:
        norm_growth = None

    w_sum = max(1e-9, float(pop_weight) + float(vuln_weight))
    pw = float(pop_weight) / w_sum
    vw = float(vuln_weight) / w_sum

    scores = []
    for i in range(n):
        nv = norm_vuln[i] if norm_vuln[i] is not None else 0.0
        np_val = norm_pop[i] if norm_pop[i] is not None else 50.0
        base_score = (vw * nv + pw * np_val) if has_pop else nv
        if norm_growth and norm_growth[i] is not None:
            base_score = 0.85 * base_score + 0.15 * norm_growth[i]
        scores.append(round(max(0.0, min(100.0, base_score)), 2))

    fn = vu.BREAK_METHODS.get(break_method, vu.BREAK_METHODS["geometrik"])[1]
    breaks = fn(scores, 5)
    degrees = vu.classify(scores, breaks)

    if not vuln_classes or len(vuln_classes) != n:
        v_breaks = fn(clean_vuln, 5)
        vuln_classes = vu.classify(clean_vuln, v_breaks)

    risk_pops = []
    decisions = []
    for i in range(n):
        deg = degrees[i] if degrees[i] is not None else 3
        v_deg = vuln_classes[i] if vuln_classes[i] is not None else deg
        factor = RISK_EXPOSURE_FACTORS.get(v_deg, 0.50)
        risk_pops.append(int(round(clean_pop[i] * factor)))
        decisions.append(ACTION_LABELS[max(0, min(4, deg - 1))])

    return {
        "scores": scores,
        "degrees": degrees,
        "breaks": breaks,
        "risk_pops": risk_pops,
        "decisions": decisions,
    }
