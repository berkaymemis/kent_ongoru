# -*- coding: utf-8 -*-
"""Ortak arayüz parçaları ve stil."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QFrame, QHBoxLayout,
                                 QHeaderView, QLabel, QPushButton, QSizePolicy, QSpinBox,
                                 QTableWidget, QTableWidgetItem, QVBoxLayout)

ACCENT = "#147a8a"
DEEP = "#0f3d5e"

QSS = """
QWidget#koRoot { background: #f4f6f8; }
QListWidget#koNav { background: #0f3d5e; border: none; color: #dbe7ef; font-size: 13px;
  outline: 0; padding-top: 6px; }
QListWidget#koNav::item { padding: 11px 14px; border-left: 3px solid transparent; }
QListWidget#koNav::item:selected { background: #145073; color: white;
  border-left: 3px solid #4fd1c5; }
QListWidget#koNav::item:hover { background: #134a6b; }
QLabel#koH1 { font-size: 17px; font-weight: 600; color: #0f3d5e; }
QLabel#koHint { color: #52606d; }
QFrame#koCard { background: white; border: 1px solid #e4e7eb; border-radius: 8px; }
QLabel#koCardValue { font-size: 19px; font-weight: 700; color: #0f3d5e; }
QLabel#koCardLabel { color: #52606d; font-size: 11px; }
QGroupBox { background: white; border: 1px solid #e4e7eb; border-radius: 8px;
  margin-top: 14px; padding: 10px 8px 8px 8px; font-weight: 600; color: #0f3d5e; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTabWidget::pane { border: 1px solid #e4e7eb; background: white; border-radius: 6px; }
QTabBar::tab { padding: 7px 14px; color: #52606d; }
QTabBar::tab:selected { color: #0f3d5e; border-bottom: 2px solid #147a8a; }
QPushButton#koPrimary { background: #147a8a; color: white; border: none; border-radius: 5px;
  padding: 7px 16px; font-weight: 600; }
QPushButton#koPrimary:hover { background: #11697a; }
QPushButton#koPrimary:disabled { background: #9fb3b8; }
QTableWidget { gridline-color: #eef1f4; background: white; alternate-background-color: #f8fafb; }
QHeaderView::section { background: #eef2f5; color: #0f3d5e; border: none;
  border-right: 1px solid #e4e7eb; padding: 4px 6px; font-weight: 600; }
"""


def primary_button(text, slot=None):
    b = QPushButton(text)
    b.setObjectName("koPrimary")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


def button(text, slot=None, tip=""):
    b = QPushButton(text)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def hint(text):
    lbl = QLabel(text)
    lbl.setObjectName("koHint")
    lbl.setWordWrap(True)
    return lbl


def heading(text):
    lbl = QLabel(text)
    lbl.setObjectName("koH1")
    return lbl


class Card(QFrame):
    def __init__(self, label, value="—", accent=ACCENT):
        super().__init__()
        self.setObjectName("koCard")
        self.setStyleSheet("QFrame#koCard{border-left:4px solid %s;}" % accent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self.value = QLabel(value)
        self.value.setObjectName("koCardValue")
        self.label = QLabel(label)
        self.label.setObjectName("koCardLabel")
        self.label.setWordWrap(True)
        lay.addWidget(self.value)
        lay.addWidget(self.label)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, value, label=None):
        self.value.setText(value)
        if label is not None:
            self.label.setText(label)


def card_row(cards):
    row = QHBoxLayout()
    row.setSpacing(10)
    for c in cards:
        row.addWidget(c)
    return row


def spin(lo, hi, value, step=1, suffix="", group=True):
    w = QSpinBox()
    w.setRange(int(lo), int(hi))
    w.setValue(int(value))
    w.setSingleStep(int(step))
    w.setGroupSeparatorShown(group)
    if suffix:
        w.setSuffix(suffix)
    return w


def dspin(lo, hi, value, step=0.1, decimals=2, suffix=""):
    w = QDoubleSpinBox()
    w.setDecimals(decimals)
    w.setRange(lo, hi)
    w.setValue(value)
    w.setSingleStep(step)
    if suffix:
        w.setSuffix(suffix)
    return w


def make_table(headers, stretch_last=True, editable=False):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch_last:
        t.horizontalHeader().setStretchLastSection(True)
    if not editable:
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    return t


def fmt_int(v):
    if v is None:
        return "—"
    return format(int(round(v)), ",").replace(",", ".")


def fmt_num(v, d=2):
    if v is None:
        return "—"
    s = ("{:,.%df}" % d).format(v)
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def num_item(value, text=None, editable=False):
    it = QTableWidgetItem(text if text is not None else fmt_int(value))
    it.setData(Qt.ItemDataRole.UserRole, value)
    it.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
    if not editable:
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def text_item(text, editable=False):
    it = QTableWidgetItem("" if text is None else str(text))
    if not editable:
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def fill_table(table, rows, numeric=(), decimals=None):
    """rows: liste-liste. numeric: sayı sütun indeksleri; decimals: {sütun: ondalık}."""
    decimals = decimals or {}
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if c in numeric and isinstance(v, (int, float)):
                d = decimals.get(c)
                table.setItem(r, c, num_item(v, fmt_num(v, d) if d else None))
            else:
                table.setItem(r, c, text_item(v))


def table_rows(table):
    """Tablo içeriği (başlık dahil) — Excel aktarımı için."""
    head = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
    out = [head]
    for r in range(table.rowCount()):
        row = []
        for c in range(table.columnCount()):
            it = table.item(r, c)
            if it is None:
                row.append(None)
                continue
            v = it.data(Qt.ItemDataRole.UserRole)
            row.append(v if isinstance(v, (int, float)) else it.text())
        out.append(row)
    return out
