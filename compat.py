# -*- coding: utf-8 -*-
"""QGIS 3.28 – 4.x uyumluluk yardımcıları."""

from qgis.core import Qgis, QgsField, QgsWkbTypes

try:  # QGIS >= 3.38: QgsField QMetaType kabul eder; QGIS 4'te zorunludur
    from qgis.PyQt.QtCore import QMetaType
    _USE_METATYPE = Qgis.QGIS_VERSION_INT >= 33800
except ImportError:  # pragma: no cover
    QMetaType = None
    _USE_METATYPE = False

if not _USE_METATYPE:
    from qgis.PyQt.QtCore import QVariant


def _type(kind):
    if _USE_METATYPE:
        return {"double": QMetaType.Type.Double, "int": QMetaType.Type.Int,
                "string": QMetaType.Type.QString}[kind]
    return {"double": QVariant.Double, "int": QVariant.Int, "string": QVariant.String}[kind]


def make_field(name, kind, length=0, precision=0):
    f = QgsField(name, _type(kind))
    if length:
        f.setLength(length)
    if precision:
        f.setPrecision(precision)
    return f


def geometry_kind(layer):
    """'polygon' | 'line' | 'point' | 'other'"""
    gt = layer.geometryType()
    try:
        poly, line, point = (Qgis.GeometryType.Polygon, Qgis.GeometryType.Line,
                             Qgis.GeometryType.Point)
    except AttributeError:  # QGIS < 3.30
        poly, line, point = (QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry,
                             QgsWkbTypes.PointGeometry)
    if gt == poly:
        return "polygon"
    if gt == line:
        return "line"
    if gt == point:
        return "point"
    return "other"


def layer_filter(kind):
    """QgsMapLayerComboBox süzgeci."""
    try:
        lf = Qgis.LayerFilter
        return {"polygon": lf.PolygonLayer, "line": lf.LineLayer, "point": lf.PointLayer,
                "raster": lf.RasterLayer, "vector": lf.VectorLayer,
                "any": lf.VectorLayer}[kind]
    except AttributeError:  # QGIS < 3.34
        from qgis.core import QgsMapLayerProxyModel as P
        return {"polygon": P.PolygonLayer, "line": P.LineLayer, "point": P.PointLayer,
                "raster": P.RasterLayer, "vector": P.VectorLayer,
                "any": P.VectorLayer}[kind]


def field_filter_numeric():
    try:
        from qgis.core import QgsFieldProxyModel
        return QgsFieldProxyModel.Filter.Numeric
    except AttributeError:
        from qgis.core import QgsFieldProxyModel
        return QgsFieldProxyModel.Numeric
