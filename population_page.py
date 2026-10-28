# -*- coding: utf-8 -*-
"""Modül 1 — Nüfus projeksiyonu."""

import os

from qgis.core import QgsProject
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
                                 QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                                 QMessageBox, QRadioButton, QScrollArea, QSplitter, QTabWidget,
                                 QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from ..core import allocation, cohort, economic, facilities, report, trends, xlsx
from ..gis.compat import field_filter_numeric, layer_filter, make_field
from ..gis.output import apply_graduated_field, create_copy_layer
from .charts import SERIES, BarChart, LineChart, PyramidChart
from .widgets import (Card, button, card_row, dspin, fill_table, fmt_int, fmt_num, heading, hint,
                      make_table, num_item, primary_button, spin, table_rows, text_item)

BASE_FIELD_HINTS = {
    "m_0_14": ["yas_0_14_erkek", "erkek_0_14"], "m_15_64": ["yas_15_64_erkek", "erkek_15_64"],
    "m_65": ["yas_64_ustu_erkek", "yas_65_ustu_erkek", "erkek_65"],
    "f_0_14": ["yas_0_14_kadin", "kadin_0_14"], "f_15_64": ["yas_15_64_kadin", "kadin_15_64"],
    "f_65": ["yas_64_ustu_kadin", "yas_65_ustu_kadin", "kadin_65"],
}
NAME_HINTS = ["mahalle_adi", "mahalle", "ad", "adi", "name", "mah_adi"]
POP_HINTS = ["nufus_2025", "nufus", "toplam_nufus", "population", "pop"]
SCEN_COLORS = ["#64748b", "#3f6fb5", "#147a8a"]


def _find(layer, hints):
    if layer is None:
        return ""
    names = [f.name() for f in layer.fields()]
    low = {n.lower(): n for n in names}
    for h in hints:
        if h in low:
            return low[h]
    for h in hints:
        for k, v in low.items():
            if h in k:
                return v
    return ""


