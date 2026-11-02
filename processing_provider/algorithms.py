# -*- coding: utf-8 -*-
"""Processing algoritmaları.

* Pay / payda kırılganlık endeksi — puanları zaten alanlarda olan bir katmandan
  K = Π(pay alanları) / Π(payda alanları) ve 5 derece üretir (öğrencinin CSV/
  alan tabanlı "basit hesaplayıcı" yolunun Processing karşılığı; model
  oluşturucuda ve toplu işlemde kullanılabilir).
* Bileşik endeks — birden çok K alanını normalize edip ağırlıklandırır.
* Nüfus × Kırılganlık müdahale öncelik matrisi — nüfus ve kırılganlık endeksini
  çaprazlayarak 0-100 öncelik skoru, 1-5 öncelik derecesi, risk altındaki nüfus
  ve kentsel planlama müdahale kararı üretir.
* Hedef nüfus mahalle dağıtımı ve donatı ihtiyacı — hedef ilçe nüfusunu oransal,
  plan kapasitesi sınırlı veya kırılganlık duyarlı yöntemle mahallelere dağıtır
  ve kişi başı MPYY standardına göre net ek donatı alanı (m²) hesaplar.
"""

import re

from qgis.core import (Qgis, QgsFeature, QgsFeatureSink, QgsFields, QgsProcessing,
                       QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField, QgsProcessingParameterNumber,
                       QgsProcessingParameterString)

from ..core import allocation, facilities, presets
from ..core import priority as pr
from ..core import vulnerability as vu
from ..gis.compat import make_field

BREAK_KEYS = list(vu.BREAK_METHODS.keys())

try:
    NUMERIC = Qgis.ProcessingFieldParameterDataType.Numeric
except AttributeError:  # QGIS < 3.36
    NUMERIC = QgsProcessingParameterField.Numeric
try:
    FAST = QgsFeatureSink.Flag.FastInsert
except AttributeError:  # pragma: no cover
    FAST = QgsFeatureSink.FastInsert


def _float(v):
    if v is None:
        return None
    try:
        if hasattr(v, "isNull") and v.isNull():
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


class _Base(QgsProcessingAlgorithm):
    def group(self):
        return "Kentsel kırılganlık"

    def groupId(self):  # noqa: N802 (QGIS API)
        return "kirilganlik"

    def createInstance(self):  # noqa: N802 (QGIS API)
        return type(self)()

    def _fields(self, parameters, name, context):
        fn = getattr(self, "parameterAsStrings", None) or self.parameterAsFields  # QGIS >= 3.32
        return fn(parameters, name, context)

    def _style(self, context, dest_id, field, breaks, palette, name):
        if not dest_id or not breaks:
            return
        layer = context.getMapLayer(dest_id)
        if layer is None:
            return
        from ..gis.output import apply_class_style
        apply_class_style(layer, field, breaks, palette, style_name=name)

    def postProcessAlgorithm(self, context, feedback):  # noqa: N802 (QGIS API)
        self._style(context, getattr(self, "_dest", None), getattr(self, "_field", None),
                    getattr(self, "_breaks", None), getattr(self, "_palette", None),
                    getattr(self, "_style_name", None))
        return {}


