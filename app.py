"""
Orecchio — app web. Pegás un link de Google Maps y genera el reporte.

Local:   streamlit run app.py   (lee las claves del archivo .env)
Cloud:   Streamlit Community Cloud, con las claves cargadas en "Secrets".

Secrets / variables necesarias:
    OUTSCRAPER_API_KEY, ANTHROPIC_API_KEY, APP_PASSWORD, REVIEW_CAP (opcional, def. 100)
"""

import os
from datetime import date

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

import pipeline
import pdf_report

load_dotenv()


def secret(key, default=""):
    """Lee de st.secrets (Cloud) o de variables de entorno / .env (local)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:  # noqa: BLE001 - st.secrets no existe si no hay secrets.toml
        pass
    return os.getenv(key, default)


OUTSCRAPER_KEY = secret("OUTSCRAPER_API_KEY")
ANTHROPIC_KEY = secret("ANTHROPIC_API_KEY")
APP_PASSWORD = secret("APP_PASSWORD")
REVIEW_CAP = int(secret("REVIEW_CAP", "100") or "100")
MAX_TRIES = int(secret("MAX_TRIES", "3") or "3")        # pruebas por sesión (demo)
GLOBAL_CAP = int(secret("GLOBAL_CAP", "200") or "200")  # tope global de la demo (backstop de costo)

st.set_page_config(page_title="Orecchio — Análisis de reseñas", page_icon="👂", layout="wide")


@st.cache_resource
def _global_usage():
    """Contador global compartido entre sesiones (se reinicia si la app se reinicia)."""
    return {"n": 0}


# ---- Contraseña ----
def check_password():
    if not APP_PASSWORD:
        return True  # sin contraseña configurada -> acceso libre
    if st.session_state.get("auth"):
        return True
    st.title("👂 Orecchio")
    st.caption("Análisis de reseñas de Google Maps")
    pw = st.text_input("Contraseña de acceso", type="password")
    if st.button("Entrar"):
        if pw == APP_PASSWORD:
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


if not check_password():
    st.stop()


# ---- App ----
st.title("👂 Orecchio")
st.subheader("Convertí las reseñas de Google Maps en un reporte accionable")
st.write("Pegá el **link de Google Maps** de un negocio (o su nombre) y generá el análisis de temas y sentimiento.")

if not OUTSCRAPER_KEY or not ANTHROPIC_KEY:
    st.error("Faltan las API keys en el servidor. Configurá OUTSCRAPER_API_KEY y ANTHROPIC_API_KEY.")
    st.stop()

url = st.text_input("Link de Google Maps", placeholder="https://maps.app.goo.gl/...  (o el nombre del negocio)")
n = st.slider("Cantidad de reseñas a analizar", min_value=30, max_value=REVIEW_CAP,
              value=min(100, REVIEW_CAP), step=10,
              help="Más reseñas = análisis más completo, pero más lento y costoso.")

st.caption(f"⏱️ El análisis tarda ~1-2 minutos. Tope: {REVIEW_CAP} reseñas por corrida.")

# ---- Límite de uso (demo) ----
if "uses" not in st.session_state:
    st.session_state["uses"] = 0
restantes = max(0, MAX_TRIES - st.session_state["uses"])
gusage = _global_usage()
demo_cerrada = gusage["n"] >= GLOBAL_CAP

if restantes > 0:
    st.info(f"🧪 Te quedan **{restantes}** prueba(s) de un total de **{MAX_TRIES}** a modo de demostración.")
else:
    st.warning(f"Alcanzaste el límite de **{MAX_TRIES}** pruebas de la demostración. ¡Gracias por probar Orecchio!")
if demo_cerrada:
    st.error("La demo alcanzó su cupo de uso por ahora. Probá más tarde.")

if st.button("Generar reporte", type="primary", disabled=(restantes <= 0 or demo_cerrada)):
    if not url.strip():
        st.warning("Pegá un link de Google Maps primero.")
        st.stop()

    # cuenta este intento (protege el costo)
    st.session_state["uses"] += 1
    gusage["n"] += 1

    prog = st.progress(0.0, text="Iniciando...")

    def cb(msg, frac=None):
        prog.progress(min(max(frac or 0.5, 0.0), 1.0), text=msg)

    try:
        cb("Colectando reseñas desde Google Maps...", 0.05)
        meta, reviews = pipeline.collect(url.strip(), OUTSCRAPER_KEY, reviews_limit=n, progress=cb)
        nombre = meta.get("place_name") or "Negocio"
        cb(f"{len(reviews)} reseñas colectadas de «{nombre}». Analizando...", 0.15)
        analysis = pipeline.analyze(reviews, nombre, meta, ANTHROPIC_KEY, progress=cb)
        cb("Generando el tablero y el PDF...", 0.97)
        html = pipeline.build_html(analysis)
        pdf_bytes = pdf_report.build_pdf(analysis)
        prog.empty()
    except Exception as e:  # noqa: BLE001
        prog.empty()
        st.error(f"Hubo un error: {e}")
        st.stop()

    st.session_state["result"] = {
        "html": html, "pdf": pdf_bytes,
        "nombre": analysis.get("place_name"), "n": analysis["reviews_analizadas"],
        "quedan": max(0, MAX_TRIES - st.session_state["uses"]),
    }

# ---- Resultado (persiste entre interacciones, p.ej. al descargar) ----
res = st.session_state.get("result")
if res:
    slug = "".join(c if c.isalnum() else "-" for c in (res["nombre"] or "reporte").lower()).strip("-")
    fecha = date.today().strftime("%Y-%m-%d")
    st.success(f"✅ {res['n']} reseñas analizadas de «{res['nombre']}»")
    st.caption(f"🧪 Te quedan {res['quedan']} prueba(s) de {MAX_TRIES} a modo de demostración.")
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Descargar PDF", data=res["pdf"],
                       file_name=f"reporte-{slug}-{fecha}.pdf", mime="application/pdf")
    c2.download_button("⬇️ Descargar tablero (HTML)", data=res["html"],
                       file_name=f"reporte-{slug}-{fecha}.html", mime="text/html")
    components.html(res["html"], height=900, scrolling=True)
