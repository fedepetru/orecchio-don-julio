"""
Paso 1 del pipeline: colectar reseñas de Google Maps via Outscraper.

Uso:
    python collect_reviews.py

Configurá el comercio en CONFIG (más abajo). El resultado crudo se guarda en
data/raw/<slug>_raw.json y una versión normalizada en data/<slug>_reviews.json
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from outscraper import OutscraperClient

# ----------------------------------------------------------------------------
# CONFIG: lo único que se cambia por cada cliente
# ----------------------------------------------------------------------------
CONFIG = {
    "client_name": "Don Julio",
    # Puede ser el nombre+dirección, una URL de Google Maps, o un place_id.
    "query": "Don Julio, Guatemala 4699, C1425 Palermo, Buenos Aires, Argentina",
    "reviews_limit": 1000,   # cuántas reseñas bajar (prueba = 1000)
    "sort": "newest",        # newest | most_relevant | highest_rating | lowest_rating
    "language": "es",
}
# ----------------------------------------------------------------------------


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def normalize_review(r: dict) -> dict:
    """Extrae solo los campos que nos importan para el análisis."""
    ts = r.get("review_timestamp")
    fecha = None
    if ts:
        try:
            fecha = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            fecha = None
    if not fecha:
        fecha = r.get("review_datetime_utc")

    # Limpiar saltos HTML (<br>) y espacios redundantes del texto
    texto = re.sub(r"<br\s*/?>", " ", r.get("review_text") or "", flags=re.IGNORECASE)
    texto = re.sub(r"\s+", " ", texto).strip()

    return {
        "review_id": r.get("review_id"),
        "fecha": fecha,
        "usuario": r.get("author_title"),
        "author_id": r.get("author_id"),
        "estrellas": r.get("review_rating"),
        # 'local guide' y cantidad de reseñas previas del usuario:
        "es_local_guide": r.get("author_local_guide") or r.get("is_local_guide"),
        "reseñas_del_usuario": r.get("author_reviews_count"),
        "texto": texto,
        "likes": r.get("review_likes"),
        "respuesta_dueño": (r.get("owner_answer") or "").strip() or None,
    }


def main():
    load_dotenv()
    api_key = os.getenv("OUTSCRAPER_API_KEY")
    if not api_key:
        sys.exit("ERROR: falta OUTSCRAPER_API_KEY en el archivo .env")

    client = OutscraperClient(api_key=api_key)
    slug = slugify(CONFIG["client_name"])
    os.makedirs("data/raw", exist_ok=True)

    print(f"Colectando hasta {CONFIG['reviews_limit']} reseñas de '{CONFIG['client_name']}'...")
    print("(esto puede tardar varios minutos; Outscraper procesa de a tandas)\n")

    results = client.google_maps_reviews(
        CONFIG["query"],
        reviews_limit=CONFIG["reviews_limit"],
        limit=1,                       # un solo comercio
        sort=CONFIG["sort"],
        language=CONFIG["language"],
        async_request=False,           # esperar el resultado completo
    )

    # results es una lista de lugares; tomamos el primero
    if not results:
        sys.exit("ERROR: no se obtuvieron resultados. Revisá el query o el crédito de la API.")

    place = results[0]
    reviews = place.get("reviews_data", []) or []

    # Guardar crudo (todo lo que devolvió Outscraper)
    raw_path = f"data/raw/{slug}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(place, f, ensure_ascii=False, indent=2)

    # Guardar normalizado
    normalized = [normalize_review(r) for r in reviews]
    norm_path = f"data/{slug}_reviews.json"
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "client_name": CONFIG["client_name"],
                "place_name": place.get("name"),
                "place_address": place.get("full_address"),
                "rating_global": place.get("rating"),
                "total_reviews_en_google": place.get("reviews"),
                "reviews_colectadas": len(normalized),
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "reviews": normalized,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Resumen
    con_texto = sum(1 for r in normalized if r["texto"])
    print("=" * 60)
    print(f"Comercio:           {place.get('name')}")
    print(f"Dirección:          {place.get('full_address')}")
    print(f"Rating global:      {place.get('rating')}  ({place.get('reviews')} reseñas en Google)")
    print(f"Reseñas colectadas: {len(normalized)}  (con texto: {con_texto})")
    print(f"Crudo guardado en:  {raw_path}")
    print(f"Normalizado en:     {norm_path}")
    print("=" * 60)
    if normalized:
        print("\nCampos disponibles en una reseña de muestra:")
        print(json.dumps(reviews[0], ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    main()