class PayPaydaIndexAlgorithm(_Base):
    def name(self):
        return "pay_payda_endeksi"

    def displayName(self):  # noqa: N802 (QGIS API)
        return "Pay / payda kırılganlık endeksi"

    def shortHelpString(self):  # noqa: N802 (QGIS API)
        return ("Göstergeleri 1-5 puanlanmış alanlardan K = Π(kötü yönlü alanlar) / "
                "Π(iyi yönlü alanlar) hesaplar ve 5 dereceye sınıflar (1 = çok yüksek). "
                "Boş değerli alan nötr puan (3) ile işlenir.")

    def initAlgorithm(self, config=None):  # noqa: N802 (QGIS API)
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", "Bölge katmanı", [QgsProcessing.SourceType.TypeVectorPolygon]
            if hasattr(QgsProcessing, "SourceType") else [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            "PAY", "Pay: kötü yönlü puan alanları (maruziyet, hassasiyet)", None, "INPUT",
            NUMERIC, True, True))
        self.addParameter(QgsProcessingParameterField(
            "PAYDA", "Payda: iyi yönlü puan alanları (uyum kapasitesi)", None, "INPUT",
            NUMERIC, True, True))
        self.addParameter(QgsProcessingParameterString("ALAN", "Sonuç alanı", "K"))
        self.addParameter(QgsProcessingParameterEnum(
            "YONTEM", "Sınıflama", [vu.BREAK_METHODS[k][0] for k in BREAK_KEYS], False, 0))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Kırılganlık"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 (QGIS API)
        source = self.parameterAsSource(parameters, "INPUT", context)
        pay = self._fields(parameters, "PAY", context)
        payda = self._fields(parameters, "PAYDA", context)
        if not pay and not payda:
            raise QgsProcessingException("En az bir pay ya da payda alanı seçin.")
        out_field = (self.parameterAsString(parameters, "ALAN", context) or "K").strip()
        method = BREAK_KEYS[self.parameterAsEnum(parameters, "YONTEM", context)]
        feats = list(source.getFeatures())
        index, numer, denom = [], [], []
        for f in feats:
            n = d = 1.0
            for fld in pay:
                v = _float(f[fld])
                n *= v if v is not None and v > 0 else vu.NEUTRAL_SCORE
            for fld in payda:
                v = _float(f[fld])
                d *= v if v is not None and v > 0 else vu.NEUTRAL_SCORE
            numer.append(n)
            denom.append(d)
            index.append(n / d)
        breaks = vu.BREAK_METHODS[method][1](index, 5)
        classes = vu.classify(index, breaks)
        fields = QgsFields(source.fields())
        for name, kind in ((out_field, "double"), (out_field + "_Pay", "double"),
                           (out_field + "_Payda", "double"), (out_field + "_Derece", "int"),
                           (out_field + "_Sinif", "string")):
            if fields.indexFromName(name) < 0:
                fields.append(make_field(name, kind))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, source.wkbType(),
                                          source.sourceCrs())
        total = len(feats) or 1
        for i, f in enumerate(feats):
            if feedback.isCanceled():
                break
            nf = QgsFeature(fields)
            nf.setGeometry(f.geometry())
            attrs = dict(zip(source.fields().names(), f.attributes()))
            attrs.update({out_field: index[i], out_field + "_Pay": numer[i],
                          out_field + "_Payda": denom[i], out_field + "_Derece": classes[i],
                          out_field + "_Sinif": vu.CLASS_LABELS[classes[i] - 1] if classes[i] else None})
            nf.setAttributes([attrs.get(n) for n in fields.names()])
            sink.addFeature(nf, FAST)
            feedback.setProgress(100.0 * (i + 1) / total)
        self._dest, self._field, self._breaks = dest, out_field, breaks
        self._palette, self._style_name = presets.PALETTES["sicak"], out_field
        return {"OUTPUT": dest}


