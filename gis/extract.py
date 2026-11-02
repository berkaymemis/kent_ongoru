# -*- coding: utf-8 -*-
"""Katmanlardan gösterge ham değerlerini çıkarma.

Tüm geometri hesapları metrik bir çalışma koordinat sisteminde yapılır: bölge
katmanı projeksiyonlu ise onun CRS'i, coğrafi ise (EPSG:4326 gibi) alanın
merkezine göre UTM dilimi. Öğrenci sürümü katman CRS'leri farklıysa bazı
katmanları dönüştürüp bazılarını dönüştürmüyordu; coğrafi CRS'te alanlar
derece² olarak hesaplanıyordu.

Bir bölgede hesaplanamayan değer ``None`` döner (ör. hiç yapı yok, raster
bölgeyi kapsamıyor). Uydurma bir varsayılan konmaz; puanlama motoru eksik
değeri nötr puanla işler ve raporlar.
"""

import math

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature,
                       QgsGeometry, QgsPoint, QgsPointXY, QgsProject, QgsRectangle,
                       QgsSpatialIndex)

from ..core.vulnerability import score_categories

RASTER_CELL_CAP = 40000          # bölge başına okunacak en çok hücre (alt örnekleme)
RESIDENTIAL_KEYWORDS = ["konut", "mesken", "yerles", "yerleş", "residential"]


def parse_float(value):
    if value is None:
        return None
    try:
        if hasattr(value, "isNull") and value.isNull():
            return None
    except TypeError:
        pass
    try:
        f = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def working_crs(layer):
    crs = layer.crs()
    if crs.isValid() and not crs.isGeographic():
        return crs
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    ext = layer.extent()
    if crs.isValid() and crs != wgs:
        ext = QgsCoordinateTransform(crs, wgs, QgsProject.instance()).transformBoundingBox(ext)
    lon = ext.center().x()
    lat = ext.center().y()
    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(60, max(1, zone))
    epsg = (32600 if lat >= 0 else 32700) + zone
    return QgsCoordinateReferenceSystem("EPSG:%d" % epsg)


def find_field(layer, hints, explicit=None):
    """Kullanıcı seçimi yoksa ad ipuçlarından ilk eşleşen alanı bulur."""
    if layer is None:
        return None
    names = [f.name() for f in layer.fields()]
    if explicit:
        return explicit if explicit in names else None
    lower = {n.lower(): n for n in names}
    for h in hints or []:
        if h.lower() in lower:
            return lower[h.lower()]
    for h in hints or []:
        for low, real in lower.items():
            if h.lower() in low:
                return real
    return None


class VectorCache:
    """Bir katmanın öğelerini çalışma CRS'ine dönüştürüp indeksler."""

    def __init__(self, layer, crs, feedback=None):
        self.layer = layer
        xf = None
        if layer.crs() != crs:
            xf = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
        self.geoms = {}
        self.attrs = {}
        self.index = QgsSpatialIndex()
        names = [f.name() for f in layer.fields()]
        for feat in layer.getFeatures():
            if feedback and feedback():
                break
            g = feat.geometry()
            if g is None or g.isEmpty():
                continue
            g = QgsGeometry(g)
            if xf:
                g.transform(xf)
            if not g.isGeosValid():
                g = g.makeValid()
            fid = feat.id()
            self.geoms[fid] = g
            self.attrs[fid] = dict(zip(names, feat.attributes()))
            f2 = QgsFeature(fid)
            f2.setGeometry(g)
            self.index.addFeature(f2)

    def intersecting(self, geom):
        for fid in self.index.intersects(geom.boundingBox()):
            g = self.geoms[fid]
            if g.intersects(geom):
                yield fid, g

    def nearest_distance(self, geom):
        if not self.geoms:
            return None
        ids = self.index.nearestNeighbor(geom, 8)
        if not ids:
            return None
        best = None
        for fid in ids:
            d = 0.0 if self.geoms[fid].intersects(geom) else geom.distance(self.geoms[fid])
            best = d if best is None else min(best, d)
        return best


