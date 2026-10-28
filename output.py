# -*- coding: utf-8 -*-
"""Sonuç katmanları ve tematik stil.

Öğrenci sürümü sonuçları doğrudan kullanıcının kaynak katmanına yazıyordu
(``startEditing`` + ``commitChanges``) ve bunu QThread içinden yapıyordu — bu
hem veriyi kalıcı olarak değiştirir hem de QGIS'i çökertebilir. Burada:

* kaynak katman hiç değiştirilmez;
* sonuçlar bellek katmanına (istenirse GeoPackage'a) yazılır;
* her tehlike için ayrı adlandırılmış stil kaydedilir; Katman Stilleri
  panelinden Sel / Sıcak / Deprem / Bileşik arasında geçilebilir.
"""

from qgis.core import (QgsFeature, QgsGraduatedSymbolRenderer, QgsMapLayerStyle, QgsProject,
                       QgsRendererRange, QgsSymbol, QgsVectorLayer, QgsWkbTypes)
from qgis.PyQt.QtGui import QColor

from ..core.vulnerability import CLASS_LABELS
from .compat import make_field

RESULT_PROP = "kent_ongoru/result_of"


def create_copy_layer(source, name):
    """Kaynağın geometri + özniteliklerini taşıyan bellek katmanı."""
    wkb = QgsWkbTypes.displayString(source.wkbType())
    uri = "%s?crs=%s" % (wkb, source.crs().authid() or "EPSG:4326")
    if not source.crs().authid():
        uri = wkb
    lyr = QgsVectorLayer(uri, name, "memory")
    if not source.crs().authid():
        lyr.setCrs(source.crs())
    pr = lyr.dataProvider()
    pr.addAttributes(source.fields().toList())
    lyr.updateFields()
    feats = []
    for f in source.getFeatures():
        nf = QgsFeature(lyr.fields())
        nf.setGeometry(f.geometry())
        nf.setAttributes(f.attributes())
        feats.append(nf)
    pr.addFeatures(feats)
    lyr.updateExtents()
    lyr.setCustomProperty(RESULT_PROP, source.id())
    return lyr


def find_result_layer(source):
    for lyr in QgsProject.instance().mapLayers().values():
        if lyr.customProperty(RESULT_PROP) == source.id() and isinstance(lyr, QgsVectorLayer):
            if lyr.featureCount() == source.featureCount():
                return lyr
    return None


def ensure_fields(layer, specs):
    """``specs``: [(ad, tür)] — eksik alanları ekler."""
    have = set(layer.fields().names())
    new = [make_field(n, k) for n, k in specs if n not in have]
    if new:
        layer.dataProvider().addAttributes(new)
        layer.updateFields()


def write_columns(layer, columns):
    """``columns``: {alan: [değer (öğe sırasıyla)]} — sağlayıcıya doğrudan yazar."""
    fids = [f.id() for f in layer.getFeatures()]
    idx = {name: layer.fields().indexFromName(name) for name in columns}
    changes = {}
    for r, fid in enumerate(fids):
        attrs = {}
        for name, values in columns.items():
            if idx[name] >= 0 and r < len(values):
                attrs[idx[name]] = values[r]
        changes[fid] = attrs
    layer.dataProvider().changeAttributeValues(changes)
    layer.triggerRepaint()


def apply_class_style(layer, field, breaks, palette, style_name=None, title=""):
    """5 sınıflı dereceli stil. palet: 1. derece (çok yüksek) → 5. derece."""
    if not breaks or len(breaks) < 2:
        return
    k = len(breaks) - 1
    ranges = []
    for i in range(k):
        derece = k - i                       # en alçak aralık = 5. derece
        color = palette[derece - 1] if derece - 1 < len(palette) else "#cccccc"
        sym = QgsSymbol.defaultSymbol(layer.geometryType())
        sym.setColor(QColor(color))
        sym.setOpacity(0.9)
        try:
            sym.symbolLayer(0).setStrokeColor(QColor(255, 255, 255, 180))
            sym.symbolLayer(0).setStrokeWidth(0.2)
        except AttributeError:
            pass
        label = "%s  (%s – %s)" % (CLASS_LABELS[derece - 1] if k == 5 else str(derece),
                                   _num(breaks[i]), _num(breaks[i + 1]))
        lo = breaks[i] if i else breaks[i] - abs(breaks[i]) * 1e-9 - 1e-9
        ranges.append(QgsRendererRange(lo, breaks[i + 1], sym, label))
    renderer = QgsGraduatedSymbolRenderer(field, ranges)
    try:
        renderer.setClassificationMethod(_manual_method())
    except (AttributeError, TypeError):
        pass
    layer.setRenderer(renderer)
    if style_name:
        mgr = layer.styleManager()
        style = QgsMapLayerStyle()
        style.readFromLayer(layer)
        if style_name in mgr.styles():
            mgr.removeStyle(style_name)
        mgr.addStyle(style_name, style)
        mgr.setCurrentStyle(style_name)
    layer.triggerRepaint()


def _manual_method():
    from qgis.core import QgsClassificationCustom
    return QgsClassificationCustom()


def _num(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 100:
        return "%.0f" % v
    if a >= 1:
        return "%.2f" % v
    return "%.3f" % v


def apply_graduated_field(layer, field, values, palette_hex, n=5, title=""):
    """Sayısal alan için eşit sayılı (quantile) basit stil (nüfus haritası)."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return
    breaks = [vals[0]]
    for i in range(1, n):
        breaks.append(vals[min(len(vals) - 1, int(len(vals) * i / n))])
    breaks.append(vals[-1])
    uniq = []
    for b in breaks:
        if not uniq or b > uniq[-1]:
            uniq.append(b)
    if len(uniq) < 2:
        uniq = [vals[0], vals[-1] + 1]
    ranges = []
    for i in range(len(uniq) - 1):
        sym = QgsSymbol.defaultSymbol(layer.geometryType())
        sym.setColor(QColor(palette_hex[min(i, len(palette_hex) - 1)]))
        lo = uniq[i] - (1e-9 if i == 0 else 0)
        ranges.append(QgsRendererRange(lo, uniq[i + 1], sym,
                                       "%s – %s" % (_num(uniq[i]), _num(uniq[i + 1]))))
    layer.setRenderer(QgsGraduatedSymbolRenderer(field, ranges))
    layer.triggerRepaint()