class CompositeIndexAlgorithm(_Base):
    def name(self):
        return "bilesik_endeks"

    def displayName(self):  # noqa: N802 (QGIS API)
        return "Bileşik (çoklu tehlike) endeksi"

    def shortHelpString(self):  # noqa: N802 (QGIS API)
        return ("Seçilen endeks alanlarını 0-100'e normalize edip ağırlıklı ortalamasını alır "
                "(K_BIL), 5 dereceye sınıflar ve 50'nin üzerindeki tehlike sayısını yazar. "
                "Ağırlıklar alan sırasıyla virgülle girilir (ör. 40,35,25); boş bırakılırsa eşit.")

    def initAlgorithm(self, config=None):  # noqa: N802 (QGIS API)
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", "Katman", [QgsProcessing.SourceType.TypeVectorPolygon]
            if hasattr(QgsProcessing, "SourceType") else [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            "ALANLAR", "Endeks alanları (ör. K_D, K_Y, K_S)", None, "INPUT", NUMERIC, True))
        self.addParameter(QgsProcessingParameterString("AGIRLIK", "Ağırlıklar", "", optional=True))
        self.addParameter(QgsProcessingParameterBoolean("LOG", "Logaritmik normalleştirme", False))
        self.addParameter(QgsProcessingParameterEnum(
            "YONTEM", "Sınıflama", [vu.BREAK_METHODS[k][0] for k in BREAK_KEYS], False, 0))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Bileşik endeks"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 (QGIS API)
        source = self.parameterAsSource(parameters, "INPUT", context)
        names = self._fields(parameters, "ALANLAR", context)
        if not names:
            raise QgsProcessingException("En az bir endeks alanı seçin.")
        raw = self.parameterAsString(parameters, "AGIRLIK", context) or ""
        try:
            ws = [float(x) for x in re.split(r"[,;\s]+", raw.strip()) if x]
        except ValueError:
            raise QgsProcessingException("Ağırlıklar sayı olmalı: %s" % raw)
        if not ws:
            ws = [1.0] * len(names)
        if len(ws) != len(names):
            raise QgsProcessingException("Ağırlık sayısı (%d) alan sayısına (%d) eşit olmalı." % (
                len(ws), len(names)))
        feats = list(source.getFeatures())
        series = {n: [_float(f[n]) for f in feats] for n in names}
        comp, norm, _ = vu.composite(series, dict(zip(names, ws)),
                                     self.parameterAsBool(parameters, "LOG", context))
        method = BREAK_KEYS[self.parameterAsEnum(parameters, "YONTEM", context)]
        breaks = vu.BREAK_METHODS[method][1](comp, 5)
        classes = vu.classify(comp, breaks)
        fields = QgsFields(source.fields())
        for name, kind in (("K_BIL", "double"), ("BIL_Derece", "int"), ("BIL_Sinif", "string"),
                           ("BIL_TehlikeSay", "int")):
            if fields.indexFromName(name) < 0:
                fields.append(make_field(name, kind))
        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, source.wkbType(),
                                          source.sourceCrs())
        for i, f in enumerate(feats):
            nf = QgsFeature(fields)
            nf.setGeometry(f.geometry())
            attrs = dict(zip(source.fields().names(), f.attributes()))
            attrs.update({"K_BIL": comp[i], "BIL_Derece": classes[i],
                          "BIL_Sinif": vu.CLASS_LABELS[classes[i] - 1] if classes[i] else None,
                          "BIL_TehlikeSay": sum(1 for n in names
                                                if norm[n][i] is not None and norm[n][i] >= 50.0)})
            nf.setAttributes([attrs.get(n) for n in fields.names()])
            sink.addFeature(nf, FAST)
        self._dest, self._field, self._breaks = dest, "K_BIL", breaks
        self._palette, self._style_name = presets.PALETTES["bilesik"], "Bileşik"
        return {"OUTPUT": dest}


