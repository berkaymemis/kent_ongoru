# -*- coding: utf-8 -*-
"""Kent Öngörü — QGIS eklenti girişi."""

import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon

try:
    from qgis.PyQt.QtWidgets import QAction
except ImportError:  # pragma: no cover - Qt6
    from qgis.PyQt.QtGui import QAction

MENU = "&Kent Öngörü"


class KentOngoruPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar_action = None
        self.dialog = None
        self.provider = None
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

    def initProcessing(self):  # noqa: N802 (QGIS API)
        if self.provider is not None:
            return
        from .processing_provider.provider import KentOngoruProvider
        self.provider = KentOngoruProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):  # noqa: N802 (QGIS API)
        self.initProcessing()
        icon = QIcon(os.path.join(self.plugin_dir, "icons", "icon.png"))
        main = QAction(icon, "Kent Öngörü", self.iface.mainWindow())
        main.setToolTip("Kent Öngörü — nüfus projeksiyonu ve kentsel kırılganlık")
        main.triggered.connect(lambda: self.open(0))
        self.iface.addToolBarIcon(main)
        self.toolbar_action = main
        self.iface.addPluginToMenu(MENU, main)
        self.actions.append(main)
        for idx, text in ((0, "Nüfus projeksiyonu"), (1, "Kentsel kırılganlık analizi")):
            act = QAction(text, self.iface.mainWindow())
            act.triggered.connect(lambda checked=False, i=idx: self.open(i))
            self.iface.addPluginToMenu(MENU, act)
            self.actions.append(act)

    def unload(self):
        for act in self.actions:
            self.iface.removePluginMenu(MENU, act)
        if self.toolbar_action is not None:
            self.iface.removeToolBarIcon(self.toolbar_action)
            self.toolbar_action = None
        self.actions = []
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None

    def open(self, module=0):
        if self.dialog is None:
            from .ui.main_dialog import MainDialog
            self.dialog = MainDialog(self.iface, self.iface.mainWindow())
        self.dialog.show_module(module)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
