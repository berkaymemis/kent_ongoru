# -*- coding: utf-8 -*-
"""İlçe hedef nüfusunun mahallelere dağıtımı.

Yöntemler
---------
``oransal``   Mevcut nüfus payı ile.
``bolge``     Her mahalleye bir planlama bölgesi atanır (ör. gelişme aksı,
              koruma, kırsal); artışın payı bölge bazında verilir, bölge içinde
              mevcut nüfusla orantılı dağıtılır. Öğrencinin "%75 gelişme /
              %20 kırsal / %5 koruma" modeli bu yöntemin bir ön ayarıdır; ama
              bölge ataması artık sabit mahalle adı listesinden değil, katmandaki
              bir alandan ya da tablodan gelir.
``kapasite``  Artış, mahallelerin boş plan kapasitesiyle (kapasite − mevcut)
              orantılı dağıtılır; kapasitesi dolan mahalle sınırda tutulur ve
              artan pay diğerlerine aktarılır. Hiçbir yere sığmayan nüfus
              "dağıtılamayan" olarak raporlanır.

Tüm yöntemler en büyük kalan yöntemiyle tam sayıya yuvarlar; mahalle toplamı
hedef nüfusa birebir eşittir (dağıtılamayan dışında).
"""


def _round_preserving(values, total):
    """Ondalık değerleri toplamı ``total`` olacak şekilde tam sayıya yuvarlar."""
    floors = [int(v // 1) for v in values]
    remainder = int(round(total)) - sum(floors)
    order = sorted(range(len(values)), key=lambda i: values[i] - floors[i], reverse=True)
    if remainder >= 0:
        for i in order[:remainder]:
            floors[i] += 1
    else:
        for i in list(reversed(order))[:(-remainder)]:
            floors[i] -= 1
    return floors


def _shares(weights, amount):
    total = float(sum(weights))
    if total <= 0:
        n = len(weights)
        return [amount / n] * n if n else []
    return [amount * w / total for w in weights]


def proportional(pops, target):
    return _shares(pops, target)


def by_zone(pops, zones, zone_shares, target):
    """``zones``: mahalle başına bölge adı; ``zone_shares``: {bölge: pay (0-1)}."""
    growth = target - sum(pops)
    result = [float(p) for p in pops]
    if growth < 0:
        # küçülmede bölge payları anlamsızlaşır; oransal küçült
        return _shares(pops, target)
    present = {z for z in zones}
    shares = {z: float(zone_shares.get(z, 0.0)) for z in present}
    total_share = sum(shares.values())
    if total_share <= 0:
        return _shares(pops, target)
    for zone in present:
        idx = [i for i, z in enumerate(zones) if z == zone]
        zone_growth = growth * shares[zone] / total_share
        weights = [pops[i] for i in idx]
        if sum(weights) <= 0:
            weights = [1.0] * len(idx)
        for i, add in zip(idx, _shares(weights, zone_growth)):
            result[i] += add
    return result


def by_capacity(pops, capacities, target, max_iter=100):
    """Kapasite sınırlı dağıtım. (değerler, dağıtılamayan) döndürür."""
    result = [float(p) for p in pops]
    growth = target - sum(pops)
    if growth <= 0:
        return _shares(pops, target), 0.0
    remaining = growth
    open_idx = [i for i in range(len(pops))
                if capacities[i] is not None and capacities[i] > result[i]]
    for _ in range(max_iter):
        if remaining <= 1e-6 or not open_idx:
            break
        room = [capacities[i] - result[i] for i in open_idx]
        adds = _shares(room, remaining)
        still_open = []
        used = 0.0
        for i, add, r in zip(open_idx, adds, room):
            take = min(add, r)
            result[i] += take
            used += take
            if capacities[i] - result[i] > 1e-6:
                still_open.append(i)
        remaining -= used
        open_idx = still_open
    return result, max(0.0, remaining)


def allocate(names, pops, target, method="oransal", zones=None, zone_shares=None,
             capacities=None):
    pops = [max(0.0, float(p or 0)) for p in pops]
    unallocated = 0.0
    if method == "bolge":
        values = by_zone(pops, zones or ["—"] * len(pops), zone_shares or {}, target)
    elif method == "kapasite":
        values, unallocated = by_capacity(pops, capacities or [None] * len(pops), target)
    else:
        values = proportional(pops, target)
    ints = _round_preserving(values, target - unallocated)
    rows = []
    for i, name in enumerate(names):
        base = pops[i]
        new = ints[i]
        rows.append({
            "mahalle": name,
            "bolge": (zones[i] if zones else ""),
            "kapasite": (capacities[i] if capacities else None),
            "mevcut": int(round(base)),
            "hedef": new,
            "net_artis": new - int(round(base)),
            "artis_yuzde": (100.0 * (new - base) / base) if base > 0 else None,
        })
    return rows, unallocated


# Öğrencinin "ŞBP akıllı model" bölge payları (ön ayar).
STUDENT_ZONE_SHARES = {
    "Kentsel gelişme aksı": 0.75,
    "Kırsal / çevre yerleşim": 0.20,
    "Tarihi merkez / koruma": 0.05,
}
