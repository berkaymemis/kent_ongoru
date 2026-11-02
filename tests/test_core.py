# -*- coding: utf-8 -*-
"""
Kent Öngörü — Pure Python Core Unit Tests.
Tests all 7 trend models, cohort-component 17-age-group demographic model,
economic base migration multiplier, MPYY facility area standards,
proportional/zone/capacity neighbourhood allocation, bad-over-good vulnerability index,
and zero-dependency HTML & OpenXML (.xlsx) exporters.
"""

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT.parent))

from kent_ongoru.core import (
    allocation,
    cohort,
    economic,
    facilities,
    presets,
    priority,
    report,
    trends,
    vulnerability,
    xlsx,
)


class TestKentOngoruCore(unittest.TestCase):
    def test_all_seven_trend_models_and_backtest(self):
        years = [y for y, _ in trends.EXAMPLE_SERIES_TIRE]
        pops = [p for _, p in trends.EXAMPLE_SERIES_TIRE]
        models, errors = trends.run_all(years, pops, saturation=150000)
        self.assertEqual(len(errors), 0, f"Unexpected trend model errors: {errors}")
        self.assertEqual(len(models), 7)
        for m in models:
            pred_2035 = m.predict(2035)
            self.assertGreater(pred_2035, 50000, f"Model {m.key} produced unrealistic prediction")
            self.assertIsNotNone(m.backtest_error, f"Model {m.key} missing leave-last-out backtest error")
            self.assertIsNotNone(m.mape, f"Model {m.key} missing MAPE")
            self.assertIsNotNone(m.rmse, f"Model {m.key} missing RMSE")
        rate = trends.cagr(years, pops)
        self.assertGreater(rate, 0.0)
        dt = trends.doubling_time(rate)
        self.assertIsNotNone(dt)
        self.assertGreater(dt, 10.0)

    def test_cohort_component_projection_and_demographics(self):
        m0, f0 = cohort.baseline_from_broad_groups(9500, 29000, 5500, 9000, 28500, 6500)
        self.assertEqual(len(m0), 17)
        self.assertEqual(len(f0), 17)
        params = cohort.CohortParams()
        params.migration_mode = "rate"
        params.migration_rate = 0.005
        res = cohort.project(m0, f0, base_year=2025, target_year=2040, params=params)
        self.assertEqual(res.years, [2025, 2030, 2035, 2040])
        self.assertAlmostEqual(res.total(2025), 88000.0, places=2)
        self.assertGreater(res.total(2040), 80000.0)
        # Check non-5-multiple geometric interpolation
        pop_2033 = res.total_at(2033)
        self.assertTrue(min(res.total(2030), res.total(2035)) <= pop_2033 <= max(res.total(2030), res.total(2035)))
        ind = res.indicators(2040)
        self.assertGreater(ind["medyan_yas"], 20.0)
        self.assertGreater(ind["toplam_bagimlilik"], 10.0)

    def test_economic_employment_migration(self):
        res = economic.employment_migration(
            mode="temel",
            basic_new_jobs=1200,
            base_multiplier=1.8,
            dependency_ratio=2.2,
            natural_working_age_change=1000,
            participation_rate=0.6,
            unemployment_rate=0.1,
            subtract_local_supply=True,
        )
        self.assertAlmostEqual(res["yeni_istihdam"], 2160.0)
        self.assertAlmostEqual(res["yerel_karsilanan"], 540.0)
        self.assertAlmostEqual(res["goc_ile_karsilanan_is"], 1620.0)
        self.assertAlmostEqual(res["goc_nufusu"], 1620.0 * 2.2)

    def test_facility_needs_and_allocation(self):
        rows = facilities.facility_needs(facilities.DEFAULT_STANDARDS, base_pop=88000, target_pop=110000)
        self.assertEqual(len(rows), len(facilities.DEFAULT_STANDARDS))
        totals = facilities.group_totals(rows)
        self.assertGreater(totals["Eğitim"], 0.0)

        names = ["Mahalle_A", "Mahalle_B", "Mahalle_C"]
        pops = [30000, 40000, 18000]
        zones = ["Kentsel gelişme aksı", "Kırsal / çevre yerleşim", "Tarihi merkez / koruma"]
        caps = [50000, 45000, 20000]

        for method in ("oransal", "bolge", "kapasite", "kirilganlik_duyarli"):
            alloc_rows, unalloc = allocation.allocate(
                names,
                pops,
                target=105000,
                method=method,
                zones=zones,
                zone_shares=allocation.STUDENT_ZONE_SHARES,
                capacities=caps if method == "kapasite" else None,
                vuln_classes=[1, 3, 5],
            )
            self.assertEqual(len(alloc_rows), 3)
            self.assertEqual(sum(r["hedef"] for r in alloc_rows), int(round(105000 - unalloc)))
            if method == "kirilganlik_duyarli":
                # 1st degree high vulnerability neighbourhood must receive less growth than 5th degree safe neighbourhood
                self.assertLess(alloc_rows[0]["net_artis"], alloc_rows[2]["net_artis"])

    def test_priority_matrix_engine(self):
        pops = [12000, 8500, 4200, 15000, 3100]
        vuln_idx = [88.5, 62.0, 35.0, 91.0, 14.0]
        vuln_deg = [1, 2, 3, 1, 5]
        mat = priority.compute_priority_matrix(
            populations=pops,
            vuln_indices=vuln_idx,
            vuln_classes=vuln_deg,
            growth_rates=[1.2, 0.8, 0.5, 2.1, 0.3],
        )
        self.assertEqual(len(mat["scores"]), 5)
        self.assertEqual(len(mat["degrees"]), 5)
        self.assertEqual(len(mat["risk_pops"]), 5)
        self.assertEqual(len(mat["decisions"]), 5)
        # Region 3 (idx=3) has both highest pop (15000) and highest vuln (91.0) -> must have highest priority score
        self.assertEqual(mat["scores"][3], max(mat["scores"]))
        self.assertEqual(mat["degrees"][3], 1)
        self.assertIn("1. Öncelik", mat["decisions"][3])

    def test_vulnerability_index_and_composite(self):
        indicators = presets.flood_preset()
        # Enable first 3 indicators for synthetic test
        for idx, ind in enumerate(indicators):
            ind.enabled = idx < 3
        raw = {
            indicators[0].key: [10.0, 250.0, 600.0, 1200.0, 50.0],
            indicators[1].key: [1.5, 4.0, 8.0, 14.0, 2.0],
            indicators[2].key: [0.15, 0.35, 0.55, 0.75, 0.25],
        }
        res = vulnerability.compute_index(indicators, raw)
        vulnerability.classify_index(res, "geometrik")
        self.assertEqual(len(res.index), 5)
        self.assertEqual(len(res.classes), 5)
        self.assertTrue(all(1 <= c <= 5 for c in res.classes))

        sens = vulnerability.sensitivity(indicators, res, "geometrik")
        self.assertEqual(len(sens), 3)

        # Composite index test
        comp_series = {
            "K_Y": [125.0, 45.0, 15.0, 5.0, 80.0],
            "K_S": [90.0, 60.0, 20.0, 10.0, 50.0],
            "K_D": [110.0, 30.0, 25.0, 8.0, 70.0],
        }
        comp_vals, norm, weights = vulnerability.composite(
            comp_series, {"K_Y": 0.35, "K_S": 0.25, "K_D": 0.40}, log=True
        )
        self.assertEqual(len(comp_vals), 5)
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_html_and_xlsx_exporters(self):
        html_doc = report.page(
            "Kent Öngörü Test Raporu",
            "Birim Test Alt Başlığı",
            [("Özet Kartlar", report.cards([("2040 Nüfusu", "112.450")]))],
            author="Berkay Memiş",
        )
        self.assertIn("<!doctype html>", html_doc)
        self.assertIn("112.450", html_doc)

        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = os.path.join(tmpdir, "kent_ongoru_test.xlsx")
            xlsx.write_xlsx(
                xlsx_path,
                [
                    ("Projeksiyon", [["Yıl", "Nüfus"], [2025, 87528], [2035, 102400]]),
                    ("Kırılganlık", [["Bölge", "K_Y", "Derece"], ["A1", 25.4, 2]]),
                ],
            )
            self.assertTrue(os.path.isfile(xlsx_path))
            with zipfile.ZipFile(xlsx_path, "r") as zf:
                self.assertIn("xl/workbook.xml", zf.namelist())
                self.assertIn("xl/worksheets/sheet1.xml", zf.namelist())
                self.assertIn("xl/worksheets/sheet2.xml", zf.namelist())


if __name__ == "__main__":
    unittest.main()
