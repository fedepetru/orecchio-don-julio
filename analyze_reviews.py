"""
Paso 2 del pipeline: analizar las reseñas con IA (Claude).

Hace dos cosas:
  FASE 1 - Taxonomía: a partir de una muestra, descubre los ~10 temas
           principales (con sus sub-temas), tipo "Atención" engloba
           "mozos", "sommelier", "espumante", etc.
  FASE 2 - Clasificación: por cada reseña detecta qué temas menciona y con
           qué sentimiento (positivo / negativo / neutro / mixto).

Luego agrega todo y calcula porcentajes por tema (crudo y ponderado por la
cantidad de reseñas del usuario), y guarda data/<slug>_analysis.json

Uso:
    python analyze_reviews.py don-julio

Requiere ANTHROPIC_API_KEY en el archivo .env
"""

import json
import math
import os
import sys
from collections import defaultdict

from dotenv import load_dotenv
from anthropic import Anthropic

MODEL = "claude-haiku-4-5-20251001"  # barato y rápido para clasificar
TAXONOMY_SAMPLE = 250               # cuántas reseñas se leen para definir temas
BATCH_SIZE = 20                     # reseñas por llamada en la clasificación
SENTIMENTS = ["positivo", "negativo", "neutro", "mixto"]


def load_reviews(slug: str):
    path = f"data/{slug}_reviews.json"
    if not os.path.exists(path):
        sys.exit(f"ERROR: no existe {path}. Corré primero collect_reviews.py")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # solo las que tienen texto sirven para el análisis temático
    data["reviews_con_texto"] = [r for r in data["reviews"] if r.get("texto")]
    return data


def call_json(client, prompt, max_tokens=4000):
    """Llama a Claude y parsea la respuesta como JSON."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    # quitar fences ```json ... ``` si aparecen
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# FASE 1: descubrir la taxonomía de temas
# ---------------------------------------------------------------------------
def discover_themes(client, reviews):
    sample = [r["texto"] for r in reviews[:TAXONOMY_SAMPLE]]
    joined = "\n".join(f"- {t}" for t in sample)
    prompt = f"""Sos un analista de experiencia del cliente. Abajo hay reseñas reales de un restaurante en Google Maps.

Identificá los 10 TEMAS principales y recurrentes de los que habla la gente
(ej: Calidad de la comida, Precios, Atención/Servicio, Ambiente, Tiempos de espera,
Reservas, etc). Cada tema debe ser general y agrupar sub-temas relacionados.

Devolvé SOLO un JSON con esta forma exacta:
{{
  "temas": [
    {{"nombre": "Calidad de la comida", "descripcion": "...", "palabras_clave": ["asado","carne","cortes","postre"]}},
    ...
  ]
}}

Reseñas:
{joined}
"""
    result = call_json(client, prompt)
    return result["temas"]


# ---------------------------------------------------------------------------
# FASE 2: clasificar cada reseña contra la taxonomía
# ---------------------------------------------------------------------------
def classify_batch(client, batch, temas):
    nombres = [t["nombre"] for t in temas]
    items = "\n".join(f'{i}. "{r["texto"]}"' for i, r in enumerate(batch))
    prompt = f"""Tenés esta lista de TEMAS posibles: {nombres}

Para cada reseña numerada, indicá qué temas de la lista menciona y con qué
sentimiento cada uno: "positivo", "negativo", "neutro" o "mixto".
Una reseña puede tocar varios temas. Si no menciona ninguno, devolvé lista vacía.

Devolvé SOLO un JSON:
{{
  "0": [{{"tema": "Precios", "sentimiento": "negativo"}}, ...],
  "1": [...],
  ...
}}