class Extractor:
    """Bölge katmanı + rol katmanları → gösterge ham değerleri."""

    def __init__(self, region_layer, roles, feedback=None):
        self.region = region_layer
        self.roles = {k: v for k, v in (roles or {}).items() if v is not None and v.isValid()}
        self.crs = working_crs(region_layer)
        self.feedback = feedback
        xf = None
        if region_layer.crs() != self.crs:
            xf = QgsCoordinateTransform(region_layer.crs(), self.crs, QgsProject.instance())
        self.fids, self.geoms, self.attrs = [], [], []
        names = [f.name() for f in region_layer.fields()]
        for feat in region_layer.getFeatures():
            g = QgsGeometry(feat.geometry())
            if xf and not g.isEmpty():
                g.transform(xf)
            if not g.isEmpty() and not g.isGeosValid():
                g = g.makeValid()
            self.fids.append(feat.id())
            self.geoms.append(g)
            self.attrs.append(dict(zip(names, feat.attributes())))
        self._vec = {}
        self._overlap = {}
        self._mahalle_match = None

    # -- yardımcılar ---------------------------------------------------------
    def vector(self, role):
        if role not in self._vec:
            lyr = self.roles.get(role)
            self._vec[role] = VectorCache(lyr, self.crs) if lyr is not None and hasattr(lyr, "fields") else None
        return self._vec[role]

    def overlaps(self, role, i):
        """(fid, kesişim ölçüsü) listesi — poligonlarda alan, çizgilerde uzunluk."""
        key = (role, i)
        if key in self._overlap:
            return self._overlap[key]
        cache = self.vector(role)
        out = []
        geom = self.geoms[i]
        if cache is not None and not geom.isEmpty():
            for fid, g in cache.intersecting(geom):
                inter = g.intersection(geom)
                if inter.isEmpty():
                    continue
                size = inter.area() if inter.area() > 0 else inter.length()
                if size > 0:
                    out.append((fid, size))
        self._overlap[key] = out
        return out

    def mahalle_feature(self, i):
        """Bölgeyle en çok örtüşen mahalle öğesinin öznitelikleri."""
        if self._mahalle_match is None:
            self._mahalle_match = {}
        if i in self._mahalle_match:
            return self._mahalle_match[i]
        best, best_a = None, 0.0
        cache = self.vector("mahalle")
        for fid, a in self.overlaps("mahalle", i):
            if a > best_a:
                best, best_a = fid, a
        attrs = cache.attrs.get(best) if (cache and best is not None) else None
        self._mahalle_match[i] = attrs
        return attrs

    def region_value(self, i, ref):
        """``ref`` = 'alan' (bölge) ya da 'mahalle:alan' (en çok örtüşen mahalle)."""
        if not ref:
            return None
        if ref.startswith("mahalle:"):
            attrs = self.mahalle_feature(i)
            return attrs.get(ref.split(":", 1)[1]) if attrs else None
        return self.attrs[i].get(ref)

    def area_m2(self, i):
        g = self.geoms[i]
        return g.area() if not g.isEmpty() else 0.0

    # -- alan çözümleme ---------------------------------------------------------
    def resolve_region_field(self, explicit, hints):
        """Bölge katmanında, yoksa mahalle katmanında alan referansı."""
        if explicit:
            return explicit
        f = find_field(self.region, hints)
        if f:
            return f
        m = self.roles.get("mahalle")
        if m is not None:
            f = find_field(m, hints)
            if f:
                return "mahalle:" + f
        return None

    def resolve_layer_field(self, role, explicit, hints):
        return find_field(self.roles.get(role), hints, explicit)

    def requirement_problem(self, measure):
        """Ölçüm hesaplanamayacaksa nedeni (metin), aksi halde None."""
        t = measure.get("type")
        role = measure.get("role")
        if t == "area_ha":
            return None
        if t in ("field", "field_text"):
            if self.resolve_region_field(measure.get("field"), measure.get("hints")):
                return None
            if measure.get("fallback"):
                return self.requirement_problem(measure["fallback"])
            return "alan bulunamadı"
        if t == "field_ratio":
            a = self.resolve_region_field(measure.get("field"), measure.get("hints"))
            b = self.resolve_region_field(measure.get("field2"), measure.get("hints2"))
            return None if (a and b) else "pay/payda alanı bulunamadı"
        if role and role not in self.roles:
            return "katman seçilmedi"
        if t in ("area_mean", "area_category", "area_share", "length_mean", "length_share",
                 "length_category", "floor_area_ratio", "residential_pop"):
            if not self.resolve_layer_field(role, measure.get("field"), measure.get("hints")):
                return "katmanda uygun alan yok"
        return None

    # -- ölçümler -------------------------------------------------------------
    def values(self, measure, progress=None):
        n = len(self.geoms)
        t = measure.get("type")
        out = []
        resolved = dict(measure)
        if t in ("field", "field_text", "field_ratio"):
            resolved["field"] = self.resolve_region_field(measure.get("field"), measure.get("hints"))
            if t == "field_ratio":
                resolved["field2"] = self.resolve_region_field(measure.get("field2"),
                                                               measure.get("hints2"))
            if t == "field" and not resolved["field"] and measure.get("fallback"):
                return self.values(measure["fallback"], progress)
        elif measure.get("role") and t not in ("distance", "raster_mean", "raster_aspect",
                                               "cover_ratio", "open_ratio"):
            resolved["field"] = self.resolve_layer_field(measure["role"], measure.get("field"),
                                                         measure.get("hints"))
            if t == "residential_pop":
                resolved["landuse_field"] = self.resolve_layer_field(
                    measure["role"], measure.get("landuse_field"), measure.get("landuse_hints"))
        if t in ("raster_mean", "raster_aspect"):
            return self._raster_values(resolved, progress)
        for i in range(n):
            if progress and progress(i, n):
                break
            out.append(self._value(resolved, i))
        return out

    def _value(self, m, i):
        t = m.get("type")
        geom = self.geoms[i]
        if geom.isEmpty():
            return None
        area = self.area_m2(i)
        if t == "area_ha":
            return area / 10000.0
        if t == "field":
            return parse_float(self.region_value(i, m.get("field")))
        if t == "field_text":
            v = self.region_value(i, m.get("field"))
            return None if v is None else str(v)
        if t == "field_ratio":
            a = parse_float(self.region_value(i, m.get("field")))
            b = parse_float(self.region_value(i, m.get("field2")))
            if a is None or not b:
                return None
            return 100.0 * a / b
        role = m.get("role")
        if t == "distance":
            cache = self.vector(role)
            return cache.nearest_distance(geom) if cache else None
        ov = self.overlaps(role, i)
        cache = self.vector(role)
        fld = m.get("field")
        if t in ("cover_ratio", "open_ratio"):
            if area <= 0:
                return None
            if fld and t == "cover_ratio":
                return self._weighted(ov, cache, fld)
            cover = min(1.0, sum(a for _, a in ov) / area)
            return cover if t == "cover_ratio" else 100.0 * (1.0 - cover)
        if t == "floor_area_ratio":
            if area <= 0:
                return None
            tot = 0.0
            for fid, a in ov:
                k = parse_float(cache.attrs[fid].get(fld))
                tot += a * (k if k and k > 0 else 1.0)
            return tot / area
        if t == "residential_pop":
            per = float(m.get("m2_per_person", 35.0))
            lu = m.get("landuse_field")
            tot = 0.0
            for fid, a in ov:
                attrs = cache.attrs[fid]
                if lu and not any(k in str(attrs.get(lu) or "").lower() for k in RESIDENTIAL_KEYWORDS):
                    continue
                k = parse_float(attrs.get(fld))
                tot += a * (k if k and k > 0 else 1.0)
            return tot / per if tot > 0 else None
        if t in ("area_mean", "length_mean"):
            return self._weighted(ov, cache, fld)
        if t in ("area_category", "length_category"):
            num = den = 0.0
            for fid, a in ov:
                v = cache.attrs[fid].get(fld)
                if v is None or str(v).strip() in ("", "NULL"):
                    continue
                num += a * score_categories(v, m.get("map", []), 3)
                den += a
            return num / den if den > 0 else None
        if t in ("area_share", "length_share"):
            num = den = 0.0
            kws = [k.lower() for k in m.get("keywords", [])]
            for fid, a in ov:
                v = cache.attrs[fid].get(fld)
                if kws:
                    s = str(v or "").lower()
                    if not s.strip() or s == "null":
                        continue
                    hit = any(k in s for k in kws)
                else:
                    f = parse_float(v)
                    if f is None:
                        continue
                    hit = True
                    if "lt" in m:
                        hit = hit and f < float(m["lt"])
                    if "ge" in m:
                        hit = hit and f >= float(m["ge"])
                den += a
                if hit:
                    num += a
            return 100.0 * num / den if den > 0 else None
        return None

    @staticmethod
    def _weighted(ov, cache, fld):
        num = den = 0.0
        for fid, a in ov:
            v = parse_float(cache.attrs[fid].get(fld))
            if v is None:
                continue
            num += a * v
            den += a
        return num / den if den > 0 else None

    # -- raster ---------------------------------------------------------------
    def _raster_values(self, m, progress=None):
        lyr = self.roles.get(m.get("role"))
        n = len(self.geoms)
        if lyr is None or not hasattr(lyr, "dataProvider") or not hasattr(lyr, "rasterUnitsPerPixelX"):
            return [None] * n
        xf = None
        if lyr.crs() != self.crs:
            xf = QgsCoordinateTransform(self.crs, lyr.crs(), QgsProject.instance())
        circular = m.get("type") == "raster_aspect"
        out = []
        for i in range(n):
            if progress and progress(i, n):
                break
            out.append(zonal(lyr, self.geoms[i], xf, circular))
        return out


