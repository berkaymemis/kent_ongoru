# -*- coding: utf-8 -*-
"""Qt-yerel grafikler (matplotlib gerekmez).

Her grafik ``draw(painter, rect)`` ile çizilir; aynı işlev ekrana ve yüksek
çözünürlüklü PNG'ye (``to_image``) kullanılır, böylece paftaya giden görsel
ekrandakinin birebir aynısıdır.
"""

import math

from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget

INK = QColor("#1f2933")
MUTED = QColor("#7b8794")
GRID = QColor("#e4e7eb")
SERIES = ["#147a8a", "#e07a1f", "#3f6fb5", "#b23a48", "#6a8d3a", "#8a5ab5", "#c9a227",
          "#4a5568"]


def thousands(v):
    try:
        return format(int(round(v)), ",").replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def nice_ticks(lo, hi, n=5):
    if hi <= lo:
        hi = lo + 1
    span = hi - lo
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=mag * 10)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.5:
        ticks.append(v)
        v += step
    return ticks


class ChartBase(QWidget):
    title = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.subtitle = ""

    def has_data(self):
        return False

    def paintEvent(self, event):  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        self.draw(p, QRectF(self.rect()), 1.0)
        p.end()

    def to_image(self, width=2400, height=1350):
        img = QImage(QSize(width, height), QImage.Format.Format_ARGB32)
        img.fill(QColor("#ffffff"))
        img.setDotsPerMeterX(int(300 / 0.0254))
        img.setDotsPerMeterY(int(300 / 0.0254))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        scale = width / 900.0
        self.draw(p, QRectF(0, 0, width, height), scale)
        p.end()
        return img

    def to_png_base64(self, width=1600, height=900):
        img = self.to_image(width, height)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        return bytes(ba.toBase64()).decode("ascii")

    # -- ortak çizim yardımcıları ---------------------------------------------
    @staticmethod
    def font(scale, size=9, bold=False):
        f = QFont()
        f.setPointSizeF(size * scale)
        f.setBold(bold)
        return f

    def draw_title(self, p, rect, scale):
        p.setPen(INK)
        p.setFont(self.font(scale, 11, True))
        p.drawText(QRectF(rect.left() + 12 * scale, rect.top() + 6 * scale, rect.width(), 22 * scale),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.title)
        if self.subtitle:
            p.setPen(MUTED)
            p.setFont(self.font(scale, 8))
            p.drawText(QRectF(rect.left() + 12 * scale, rect.top() + 26 * scale, rect.width(),
                              16 * scale),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), self.subtitle)

    def draw_empty(self, p, rect, scale, text="Veri yok — önce hesaplayın."):
        p.setPen(MUTED)
        p.setFont(self.font(scale, 10))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def draw(self, p, rect, scale):
        raise NotImplementedError


