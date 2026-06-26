"""
Orecchio — app web. Pegás un link de Google Maps y genera el reporte.

Local:   streamlit run app.py   (lee las claves del archivo .env)
Cloud:   Streamlit Community Cloud, con las claves cargadas en "Secrets".

Secrets / variables necesarias:
    OUTSCRAPER_API_KEY, ANTHROPIC_API_KEY, APP_PASSWORD, REVIEW_CAP (opcional, def. 100)
"""

import os

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

import pipeline

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

st.set_page_config(page_title="Orecchio — Análisis de reseñas", page_icon="👂", layout="wide")


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

if st.button("Generar reporte", type="primary"):
    if not url.strip():
        st.warning("Pegá un link de Google Maps primero.")
        st.stop()

    prog = st.progress(0.0, text="Iniciando...")

    def cb(msg, frac=None):
        prog.progress(min(max(frac or 0.5, 0.0), 1.0), text=msg)

    try:
        cb("Colectando reseñas desde Google Maps...", 0.05)
        meta, reviews = pipeline.collect(url.strip(), OUTSCRAPER_KEY, reviews_limit=n)
        nombre = meta.get("place_name") or "Negocio"
        cb(f"{len(reviews)} reseñas colectadas de «{nombre}». Analizando...", 0.15)
        analysis = pipeline.analyze(reviews, nombre, meta, ANTHROPIC_KEY, progress=cb)
        cb("Generando el tablero...", 0.97)
        html = pipeline.build_html(analysis)
        prog.empty()
    except Exception as e:  # noqa: BLE001
        prog.empty()
        st.error(f"Hubo un error: {e}")
        st.stop()

    st.success(f"✅ {analysis['reviews_analizadas']} reseñas analizadas de «{analysis.get('place_name')}»")
    components.html(html, height=900, scrolling=True)
    st.download_button("⬇️ Descargar el tablero (HTML)", data=html,
                       file_name="dashboard.html", mime="text/html")