def zonal(raster, geom, xform=None, circular=False, band=1):
    """Poligon içindeki hücre merkezlerinin ortalaması (bakıda dairesel)."""
    if geom is None or geom.isEmpty():
        return None
    g = QgsGeometry(geom)
    if xform is not None:
        g.transform(xform)
    prov = raster.dataProvider()
    ext = g.boundingBox().intersect(raster.extent())
    if ext.isEmpty() or ext.width() <= 0 or ext.height() <= 0:
        return None
    px = raster.rasterUnitsPerPixelX() or 1.0
    py = raster.rasterUnitsPerPixelY() or 1.0
    cols = max(1, int(math.ceil(ext.width() / px)))
    rows = max(1, int(math.ceil(ext.height() / py)))
    if cols * rows > RASTER_CELL_CAP:
        f = math.sqrt(cols * rows / float(RASTER_CELL_CAP))
        cols = max(1, int(cols / f))
        rows = max(1, int(rows / f))
    block = prov.block(band, QgsRectangle(ext), cols, rows)
    engine = QgsGeometry.createGeometryEngine(g.constGet())
    engine.prepareGeometry()
    cw = ext.width() / cols
    ch = ext.height() / rows
    vals = []
    for r in range(rows):
        y = ext.yMaximum() - (r + 0.5) * ch
        for c in range(cols):
            x = ext.xMinimum() + (c + 0.5) * cw
            if not engine.contains(QgsPoint(x, y)):
                continue
            if block.isNoData(r, c):
                continue
            v = block.value(r, c)
            if v is None or math.isnan(v):
                continue
            vals.append(v)
    if not vals:
        c = g.centroid()
        if c.isEmpty():
            return None
        v, ok = prov.sample(QgsPointXY(c.asPoint()), band)
        if not ok or v is None or math.isnan(v):
            return None
        vals = [v]
    if circular:
        vals = [v for v in vals if v >= 0]
        if not vals:
            return None
        s = sum(math.sin(math.radians(v)) for v in vals)
        c = sum(math.cos(math.radians(v)) for v in vals)
        if abs(s) < 1e-12 and abs(c) < 1e-12:
            return None
        return math.degrees(math.atan2(s, c)) % 360.0
    return sum(vals) / len(vals)