class RiskPriorityMatrixAlgorithm(_Base):
    def name(self):
        return "nufus_kirilganlik_oncelik"

    def displayName(self):  # noqa: N802 (QGIS API)
        return "Nüfus × Kırılganlık müdahale öncelik matrisi"

    def shortHelpString(self):  # noqa: N802 (QGIS API)
        return ("Kırılganlık endeksi alanı (ör. K_BIL, K_D, K_Y, K_S) ile mahalle nüfusu alanını "
                "birleştirerek 0-100 aralığında müdahale öncelik skoru (ONCELIK_SKOR), 1-5 öncelik "
                "derecesi (ONCELIK_DERECE), risk altındaki eşdeğer nüfus (RISK_NUFUS) ve "
                "mekansal planlama müdahale kararı (PLAN_KARARI) üretir.")

    def initAlgorithm(self, config=None):  # noqa: N802 (QGIS API)
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", "Bölge / mahalle katmanı", [QgsProcessing.SourceType.TypeVectorPolygon]
            if hasattr(QgsProcessing, "SourceType") else [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            "ENDEKS", "Kırılganlık endeksi alanı (ör. K_BIL, K_D)", None, "INPUT", NUMERIC))
        self.addParameter(QgsProcessingParameterField(
            "NUFUS", "Nüfus alanı", None, "INPUT", NUMERIC, False, True))
        self.addParameter(QgsProcessingParameterField(
            "DERECE", "Kırılganlık derece alanı (1-5, isteğe bağlı)", None, "INPUT", NUMERIC, False, True))
        self.addParameter(QgsProcessingParameterEnum(
            "YONTEM", "Sınıflama", [vu.BREAK_METHODS[k][0] for k in BREAK_KEYS], False, 0))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Müdahale önceliği"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 (QGIS API)
        source = self.parameterAsSource(parameters, "INPUT", context)
        idx_field = self.parameterAsString(parameters, "ENDEKS", context)
        pop_field = self.parameterAsString(parameters, "NUFUS", context)
        deg_field = self.parameterAsString(parameters, "DERECE", context)
        if not idx_field:
            raise QgsProcessingException("Kırılganlık endeksi alanı seçilmeli.")
        method = BREAK_KEYS[self.parameterAsEnum(parameters, "YONTEM", context)]
        feats = list(source.getFeatures())
        vuln_vals = [_float(f[idx_field]) for f in feats]
        pop_vals = [_float(f[pop_field]) if pop_field else 0.0 for f in feats]
        deg_vals = [int(round(_float(f[deg_field]))) if deg_field and _float(f[deg_field]) else None
                    for f in feats] if deg_field else None

        mat = pr.compute_priority_matrix(
            populations=pop_vals,
            vuln_indices=vuln_vals,
            vuln_classes=deg_vals,
            break_method=method,
        )

        fields = QgsFields(source.fields())
        for name, kind in (("ONCELIK_SKOR", "double"), ("ONCELIK_DERECE", "int"),
                           ("RISK_NUFUS", "int"), ("PLAN_KARARI", "string")):
            if fields.indexFromName(name) < 0:
                fields.append(make_field(name, kind))

        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, source.wkbType(),
                                          source.sourceCrs())
        total = len(feats) or 1
        for i, f in enumerate(feats):
            if feedback.isCanceled():
                break
            nf = QgsFeature(fields)
            nf.setGeometry(f.geometry())
            attrs = dict(zip(source.fields().names(), f.attributes()))
            attrs.update({
                "ONCELIK_SKOR": mat["scores"][i],
                "ONCELIK_DERECE": mat["degrees"][i],
                "RISK_NUFUS": mat["risk_pops"][i],
                "PLAN_KARARI": mat["decisions"][i],
            })
            nf.setAttributes([attrs.get(n) for n in fields.names()])
            sink.addFeature(nf, FAST)
            feedback.setProgress(100.0 * (i + 1) / total)

        self._dest, self._field, self._breaks = dest, "ONCELIK_SKOR", mat["breaks"]
        self._palette, self._style_name = presets.PALETTES["bilesik"], "Müdahale Önceliği"
        return {"OUTPUT": dest}


