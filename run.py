# -*- coding: utf-8 -*-
"""Kırılganlık analizini uçtan uca çalıştıran iş akışı (ana iş parçacığında)."""

from qgis.core import QgsProject

from ..core import presets
from ..core import vulnerability as vu
from .extract import Extractor
from .output import (RESULT_PROP, apply_class_style, create_copy_layer, ensure_fields,
                     find_result_layer, write_columns)

PREFIX = {"sel": "Y", "sicak": "S", "deprem": "D", "ozel": "O"}


class HazardRun:
    def __init__(self):
        self.hazard = None
        self.code = None
        self.layer = None
        self.indicators = []
        self.skipped = []           # [(etiket, neden)]
        self.raw = {}
        self.result = None
        self.sensitivity = []
        self.ids = []
        self.names = []
        self.populations = []


def get_or_create_results(region_layer, add_to_project=True):
    lyr = find_result_layer(region_layer)
    if lyr is None:
        lyr = create_copy_layer(region_layer, "Kent Öngörü – Kırılganlık (%s)" % region_layer.name())
        if add_to_project:
            QgsProject.instance().addMapLayer(lyr)
    return lyr


def run_hazard(region_layer, roles, indicators, hazard="sel", break_method="geometrik",
               id_field=None, name_field=None, progress=None, add_to_project=True,
               results_layer=None):
    """``progress(adim_metni, oran)`` True dönerse iptal edilir."""
    run = HazardRun()
    run.hazard = hazard
    run.code = presets.HAZARDS.get(hazard, presets.HAZARDS["ozel"])["kod"]
    pre = PREFIX.get(hazard, "O")

    ext = Extractor(region_layer, roles)
    n = len(ext.fids)
    if n == 0:
        raise ValueError("Bölge katmanında öğe yok.")
    effective = []
    for ind in indicators:
        ind = ind.copy()
        if ind.enabled:
            problem = ext.requirement_problem(ind.measure)
            if problem:
                run.skipped.append((ind.label, problem))
                ind.enabled = False
        effective.append(ind)
    active = [i for i in effective if i.enabled]
    if not active:
        raise ValueError("Hesaplanabilir gösterge kalmadı. Atlananlar: " +
                         "; ".join("%s (%s)" % s for s in run.skipped))

    for k, ind in enumerate(active):
        def cb(i, total, k=k, label=ind.label):
            if progress is None:
                return False
            return progress("%s (%d/%d)" % (label, i + 1, total),
                            (k + i / float(max(total, 1))) / len(active))
        run.raw[ind.key] = ext.values(ind.measure, cb)
        if progress and progress(ind.label, (k + 1) / float(len(active))):
            raise InterruptedError("İptal edildi")

    res = vu.compute_index(effective, run.raw)
    vu.classify_index(res, break_method)
    run.result = res
    run.indicators = effective
    run.sensitivity = vu.sensitivity(effective, res, break_method)

    run.ids = [str(a.get(id_field)) if id_field else str(fid)
               for a, fid in zip(ext.attrs, ext.fids)]
    run.names = [str(a.get(name_field)) if name_field and a.get(name_field) is not None else ""
                 for a in ext.attrs]
    pop_ind = next((i for i in active if i.key == "SN"), None)
    run.populations = run.raw.get(pop_ind.key) if pop_ind else [None] * n

    lyr = results_layer or get_or_create_results(region_layer, add_to_project)
    specs, cols = [], {}
    for ind in active:
        text = ind.measure.get("type") == "field_text"
        specs.append(("%s_R_%s" % (pre, ind.key), "string" if text else "double"))
        cols["%s_R_%s" % (pre, ind.key)] = [
            (None if v is None else (str(v) if text else round(float(v), 4)))
            for v in run.raw[ind.key]]
        specs.append(("%s_P_%s" % (pre, ind.key), "int"))
        cols["%s_P_%s" % (pre, ind.key)] = res.used[ind.key]
    extra = [
        (run.code, "double", [round(v, 4) for v in res.index]),
        ("%s_Pay" % pre, "double", res.numerator),
        ("%s_Payda" % pre, "double", res.denominator),
        ("%s_Derece" % pre, "int", res.classes),
        ("%s_Sinif" % pre, "string", [vu.CLASS_LABELS[c - 1] if c else None for c in res.classes]),
        ("%s_Etken" % pre, "string", res.drivers),
        ("%s_ZayifUyum" % pre, "string", res.weak),
        ("%s_Eksik" % pre, "string", [", ".join(m) for m in res.missing]),
    ]
    for name, kind, values in extra:
        specs.append((name, kind))
        cols[name] = values
    ensure_fields(lyr, specs)
    write_columns(lyr, cols)
    hz = presets.HAZARDS.get(hazard, presets.HAZARDS["ozel"])
    apply_class_style(lyr, run.code, res.breaks, presets.PALETTES[hz["palet"]],
                      style_name=hz["ad"])
    run.layer = lyr
    return run


