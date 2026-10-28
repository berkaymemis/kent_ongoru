# -*- coding: utf-8 -*-
"""Processing algoritmaları.

* Pay / payda kırılganlık endeksi — puanları zaten alanlarda olan bir katmandan
  K = Π(pay alanları) / Π(payda alanları) ve 5 derece üretir (öğrencinin CSV/
  alan tabanlı "basit hesaplayıcı" yolunun Processing karşılığı; model
  oluşturucuda ve toplu işlemde kullanılabilir).
* Bileşik endeks — birden çok K alanını normalize edip ağırlıklandırır.
"""

import re

from qgis.core import (Qgis, QgsFeature, QgsFeatureSink, QgsFields, QgsProcessing,
                       QgsProcessingAlgorithm, QgsProcessingException,
                       QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
                       QgsProcessingParameterFeatureSink, QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField, QgsProcessingParameterString)

from ..core import presets
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