class PopulationAllocationAlgorithm(_Base):
    ALLOC_METHODS = [
        ("oransal", "Mevcut nüfus payıyla (oransal)"),
        ("kapasite", "Plan kapasitesiyle sınırlı"),
        ("kirilganlik_duyarli", "Kırılganlık duyarlı güvenli dağıtım"),
    ]

    def group(self):
        return "Nüfus ve donatı"

    def groupId(self):  # noqa: N802 (QGIS API)
        return "nufus"

    def name(self):
        return "nufus_mahalle_dagitimi"

    def displayName(self):  # noqa: N802 (QGIS API)
        return "Hedef nüfus mahalle dağıtımı ve donatı ihtiyacı"

    def shortHelpString(self):  # noqa: N802 (QGIS API)
        return ("İlçe hedef yıl nüfusunu mahallelere oransal, plan kapasitesi sınırlı veya "
                "kırılganlık duyarlı güvenli büyüme yöntemiyle dağıtır; her mahalle için "
                "Hedef_Nufus, Net_Artis, Artis_Yuzde ve kişi başı MPYY standardına göre "
                "net ek sosyal/teknik donatı alanı (Donati_m2) hesaplar.")

    def initAlgorithm(self, config=None):  # noqa: N802 (QGIS API)
        self.addParameter(QgsProcessingParameterFeatureSource(
            "INPUT", "Mahalle katmanı", [QgsProcessing.SourceType.TypeVectorPolygon]
            if hasattr(QgsProcessing, "SourceType") else [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            "NUFUS", "Mevcut nüfus alanı", None, "INPUT", NUMERIC))
        try:
            num_type = Qgis.ProcessingNumberParameterType.Double
        except AttributeError:
            num_type = QgsProcessingParameterNumber.Double
        self.addParameter(QgsProcessingParameterNumber(
            "HEDEF", "Hedef toplam nüfus (kişi)", num_type, 100000.0, False, 1.0))
        self.addParameter(QgsProcessingParameterEnum(
            "YONTEM", "Dağıtım yöntemi", [m[1] for m in self.ALLOC_METHODS], False, 0))
        self.addParameter(QgsProcessingParameterField(
            "KAPASITE", "Plan kapasitesi alanı (kişi, isteğe bağlı)", None, "INPUT", NUMERIC, False, True))
        self.addParameter(QgsProcessingParameterField(
            "KIRILGANLIK", "Kırılganlık derece alanı (1-5, isteğe bağlı)", None, "INPUT", NUMERIC, False, True))
        self.addParameter(QgsProcessingParameterNumber(
            "DONATI_STD", "Kişi başı toplam donatı standardı (m²/kişi)", num_type,
            facilities.per_capita_total(facilities.DEFAULT_STANDARDS), False, 0.0))
        self.addParameter(QgsProcessingParameterFeatureSink("OUTPUT", "Nüfus dağıtımı"))

    def processAlgorithm(self, parameters, context, feedback):  # noqa: N802 (QGIS API)
        source = self.parameterAsSource(parameters, "INPUT", context)
        pop_field = self.parameterAsString(parameters, "NUFUS", context)
        target_pop = self.parameterAsDouble(parameters, "HEDEF", context)
        method_key = self.ALLOC_METHODS[self.parameterAsEnum(parameters, "YONTEM", context)][0]
        cap_field = self.parameterAsString(parameters, "KAPASITE", context)
        vuln_field = self.parameterAsString(parameters, "KIRILGANLIK", context)
        per_cap = self.parameterAsDouble(parameters, "DONATI_STD", context)

        feats = list(source.getFeatures())
        names = [str(f.id()) for f in feats]
        pops = [max(0.0, _float(f[pop_field]) or 0.0) for f in feats]
        caps = [_float(f[cap_field]) if cap_field else None for f in feats]
        vulns = [int(round(_float(f[vuln_field]))) if vuln_field and _float(f[vuln_field]) else 3
                 for f in feats]

        rows, unallocated = allocation.allocate(
            names=names,
            pops=pops,
            target=target_pop,
            method=method_key,
            capacities=caps,
            vuln_classes=vulns,
        )

        fields = QgsFields(source.fields())
        for name, kind in (("Hedef_Nufus", "int"), ("Net_Artis", "int"),
                           ("Artis_Yuzde", "double"), ("Donati_m2", "double")):
            if fields.indexFromName(name) < 0:
                fields.append(make_field(name, kind))

        sink, dest = self.parameterAsSink(parameters, "OUTPUT", context, fields, source.wkbType(),
                                          source.sourceCrs())
        total = len(feats) or 1
        for i, (f, row) in enumerate(zip(feats, rows)):
            if feedback.isCanceled():
                break
            nf = QgsFeature(fields)
            nf.setGeometry(f.geometry())
            attrs = dict(zip(source.fields().names(), f.attributes()))
            donati_m2 = round(max(0, row["net_artis"]) * per_cap, 2)
            attrs.update({
                "Hedef_Nufus": row["hedef"],
                "Net_Artis": row["net_artis"],
                "Artis_Yuzde": None if row["artis_yuzde"] is None else round(row["artis_yuzde"], 2),
                "Donati_m2": donati_m2,
            })
            nf.setAttributes([attrs.get(n) for n in fields.names()])
            sink.addFeature(nf, FAST)
            feedback.setProgress(100.0 * (i + 1) / total)

        return {"OUTPUT": dest, "UNALLOCATED": unallocated}
