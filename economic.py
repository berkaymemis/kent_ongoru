# -*- coding: utf-8 -*-
"""İktisadi temel / istihdam çarpanı ile göç nüfusu.

İki hesap biçimi:

``toplam``  (öğrenci sürümü ile aynı)
    Yeni istihdam = hedef toplam istihdam − mevcut toplam istihdam

``temel``  (iktisadi temel kuramı)
    Yeni istihdam = temel (ihracat) sektöründeki yeni iş × baz çarpanı
    Öğrenci sürümünde baz çarpanı ekranda gösteriliyor ama hesaba hiç
    girmiyordu; bu biçim onu gerçekten kullanır.

Göç ile gelecek nüfus = göçle karşılanacak iş × bağımlılık oranı
(bir çalışanın hane içinde taşıdığı toplam kişi).

İsteğe bağlı düzeltme: yeni işlerin bir kısmı yerel çalışma çağı nüfusundaki
doğal artışla zaten karşılanır. Bu açıldığında
  yerel karşılanan = Δ(15-64 nüfus) × işgücüne katılım × (1 − işsizlik)
göçle karşılanacak işten düşülür; aksi halde göç iki kez sayılmış olur.
"""


def employment_migration(mode="toplam", current_employment=0.0, target_employment=0.0,
                         basic_new_jobs=0.0, base_multiplier=1.0, dependency_ratio=1.0,
                         natural_working_age_change=0.0, participation_rate=0.0,
                         unemployment_rate=0.0, subtract_local_supply=False):
    if mode == "temel":
        new_jobs = max(0.0, float(basic_new_jobs) * float(base_multiplier))
    else:
        new_jobs = max(0.0, float(target_employment) - float(current_employment))
    local_supply = 0.0
    if subtract_local_supply:
        local_supply = max(0.0, float(natural_working_age_change)
                           * float(participation_rate) * (1.0 - float(unemployment_rate)))
    jobs_for_migrants = max(0.0, new_jobs - local_supply)
    migrant_pop = jobs_for_migrants * float(dependency_ratio)
    return {
        "yontem": mode,
        "yeni_istihdam": new_jobs,
        "yerel_karsilanan": local_supply,
        "goc_ile_karsilanan_is": jobs_for_migrants,
        "baz_carpani": float(base_multiplier),
        "bagimlilik_orani": float(dependency_ratio),
        "goc_nufusu": migrant_pop,
    }
