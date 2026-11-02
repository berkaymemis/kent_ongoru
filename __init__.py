# -*- coding: utf-8 -*-


def classFactory(iface):  # noqa: N802 (QGIS API name)
    from .plugin import KentOngoruPlugin
    return KentOngoruPlugin(iface)