class PopulationPage(QWidget):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.cohort_result = None
        self.cohort_natural = None
        self.trend_models = []
        self.trend_errors = {}
        self.econ = None
        self.scenarios = []
        self.plan_pop = None
        self.plan_label = ""
        self.facility_rows = []
        self.alloc_rows = []
        self.alloc_unallocated = 0.0
        self.neighbourhoods = []      # [(ad, nüfus, bölge, kapasite)]
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self.recompute_all)
        self._building = True
        self._build()
        self._building = False
        self.load_defaults()

    # ------------------------------------------------------------------ UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        top.addWidget(heading("Nüfus projeksiyonu"))
        top.addStretch()
        top.addWidget(QLabel("Başlangıç yılı"))
        self.base_year = spin(1990, 2100, 2025, group=False)
        top.addWidget(self.base_year)
        top.addWidget(QLabel("Hedef yıl"))
        self.target_year = spin(2000, 2150, 2040, 5, group=False)
        top.addWidget(self.target_year)
        top.addWidget(primary_button("Hesapla", self.recompute_all))
        root.addLayout(top)

        self.cards = [Card("Başlangıç nüfusu"), Card("Doğal nüfus (kuşak-bileşen)", accent="#3f6fb5"),
                      Card("İstihdam göçü", accent="#e07a1f"), Card("Plan nüfusu", accent="#b23a48")]
        root.addLayout(card_row(self.cards))

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._scroll(self._tab_data()), "1 · Veri")
        self.tabs.addTab(self._tab_trends(), "2 · Trend yöntemleri")
        self.tabs.addTab(self._tab_cohort(), "3 · Kuşak-bileşen")
        self.tabs.addTab(self._scroll(self._tab_econ()), "4 · İstihdam ve göç")
        self.tabs.addTab(self._tab_scenarios(), "5 · Senaryolar")
        self.tabs.addTab(self._tab_facilities(), "6 · Donatı ihtiyacı")
        self.tabs.addTab(self._tab_allocation(), "7 · Mahalle dağıtımı")
        self.tabs.addTab(self._tab_report(), "8 · Rapor")
        for w in (self.base_year, self.target_year):
            w.valueChanged.connect(self.schedule)

    @staticmethod
    def _scroll(w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setWidget(w)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        return sa

    def schedule(self, *args):
        if not self._building:
            self._timer.start()

    # -- 1 veri -----------------------------------------------------------------
    def _tab_data(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Mahalle katmanı (isteğe bağlı)")
        f = QFormLayout(g)
        self.mh_layer = QgsMapLayerComboBox()
        self.mh_layer.setFilters(layer_filter("polygon"))
        self.mh_layer.setAllowEmptyLayer(True)
        self.mh_layer.setLayer(None)
        self.mh_name = QgsFieldComboBox()
        self.mh_pop = QgsFieldComboBox()
        self.mh_pop.setFilters(field_filter_numeric())
        self.mh_layer.layerChanged.connect(self._mh_layer_changed)
        f.addRow("Katman", self.mh_layer)
        f.addRow("Mahalle adı alanı", self.mh_name)
        f.addRow("Nüfus alanı", self.mh_pop)
        row = QHBoxLayout()
        row.addWidget(primary_button("Katmandan oku", self.read_layer))
        row.addWidget(hint("Toplam nüfus, mahalle listesi ve (varsa yas_0_14_erkek … "
                           "yas_64_ustu_kadin alanlarından) yaş-cinsiyet yapısı okunur."))
        f.addRow(row)
        lay.addWidget(g)

        g2 = QGroupBox("Başlangıç yaş-cinsiyet yapısı")
        g2l = QVBoxLayout(g2)
        grid = QGridLayout()
        self.broad = {}
        for c, (lbl, key) in enumerate((("0-14", "0_14"), ("15-64", "15_64"), ("65+", "65"))):
            grid.addWidget(QLabel(lbl), 0, c + 1, alignment=Qt.AlignmentFlag.AlignCenter)
            for r, (sx, sl) in enumerate((("m", "Erkek"), ("f", "Kadın"))):
                if c == 0:
                    grid.addWidget(QLabel(sl), r + 1, 0)
                s = spin(0, 50_000_000, 0, 100)
                self.broad["%s_%s" % (sx, key)] = s
                grid.addWidget(s, r + 1, c + 1)
        grid.addWidget(button("17 yaş grubuna dağıt", self.spread_broad,
                              "Geniş grupları standart dağılım ağırlıklarıyla 5'li gruplara böler"),
                       1, 4, 2, 1)
        g2l.addLayout(grid)
        self.base_table = make_table(["Yaş grubu", "Erkek", "Kadın", "Toplam"], editable=True)
        self.base_table.setRowCount(cohort.N_GROUPS)
        for i, grp in enumerate(cohort.AGE_GROUPS):
            self.base_table.setItem(i, 0, text_item(grp))
        self.base_table.itemChanged.connect(self._base_edited)
        self.base_table.setMinimumHeight(300)
        g2l.addWidget(self.base_table)
        g2l.addWidget(hint("Hücreleri doğrudan düzenleyebilir ya da Excel'den kopyalayıp "
                           "seçili hücreye Ctrl+V ile yapıştırabilirsiniz."))
        lay.addWidget(g2)

        g3 = QGroupBox("Geçmiş nüfus serisi (TÜİK ADNKS)")
        g3l = QVBoxLayout(g3)
        self.series_table = make_table(["Yıl", "Nüfus"], editable=True)
        self.series_table.setMinimumHeight(190)
        self.series_table.itemChanged.connect(self.schedule)
        g3l.addWidget(self.series_table)
        b = QHBoxLayout()
        b.addWidget(button("+ Satır", lambda: self.series_table.insertRow(self.series_table.rowCount())))
        b.addWidget(button("− Satır", self._remove_series_row))
        b.addWidget(button("Panodan yapıştır", self._paste_series,
                           "İki sütun (yıl, nüfus) — Excel'den kopyalanmış olabilir"))
        b.addWidget(button("Örnek: Tire (İzmir)", self.load_example))
        b.addStretch()
        g3l.addLayout(b)
        lay.addWidget(g3)
        lay.addStretch()
        return w

    # -- 2 trend ------------------------------------------------------------------
    def _tab_trends(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("Lojistik doyum nüfusu (K)"))
        self.saturation = spin(0, 100_000_000, 0, 1000)
        self.saturation.setSpecialValueText("otomatik")
        self.saturation.valueChanged.connect(self.schedule)
        row.addWidget(self.saturation)
        row.addWidget(hint("Geriye dönük sınama: son gözlem dışarıda bırakılıp yeniden tahmin "
                           "edilir; hatası küçük yöntem bu seride daha güvenilirdir."))
        lay.addLayout(row)
        split = QSplitter(Qt.Orientation.Vertical)
        self.trend_table = make_table(["Yöntem", "Hedef yıl nüfusu", "Parametre", "R²",
                                       "Geriye dönük hata (%)"])
        split.addWidget(self.trend_table)
        self.trend_chart = LineChart()
        split.addWidget(self.trend_chart)
        split.setSizes([220, 380])
        lay.addWidget(split, 1)
        return w

    # -- 3 kuşak-bileşen ---------------------------------------------------------
    def _tab_cohort(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        g = QGroupBox("Bileşenler")
        f = QFormLayout(g)
        self.srb = dspin(90, 120, 105, 0.5, 1)
        self.srb.setToolTip("100 kız doğuma karşılık erkek doğum")
        f.addRow("Doğumda cinsiyet oranı", self.srb)
        self.tfr_label = QLabel("—")
        f.addRow("Mevcut TFR (5·ΣASFR)", self.tfr_label)
        tr = QHBoxLayout()
        self.tfr_on = QCheckBox("hedef yıla doğru")
        self.tfr_target = dspin(0.5, 5, 1.5, 0.05, 2)
        tr.addWidget(self.tfr_on)
        tr.addWidget(self.tfr_target)
        f.addRow("Hedef TFR", tr)
        self.mig_mode = QComboBox()
        self.mig_mode.addItem("Göç yok (doğal nüfus)", "none")
        self.mig_mode.addItem("Yıllık net göç hızı (%)", "rate")
        self.mig_mode.addItem("Yıllık net göçmen (kişi)", "absolute")
        self.mig_value = dspin(-1_000_000, 1_000_000, 0, 0.1, 2)
        mr = QHBoxLayout()
        mr.addWidget(self.mig_mode)
        mr.addWidget(self.mig_value)
        f.addRow("Göç", mr)
        ll.addWidget(g)
        ll.addWidget(hint("Sx: 5 yıllık yaşama oranı (TÜİK hayat tablosu, öğrenci çalışmasından). "
                          "ASFR: yıllık yaşa özel doğurganlık. Göç profili: net göçün yaş dağılımı."))
        self.param_table = make_table(["Yaş", "Sx Erkek", "Sx Kadın", "ASFR", "Göç profili"],
                                      editable=True)
        self.param_table.setRowCount(cohort.N_GROUPS)
        ll.addWidget(self.param_table, 1)
        ll.addWidget(button("Varsayılan parametreler", self._fill_params))
        for wdg in (self.srb, self.tfr_target, self.mig_value):
            wdg.valueChanged.connect(self.schedule)
        self.tfr_on.toggled.connect(self.schedule)
        self.mig_mode.currentIndexChanged.connect(self.schedule)
        self.param_table.itemChanged.connect(self.schedule)
        lay.addWidget(left, 2)

        right = QSplitter(Qt.Orientation.Vertical)
        self.pyramid = PyramidChart()
        right.addWidget(self.pyramid)
        self.cohort_table = make_table(["Yıl", "Toplam", "Erkek", "Kadın", "Dönem doğumu",
                                        "Dönem net göçü", "Bağımlılık (%)", "Yaşlı oranı (%)",
                                        "Yaşlanma endeksi", "Medyan yaş"])
        right.addWidget(self.cohort_table)
        right.setSizes([420, 200])
        lay.addWidget(right, 3)
        return w

    # -- 4 istihdam -------------------------------------------------------------
    def _tab_econ(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("İktisadi temel / istihdam çarpanı")
        f = QFormLayout(g)
        self.econ_mode = QComboBox()
        self.econ_mode.addItem("Toplam istihdam artışı (mevcut → hedef)", "toplam")
        self.econ_mode.addItem("Temel sektör işi × baz çarpanı", "temel")
        f.addRow("Hesap biçimi", self.econ_mode)
        self.emp_now = spin(0, 50_000_000, 32000, 500)
        self.emp_target = spin(0, 50_000_000, 45000, 500)
        self.basic_jobs = spin(0, 10_000_000, 2650, 50)
        self.multiplier = dspin(1, 20, 4.9, 0.1, 2)
        self.dependency = dspin(0.5, 10, 1.96, 0.01, 2)
        f.addRow("Mevcut toplam istihdam", self.emp_now)
        f.addRow("Hedef yıl toplam istihdam", self.emp_target)
        f.addRow("Temel sektörde yeni iş", self.basic_jobs)
        f.addRow("Baz çarpanı", self.multiplier)
        f.addRow("Bağımlılık oranı (kişi / çalışan)", self.dependency)
        self.local_on = QCheckBox("Doğal çalışma çağı artışının karşıladığı işleri düş")
        self.lfpr = dspin(0, 1, 0.48, 0.01, 2)
        self.unemp = dspin(0, 0.9, 0.09, 0.01, 2)
        f.addRow(self.local_on)
        f.addRow("İşgücüne katılım oranı", self.lfpr)
        f.addRow("İşsizlik oranı", self.unemp)
        lay.addWidget(g)
        lay.addWidget(hint("Öğrenci sürümünde baz çarpanı yalnızca gösteriliyordu; 'temel sektör' "
                           "biçimi onu gerçekten kullanır. Yerel arz düzeltmesi, yeni işlerin bir "
                           "kısmı zaten kentte yaşayan gençlerce doldurulacağı için göçün iki kez "
                           "sayılmasını önler."))
        self.econ_view = QTextBrowser()
        self.econ_view.setMinimumHeight(220)
        lay.addWidget(self.econ_view)
        for wdg in (self.emp_now, self.emp_target, self.basic_jobs, self.multiplier,
                    self.dependency, self.lfpr, self.unemp):
            wdg.valueChanged.connect(self.schedule)
        self.econ_mode.currentIndexChanged.connect(self.schedule)
        self.local_on.toggled.connect(self.schedule)
        return w

    # -- 5 senaryolar -------------------------------------------------------------
    def _tab_scenarios(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(hint("Her senaryo için bir kaynak seçin; plan nüfusu donatı hesabını ve "
                           "mahalle dağıtımını belirler."))
        grid = QGridLayout()
        self.scen_src, self.scen_val, self.scen_manual, self.scen_radio = [], [], [], []
        self.scen_wanted = ["Kuşak-bileşen · doğal (göçsüz)", "Doğrusal regresyon (EKK)",
                            "Kuşak-bileşen + istihdam göçü"]
        self.scen_group = QButtonGroup(self)
        for i, name in enumerate(("Düşük", "Orta", "Yüksek")):
            lbl = QLabel("<b style='color:%s'>%s</b>" % (SCEN_COLORS[i], name))
            src = QComboBox()
            man = spin(0, 100_000_000, 0, 100)
            man.setVisible(False)
            val = QLabel("—")
            val.setMinimumWidth(110)
            rb = QRadioButton("plan nüfusu")
            self.scen_group.addButton(rb, i)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(src, i, 1)
            grid.addWidget(man, i, 2)
            grid.addWidget(val, i, 3)
            grid.addWidget(rb, i, 4)
            src.currentIndexChanged.connect(self._scenario_changed)
            src.activated.connect(lambda _i, k=i, c=src: self._scenario_picked(k, c))
            man.valueChanged.connect(self._scenario_changed)
            rb.toggled.connect(self._scenario_changed)
            self.scen_src.append(src)
            self.scen_val.append(val)
            self.scen_manual.append(man)
            self.scen_radio.append(rb)
        self.scen_radio[2].setChecked(True)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.scen_chart = BarChart(title="Yöntem ve senaryo karşılaştırması")
        self.scen_chart.zero_based = False
        lay.addWidget(self.scen_chart, 1)
        return w

    # -- 6 donatı ---------------------------------------------------------------------
    def _tab_facilities(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        left.addWidget(hint("Kişi başı standartlar öğrenci çalışmasından alınmıştır (MPYY Ek-2, "
                            "100.001-250.000 nüfus grubu olarak girilmiş). Kullanmadan önce "
                            "yürürlükteki yönetmelikle karşılaştırın; hücreler düzenlenebilir."))
        self.std_table = make_table(["Donatı", "Tür", "m²/kişi"], editable=True)
        self.std_table.itemChanged.connect(self.schedule)
        left.addWidget(self.std_table, 1)
        sb = QHBoxLayout()
        sb.addWidget(button("+ Satır", lambda: self.std_table.insertRow(self.std_table.rowCount())))
        sb.addWidget(button("− Satır", lambda: self.std_table.removeRow(self.std_table.currentRow())))
        sb.addWidget(button("Varsayılanlar", self._fill_standards))
        left.addLayout(sb)
        lay.addLayout(left, 2)
        right = QVBoxLayout()
        self.fac_card = Card("Net ek donatı alanı (plan nüfusu − başlangıç)")
        right.addWidget(self.fac_card)
        self.fac_table = make_table(["Donatı", "Tür", "m²/kişi", "Başlangıç ihtiyacı (m²)",
                                     "Hedef ihtiyaç (m²)", "Net ek (m²)", "Net ek (ha)"])
        right.addWidget(self.fac_table, 1)
        self.fac_chart = BarChart(title="Türe göre net ek alan (m²)")
        self.fac_chart.setMinimumHeight(200)
        right.addWidget(self.fac_chart)
        lay.addLayout(right, 3)
        return w

    # -- 7 dağıtım ------------------------------------------------------------------
    def _tab_allocation(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Dağıtım yöntemi")
        f = QFormLayout(g)
        self.alloc_method = QComboBox()
        self.alloc_method.addItem("Mevcut nüfus payıyla (oransal)", "oransal")
        self.alloc_method.addItem("Planlama bölgesine göre artış payı", "bolge")
        self.alloc_method.addItem("Plan kapasitesiyle sınırlı", "kapasite")
        f.addRow("Yöntem", self.alloc_method)
        self.zone_field = QgsFieldComboBox()
        self.zone_field.setAllowEmptyFieldName(True)
        f.addRow("Bölge alanı (katmanda)", self.zone_field)
        self.zone_table = make_table(["Bölge", "Artış payı (%)"], editable=True)
        self.zone_table.setMaximumHeight(150)
        f.addRow(self.zone_table)
        zb = QHBoxLayout()
        zb.addWidget(button("Bölgeleri katmandan al", self._load_zones))
        zb.addWidget(button("Öğrenci ön ayarı (75 / 20 / 5)", self._student_zones))
        f.addRow(zb)
        self.cap_field = QgsFieldComboBox()
        self.cap_field.setFilters(field_filter_numeric())
        self.cap_field.setAllowEmptyFieldName(True)
        f.addRow("Kapasite alanı (kişi)", self.cap_field)
        lay.addWidget(g)
        for wdg in (self.alloc_method,):
            wdg.currentIndexChanged.connect(self.schedule)
        self.zone_table.itemChanged.connect(self.schedule)
        self.zone_field.fieldChanged.connect(self._read_neighbourhood_attrs)
        self.cap_field.fieldChanged.connect(self._read_neighbourhood_attrs)
        row = QHBoxLayout()
        self.alloc_info = hint("")
        row.addWidget(self.alloc_info, 1)
        row.addWidget(primary_button("Haritaya aktar (yeni katman)", self.export_to_map))
        lay.addLayout(row)
        self.alloc_table = make_table(["Mahalle", "Bölge", "Mevcut", "Hedef", "Net artış",
                                       "Artış (%)", "Net donatı ihtiyacı (m²)"])
        lay.addWidget(self.alloc_table, 1)
        return w

    # -- 8 rapor ----------------------------------------------------------------------
    def _tab_report(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(primary_button("HTML rapor kaydet", self.save_report))
        row.addWidget(button("Excel (.xlsx) kaydet", self.save_xlsx))
        row.addWidget(button("Grafikleri PNG kaydet (300 DPI)", self.save_charts))
        row.addStretch()
        lay.addLayout(row)
        self.report_view = QTextBrowser()
        lay.addWidget(self.report_view, 1)
        return w

    # ------------------------------------------------------------ varsayılanlar
    def load_defaults(self):
        self._building = True
        self._fill_params()
        self._fill_standards()
        self._building = False
        self.recompute_all()

    def _fill_params(self):
        blocked = self.param_table.blockSignals(True)
        for i, g in enumerate(cohort.AGE_GROUPS):
            self.param_table.setItem(i, 0, text_item(g))
            self.param_table.setItem(i, 1, QTableWidgetItem("%.6f" % cohort.DEFAULT_SX_MALE[i]))
            self.param_table.setItem(i, 2, QTableWidgetItem("%.6f" % cohort.DEFAULT_SX_FEMALE[i]))
            asfr = cohort.DEFAULT_ASFR.get(g)
            self.param_table.setItem(i, 3, QTableWidgetItem("" if asfr is None else "%.4f" % asfr))
            self.param_table.setItem(i, 4, QTableWidgetItem("%.3f" % cohort.DEFAULT_MIGRATION_PROFILE[i]))
        self.param_table.blockSignals(blocked)
        self.schedule()

    def _fill_standards(self):
        blocked = self.std_table.blockSignals(True)
        self.std_table.setRowCount(len(facilities.DEFAULT_STANDARDS))
        for r, (name, kind, v) in enumerate(facilities.DEFAULT_STANDARDS):
            self.std_table.setItem(r, 0, QTableWidgetItem(name))
            self.std_table.setItem(r, 1, QTableWidgetItem(kind))
            self.std_table.setItem(r, 2, QTableWidgetItem(str(v)))
        self.std_table.blockSignals(blocked)
        self.schedule()

    def load_example(self):
        """Öğrencinin Tire verisi: ADNKS serisi + 2025 geniş yaş grupları kestirimi."""
        self._building = True
        self.series_table.setRowCount(0)
        for y, p in trends.EXAMPLE_SERIES_TIRE:
            r = self.series_table.rowCount()
            self.series_table.insertRow(r)
            self.series_table.setItem(r, 0, QTableWidgetItem(str(y)))
            self.series_table.setItem(r, 1, QTableWidgetItem(str(p)))
        if self._base_total() <= 0:
            total = trends.EXAMPLE_SERIES_TIRE[-1][1]
            # yaş yapısı verisi yoksa: Tire 2025 için öğrenci sürümünün oranları
            shares = {"m_0_14": 0.08, "m_15_64": 0.32, "m_65": 0.09,
                      "f_0_14": 0.08, "f_15_64": 0.33, "f_65": 0.10}
            ssum = sum(shares.values())
            for k, s in shares.items():
                self.broad[k].setValue(int(round(total * s / ssum)))
            self.spread_broad()
        self.base_year.setValue(2025)
        self._building = False
        self.recompute_all()

    # ------------------------------------------------------------ veri okuma
    def _mh_layer_changed(self, layer):
        self.mh_name.setLayer(layer)
        self.mh_pop.setLayer(layer)
        self.zone_field.setLayer(layer)
        self.cap_field.setLayer(layer)
        if layer is not None:
            self.mh_name.setField(_find(layer, NAME_HINTS))
            self.mh_pop.setField(_find(layer, POP_HINTS))

    def read_layer(self):
        layer = self.mh_layer.currentLayer()
        if layer is None:
            QMessageBox.information(self, "Kent Öngörü", "Önce bir mahalle katmanı seçin.")
            return
        pop_f = self.mh_pop.currentField()
        if not pop_f:
            QMessageBox.warning(self, "Kent Öngörü", "Nüfus alanı seçilmeli.")
            return
        sums = {k: 0.0 for k in BASE_FIELD_HINTS}
        found = {k: _find(layer, h) for k, h in BASE_FIELD_HINTS.items()}
        for feat in layer.getFeatures():
            for k, fld in found.items():
                if fld:
                    try:
                        sums[k] += float(feat[fld] or 0)
                    except (TypeError, ValueError):
                        pass
        self._read_neighbourhood_attrs()
        if all(found.values()) and sum(sums.values()) > 0:
            self._building = True
            for k, v in sums.items():
                self.broad[k].setValue(int(round(v)))
            self._building = False
            self.spread_broad()
            msg = "Yaş-cinsiyet yapısı katmandan okundu."
        else:
            total = sum(p for _, p, _, _ in self.neighbourhoods)
            msg = ("Katmanda yaş-cinsiyet alanları bulunamadı; toplam nüfus %s. Başlangıç "
                   "yapısını tabloya girin ya da geniş gruplardan üretin." % fmt_int(total))
        if self.iface:
            self.iface.messageBar().pushInfo("Kent Öngörü", "%d mahalle okundu. %s" % (
                len(self.neighbourhoods), msg))
        self.recompute_all()

    def _read_neighbourhood_attrs(self, *args):
        if self._building:
            return
        layer = self.mh_layer.currentLayer()
        if layer is None:
            return
        name_f, pop_f = self.mh_name.currentField(), self.mh_pop.currentField()
        zone_f, cap_f = self.zone_field.currentField(), self.cap_field.currentField()
        out = []
        for feat in layer.getFeatures():
            name = str(feat[name_f]) if name_f else str(feat.id())
            try:
                pop = float(feat[pop_f] or 0) if pop_f else 0.0
            except (TypeError, ValueError):
                pop = 0.0
            zone = str(feat[zone_f]) if zone_f and feat[zone_f] is not None else "—"
            cap = None
            if cap_f:
                try:
                    cap = float(feat[cap_f])
                except (TypeError, ValueError):
                    cap = None
            out.append((name, pop, zone, cap))
        self.neighbourhoods = out
        self.schedule()

    def _load_zones(self):
        zones = sorted({z for _, _, z, _ in self.neighbourhoods})
        if not zones or zones == ["—"]:
            QMessageBox.information(self, "Kent Öngörü", "Önce bir bölge alanı seçin ve katmanı okuyun.")
            return
        blocked = self.zone_table.blockSignals(True)
        self.zone_table.setRowCount(len(zones))
        for r, z in enumerate(zones):
            self.zone_table.setItem(r, 0, text_item(z))
            self.zone_table.setItem(r, 1, QTableWidgetItem("%.1f" % (100.0 / len(zones))))
        self.zone_table.blockSignals(blocked)
        self.alloc_method.setCurrentIndex(1)
        self.schedule()

    def _student_zones(self):
        blocked = self.zone_table.blockSignals(True)
        self.zone_table.setRowCount(len(allocation.STUDENT_ZONE_SHARES))
        for r, (z, s) in enumerate(allocation.STUDENT_ZONE_SHARES.items()):
            self.zone_table.setItem(r, 0, QTableWidgetItem(z))
            self.zone_table.setItem(r, 1, QTableWidgetItem("%.0f" % (s * 100)))
        self.zone_table.blockSignals(blocked)
        if self.iface:
            self.iface.messageBar().pushInfo(
                "Kent Öngörü", "Bölge adlarının katmandaki bölge alanı değerleriyle aynı olması gerekir.")
        self.alloc_method.setCurrentIndex(1)
        self.schedule()

    def spread_broad(self):
        b = {k: s.value() for k, s in self.broad.items()}
        m, f = cohort.baseline_from_broad_groups(b["m_0_14"], b["m_15_64"], b["m_65"],
                                                 b["f_0_14"], b["f_15_64"], b["f_65"])
        self._set_base(m, f)
        self.schedule()

    def _set_base(self, m, f):
        blocked = self.base_table.blockSignals(True)
        for i in range(cohort.N_GROUPS):
            self.base_table.setItem(i, 1, QTableWidgetItem(str(int(round(m[i])))))
            self.base_table.setItem(i, 2, QTableWidgetItem(str(int(round(f[i])))))
            self.base_table.setItem(i, 3, num_item(m[i] + f[i]))
        self.base_table.blockSignals(blocked)

    def _base_edited(self, item):
        if item.column() in (1, 2):
            m, f = self._base_vectors()
            blocked = self.base_table.blockSignals(True)
            r = item.row()
            self.base_table.setItem(r, 3, num_item(m[r] + f[r]))
            self.base_table.blockSignals(blocked)
            self.schedule()

    def _cell_float(self, table, r, c, default=0.0):
        it = table.item(r, c)
        if it is None or not it.text().strip():
            return default
        try:
            return float(it.text().replace(".", "").replace(",", ".")) if c in (1, 2) and table is self.base_table \
                else float(it.text().replace(",", "."))
        except ValueError:
            return default

    def _base_vectors(self):
        m = [self._cell_float(self.base_table, i, 1) for i in range(cohort.N_GROUPS)]
        f = [self._cell_float(self.base_table, i, 2) for i in range(cohort.N_GROUPS)]
        return m, f

    def _base_total(self):
        m, f = self._base_vectors()
        return sum(m) + sum(f)

    def _series(self):
        ys, ps = [], []
        for r in range(self.series_table.rowCount()):
            try:
                y = float(self.series_table.item(r, 0).text())
                p = float(self.series_table.item(r, 1).text().replace(".", "").replace(",", "."))
            except (AttributeError, ValueError):
                continue
            ys.append(y)
            ps.append(p)
        return ys, ps

    def _remove_series_row(self):
        r = self.series_table.currentRow()
        if r >= 0:
            self.series_table.removeRow(r)
            self.schedule()

    def _paste_series(self):
        text = QApplication.clipboard().text()
        rows = []
        for line in text.splitlines():
            parts = [p for p in line.replace(";", "\t").split("\t") if p.strip()]
            if len(parts) < 2:
                parts = line.split()
            try:
                rows.append((int(float(parts[0])), float(parts[1].replace(".", "").replace(",", "."))))
            except (ValueError, IndexError):
                continue
        if not rows:
            QMessageBox.information(self, "Kent Öngörü", "Panoda (yıl, nüfus) satırı bulunamadı.")
            return
        self._building = True
        self.series_table.setRowCount(0)
        for y, p in rows:
            r = self.series_table.rowCount()
            self.series_table.insertRow(r)
            self.series_table.setItem(r, 0, QTableWidgetItem(str(y)))
            self.series_table.setItem(r, 1, QTableWidgetItem(str(int(p))))
        self._building = False
        self.recompute_all()

    def _params(self, migration=True):
        p = cohort.CohortParams()
        p.sx_male = [self._cell_float(self.param_table, i, 1, cohort.DEFAULT_SX_MALE[i])
                     for i in range(cohort.N_GROUPS)]
        p.sx_female = [self._cell_float(self.param_table, i, 2, cohort.DEFAULT_SX_FEMALE[i])
                       for i in range(cohort.N_GROUPS)]
        p.asfr = {g: self._cell_float(self.param_table, cohort.AGE_GROUPS.index(g), 3, 0.0)
                  for g in cohort.FERTILE_GROUPS}
        p.migration_profile = [max(0.0, self._cell_float(self.param_table, i, 4, 0.0))
                               for i in range(cohort.N_GROUPS)]
        if sum(p.migration_profile) <= 0:
            p.migration_profile = list(cohort.DEFAULT_MIGRATION_PROFILE)
        p.sex_ratio_at_birth = self.srb.value()
        p.tfr_target = self.tfr_target.value() if self.tfr_on.isChecked() else None
        mode = self.mig_mode.currentData() if migration else "none"
        p.migration_mode = mode
        if mode == "rate":
            p.migration_rate = self.mig_value.value() / 100.0
        elif mode == "absolute":
            p.migration_annual = self.mig_value.value()
        return p

    def _standards(self):
        out = []
        for r in range(self.std_table.rowCount()):
            try:
                out.append((self.std_table.item(r, 0).text(), self.std_table.item(r, 1).text(),
                            float(self.std_table.item(r, 2).text().replace(",", "."))))
            except (AttributeError, ValueError):
                continue
        return out

    # ------------------------------------------------------------ hesap zinciri
    def recompute_all(self):
        self._timer.stop()
        by, ty = self.base_year.value(), self.target_year.value()
        if ty <= by:
            self.target_year.setValue(by + 5)
            return
        m0, f0 = self._base_vectors()
        base_total = sum(m0) + sum(f0)
        ys, ps = self._series()
        # trend
        self.trend_models, self.trend_errors = [], {}
        if len(ys) >= 2:
            try:
                self.trend_models, self.trend_errors = trends.run_all(
                    ys, ps, self.saturation.value() or None)
            except ValueError as exc:
                self.trend_errors = {"seri": str(exc)}
        if base_total <= 0 and ps:
            base_total = ps[-1]
        # kuşak-bileşen
        self.cohort_result = self.cohort_natural = None
        if sum(m0) + sum(f0) > 0:
            try:
                self.cohort_natural = cohort.project(m0, f0, by, ty, self._params(False))
                self.cohort_result = cohort.project(m0, f0, by, ty, self._params(True))
                self.tfr_label.setText("%.2f" % cohort.tfr(self._params().asfr))
            except ValueError as exc:
                self.tfr_label.setText("Hata: %s" % exc)
        natural = self.cohort_natural.total_at(ty) if self.cohort_natural else None
        # istihdam
        wa_change = 0.0
        if self.cohort_natural:
            last = self.cohort_natural.years[-1]
            wa_change = (cohort.demographic_indicators(self.cohort_natural.male[last],
                                                       self.cohort_natural.female[last])["calisma_15_64"]
                         - cohort.demographic_indicators(m0, f0)["calisma_15_64"])
        self.econ = economic.employment_migration(
            self.econ_mode.currentData(), self.emp_now.value(), self.emp_target.value(),
            self.basic_jobs.value(), self.multiplier.value(), self.dependency.value(),
            wa_change, self.lfpr.value(), self.unemp.value(), self.local_on.isChecked())
        self.econ["dogal_calisma_cagi_degisimi"] = wa_change
        self._update_trends(ys, ps, ty)
        self._update_cohort(ty)
        self._update_econ(natural, ty)
        self._update_sources(natural)
        self._scenario_changed()
        self.cards[0].set(fmt_int(base_total), "Başlangıç nüfusu (%d)" % by)
        self.cards[1].set(fmt_int(natural), "Doğal nüfus %d (kuşak-bileşen, göçsüz)" % ty)
        self.cards[2].set("+" + fmt_int(self.econ["goc_nufusu"]), "İstihdam göçü (%s yeni iş)" %
                          fmt_int(self.econ["yeni_istihdam"]))

    def _update_trends(self, ys, ps, ty):
        rows = []
        series = []
        for i, mdl in enumerate(self.trend_models):
            rows.append([mdl.name, mdl.predict(ty), mdl.params_text,
                         None if mdl.r2 is None else round(mdl.r2, 4),
                         None if mdl.backtest_error is None else round(mdl.backtest_error, 2)])
            x0 = min(ys)
            pts = [(x, mdl.predict(x)) for x in range(int(x0), int(ty) + 1)]
            series.append((mdl.name, SERIES[i % len(SERIES)], pts, False))
        for key, err in self.trend_errors.items():
            rows.append([key, None, "kurulamadı: " + err, None, None])
        fill_table(self.trend_table, rows, numeric=(1, 3, 4), decimals={3: 4, 4: 2})
        self.trend_chart.subtitle = "Hedef yıl %d · noktalar: gözlenen seri" % ty
        self.trend_chart.set_data(series, list(zip(ys, ps)), vline=self.base_year.value())

    def _update_cohort(self, ty):
        res = self.cohort_result
        if res is None:
            self.pyramid.set_data([], None, None, ("", ""))
            self.cohort_table.setRowCount(0)
            return
        y0, y1 = res.years[0], res.years[-1]
        self.pyramid.title = "Yaş piramidi %d → %d" % (y0, y1)
        mode = self.mig_mode.currentText() if self.mig_mode.currentData() != "none" else "göçsüz"
        self.pyramid.subtitle = "Kuşak-bileşen · %s" % mode
        self.pyramid.set_data(cohort.AGE_GROUPS, (res.male[y0], res.female[y0]),
                              (res.male[y1], res.female[y1]), (str(y0), str(y1)))
        rows = []
        for y in res.years:
            ind = res.indicators(y)
            rows.append([str(y), ind["toplam"], ind["erkek"], ind["kadin"], res.births.get(y),
                         res.migrants.get(y), ind["toplam_bagimlilik"], ind["yasli_orani"],
                         ind["yaslanma_endeksi"], ind["medyan_yas"]])
        fill_table(self.cohort_table, rows, numeric=(1, 2, 3, 4, 5, 6, 7, 8, 9),
                   decimals={6: 1, 7: 1, 8: 1, 9: 1})

    def _update_econ(self, natural, ty):
        e = self.econ
        total = (natural or 0) + e["goc_nufusu"]
        rows = [("Hesap biçimi", "Toplam istihdam artışı" if e["yontem"] == "toplam"
                 else "Temel sektör × baz çarpanı"),
                ("Yeni istihdam", fmt_int(e["yeni_istihdam"])),
                ("Yerel arzla karşılanan iş", fmt_int(e["yerel_karsilanan"])),
                ("Göçle karşılanacak iş", fmt_int(e["goc_ile_karsilanan_is"])),
                ("Bağımlılık oranı", fmt_num(e["bagimlilik_orani"])),
                ("Göçle gelecek nüfus", "<b>+%s</b>" % fmt_int(e["goc_nufusu"])),
                ("%d doğal nüfus" % ty, fmt_int(natural)),
                ("%d toplam (doğal + göç)" % ty, "<b>%s</b>" % fmt_int(total))]
        html = "<table cellpadding='6' style='font-size:13px'>" + "".join(
            "<tr><td style='color:#52606d'>%s</td><td align='right'>%s</td></tr>" % r for r in rows) + "</table>"
        self.econ_view.setHtml(html)

    def _update_sources(self, natural):
        ty = self.target_year.value()
        self.sources = [("Kuşak-bileşen · doğal (göçsüz)", natural)]
        if self.cohort_result is not None and self.mig_mode.currentData() != "none":
            self.sources.append(("Kuşak-bileşen · göç varsayımlı", self.cohort_result.total_at(ty)))
        if natural is not None:
            self.sources.append(("Kuşak-bileşen + istihdam göçü", natural + self.econ["goc_nufusu"]))
        for mdl in self.trend_models:
            self.sources.append((mdl.name, mdl.predict(ty)))
        self.sources.append(("Elle girilen", None))
        fallback = ["Kuşak-bileşen · doğal (göçsüz)", "Doğrusal regresyon (EKK)",
                    "Kuşak-bileşen · doğal (göçsüz)"]
        for i, combo in enumerate(self.scen_src):
            blocked = combo.blockSignals(True)
            combo.clear()
            for name, _ in self.sources:
                combo.addItem(name)
            idx = combo.findText(self.scen_wanted[i])
            if idx < 0:
                idx = max(0, combo.findText(fallback[i]))
            combo.setCurrentIndex(idx)
            combo.blockSignals(blocked)

    def _scenario_picked(self, i, combo):
        self.scen_wanted[i] = combo.currentText()
        self._scenario_changed()

    def _scenario_changed(self, *args):
        if self._building:
            return
        values = dict(getattr(self, "sources", []))
        self.scenarios = []
        for i, combo in enumerate(self.scen_src):
            name = combo.currentText()
            manual = name == "Elle girilen"
            self.scen_manual[i].setVisible(manual)
            v = float(self.scen_manual[i].value()) if manual else values.get(name)
            self.scen_val[i].setText(fmt_int(v))
            self.scenarios.append((("Düşük", "Orta", "Yüksek")[i], name, v))
        chosen = self.scen_group.checkedId()
        chosen = chosen if chosen >= 0 else 2
        self.plan_pop = self.scenarios[chosen][2]
        self.plan_label = "%s senaryo (%s)" % (self.scenarios[chosen][0], self.scenarios[chosen][1])
        self.cards[3].set(fmt_int(self.plan_pop), "Plan nüfusu %d · %s" % (
            self.target_year.value(), self.plan_label))
        items = [(name, v, "#9aa5b1") for name, v in getattr(self, "sources", []) if v is not None]
        items = sorted(items, key=lambda t: t[1])
        for i, (lbl, name, v) in enumerate(self.scenarios):
            for k, it in enumerate(items):
                if it[0] == name:
                    items[k] = ("%s  ◀ %s" % (name, lbl), v, SCEN_COLORS[i])
        ref = None
        if self.plan_pop:
            ref = (self.plan_pop, "plan nüfusu")
        self.scen_chart.subtitle = "Hedef yıl %d" % self.target_year.value()
        self.scen_chart.set_data(items, ref)
        self._update_facilities()
        self._update_allocation()
        self._update_report_preview()

    def _base_pop(self):
        t = self._base_total()
        if t > 0:
            return t
        ys, ps = self._series()
        return ps[-1] if ps else 0.0

    def _update_facilities(self):
        base = self._base_pop()
        target = self.plan_pop or base
        self.facility_rows = facilities.facility_needs(self._standards(), base, target)
        rows = [[r["kategori"], r["tur"], r["kisi_basi"], r["mevcut_ihtiyac_m2"],
                 r["hedef_ihtiyac_m2"], r["net_m2"], r["net_ha"]] for r in self.facility_rows]
        fill_table(self.fac_table, rows, numeric=(2, 3, 4, 5, 6), decimals={2: 2, 6: 2})
        tot = sum(r["net_m2"] for r in self.facility_rows)
        self.fac_card.set("%s ha" % fmt_num(tot / 10000.0), "Net ek donatı alanı (%s m²) · "
                          "%s → %s kişi" % (fmt_int(tot), fmt_int(base), fmt_int(target)))
        groups = facilities.group_totals(self.facility_rows)
        palette = ["#147a8a", "#3f6fb5", "#e07a1f", "#6a8d3a", "#8a5ab5", "#b23a48", "#c9a227"]
        self.fac_chart.set_data([(k, v, palette[i % len(palette)])
                                 for i, (k, v) in enumerate(sorted(groups.items(), key=lambda t: -t[1]))])

    def _zone_shares(self):
        out = {}
        for r in range(self.zone_table.rowCount()):
            try:
                out[self.zone_table.item(r, 0).text()] = float(
                    self.zone_table.item(r, 1).text().replace(",", ".")) / 100.0
            except (AttributeError, ValueError):
                continue
        return out

    def _update_allocation(self):
        if not self.neighbourhoods or not self.plan_pop:
            self.alloc_rows = []
            self.alloc_table.setRowCount(0)
            self.alloc_info.setText("Mahalle katmanını 'Veri' sekmesinde okuyun.")
            return
        names = [n for n, _, _, _ in self.neighbourhoods]
        pops = [p for _, p, _, _ in self.neighbourhoods]
        zones = [z for _, _, z, _ in self.neighbourhoods]
        caps = [c for _, _, _, c in self.neighbourhoods]
        method = self.alloc_method.currentData()
        target = self.plan_pop * (sum(pops) / self._base_pop()) if self._base_pop() else self.plan_pop
        self.alloc_rows, self.alloc_unallocated = allocation.allocate(
            names, pops, target, method, zones, self._zone_shares(), caps)
        per_cap = facilities.per_capita_total(self._standards())
        rows = []
        for r in sorted(self.alloc_rows, key=lambda d: -d["net_artis"]):
            r["donati_m2"] = max(0, r["net_artis"]) * per_cap
            rows.append([r["mahalle"], r["bolge"], r["mevcut"], r["hedef"], r["net_artis"],
                         r["artis_yuzde"], r["donati_m2"]])
        fill_table(self.alloc_table, rows, numeric=(2, 3, 4, 5, 6), decimals={5: 1})
        info = "Mahalle toplamı: %s → %s." % (fmt_int(sum(pops)), fmt_int(target))
        if abs(sum(pops) - self._base_pop()) > 1:
            info += " (Mahalle toplamı başlangıç nüfusundan farklı; hedef aynı oranla ölçeklendi.)"
        if self.alloc_unallocated > 0.5:
            info += " <b style='color:#b23a48'>Kapasiteye sığmayan: %s kişi.</b>" % fmt_int(
                self.alloc_unallocated)
        if method == "bolge" and not self._zone_shares():
            info += " Bölge payı tablosu boş — oransal dağıtıldı."
        self.alloc_info.setText(info)

    # ------------------------------------------------------------ çıktılar
    def export_to_map(self):
        layer = self.mh_layer.currentLayer()
        if layer is None or not self.alloc_rows:
            QMessageBox.information(self, "Kent Öngörü", "Önce mahalle katmanını okuyup dağıtımı hesaplayın.")
            return
        ty = self.target_year.value()
        out = create_copy_layer(layer, "Kent Öngörü – Nüfus %d (%s)" % (ty, layer.name()))
        fields = [("Nufus_%d" % ty, "int"), ("Net_Artis", "int"), ("Artis_Yuzde", "double"),
                  ("Plan_Bolge", "string"), ("Donati_m2", "double")]
        out.dataProvider().addAttributes([make_field(n, k) for n, k in fields])
        out.updateFields()
        idx = {n: out.fields().indexFromName(n) for n, _ in fields}
        changes = {}
        for feat, row in zip(out.getFeatures(), self.alloc_rows):
            changes[feat.id()] = {idx["Nufus_%d" % ty]: row["hedef"], idx["Net_Artis"]: row["net_artis"],
                                  idx["Artis_Yuzde"]: (None if row["artis_yuzde"] is None
                                                       else round(row["artis_yuzde"], 2)),
                                  idx["Plan_Bolge"]: row["bolge"],
                                  idx["Donati_m2"]: round(row.get("donati_m2", 0.0), 1)}
        out.dataProvider().changeAttributeValues(changes)
        apply_graduated_field(out, "Net_Artis", [r["net_artis"] for r in self.alloc_rows],
                              ["#f7fcf0", "#ccebc5", "#7bccc4", "#2b8cbe", "#084081"])
        QgsProject.instance().addMapLayer(out)
        if self.iface:
            self.iface.messageBar().pushSuccess("Kent Öngörü", "'%s' katmanı eklendi." % out.name())

    def chart_images(self):
        return [("nufus_piramidi", self.pyramid.to_image()),
                ("trend_yontemleri", self.trend_chart.to_image()),
                ("senaryolar", self.scen_chart.to_image()),
                ("donati", self.fac_chart.to_image())]

    def save_charts(self):
        folder = QFileDialog.getExistingDirectory(self, "Grafik klasörü")
        if not folder:
            return
        for name, img in self.chart_images():
            img.save(os.path.join(folder, "%s_%d.png" % (name, self.target_year.value())), "PNG")
        if self.iface:
            self.iface.messageBar().pushSuccess("Kent Öngörü", "Grafikler kaydedildi: %s" % folder)

    def xlsx_sheets(self):
        ty = self.target_year.value()
        m0, f0 = self._base_vectors()
        sheets = [("Başlangıç yapısı", [["Yaş", "Erkek", "Kadın", "Toplam"]] +
                   [[g, m0[i], f0[i], m0[i] + f0[i]] for i, g in enumerate(cohort.AGE_GROUPS)])]
        ys, ps = self._series()
        sheets.append(("Gözlenen seri", [["Yıl", "Nüfus"]] + [[int(y), p] for y, p in zip(ys, ps)]))
        sheets.append(("Trend yöntemleri", table_rows(self.trend_table)))
        if self.cohort_result:
            res = self.cohort_result
            head = ["Yaş"]
            for y in res.years:
                head += ["Erkek %d" % y, "Kadın %d" % y, "Toplam %d" % y]
            rows = [head]
            for i, g in enumerate(cohort.AGE_GROUPS):
                row = [g]
                for y in res.years:
                    row += [round(res.male[y][i]), round(res.female[y][i]),
                            round(res.male[y][i] + res.female[y][i])]
                rows.append(row)
            sheets.append(("Kuşak-bileşen", rows))
            sheets.append(("Demografik göstergeler", table_rows(self.cohort_table)))
        e = self.econ or {}
        sheets.append(("İstihdam ve göç", [["Gösterge", "Değer"]] + [[k, v] for k, v in e.items()]))
        sheets.append(("Senaryolar", [["Senaryo", "Kaynak", "Nüfus %d" % ty]] +
                       [[a, b, c] for a, b, c in self.scenarios] +
                       [["Plan nüfusu", self.plan_label, self.plan_pop]]))
        sheets.append(("Donatı ihtiyacı", table_rows(self.fac_table)))
        if self.alloc_rows:
            sheets.append(("Mahalle dağıtımı", table_rows(self.alloc_table)))
        return sheets

    def export_xlsx_to(self, path):
        return xlsx.write_xlsx(path, self.xlsx_sheets())

    def save_xlsx(self):
        path, _ = QFileDialog.getSaveFileName(self, "Excel kaydet", "nufus_projeksiyonu_%d.xlsx" %
                                              self.target_year.value(), "Excel (*.xlsx)")
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self.export_xlsx_to(path)
            if self.iface:
                self.iface.messageBar().pushSuccess("Kent Öngörü", "Excel kaydedildi: %s" % path)

    def build_report_html(self, with_images=True):
        ty, by = self.target_year.value(), self.base_year.value()
        img = (lambda chart, cap: report.image(chart.to_png_base64(), cap)) if with_images else \
            (lambda chart, cap: "")
        e = self.econ or {}
        natural = self.cohort_natural.total_at(ty) if self.cohort_natural else None
        summary = report.cards([("Başlangıç nüfusu (%d)" % by, report.fmt(self._base_pop())),
                                ("Doğal nüfus %d" % ty, report.fmt(natural)),
                                ("İstihdam göçü", "+" + report.fmt(e.get("goc_nufusu"))),
                                ("Plan nüfusu %d" % ty, report.fmt(self.plan_pop))])
        scen = report.table(["Senaryo", "Kaynak", "Nüfus %d" % ty],
                            [[a, b, c] for a, b, c in self.scenarios], numeric_cols=(2,))
        scen += "<p class='note'>Plan nüfusu: %s</p>" % report.escape(self.plan_label)
        trend_rows = [[m.name, m.predict(ty), m.params_text,
                       "—" if m.r2 is None else "%.4f" % m.r2,
                       "—" if m.backtest_error is None else "%.2f" % m.backtest_error]
                      for m in self.trend_models]
        trend = report.table(["Yöntem", "Nüfus %d" % ty, "Parametre", "R²", "Geriye dönük hata %"],
                             trend_rows, numeric_cols=(1, 3, 4)) + img(self.trend_chart, "Trend yöntemleri")
        coh = ""
        if self.cohort_result:
            rows = table_rows(self.cohort_table)
            coh = report.table(rows[0], rows[1:], numeric_cols=tuple(range(1, len(rows[0])))) + \
                img(self.pyramid, "Yaş piramidi")
        econ = report.table(["Gösterge", "Değer"], [
            ["Yeni istihdam", e.get("yeni_istihdam")], ["Yerel arzla karşılanan", e.get("yerel_karsilanan")],
            ["Göçle karşılanacak iş", e.get("goc_ile_karsilanan_is")],
            ["Bağımlılık oranı", report.fmt(e.get("bagimlilik_orani"), 2)],
            ["Göçle gelecek nüfus", e.get("goc_nufusu")]], numeric_cols=(1,))
        fac = report.table(["Donatı", "Tür", "m²/kişi", "Net ek m²", "Net ek ha"],
                           [[r["kategori"], r["tur"], report.fmt(r["kisi_basi"], 2), r["net_m2"],
                             report.fmt(r["net_ha"], 2)] for r in self.facility_rows],
                           numeric_cols=(2, 3, 4)) + img(self.fac_chart, "Türe göre net ek alan")
        alloc = ""
        if self.alloc_rows:
            rows = table_rows(self.alloc_table)
            alloc = report.table(rows[0], rows[1:], numeric_cols=(2, 3, 4, 5, 6))
        return report.page("Nüfus projeksiyonu %d → %d" % (by, ty),
                           "Kuşak-bileşen, trend yöntemleri, iktisadi temel, donatı ve mahalle dağıtımı",
                           [("Özet", summary), ("Senaryolar", scen + img(self.scen_chart, "Senaryolar")),
                            ("Trend yöntemleri", trend), ("Kuşak-bileşen projeksiyonu", coh),
                            ("İstihdam ve göç", econ), ("Donatı ihtiyacı", fac),
                            ("Mahalle dağıtımı", alloc)])

    def _update_report_preview(self):
        if self.tabs.currentIndex() == 7 or not self.report_view.toPlainText():
            self.report_view.setHtml(self.build_report_html(with_images=False))

    def save_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "HTML rapor", "nufus_raporu_%d.html" %
                                              self.target_year.value(), "HTML (*.html)")
        if not path:
            return
        if not path.lower().endswith(".html"):
            path += ".html"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(self.build_report_html(with_images=True))
        if self.iface:
            self.iface.messageBar().pushSuccess("Kent Öngörü", "Rapor kaydedildi: %s" % path)
