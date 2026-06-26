"""
Genera un PDF del reporte a partir del dict de análisis.

Usa fpdf2 con fuentes core (latin-1): el contenido es en español, y para las reseñas
en otros idiomas se usa la traducción. Se sanitiza el texto para evitar errores de fuente.

    from pdf_report import build_pdf
    pdf_bytes = build_pdf(analysis)
"""

import re
from datetime import date

from fpdf import FPDF
from fpdf.enums import XPos, YPos

SENT_LBL = {"positivo": "POSITIVO", "negativo": "NEGATIVO", "neutro": "NEUTRO", "mixto": "MIXTO"}
_REPL = {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-",
         "—": "-", "…": "...", " ": " ", "★": "*", "•": "-",
         "«": '"', "»": '"'}


def _l1(s):
    """Deja el texto compatible con latin-1 (fuentes core de fpdf2)."""
    s = re.sub(r"<br\s*/?>", " ", str(s or ""), flags=re.IGNORECASE)
    for k, v in _REPL.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "ignore").decode("latin-1")


def _w(pdf, text, size=10, style="", color=0, h=5):
    """Escribe un bloque y vuelve al margen izquierdo (evita el error de espacio)."""
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(color)
    try:
        pdf.multi_cell(0, h, _l1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    except Exception:  # noqa: BLE001 - texto raro: lo saltea sin romper el PDF
        pass
    pdf.set_text_color(0)


def _heading(pdf, text):
    pdf.ln(2)
    _w(pdf, text, size=13, style="B", color=20, h=7)


def _theme_comments(revs, theme, k):
    groups = {"negativo": [], "positivo": [], "mixto": [], "neutro": []}
    for r in revs:
        for t in (r.get("tags") or []):
            if t.get("tema") == theme and t.get("sentimiento") in groups:
                groups[t["sentimiento"]].append({**r, "_sent": t["sentimiento"]})
    for g in groups.values():
        g.sort(key=lambda r: len(r.get("texto") or ""), reverse=True)
    out, order, added = [], ["negativo", "positivo", "mixto", "neutro"], True
    while len(out) < k and added:
        added = False
        for s in order:
            if groups[s] and len(out) < k:
                out.append(groups[s].pop(0))
                added = True
    return out


def build_pdf(analysis: dict) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Encabezado
    _w(pdf, analysis.get("client_name", "Reporte"), size=20, style="B", h=9)
    _w(pdf, f"Reporte de reseñas de Google Maps - Generado el {date.today().strftime('%d/%m/%Y')}",
       size=11, color=110, h=6)
    if analysis.get("place_name"):
        _w(pdf, analysis["place_name"], size=11, color=110, h=6)
    pdf.ln(2)
    _w(pdf, f"Rating global (Google): {analysis.get('rating_global', '-')}    |    "
            f"Reseñas analizadas: {analysis.get('reviews_analizadas', '-')}    |    "
            f"Rating promedio: {analysis.get('rating_promedio_analizadas', '-')}", size=11, h=6)

    # Resumen
    if analysis.get("resumen"):
        _heading(pdf, "Resumen")
        _w(pdf, analysis["resumen"])

    # Distribución por estrellas
    dist = analysis.get("distribucion_estrellas", {})
    tot = sum(int(v) for v in dist.values()) or 1
    _heading(pdf, "Distribución por estrellas")
    for s in ["5", "4", "3", "2", "1"]:
        v = int(dist.get(s, 0))
        _w(pdf, f"{s} estrellas: {v} reseñas ({100 * v / tot:.1f}%)")

    # Sentimiento por tema + comentarios
    revs = analysis.get("reviews_clasificadas", [])
    _heading(pdf, "Sentimiento por tema")
    for t in analysis.get("temas", []):
        p = t.get("sentimiento_pct", {})
        pdf.ln(1)
        _w(pdf, f"{t['nombre']}  (menciones: {t.get('menciones', 0)} - score {t.get('score_0_100', '-')}/100)",
           size=11, style="B", h=6)
        _w(pdf, f"Positivo {p.get('positivo', 0)}%  -  Mixto {p.get('mixto', 0)}%  -  "
                f"Neutro {p.get('neutro', 0)}%  -  Negativo {p.get('negativo', 0)}%", size=9, color=110)
        for c in _theme_comments(revs, t["nombre"], 3):
            txt = c.get("traduccion") or c.get("texto") or ""
            _w(pdf, f"[{SENT_LBL.get(c['_sent'], '')}]", size=8, style="B")
            _w(pdf, f'"{txt}"', size=9)

    # Puntos a mejorar
    _heading(pdf, "Puntos a mejorar (sub-temas negativos más mencionados)")
    subs = (analysis.get("subtemas_negativos") or [])[:5]
    if subs:
        for i, s in enumerate(subs, 1):
            _w(pdf, f"{i}. {s.get('subtema', '')}  ({s.get('menciones', 0)} menciones)")
    else:
        _w(pdf, "Sin sub-temas negativos relevantes.")

    # 4 estrellas
    if analysis.get("resumen_4_estrellas"):
        _heading(pdf, "4 estrellas: la crítica más honesta")
        _w(pdf, analysis["resumen_4_estrellas"])

    return bytes(pdf.output())
