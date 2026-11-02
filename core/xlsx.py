# -*- coding: utf-8 -*-
"""Bağımlılıksız, çok sayfalı .xlsx yazıcı.

Öğrenci sürümü pandas + openpyxl istiyordu; ikisi de her QGIS kurulumunda
yok. Bu modül yalnızca standart kütüphane (zipfile) ile Excel'in açtığı
geçerli bir Office Open XML çalışma kitabı üretir: kalın başlık satırı,
sabitlenmiş ilk satır, sayılar sayı olarak.
"""

import re
import zipfile

_BAD_SHEET = re.compile(r"[\[\]\:\*\?\/\\]")
_PKG = "application/vnd.openxmlformats-package."
_SML = "application/vnd.openxmlformats-officedocument.spreadsheetml."
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def escape(text, extra=None):
    """XML metin kaçışı (yalnızca yazma için; hiçbir XML ayrıştırılmaz)."""
    out = _ILLEGAL.sub("", str(text)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for k, v in (extra or {}).items():
        out = out.replace(k, v)
    return out


def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, value, style=0):
    st = ' s="%d"' % style if style else ""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            return ""
        return '<c r="%s"%s><v>%s</v></c>' % (ref, st, repr(float(value)) if isinstance(value, float) else value)
    text = escape(str(value))
    return '<c r="%s" t="inlineStr"%s><is><t xml:space="preserve">%s</t></is></c>' % (ref, st, text)


def _sheet_xml(rows):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
           'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>']
    if rows:
        widths = {}
        for row in rows:
            for c, v in enumerate(row):
                widths[c] = max(widths.get(c, 6), min(60, len(str(v if v is not None else "")) + 2))
        out.append("<cols>")
        for c in sorted(widths):
            out.append('<col min="%d" max="%d" width="%d" customWidth="1"/>' % (c + 1, c + 1, widths[c]))
        out.append("</cols>")
    out.append("<sheetData>")
    for r, row in enumerate(rows):
        cells = "".join(_cell("%s%d" % (_col(c), r + 1), v, 1 if r == 0 else 0)
                        for c, v in enumerate(row))
        out.append('<row r="%d">%s</row>' % (r + 1, cells))
    out.append("</sheetData></worksheet>")
    return "".join(out)


def write_xlsx(path, sheets):
    """``sheets``: [(ad, [[başlık...], [satır...], ...]), ...]"""
    names = []
    for name, _ in sheets:
        clean = _BAD_SHEET.sub("_", str(name))[:31] or "Sayfa"
        base, k = clean, 2
        while clean in names:
            suffix = "_%d" % k
            clean = base[:31 - len(suffix)] + suffix
            k += 1
        names.append(clean)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="%s"/>' % (_PKG + "relationships+xml"),
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" ContentType="%s"/>' % (_SML + "sheet.main+xml"),
          '<Override PartName="/xl/styles.xml" ContentType="%s"/>' % (_SML + "styles+xml")]
    for i in range(len(sheets)):
        ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="%s"/>'
                  % (i + 1, _SML + "worksheet+xml"))
    ct.append("</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="%sofficeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>') % _REL
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    wbr = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i, name in enumerate(names):
        wb.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(name, {'"': "&quot;"}), i + 1, i + 1))
        wbr.append('<Relationship Id="rId%d" Type="%sworksheet" Target="worksheets/sheet%d.xml"/>'
                   % (i + 1, _REL, i + 1))
    wb.append("</sheets></workbook>")
    wbr.append('<Relationship Id="rId%d" Type="%sstyles" Target="styles.xml"/>' % (len(names) + 1, _REL))
    wbr.append("</Relationships>")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill>'
              '<fill><patternFill patternType="gray125"/></fill>'
              '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E79"/>'
              '<bgColor indexed="64"/></patternFill></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
              '</styleSheet>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(ct))
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", "".join(wb))
        z.writestr("xl/_rels/workbook.xml.rels", "".join(wbr))
        z.writestr("xl/styles.xml", styles)
        for i, (_, rows) in enumerate(sheets):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _sheet_xml(rows))
    return path
