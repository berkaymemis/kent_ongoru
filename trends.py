# -*- coding: utf-8 -*-
"""Eğilim (trend) temelli nüfus projeksiyon yöntemleri.

Her yöntem gözlenen (yıl, nüfus) serisinden bir model kurar ve
``predict(yil)`` ile kestirim yapar. İki noktalı klasik yöntemler serinin
ilk ve son gözlemini (ya da kullanıcının seçtiği dönemi) kullanır; regresyon
temelli yöntemler tüm noktaları kullanır.

Geriye dönük sınama (backtest): son gözlem dışarıda bırakılarak model yeniden
kurulur, o yılın nüfusu tahmin edilir ve yüzde hata raporlanır. Bu, jüride
"neden bu yöntem?" sorusuna sayısal bir yanıt verir.
"""

import math


class TrendModel:
    def __init__(self, key, name, predict, params_text, fitted=None, r2=None):
        self.key = key
        self.name = name
        self._predict = predict
        self.params_text = params_text
        self.fitted = fitted or []
        self.r2 = r2
        self.backtest_error = None   # yüzde (+ fazla tahmin, - eksik tahmin)

    def predict(self, year):
        return self._predict(float(year))


def _clean(years, pops):
    pairs = sorted((float(y), float(p)) for y, p in zip(years, pops)
                   if y is not None and p is not None and float(p) > 0)
    if len(pairs) < 2:
        raise ValueError("En az iki geçerli (yıl, nüfus) gözlemi gerekli.")
    return [a for a, _ in pairs], [b for _, b in pairs]


def _r2(obs, pred):
    mean = sum(obs) / len(obs)
    ss_tot = sum((o - mean) ** 2 for o in obs)
    ss_res = sum((o - p) ** 2 for o, p in zip(obs, pred))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else None


def arithmetic(years, pops):
    ys, ps = _clean(years, pops)
    y0, y1, p0, p1 = ys[0], ys[-1], ps[0], ps[-1]
    k = (p1 - p0) / (y1 - y0)
    return TrendModel("aritmetik", "Aritmetik artış",
                      lambda t: p1 + k * (t - y1),
                      "k = %.1f kişi/yıl" % k)


def geometric(years, pops):
    ys, ps = _clean(years, pops)
    y0, y1, p0, p1 = ys[0], ys[-1], ps[0], ps[-1]
    r = (p1 / p0) ** (1.0 / (y1 - y0)) - 1.0
    return TrendModel("geometrik", "Geometrik artış",
                      lambda t: p1 * (1.0 + r) ** (t - y1),
                      "r = %%%.3f / yıl" % (100 * r))


def exponential(years, pops):
    ys, ps = _clean(years, pops)
    y0, y1, p0, p1 = ys[0], ys[-1], ps[0], ps[-1]
    r = math.log(p1 / p0) / (y1 - y0)
    return TrendModel("ustel", "Üstel artış",
                      lambda t: p1 * math.exp(r * (t - y1)),
                      "r = %%%.3f / yıl (sürekli)" % (100 * r))


def iller_bankasi(years, pops, lower=1.0, upper=3.0):
    """İller Bankası: geometrik yıllık artış hızı %1-%3 aralığına sınırlanır."""
    ys, ps = _clean(years, pops)
    y0, y1, p0, p1 = ys[0], ys[-1], ps[0], ps[-1]
    a_raw = ((p1 / p0) ** (1.0 / (y1 - y0)) - 1.0) * 100.0
    a = max(lower, min(upper, a_raw))
    note = "a = %%%.2f" % a
    if abs(a - a_raw) > 1e-9:
        note += " (hesaplanan %%%.2f sınıra çekildi)" % a_raw
    return TrendModel("iller_bankasi", "İller Bankası",
                      lambda t: p1 * (1.0 + a / 100.0) ** (t - y1), note)


def linear_regression(years, pops):
    ys, ps = _clean(years, pops)
    n = len(ys)
    xm, ym = sum(ys) / n, sum(ps) / n
    sxx = sum((x - xm) ** 2 for x in ys)
    a = sum((x - xm) * (y - ym) for x, y in zip(ys, ps)) / sxx
    b = ym - a * xm
    fitted = [a * x + b for x in ys]
    return TrendModel("dogrusal_regresyon", "Doğrusal regresyon (EKK)",
                      lambda t: a * t + b,
                      "y = %.2f·x %+.1f" % (a, b), fitted, _r2(ps, fitted))


