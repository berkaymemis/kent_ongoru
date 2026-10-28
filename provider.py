# -*- coding: utf-8 -*-
"""Processing sağlayıcısı: model oluşturucu ve toplu işlem için iki algoritma."""

import os

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms import CompositeIndexAlgorithm, PayPaydaIndexAlgorithm


class KentOngoruProvider(QgsProcessingProvider):
    def loadAlgorithms(self):  # noqa: N802 (QGIS API)
        self.addAlgorithm(PayPaydaIndexAlgorithm())
        self.addAlgorithm(CompositeIndexAlgorithm())

    def id(self):
        return "kent_ongoru"

    def name(self):
        return "Kent Öngörü"

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "icon.png"))

    def longName(self):  # noqa: N802 (QGIS API)
        return self.name()