class PyramidChart(ChartBase):
    """Yaş-cinsiyet piramidi: başlangıç (açık, çerçeve) ve hedef (dolu)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = "Yaş piramidi"
        self.groups = []
        self.base = None
        self.target = None
        self.labels = ("Başlangıç", "Hedef")

    def set_data(self, groups, base, target, labels):
        self.groups, self.base, self.target, self.labels = groups, base, target, labels
        self.update()

    def has_data(self):
        return bool(self.groups and self.target)

    def draw(self, p, rect, s):
        self.draw_title(p, rect, s)
        if not self.has_data():
            return self.draw_empty(p, rect, s)
        top = rect.top() + 48 * s
        bottom = rect.bottom() - 40 * s
        mid = rect.center().x()
        label_w = 46 * s
        half = rect.width() / 2 - label_w / 2 - 24 * s
        vmax = max(max(self.target[0]), max(self.target[1]),
                   max(self.base[0]) if self.base else 0, max(self.base[1]) if self.base else 0) or 1
        n = len(self.groups)
        row_h = (bottom - top) / n
        bar_h = row_h * 0.78
        male_c, female_c = QColor("#3f6fb5"), QColor("#c2456e")
        p.setFont(self.font(s, 7.5))
        for i, g in enumerate(self.groups):
            y = bottom - (i + 1) * row_h + (row_h - bar_h) / 2
            for side, color in ((0, male_c), (1, female_c)):
                w = half * self.target[side][i] / vmax
                x = mid - label_w / 2 - w if side == 0 else mid + label_w / 2
                c = QColor(color)
                c.setAlpha(215)
                p.fillRect(QRectF(x, y, w, bar_h), c)
                if self.base:
                    wb = half * self.base[side][i] / vmax
                    xb = mid - label_w / 2 - wb if side == 0 else mid + label_w / 2
                    pen = QPen(QColor("#111827"), 1.1 * s)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(QRectF(xb, y, wb, bar_h))
            p.setPen(INK)
            p.drawText(QRectF(mid - label_w / 2, y - 2 * s, label_w, bar_h + 4 * s),
                       int(Qt.AlignmentFlag.AlignCenter), g)
        # eksen etiketleri
        p.setPen(MUTED)
        p.setFont(self.font(s, 7.5))
        for frac in (0.5, 1.0):
            val = thousands(vmax * frac)
            for sign in (-1, 1):
                x = mid + sign * (label_w / 2 + half * frac)
                p.drawText(QRectF(x - 40 * s, bottom + 2 * s, 80 * s, 14 * s),
                           int(Qt.AlignmentFlag.AlignCenter), val)
        # lejant
        p.setFont(self.font(s, 8))
        lx = rect.left() + 14 * s
        ly = rect.bottom() - 20 * s
        items = [(male_c, "Erkek " + self.labels[1], True), (female_c, "Kadın " + self.labels[1], True),
                 (QColor("#111827"), self.labels[0] + " (çerçeve)", False)]
        for color, text, filled in items:
            if filled:
                p.fillRect(QRectF(lx, ly, 12 * s, 10 * s), color)
            else:
                p.setPen(QPen(color, 1.2 * s))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(lx, ly, 12 * s, 10 * s))
            p.setPen(INK)
            p.drawText(QRectF(lx + 16 * s, ly - 3 * s, 170 * s, 16 * s),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text)
            lx += 175 * s


class LineChart(ChartBase):
    """Çok serili çizgi grafiği + gözlem noktaları."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = "Nüfus eğilimleri"
        self.series = []          # [(ad, renk, [(x, y)], kalın)]
        self.points = []          # gözlemler [(x, y)]
        self.markers = []         # [(x, y, etiket, renk)]
        self.vline = None

    def set_data(self, series, points=None, markers=None, vline=None):
        self.series, self.points = series, points or []
        self.markers, self.vline = markers or [], vline
        self.update()

    def has_data(self):
        return bool(self.series or self.points)

    def draw(self, p, rect, s):
        self.draw_title(p, rect, s)
        if not self.has_data():
            return self.draw_empty(p, rect, s)
        xs = [x for _, _, pts, _ in self.series for x, _ in pts] + [x for x, _ in self.points]
        ys = [y for _, _, pts, _ in self.series for _, y in pts] + [y for _, y in self.points]
        ys += [m[1] for m in self.markers]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        pad = (y1 - y0) * 0.08 or abs(y1) * 0.05 or 1
        yt = nice_ticks(y0 - pad, y1 + pad)
        y0, y1 = yt[0], yt[-1]
        legend_w = 210 * s
        plot = QRectF(rect.left() + 70 * s, rect.top() + 50 * s,
                      rect.width() - 90 * s - legend_w, rect.height() - 90 * s)

        def px(x):
            return plot.left() + (x - x0) / ((x1 - x0) or 1) * plot.width()

        def py(y):
            return plot.bottom() - (y - y0) / ((y1 - y0) or 1) * plot.height()
        p.setFont(self.font(s, 7.5))
        for t in yt:
            p.setPen(QPen(GRID, 1 * s))
            p.drawLine(QPointF(plot.left(), py(t)), QPointF(plot.right(), py(t)))
            p.setPen(MUTED)
            p.drawText(QRectF(rect.left(), py(t) - 8 * s, 64 * s, 16 * s),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), thousands(t))
        for t in nice_ticks(x0, x1, 8):
            if t < x0 or t > x1:
                continue
            p.setPen(MUTED)
            p.drawText(QRectF(px(t) - 30 * s, plot.bottom() + 4 * s, 60 * s, 14 * s),
                       int(Qt.AlignmentFlag.AlignCenter), str(int(t)))
        if self.vline is not None and x0 <= self.vline <= x1:
            pen = QPen(QColor("#9aa5b1"), 1 * s, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(px(self.vline), plot.top()), QPointF(px(self.vline), plot.bottom()))
        for name, color, pts, bold in self.series:
            if len(pts) < 2:
                continue
            path = QPainterPath(QPointF(px(pts[0][0]), py(pts[0][1])))
            for x, y in pts[1:]:
                path.lineTo(QPointF(px(x), py(y)))
            p.setPen(QPen(QColor(color), (3.0 if bold else 1.8) * s))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(QPen(QColor("#111827"), 1 * s))
        p.setBrush(QBrush(QColor("#ffffff")))
        for x, y in self.points:
            p.drawEllipse(QPointF(px(x), py(y)), 3.6 * s, 3.6 * s)
        for x, y, label, color in self.markers:
            p.setBrush(QBrush(QColor(color)))
            p.setPen(QPen(QColor("#111827"), 1 * s))
            p.drawEllipse(QPointF(px(x), py(y)), 5 * s, 5 * s)
        # lejant
        lx = plot.right() + 16 * s
        ly = plot.top()
        p.setFont(self.font(s, 8))
        for name, color, pts, bold in self.series:
            p.setPen(QPen(QColor(color), 3 * s))
            p.drawLine(QPointF(lx, ly + 7 * s), QPointF(lx + 18 * s, ly + 7 * s))
            p.setPen(INK)
            last = thousands(pts[-1][1]) if pts else ""
            p.drawText(QRectF(lx + 24 * s, ly, legend_w - 30 * s, 15 * s),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       "%s  %s" % (name, last))
            ly += 18 * s
        if self.points:
            p.setPen(QPen(QColor("#111827"), 1 * s))
            p.setBrush(QBrush(QColor("#ffffff")))
            p.drawEllipse(QPointF(lx + 9 * s, ly + 7 * s), 3.6 * s, 3.6 * s)
            p.setPen(INK)
            p.drawText(QRectF(lx + 24 * s, ly, legend_w, 15 * s),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "Gözlem (TÜİK)")


