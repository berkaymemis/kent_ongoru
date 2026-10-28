# -*- coding: utf-8 -*-
"""Bağımsız (tek dosya) HTML rapor üretimi. Grafikler base64 PNG gömülür."""

import datetime
from html import escape

CSS = """
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#1f2933;margin:0;background:#f4f6f8}
.wrap{max-width:1100px;margin:0 auto;padding:28px 24px 48px}
header{background:linear-gradient(120deg,#0f3d5e,#147a8a);color:#fff;padding:26px 24px}
header h1{margin:0 0 4px;font-size:24px}header p{margin:0;opacity:.85}
section{background:#fff;border-radius:10px;padding:18px 20px;margin:18px 0;
box-shadow:0 1px 3px rgba(0,0,0,.08)}
h2{font-size:18px;margin:0 0 12px;color:#0f3d5e}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#0f3d5e;color:#fff;text-align:left;padding:6px 8px;font-weight:600}
td{padding:5px 8px;border-bottom:1px solid #e4e7eb}
tr:nth-child(even) td{background:#f8fafb}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.cards{display:flex;flex-wrap:wrap;gap:12px}
.card{flex:1 1 160px;border-left:4px solid #147a8a;background:#f8fafb;padding:10px 12px;border-radius:6px}
.card b{display:block;font-size:20px;color:#0f3d5e}.card span{font-size:12px;color:#52606d}
.note{font-size:12px;color:#52606d}img{max-width:100%;border:1px solid #e4e7eb;border-radius:6px}
footer{font-size:12px;color:#7b8794;text-align:center;margin-top:24px}
"""


def fmt(v, digits=0):
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if digits == 0:
            return format(int(round(v)), ",").replace(",", ".")
        s = ("{:,.%df}" % digits).format(v)
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    return escape(str(v))


def table(headers, rows, numeric_cols=()):
    out = ["<table><tr>"]
    out += ["<th>%s</th>" % escape(str(h)) for h in headers]
    out.append("</tr>")
    for row in rows:
        out.append("<tr>")
        for c, v in enumerate(row):
            cls = ' class="n"' if c in numeric_cols else ""
            text = v if isinstance(v, str) else fmt(v)
            out.append("<td%s>%s</td>" % (cls, text))
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def cards(items):
    return '<div class="cards">' + "".join(
        '<div class="card"><b>%s</b><span>%s</span></div>' % (v, escape(k)) for k, v in items) + "</div>"


def image(b64png, caption=""):
    if not b64png:
        return ""
    cap = '<p class="note">%s</p>' % escape(caption) if caption else ""
    return '<img alt="%s" src="data:image/png;base64,%s"/>%s' % (escape(caption), b64png, cap)


def page(title, subtitle, sections, author=""):
    body = "".join('<section><h2>%s</h2>%s</section>' % (escape(h), content)
                   for h, content in sections if content)
    stamp = datetime.date.today().strftime("%d.%m.%Y")
    return ("<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s</title><style>%s</style></head><body>"
            "<header><div class='wrap' style='padding:0'><h1>%s</h1><p>%s</p></div></header>"
            "<div class='wrap'>%s<footer>Kent Öngörü ile üretildi · %s%s</footer></div>"
            "</body></html>") % (escape(title), CSS, escape(title), escape(subtitle), body,
                                 stamp, (" · " + escape(author)) if author else "")