class CompositeRun:
    def __init__(self):
        self.layer = None
        self.values = []
        self.norm = {}
        self.weights = {}
        self.breaks = []
        self.classes = []
        self.labels = []
        self.ids = []


def run_composite(layer, weights, log=False, break_method="geometrik", id_field=None,
                  labels=None, add_to_project=True):
    """``weights``: {alan adı: ağırlık}. Kaynak katman sonuç katmanı değilse kopyalanır."""
    if not layer.customProperty(RESULT_PROP):
        copy = create_copy_layer(layer, "Kent Öngörü – Bileşik (%s)" % layer.name())
        if add_to_project:
            QgsProject.instance().addMapLayer(copy)
        layer = copy
    series = {}
    feats = list(layer.getFeatures())
    for fld in weights:
        vals = []
        for f in feats:
            v = f[fld]
            try:
                vals.append(None if v is None or (hasattr(v, "isNull") and v.isNull()) else float(v))
            except (TypeError, ValueError):
                vals.append(None)
        series[fld] = vals
    comp, norm, w = vu.composite(series, weights, log)
    fn = vu.BREAK_METHODS.get(break_method, vu.BREAK_METHODS["geometrik"])[1]
    breaks = fn(comp, 5)
    classes = vu.classify(comp, breaks)
    labels = labels or {}
    names = list(w.keys())
    nice = [labels.get(k, k) for k in names]
    diag = []
    for r in range(len(feats)):
        row = {labels.get(k, k): norm[k][r] for k in names}
        diag.append(vu.multi_hazard_label(row, nice))
    hazard_count = [sum(1 for k in names if norm[k][r] is not None and norm[k][r] >= 50.0)
                    for r in range(len(feats))]
    specs = [("K_BIL", "double"), ("BIL_Derece", "int"), ("BIL_Sinif", "string"),
             ("BIL_Teshis", "string"), ("BIL_TehlikeSay", "int")]
    cols = {"K_BIL": [None if v is None else round(v, 2) for v in comp],
            "BIL_Derece": classes,
            "BIL_Sinif": [vu.CLASS_LABELS[c - 1] if c else None for c in classes],
            "BIL_Teshis": diag,
            "BIL_TehlikeSay": hazard_count}
    for k in names:
        specs.append(("N_%s" % k, "double"))
        cols["N_%s" % k] = [None if v is None else round(v, 2) for v in norm[k]]
    ensure_fields(layer, specs)
    write_columns(layer, cols)
    apply_class_style(layer, "K_BIL", breaks, presets.PALETTES["bilesik"],
                      style_name="Bileşik")
    run = CompositeRun()
    run.layer = layer
    run.values, run.norm, run.weights = comp, norm, w
    run.breaks, run.classes, run.labels = breaks, classes, diag
    run.ids = [str(f[id_field]) if id_field and id_field in f.fields().names() else str(f.id())
               for f in feats]
    return run
