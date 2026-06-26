# Orecchio — Análisis de reseñas de Google Maps para comercios

Orecchio es un servicio de consultoría para comercios (restaurantes, hoteles, bares, etc.)
que convierte **miles de reseñas de Google Maps** en inteligencia accionable: detecta
automáticamente los temas de los que habla la gente y mide el **sentimiento por tema**, para
que el dueño sepa qué conservar y qué mejorar sin tener que leer todas las reseñas.

> Un comercio como la parrilla **Don Julio** (Palermo, Buenos Aires) tiene ~19.000 reseñas:
> imposible leerlas todas. Orecchio las procesa y las resume en un tablero.

## Cómo funciona (pipeline de 3 pasos)

```
collect_reviews.py   →   analyze_reviews.py   →   build_dashboard.py
   (Outscraper)            (Claude / IA)            (HTML estático)
```

1. **`collect_reviews.py`** — baja todas las reseñas de un comercio vía la API de
   [Outscraper](https://outscraper.com) (fecha, usuario, estrellas, nº de reseñas del
   usuario, texto). Guarda crudo + normalizado en `data/`.
2. **`analyze_reviews.py`** — con la API de **Claude** (modelo Haiku): primero descubre
   los ~10 temas recurrentes y luego clasifica cada reseña (qué temas menciona y con qué
   sentimiento: positivo / negativo / neutro / mixto), procesando de a tandas para escalar
   a decenas de miles de reseñas. Pondera por la cantidad de reseñas del usuario. Genera
   resumen, conclusiones accionables (con impacto estimado), distribución de estrellas y
   un set de comentarios reales.
3. **`build_dashboard.py`** — arma un tablero HTML autocontenido (sin dependencias) con:
   nube de temas, resumen, carrusel de comentarios reales, distribución por estrellas,
   sentimiento por tema (con ejemplos al pasar el mouse) y conclusiones priorizadas.

## Caso de ejemplo: Don Julio

El tablero generado está en **`dashboard_don-julio.html`** (abrir con doble clic).
Análisis sobre 721 reseñas con texto. Hallazgos principales:

| Tema | Menciones | Score (0–100) |
|---|---|---|
| Postres y bebidas | 190 | 87 |
| Recepción y bienvenida | 98 | 85 |
| Calidad de la carne | 527 | 81 |
| Atención y servicio | 477 | 76 |
| Precios y valor | 186 | **25** ← principal dolor |

## App web (Streamlit)

Además del pipeline por línea de comandos, hay una **app web** (`app.py`): se pega el
link de Google Maps de un negocio y genera el reporte solo. Tiene contraseña de acceso y
un tope de reseñas por análisis para controlar el costo.

```bash
pip install -r requirements.txt
streamlit run app.py     # lee las claves del .env
```

**Deploy en Streamlit Community Cloud:** conectar este repo en https://share.streamlit.io,
archivo principal `app.py`, y cargar en *Secrets*: `OUTSCRAPER_API_KEY`, `ANTHROPIC_API_KEY`,
`APP_PASSWORD` y `REVIEW_CAP`.

## Cómo correr el pipeline por CLI

```bash
pip install -r requirements.txt
# crear un archivo .env con las claves (ver abajo)
python collect_reviews.py            # configurar el comercio dentro del script
python analyze_reviews.py don-julio
python build_dashboard.py don-julio
```

### Variables de entorno (`.env`)

El archivo `.env` **no se versiona** (está en `.gitignore`). Crear uno con:

```
OUTSCRAPER_API_KEY=tu_clave_de_outscraper
ANTHROPIC_API_KEY=tu_clave_de_anthropic
```

## Notas

- Los datos crudos scrapeados (`data/don-julio_reviews.json`, `data/raw/`) no se incluyen
  en el repo. Sí se incluye el análisis agregado (`data/don-julio_analysis.json`) y el
  tablero final.
- El "impacto estimado" de cada conclusión simula sumar +1 estrella a quienes criticaron
  ese punto, para priorizar los quick wins de forma cuantificable.

## Estado

Prueba de concepto funcionando end-to-end. Próximos pasos: escalar a la totalidad de las
reseñas y agregar login multi-cliente para que cada comercio acceda a su propio tablero.
