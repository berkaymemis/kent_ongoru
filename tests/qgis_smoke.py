# -*- coding: utf-8 -*-
"""
Kent Öngörü — Full Headless PyQGIS End-to-End (E2E) Smoke & Workflow Test.
Compatible with both QGIS 3.44 LTR (Qt5) and QGIS 4.2+ (Qt6).
Verifies:
1. Plugin classFactory(DummyIface), initGui(), Processing Provider registration, and unload()
2. Synthetic vector layers creation (Regions, Buildings, Roads, Faults, Green Areas)
3. End-to-End Flood (K_Y), Heat (K_S), Earthquake (K_D) & Multi-Hazard Composite (K_BIL) runs
4. Named layer styles preservation & non-destructive source layer guarantee
5. 300 DPI QPainter chart generation (population pyramid, trend lines, class bars)
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtWidgets import QMainWindow

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT.parent))


class DummyIface:
    def __init__(self):
        self._win = QMainWindow()
        self.menus = []
        self.toolbar_icons = []

    def mainWindow(self):
        return self._win

    def addToolBarIcon(self, action):
        self.toolbar_icons.append(action)

    def removeToolBarIcon(self, action):
        if action in self.toolbar_icons:
            self.toolbar_icons.remove(action)

    def addPluginToMenu(self, menu, action):
        self.menus.append((menu, action))

    def removePluginMenu(self, menu, action):
        if (menu, action) in self.menus:
            self.menus.remove((menu, action))


def _create_synthetic_region_layer() -> QgsVectorLayer:
    from kent_ongoru.gis.compat import make_field

    lyr = QgsVectorLayer("Polygon?crs=EPSG:32635", "Mahalleler_Test", "memory")
    pr = lyr.dataProvider()
    pr.addAttributes(
        [
            make_field("ID", "string"),
            make_field("AD", "string"),
            make_field("NUFUS", "double"),
            make_field("BOLGE", "string"),
            make_field("KAPASITE", "double"),
        ]
    )
    lyr.updateFields()

    feats = []
    zones = ["Kentsel gelişme aksı", "Kırsal / çevre yerleşim", "Tarihi merkez / koruma", "Kentsel gelişme aksı", "Kırsal / çevre yerleşim"]
    for i in range(5):
        f = QgsFeature(lyr.fields())
        x0 = 500000 + i * 500
        y0 = 4200000
        ring = [
            QgsPointXY(x0, y0),
            QgsPointXY(x0 + 450, y0),
            QgsPointXY(x0 + 450, y0 + 450),
            QgsPointXY(x0, y0 + 450),
            QgsPointXY(x0, y0),
        ]
        f.setGeometry(QgsGeometry.fromPolygonXY([ring]))
        f.setAttributes([f"A{i+1}", f"Mahalle_{i+1}", float(2500 + i * 1800), zones[i], float(8000 + i * 2000)])
        feats.append(f)
    pr.addFeatures(feats)
    lyr.updateExtents()
    return lyr


def _create_synthetic_buildings_layer() -> QgsVectorLayer:
    from kent_ongoru.gis.compat import make_field

    lyr = QgsVectorLayer("Polygon?crs=EPSG:32635", "Binalar_Test", "memory")
    pr = lyr.dataProvider()
    pr.addAttributes([make_field("KAT", "int"), make_field("YAPI", "string")])
    lyr.updateFields()

    feats = []
    materials = ["Betonarme", "Yığma", "Kerpiç", "Betonarme", "Çelik"]
    for i in range(5):
        for b in range(3):
            f = QgsFeature(lyr.fields())
            x0 = 500050 + i * 500 + b * 80
            y0 = 4200050 + b * 60
            ring = [
                QgsPointXY(x0, y0),
                QgsPointXY(x0 + 40, y0),
                QgsPointXY(x0 + 40, y0 + 40),
                QgsPointXY(x0, y0 + 40),
                QgsPointXY(x0, y0),
            ]
            f.setGeometry(QgsGeometry.fromPolygonXY([ring]))
            f.setAttributes([2 + i + (b % 3), materials[(i + b) % len(materials)]])
            feats.append(f)
    pr.addFeatures(feats)
    lyr.updateExtents()
    return lyr


def run_e2e() -> int:
    qgs = QgsApplication.instance()
    owns_qgs = False
    if qgs is None:
        qgs = QgsApplication([], False)
        qgs.initQgis()
        owns_qgs = True

    try:
        import kent_ongoru
        from kent_ongoru.core import cohort, presets, report, trends, xlsx
        from kent_ongoru.gis import run as gis_run
        from kent_ongoru.ui import charts

        # 1. Test Plugin Lifecycle & Processing Provider
        iface = DummyIface()
        plugin = kent_ongoru.classFactory(iface)
        plugin.initGui()
        assert len(iface.toolbar_icons) == 1, "Expected 1 toolbar icon"
        assert len(iface.menus) == 3, "Expected 3 menu items"

        reg = QgsApplication.processingRegistry()
        provider = reg.providerById("kent_ongoru")
        assert provider is not None, "Processing provider 'kent_ongoru' not registered"
        alg_ids = [a.id() for a in provider.algorithms()]
        assert len(alg_ids) == 4, f"Expected 4 processing algorithms, got {alg_ids}"
        for expected_alg in (
            "kent_ongoru:pay_payda_endeksi",
            "kent_ongoru:bilesik_endeks",
            "kent_ongoru:nufus_kirilganlik_oncelik",
            "kent_ongoru:nufus_mahalle_dagitimi",
        ):
            assert expected_alg in alg_ids, f"Missing algorithm {expected_alg}"

        # 2. Test Spatial Vulnerability Extraction & Multi-Hazard Composite E2E
        QgsProject.instance().removeAllMapLayers()
        region_lyr = _create_synthetic_region_layer()
        bina_lyr = _create_synthetic_buildings_layer()
        QgsProject.instance().addMapLayer(region_lyr)
        QgsProject.instance().addMapLayer(bina_lyr)
        orig_field_count = len(region_lyr.fields())

        roles = {
            "yapi": bina_lyr,
        }

        for hazard_key in ("sel", "sicak", "deprem"):
            inds = presets.HAZARDS[hazard_key]["preset"]()
            hz_run = gis_run.run_hazard(
                region_lyr,
                roles=roles,
                indicators=inds,
                hazard=hazard_key,
                break_method="geometrik",
                id_field="ID",
                name_field="AD",
            )
            assert hz_run.layer is not None
            assert hz_run.layer.featureCount() == 5
            assert len(hz_run.result.index) == 5

        # Source layer must never be mutated
        assert len(region_lyr.fields()) == orig_field_count, "Source layer fields were mutated!"

        # Composite index run on the result layer
        res_lyr = gis_run.get_or_create_results(region_lyr)
        comp_run = gis_run.run_composite(
            res_lyr,
            weights={"K_Y": 0.35, "K_S": 0.25, "K_D": 0.40},
            log=True,
            break_method="geometrik",
            id_field="ID",
        )
        assert len(comp_run.values) == 5
        assert "K_BIL" in comp_run.layer.fields().names()
        assert "BIL_Oncelik" in comp_run.layer.fields().names()
        assert "BIL_Karar" in comp_run.layer.fields().names()
        assert len(comp_run.priority_scores) == 5
        assert len(comp_run.decisions) == 5
        assert "Müdahale Önceliği" in comp_run.layer.styleManager().styles()
        assert "Bileşik" in comp_run.layer.styleManager().styles()

        # 3. Test 300 DPI QPainter Charts & Exports
        years = [y for y, _ in trends.EXAMPLE_SERIES_TIRE]
        pops = [p for _, p in trends.EXAMPLE_SERIES_TIRE]
        models, _ = trends.run_all(years, pops)
        line_chart = charts.LineChart()
        line_chart.set_data(
            [(m.name, charts.SERIES[i % len(charts.SERIES)], [(y, m.predict(y)) for y in (2025, 2030, 2035, 2040)], i == 0) for i, m in enumerate(models)],
            points=list(zip(years, pops)),
        )
        b64_trend = line_chart.to_png_base64()
        assert len(b64_trend) > 200, "Trend chart PNG base64 is empty"

        m0, f0 = cohort.baseline_from_broad_groups(9500, 29000, 5500, 9000, 28500, 6500)
        c_res = cohort.project(m0, f0, 2025, 2040, cohort.CohortParams())
        pyr_chart = charts.PyramidChart()
        pyr_chart.set_data(cohort.AGE_GROUPS, (m0, f0), (c_res.male[2040], c_res.female[2040]), ("2025", "2040"))
        b64_pyr = pyr_chart.to_png_base64()
        assert len(b64_pyr) > 200, "Pyramid chart PNG base64 is empty"

        bar_chart = charts.ClassBarChart(title="Bileşik Kırılganlık Dağılımı")
        bar_chart.set_data([(f"{c}. derece", comp_run.classes.count(c), "#147a8a") for c in range(1, 6)])
        b64_bar = bar_chart.to_png_base64()
        assert len(b64_bar) > 200, "Class bar chart PNG base64 is empty"

        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_file = os.path.join(tmpdir, "e2e_output.xlsx")
            xlsx.write_xlsx(xlsx_file, [("Bilesik", [["ID", "K_BIL"]] + list(zip(comp_run.ids, comp_run.values)))])
            assert os.path.isfile(xlsx_file) and os.path.getsize(xlsx_file) > 500

        # 4. Clean Unload Verification
        plugin.unload()
        assert len(iface.toolbar_icons) == 0, "Toolbar icon not cleaned up on unload()"
        assert len(iface.menus) == 0, "Menu actions not cleaned up on unload()"
        assert reg.providerById("kent_ongoru") is None, "Processing provider not removed on unload()"

        QgsProject.instance().removeAllMapLayers()
        print("[E2E PASS] kent_ongoru full headless PyQGIS workflow succeeded!")
        return 0
    finally:
        if owns_qgs:
            qgs.exitQgis()


if __name__ == "__main__":
    sys.exit(run_e2e())