def _solve3(m, v):
    """3x3 doğrusal sistem (Cramer)."""
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    if abs(d) < 1e-12:
        raise ValueError("Tekil sistem")
    out = []
    for c in range(3):
        mc = [row[:] for row in m]
        for r in range(3):
            mc[r][c] = v[r]
        out.append(det(mc) / d)
    return out


def polynomial2(years, pops):
    ys, ps = _clean(years, pops)
    if len(ys) < 3:
        raise ValueError("2. derece eğri için en az 3 gözlem gerekli.")
    x0 = ys[-1]
    xs = [x - x0 for x in ys]       # sayısal kararlılık için merkezleme
    s = [sum(x ** k for x in xs) for k in range(5)]
    t = [sum(p * x ** k for x, p in zip(xs, ps)) for k in range(3)]
    c0, c1, c2 = _solve3([[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]], t)
    fitted = [c0 + c1 * x + c2 * x * x for x in xs]
    return TrendModel("polinom", "2. derece polinom",
                      lambda tt: c0 + c1 * (tt - x0) + c2 * (tt - x0) ** 2,
                      "y = %.1f %+.2f·t %+.3f·t² (t = yıl − %d)" % (c0, c1, c2, int(x0)),
                      fitted, _r2(ps, fitted))


def logistic(years, pops, saturation=None):
    """Lojistik (doyumlu) büyüme: P = K / (1 + e^(a − b·t)).

    ``saturation`` (K) verilmezse, gözlemlere en iyi uyan K ızgara aramasıyla
    seçilir (maks. gözlemin 1.02 ile 6 katı arası).
    """
    ys, ps = _clean(years, pops)
    if len(ys) < 3:
        raise ValueError("Lojistik eğri için en az 3 gözlem gerekli.")
    pmax = max(ps)
    x0 = ys[0]

    def fit(k):
        zs = [math.log(k / p - 1.0) for p in ps]
        xs = [x - x0 for x in ys]
        n = len(xs)
        xm, zm = sum(xs) / n, sum(zs) / n
        sxx = sum((x - xm) ** 2 for x in xs)
        slope = sum((x - xm) * (z - zm) for x, z in zip(xs, zs)) / sxx
        a = zm - slope * xm
        fitted = [k / (1.0 + math.exp(a + slope * x)) for x in xs]
        return a, slope, fitted

    if saturation and saturation > pmax:
        k_best = float(saturation)
        a, slope, fitted = fit(k_best)
    else:
        best = None
        k = pmax * 1.02
        while k <= pmax * 6.0:
            a, slope, fitted = fit(k)
            sse = sum((o - f) ** 2 for o, f in zip(ps, fitted))
            if best is None or sse < best[0]:
                best = (sse, k, a, slope, fitted)
            k *= 1.01
        _, k_best, a, slope, fitted = best

    def predict(t):
        return k_best / (1.0 + math.exp(a + slope * (t - x0)))
    return TrendModel("lojistik", "Lojistik (doyumlu)", predict,
                      "K = %s kişi" % format(int(round(k_best)), ","),
                      fitted, _r2(ps, fitted))


METHODS = [
    ("aritmetik", arithmetic),
    ("geometrik", geometric),
    ("ustel", exponential),
    ("iller_bankasi", iller_bankasi),
    ("dogrusal_regresyon", linear_regression),
    ("polinom", polynomial2),
    ("lojistik", logistic),
]


def run_all(years, pops, saturation=None):
    """Tüm yöntemleri kurar; geriye dönük sınama hatasını ekler.

    Kurulamayan yöntem (ör. 2 gözlemle polinom) sessizce atlanmaz:
    ``errors`` sözlüğünde nedeni ile döner.
    """
    ys, ps = _clean(years, pops)
    models, errors = [], {}
    for key, fn in METHODS:
        try:
            model = fn(ys, ps, saturation) if key == "lojistik" else fn(ys, ps)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            errors[key] = str(exc)
            continue
        if len(ys) >= 3:
            try:
                sub = fn(ys[:-1], ps[:-1], saturation) if key == "lojistik" else fn(ys[:-1], ps[:-1])
                pred = sub.predict(ys[-1])
                model.backtest_error = 100.0 * (pred - ps[-1]) / ps[-1]
            except (ValueError, ZeroDivisionError, OverflowError):
                model.backtest_error = None
        models.append(model)
    return models, errors


# Öğrencinin ders notundaki Tire ADNKS serisi (örnek veri; düzenlenebilir).
EXAMPLE_SERIES_TIRE = [
    (2007, 76327), (2010, 78372), (2015, 82102), (2017, 83829),
    (2020, 86315), (2023, 87803), (2025, 87528),
]
