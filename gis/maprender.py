# -*- coding: utf-8 -*-
"""Sonuç katmanını (seçili adlandırılmış stille) görüntüye çizer — rapor için."""

from qgis.core import QgsMapRendererCustomPainterJob, QgsMapSettings, QgsRectangle
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter


def render_layer(layer, style_name=None, width=1600, height=1100):
    if layer is None or not layer.isValid():
        return None
    mgr = layer.styleManager()
    previous = mgr.currentStyle()
    if style_name and style_name in mgr.styles():
        mgr.setCurrentStyle(style_name)
    try:
        ms = QgsMapSettings()
        ms.setLayers([layer])
        ms.setDestinationCrs(layer.crs())
        ext = QgsRectangle(layer.extent())
        ext.scale(1.06)
        ms.setOutputSize(QSize(width, height))
        ms.setExtent(ext)
        ms.setBackgroundColor(QColor("#ffffff"))
        img = QImage(QSize(width, height), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#ffffff"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        job = QgsMapRendererCustomPainterJob(ms, p)
        job.start()
        job.waitForFinished()
        p.end()
        return img
    finally:
        if style_name and previous in mgr.styles():
            mgr.setCurrentStyle(previous)