class BarChart(ChartBase):
    """Yatay çubuk grafiği; değerin yanında etiket."""

    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self.title = title
        self.items = []           # [(etiket, değer, renk)]
        self.value_fmt = thousands
        self.reference = None     # (değer, etiket)
        self.zero_based = True    # False: eksen en küçük değerin biraz altından başlar

    def set_data(self, items, reference=None):
        self.items, self.reference = items, reference
        self.update()

    def has_data(self):
        return bool(self.items)

    def draw(self, p, rect, s):
        self.draw_title(p, rect, s)
        if not self.has_data():
            return self.draw_empty(p, rect, s)
        label_w = min(260 * s, rect.width() * 0.36)
        plot = QRectF(rect.left() + label_w + 16 * s, rect.top() + 48 * s,
                      rect.width() - label_w - 100 * s, rect.height() - 64 * s)
        vals = [v for _, v, _ in self.items if v is not None]
        vmin = min(0.0, min(vals) if vals else 0.0)
        vmax = max(vals + ([self.reference[0]] if self.reference else [])) if vals else 1.0
        vmax = vmax or 1.0
        if not self.zero_based and vals and min(vals) > 0:
            lo = min(vals + ([self.reference[0]] if self.reference else []))
            vmin = max(0.0, lo - (vmax - lo) * 0.35 - 0.02 * vmax)
        n = len(self.items)
        row = plot.height() / max(n, 1)
        bar = min(row * 0.66, 26 * s)

        def px(v):
            return plot.left() + (v - vmin) / ((vmax - vmin) or 1) * plot.width()
        p.setFont(self.font(s, 8))
        for i, (label, v, color) in enumerate(self.items):
            y = plot.top() + i * row + (row - bar) / 2
            p.setPen(INK)
            p.drawText(QRectF(rect.left() + 8 * s, y - 4 * s, label_w, bar + 8 * s),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), label)
            if v is None:
                continue
            x0, x1 = sorted((px(max(0.0, vmin)), px(v)))
            p.fillRect(QRectF(x0, y, max(1.0, x1 - x0), bar), QColor(color))
            p.setPen(MUTED)
            p.drawText(QRectF(x1 + 6 * s, y - 4 * s, 90 * s, bar + 8 * s),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       self.value_fmt(v))
        if self.reference:
            x = px(self.reference[0])
            p.setPen(QPen(QColor("#b23a48"), 1.4 * s, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, plot.top() - 6 * s), QPointF(x, plot.bottom()))
            p.setFont(self.font(s, 7.5))
            p.drawText(QRectF(x - 80 * s, plot.top() - 20 * s, 160 * s, 14 * s),
                       int(Qt.AlignmentFlag.AlignCenter), self.reference[1])


class ClassBarChart(BarChart):
    """5 derece dağılımı (bölge sayısı ve nüfus)."""

    def __init__(self, parent=None, title="Derece dağılımı"):
        super().__init__(parent, title)


def image_to_png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)