Reseñas:
{items}
"""
    return call_json(client, prompt, max_tokens=4000)


def weight(reviews_count):
    """Ponderación log: un usuario con muchas reseñas pesa más, sin que domine."""
    n = reviews_count or 1
    try:
        return 1.0 + math.log10(max(int(n), 1))
    except (ValueError, TypeError):
        return 1.0


def generate_examples(client, temas):
    """Genera, por cada tema, un comentario genérico ilustrativo de cada sentimiento."""
    info = [{"nombre": t["nombre"], "descripcion": t.get("descripcion", "")} for t in temas]
    prompt = f"""Para cada uno de estos temas de un restaurante, escribí un comentario genérico
y breve (1 oración) que ilustre qué se considera POSITIVO, NEGATIVO, NEUTRO y MIXTO en ese tema.
Que suenen a reseñas reales, en español rioplatense.

Temas: {json.dumps(info, ensure_ascii=False)}

Devolvé SOLO un JSON: {{ "Nombre del tema": {{"positivo": "...", "negativo": "...", "neutro": "...", "mixto": "..."}}, ... }}
"""
    try:
        return call_json(client, prompt, max_tokens=4000)
    except Exception:  # noqa: BLE001
        return {}


def generate_narratives(client, temas_out, four_star_texts, client_name):
    """Genera resumen general, resumen de 4 estrellas y conclusiones accionables."""
    resumen_temas = [
        {"tema": t["nombre"], "menciones": t["menciones"], "score": t["score_0_100"]}
        for t in temas_out
    ]
    muestra4 = "\n".join(f"- {t}" for t in four_star_texts[:60])
    nombres = [t["nombre"] for t in temas_out]
    prompt = f"""Sos consultor de experiencia del cliente y analizaste las reseñas de "{client_name}".

Resultados por tema (score 0=peor, 100=mejor): {json.dumps(resumen_temas, ensure_ascii=False)}

Reseñas de 4 estrellas (las más equilibradas y útiles):
{muestra4}

Devolvé SOLO un JSON con:
{{
  "resumen": "un párrafo (5-7 oraciones) sobre el clima general de las reseñas",
  "resumen_4_estrellas": "un párrafo sobre qué critican constructivamente quienes pusieron 4 estrellas",
  "conclusiones": [
    {{"titulo": "...", "detalle": "...", "tema_asociado": "uno de: {nombres}"}}
  ]
}}
Las conclusiones deben ser 4-6 quick wins accionables de corto plazo para subir las valoraciones.
"tema_asociado" es el tema principal que ese quick win mejoraría (elegí uno de la lista).
"""
    try:
        return call_json(client, prompt, max_tokens=3000)
    except Exception:  # noqa: BLE001
        return {}


def translate_batch(client, batch):
    """Detecta idioma y traduce al español las reseñas que no lo están."""
    items = "\n".join(f'{i}. "{r["texto"]}"' for i, r in enumerate(batch))
    prompt = f"""Para cada reseña numerada, detectá el idioma (código ISO: es, en, pt, it, fr, de, ...).
Si NO está en español, traducila al español rioplatense (natural, fiel). Si ya está en español,
devolvé "traduccion": null.

Devolvé SOLO un JSON: {{"0": {{"idioma": "en", "traduccion": "..."}}, "1": {{"idioma": "es", "traduccion": null}}, ...}}

