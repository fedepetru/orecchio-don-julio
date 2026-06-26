"""
Pipeline reutilizable: colectar -> analizar -> construir HTML.

Reúne la lógica de collect_reviews.py / analyze_reviews.py / build_dashboard.py en
funciones llamables desde la app web (app.py) o desde código.

Funciones:
    collect(query, outscraper_key, reviews_limit, ...) -> (meta, reviews_normalizadas)
    analyze(reviews_normalizadas, client_name, meta, anthropic_key, progress) -> dict
    build_html(analysis) -> str (HTML del dashboard)
"""

import json
from collections import defaultdict
from datetime import datetime, timezone

import requests
from outscraper import OutscraperClient
from anthropic import Anthropic

import analyze_reviews as AR
from collect_reviews import normalize_review
from build_dashboard import TEMPLATE

SENTIMENTS = AR.SENTIMENTS


# ---------------------------------------------------------------------------
# 1) COLECCIÓN
# ---------------------------------------------------------------------------
def _expand_url(query: str) -> str:
    """Sigue los redirects de los links cortos de Google Maps (maps.app.goo.gl)."""
    q = query.strip()
    if q.startswith("http"):
        try:
            r = requests.get(q, allow_redirects=True, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            return r.url or q
        except requests.RequestException:
            return q
    return q


def collect(query, outscraper_key, reviews_limit=100, sort="newest", language="es"):
    client = OutscraperClient(api_key=outscraper_key)
    q = _expand_url(query)
    results = client.google_maps_reviews(
        q, reviews_limit=reviews_limit, limit=1, sort=sort,
        language=language, async_request=False,
    )
    if not results:
        raise RuntimeError("No se encontró el negocio. Probá con el link completo o el nombre.")
    place = results[0]
    reviews = place.get("reviews_data", []) or []
    normalized = [normalize_review(r) for r in reviews]
    meta = {
        "place_name": place.get("name"),
        "full_address": place.get("full_address"),
        "rating": place.get("rating"),
        "reviews": place.get("reviews"),
    }
    return meta, normalized


# ---------------------------------------------------------------------------
# 2) ANÁLISIS  (misma lógica que analyze_reviews.main, con callback de progreso)
# ---------------------------------------------------------------------------
def _pcts(d):
    total = sum(d.values()) or 1
    return {s: round(100 * d[s] / total, 1) for s in SENTIMENTS}


def _score(p):
    return round(p["positivo"] + 0.5 * (p["mixto"] + p["neutro"]), 1)


def analyze(reviews_normalizadas, client_name, meta, anthropic_key, progress=None):
    def say(msg, frac=None):
        if progress:
            progress(msg, frac)

    reviews = [r for r in reviews_normalizadas if r.get("texto")]
    if not reviews:
        raise RuntimeError("El negocio no tiene reseñas con texto para analizar.")

    client = Anthropic(api_key=anthropic_key)

    say("Descubriendo los temas principales...", 0.12)
    temas = AR.discover_themes(client, reviews)

    counts = {t["nombre"]: {s: 0 for s in SENTIMENTS} for t in temas}
    wcounts = {t["nombre"]: {s: 0.0 for s in SENTIMENTS} for t in temas}
    menciones = defaultdict(int)
    detractores = defaultdict(int)
    valid = set(counts.keys())
    tags_por_review = [[] for _ in reviews]

    total_batches = max(1, (len(reviews) + AR.BATCH_SIZE - 1) // AR.BATCH_SIZE)
    for bi, start in enumerate(range(0, len(reviews), AR.BATCH_SIZE)):
        batch = reviews[start:start + AR.BATCH_SIZE]
        try:
            res = AR.classify_batch(client, batch, temas)
        except Exception:  # noqa: BLE001
            res = {}
        for i, r in enumerate(batch):
            for tag in res.get(str(i), []):
                tema, sent = tag.get("tema"), tag.get("sentimiento")
                if tema in valid and sent in SENTIMENTS:
                    counts[tema][sent] += 1
                    wcounts[tema][sent] += AR.weight(r.get("reseñas_del_usuario"))
                    menciones[tema] += 1
                    tags_por_review[start + i].append({"tema": tema, "sentimiento": sent})
                    if sent == "negativo" and (r.get("estrellas") or 5) < 5:
                        detractores[tema] += 1
        say(f"Clasificando reseñas ({min(start + AR.BATCH_SIZE, len(reviews))}/{len(reviews)})...",
            0.15 + 0.45 * (bi + 1) / total_batches)

    say("Traduciendo reseñas en otros idiomas...", 0.62)
    traducciones = AR.translate_reviews(client, reviews)

    reviews_clasificadas = []
    for r, tags, tr in zip(reviews, tags_por_review, traducciones):
        reviews_clasificadas.append({
            "fecha": r.get("fecha"), "estrellas": r.get("estrellas"),
            "usuario": r.get("usuario"), "reseñas_del_usuario": r.get("reseñas_del_usuario"),
            "texto": r.get("texto"), "idioma": tr.get("idioma"),
            "traduccion": tr.get("traduccion"), "tags": tags,
        })

    say("Generando ejemplos y textos del informe...", 0.88)
    ejemplos = AR.generate_examples(client, temas)

    temas_out = []
    for t in sorted(temas, key=lambda x: menciones[x["nombre"]], reverse=True):
        name = t["nombre"]
        p, wp = _pcts(counts[name]), _pcts(wcounts[name])
        temas_out.append({
            "nombre": name, "descripcion": t.get("descripcion", ""),
            "palabras_clave": t.get("palabras_clave", []), "menciones": menciones[name],
            "sentimiento_pct": p, "sentimiento_pct_ponderado": wp,
            "score_0_100": _score(p), "score_0_100_ponderado": _score(wp),
            "ejemplos": ejemplos.get(name, {}),
        })

    dist = {str(s): 0 for s in range(1, 6)}
    for r in reviews:
        if r.get("estrellas") in (1, 2, 3, 4, 5):
            dist[str(r["estrellas"])] += 1

    estrellas = [r["estrellas"] for r in reviews if isinstance(r.get("estrellas"), int)]
    n = len(estrellas) or 1
    rating_prom = round(sum(estrellas) / n, 2)

    four_star = [r["texto"] for r in reviews if r.get("estrellas") == 4]
    narr = AR.generate_narratives(client, temas_out, four_star, client_name)

    conclusiones = narr.get("conclusiones", [])
    for c in conclusiones:
        delta = round(detractores.get(c.get("tema_asociado"), 0) / n, 2)
        c["impacto_delta"] = delta
        c["impacto_estimado"] = f"+{delta:.2f} ★"
    conclusiones.sort(key=lambda x: x.get("impacto_delta", 0), reverse=True)

    nota = (f"Impacto estimado = cuánto subiría el rating promedio de las {n} reseñas analizadas "
            f"(hoy {rating_prom} ★) si quienes criticaron ese punto hubieran sumado +1 estrella. "
            "Son estimaciones independientes y NO sumables.")

    fechas = [r["fecha"] for r in reviews if r.get("fecha")]
    say("Listo.", 1.0)
    return {
        "client_name": client_name,
        "place_name": meta.get("place_name") or client_name,
        "rating_global": meta.get("rating"),
        "total_reviews_en_google": meta.get("reviews"),
        "reviews_analizadas": len(reviews),
        "rating_promedio_analizadas": rating_prom,
        "fecha_referencia": max(fechas) if fechas else None,
        "modo": "Generado en vivo desde Google Maps",
        "distribucion_estrellas": dist,
        "resumen": narr.get("resumen", ""),
        "resumen_4_estrellas": narr.get("resumen_4_estrellas", ""),
        "conclusiones_nota": nota,
        "conclusiones": conclusiones,
        "temas": temas_out,
        "reviews_clasificadas": reviews_clasificadas,
    }


# ---------------------------------------------------------------------------
# 3) HTML
# ---------------------------------------------------------------------------
def build_html(analysis: dict) -> str:
    return TEMPLATE.replace("__DATA__", json.dumps(analysis, ensure_ascii=False))
