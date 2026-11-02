# -*- coding: utf-8 -*-
"""Kişi başı donatı standardı ile alan ihtiyacı.

Varsayılan tablo, öğrenci çalışmasında "MPYY Ek-2, 100.001-250.000 nüfus
grubu" olarak girilen değerlerdir. Değerler eklenti içinde doğrulanmamıştır;
kullanıcı arayüzde düzenleyebilir ve kullanmadan önce yürürlükteki
yönetmelikle karşılaştırmalıdır.
"""

DEFAULT_STANDARDS = [
    # (kategori, tür, m²/kişi)
    ("Anaokulu", "Eğitim", 1.5),
    ("İlkokul", "Eğitim", 3.0),
    ("Ortaokul", "Eğitim", 3.0),
    ("Ortaöğretim (Lise)", "Eğitim", 3.5),
    ("Sağlık tesisleri", "Sağlık", 2.0),
    ("Sosyal ve kültürel tesisler", "Sosyo-kültürel", 2.0),
    ("İbadet alanı", "İbadet", 0.75),
    ("Çocuk bahçesi", "Açık ve yeşil alan", 2.0),
    ("Park", "Açık ve yeşil alan", 5.0),
    ("Meydan", "Açık ve yeşil alan", 1.0),
    ("Rekreasyon alanı", "Açık ve yeşil alan", 4.0),
    ("Teknik altyapı", "Teknik altyapı", 1.0),
]


def facility_needs(standards, base_pop, target_pop):
    rows = []
    for name, kind, per_cap in standards:
        per_cap = float(per_cap)
        base_m2 = base_pop * per_cap
        target_m2 = target_pop * per_cap
        rows.append({
            "kategori": name,
            "tur": kind,
            "kisi_basi": per_cap,
            "mevcut_ihtiyac_m2": base_m2,
            "hedef_ihtiyac_m2": target_m2,
            "net_m2": target_m2 - base_m2,
            "net_ha": (target_m2 - base_m2) / 10000.0,
        })
    return rows


def group_totals(rows):
    out = {}
    for r in rows:
        out[r["tur"]] = out.get(r["tur"], 0.0) + r["net_m2"]
    return out


def per_capita_total(standards):
    return sum(float(s[2]) for s in standards)