Reseñas:
{items}
"""
    return call_json(client, prompt, max_tokens=8000)


def translate_reviews(client, reviews, batch_size=12):
    """Traduce todas las reseñas (de a tandas). Devuelve lista alineada con reviews."""
    out = [{"idioma": None, "traduccion": None} for _ in reviews]
    for start in range(0, len(reviews), batch_size):
        batch = reviews[start:start + batch_size]
        try:
            res = translate_batch(client, batch)
        except Exception as e:  # noqa: BLE001
            print(f"  (traducción tanda {start} falló: {e}; se saltea)")
            continue
        for i in range(len(batch)):
            tag = res.get(str(i)) or {}
            out[start + i] = {
                "idioma": tag.get("idioma"),
                "traduccion": (tag.get("traduccion") or None),
            }
        print(f"  traducidas {min(start + batch_size, len(reviews))}/{len(reviews)}...")
    return out


def select_real_comments(reviews, plan=None):
    """Elige comentarios reales (verbatim) variados por estrellas, para el carrusel."""
    if plan is None:
        plan = {5: 3, 4: 2, 3: 2, 2: 1, 1: 1}
    by = defaultdict(list)
    for r in reviews:
        if r.get("texto"):
            by[r.get("estrellas")].append(r)
    sel = []
    for star, n in plan.items():
        cands = [r for r in by.get(star, []) if 90 <= len(r["texto"]) <= 360]
        start = max(0, len(cands) // 3)
        for r in cands[start:start + n]:
            sel.append({
                "usuario": r.get("usuario"),
                "estrellas": r.get("estrellas"),
                "fecha": r.get("fecha"),
                "reseñas_del_usuario": r.get("reseñas_del_usuario"),
                "texto": r["texto"],
            })
    return sel


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python analyze_reviews.py <slug>   (ej: don-julio)")
    slug = sys.argv[1]

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: falta ANTHROPIC_API_KEY en el archivo .env")
    client = Anthropic(api_key=api_key)

    data = load_reviews(slug)
    reviews = data["reviews_con_texto"]
    print(f"Analizando {len(reviews)} reseñas con texto de '{data['client_name']}'\n")

    print("FASE 1: descubriendo los temas principales...")
    temas = discover_themes(client, reviews)
    print(f"  -> {len(temas)} temas: {[t['nombre'] for t in temas]}\n")

    print("FASE 2: clasificando cada reseña (de a tandas)...")
    # acumuladores: por tema -> sentimiento -> conteo (crudo y ponderado)
    counts = {t["nombre"]: {s: 0 for s in SENTIMENTS} for t in temas}
    wcounts = {t["nombre"]: {s: 0.0 for s in SENTIMENTS} for t in temas}
    menciones = defaultdict(int)
    detractores = defaultdict(int)  # reseñas con crítica negativa y < 5 estrellas (para el impacto)
    valid_themes = set(counts.keys())
    tags_por_review = [[] for _ in reviews]  # etiquetas {tema, sentimiento} de cada reseña

    for start in range(0, len(reviews), BATCH_SIZE):
        batch = reviews[start:start + BATCH_SIZE]
        try:
            res = classify_batch(client, batch, temas)
        except Exception as e:  # noqa: BLE001 - una tanda que falla no frena todo
            print(f"  (tanda {start} falló: {e}; se saltea)")
            continue
        for i, r in enumerate(batch):
            for tag in res.get(str(i), []):
                tema = tag.get("tema")
                sent = tag.get("sentimiento")
                if tema in valid_themes and sent in SENTIMENTS:
                    counts[tema][sent] += 1
                    wcounts[tema][sent] += weight(r.get("reseñas_del_usuario"))
                    menciones[tema] += 1
                    tags_por_review[start + i].append({"tema": tema, "sentimiento": sent})
                    if sent == "negativo" and (r.get("estrellas") or 5) < 5:
                        detractores[tema] += 1
        done = min(start + BATCH_SIZE, len(reviews))
        print(f"  {done}/{len(reviews)} reseñas procesadas...")

    # ---- agregación final ----
    def pcts(d):
        total = sum(d.values()) or 1
        return {s: round(100 * d[s] / total, 1) for s in SENTIMENTS}

    def score(p):  # 0 (peor) a 100 (mejor): pos=1, mixto=0.5, neutro=0.5, neg=0
        return round(p["positivo"] + 0.5 * (p["mixto"] + p["neutro"]), 1)

    print("\nTraduciendo al español las reseñas en otros idiomas (de a tandas)...")
    traducciones = translate_reviews(client, reviews)

    # Datos por reseña (para que el dashboard filtre y recalcule en vivo)
    reviews_clasificadas = []
    for r, tags, tr in zip(reviews, tags_por_review, traducciones):
        reviews_clasificadas.append({
            "fecha": r.get("fecha"),
            "estrellas": r.get("estrellas"),
            "usuario": r.get("usuario"),
            "reseñas_del_usuario": r.get("reseñas_del_usuario"),
            "texto": r.get("texto"),
            "idioma": tr.get("idioma"),
            "traduccion": tr.get("traduccion"),
            "tags": tags,
        })

    print("\nGenerando ejemplos por tema y textos narrativos...")
    ejemplos = generate_examples(client, temas)

    temas_out = []
    for t in sorted(temas, key=lambda x: menciones[x["nombre"]], reverse=True):
        name = t["nombre"]
        p = pcts(counts[name])
        wp = pcts(wcounts[name])
        temas_out.append({
            "nombre": name,
            "descripcion": t.get("descripcion", ""),
            "palabras_clave": t.get("palabras_clave", []),
            "menciones": menciones[name],
            "sentimiento_pct": p,
            "sentimiento_pct_ponderado": wp,
            "score_0_100": score(p),
            "score_0_100_ponderado": score(wp),
            "ejemplos": ejemplos.get(name, {}),
        })

    # Distribución de reseñas por estrellas (sobre las analizadas, con texto)
    dist = {str(s): 0 for s in range(1, 6)}
    for r in reviews:
        s = r.get("estrellas")
        if s in (1, 2, 3, 4, 5):
            dist[str(s)] += 1

    # Rating promedio de las reseñas analizadas
    estrellas = [r["estrellas"] for r in reviews if isinstance(r.get("estrellas"), int)]
    n = len(estrellas) or 1
    rating_prom = round(sum(estrellas) / n, 2)

    # Resumen general, resumen de 4 estrellas y conclusiones
    four_star_texts = [r["texto"] for r in reviews if r.get("estrellas") == 4]
    narr = generate_narratives(client, temas_out, four_star_texts, data["client_name"])

    # Impacto estimado por conclusión: +1 estrella a los detractores del tema asociado
    conclusiones = narr.get("conclusiones", [])
    for c in conclusiones:
        d = detractores.get(c.get("tema_asociado"), 0)
        delta = round(d / n, 2)
        c["impacto_delta"] = delta
        c["impacto_estimado"] = f"+{delta:.2f} ★"
    conclusiones.sort(key=lambda x: x.get("impacto_delta", 0), reverse=True)

    nota = (
        f"Impacto estimado = cuánto subiría el rating promedio de las {n} reseñas analizadas "
        f"(hoy {rating_prom} ★) si quienes criticaron ese punto hubieran sumado +1 estrella. "
        "Son estimaciones independientes y NO sumables: una misma reseña suele criticar varias cosas."
    )

    fechas = [r["fecha"] for r in reviews if r.get("fecha")]
    out = {
        "client_name": data["client_name"],
        "place_name": data.get("place_name"),
        "rating_global": data.get("rating_global"),
        "total_reviews_en_google": data.get("total_reviews_en_google"),
        "reviews_analizadas": len(reviews),
        "rating_promedio_analizadas": rating_prom,
        "fecha_referencia": max(fechas) if fechas else None,
        "distribucion_estrellas": dist,
        "resumen": narr.get("resumen", ""),
        "resumen_4_estrellas": narr.get("resumen_4_estrellas", ""),
        "conclusiones_nota": nota,
        "conclusiones": conclusiones,
        "temas": temas_out,
        "reviews_clasificadas": reviews_clasificadas,
    }
    out_path = f"data/{slug}_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\nListo. Análisis guardado en {out_path}")
    print("\nResumen (tema -> menciones -> score 0-100):")
    for t in temas_out:
        print(f"  {t['nombre']:<28} {t['menciones']:>4} menciones   score {t['score_0_100']}")


if __name__ == "__main__":
    main()
