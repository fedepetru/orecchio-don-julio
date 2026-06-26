"""
Paso 3 del pipeline: generar el dashboard HTML a partir del análisis.

Uso:
    python build_dashboard.py don-julio

El tablero recibe los datos POR RESEÑA (fecha, estrellas, tema+sentimiento, traducción)
y recalcula todo en el navegador según los filtros de fecha y estrellas.
"""

import json
import os
import sys

TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tablero de reseñas</title>
<style>
  :root { --bg:#0f1115; --card:#181b22; --card2:#1f2330; --txt:#e8eaed; --muted:#9aa0aa;
          --pos:#2ecc71; --neg:#e74c3c; --neu:#95a5a6; --mix:#f1c40f; --accent:#e67e22; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--txt); }
  .wrap { max-width:1100px; margin:0 auto; padding:32px 20px 90px; }
  h1 { margin:0 0 4px; font-size:28px; }
  .sub { color:var(--muted); margin-bottom:16px; }
  .badge { display:inline-block; background:var(--card2); color:var(--muted); font-size:12px;
           padding:3px 10px; border-radius:20px; }
  /* filtros */
  .filters { position:sticky; top:0; z-index:50; background:rgba(15,17,21,.92); backdrop-filter:blur(6px);
             padding:14px 0; margin:14px 0 8px; border-bottom:1px solid #23262e; }
  .frow { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:5px 0; }
  .flabel { color:var(--muted); font-size:13px; width:80px; }
  .chip { background:var(--card2); color:var(--txt); border:1px solid transparent; border-radius:20px;
          padding:5px 12px; cursor:pointer; font-size:13px; user-select:none; }
  .chip:hover { border-color:var(--accent); }
  .chip.active { background:var(--accent); color:#0a0a0a; font-weight:700; }
  .stats { display:flex; gap:16px; flex-wrap:wrap; margin:18px 0 8px; }
  .stat { background:var(--card); border-radius:12px; padding:16px 20px; flex:1; min-width:150px; }
  .stat .n { font-size:26px; font-weight:700; }
  .stat .l { color:var(--muted); font-size:13px; }
  h2 { font-size:19px; margin:34px 0 14px; }
  .card { background:var(--card); border-radius:12px; padding:20px 22px; }
  .cloud { display:flex; flex-wrap:wrap; gap:14px 22px; align-items:center; justify-content:center; min-height:60px; }
  .cloud span { line-height:1; cursor:default; }
  p.resumen { line-height:1.6; margin:0; font-size:15px; }
  /* distribución de estrellas */
  .star-row { display:flex; align-items:center; gap:12px; margin:8px 0; }
  .star-lbl { width:48px; text-align:right; color:var(--muted); font-size:14px; white-space:nowrap; }
  .star-track { flex:1; background:#11141a; border-radius:6px; height:24px; overflow:hidden; }
  .star-fill { height:100%; border-radius:6px; }
  .star-val { width:140px; font-size:13px; color:var(--muted); }
  /* temas */
  .theme { background:var(--card); border-radius:12px; padding:16px 20px; margin-bottom:12px; cursor:pointer; }
  .theme:hover { outline:1px solid #2a2f3a; }
  .theme-head { display:flex; justify-content:space-between; align-items:baseline; gap:8px; flex-wrap:wrap; }
  .theme-name { font-size:17px; font-weight:600; }
  .theme-desc { color:var(--muted); font-size:13px; margin:2px 0 10px; }
  .theme-meta { color:var(--muted); font-size:13px; }
  .score { font-weight:700; font-size:18px; }
  .bar { display:flex; height:22px; border-radius:6px; overflow:hidden; background:#222; }
  .bar > div { display:flex; align-items:center; justify-content:center; font-size:11px; color:#0a0a0a; font-weight:700; }
  .kw { color:var(--muted); font-size:12px; margin-top:8px; }
  .legend { display:flex; gap:18px; flex-wrap:wrap; margin:6px 0 16px; font-size:13px; color:var(--muted); }
  .legend i { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:middle; }
  .hint { color:var(--muted); font-size:12px; font-style:italic; }
  .empty { color:var(--muted); font-style:italic; padding:8px 0; }
  /* carrusel */
  .carousel { position:relative; }
  .car-stars { color:var(--mix); font-size:17px; letter-spacing:3px; }
  .car-text { font-size:15.5px; line-height:1.6; margin:12px 0 4px; }
  .car-trad { font-size:14px; line-height:1.55; color:var(--muted); border-left:2px solid var(--accent);
              padding-left:10px; margin:8px 0; }
  .car-trad b { color:var(--txt); font-weight:600; }
  .car-meta { color:var(--muted); font-size:13px; margin-top:8px; }
  .car-nav { display:flex; justify-content:space-between; align-items:center; margin-top:14px; }
  .car-btn { background:var(--card2); color:var(--txt); border:none; border-radius:8px;
             padding:8px 14px; cursor:pointer; font-size:14px; }
  .car-btn:hover { background:#2a2f3a; }
  .car-count { color:var(--muted); font-size:13px; }
  /* conclusiones */
  .nota { color:var(--muted); font-size:12.5px; font-style:italic; margin-bottom:14px; line-height:1.55; }
  .concl { background:var(--card); border-left:3px solid var(--accent); border-radius:8px;
           padding:14px 18px; margin-bottom:10px; }
  .concl-head { display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:4px; }
  .concl-head b { font-size:15px; }
  .impacto { background:var(--accent); color:#0a0a0a; font-weight:700; font-size:13px;
             padding:3px 11px; border-radius:20px; white-space:nowrap; }
  .concl span.det { color:var(--muted); font-size:14px; line-height:1.5; }
  /* comentarios reales por tema (desplegable al hacer clic) */
  .toggle { color:var(--accent); font-size:13px; margin-top:10px; font-weight:600; }
  .theme-comments { display:none; margin-top:12px; border-top:1px solid #23262e; padding-top:10px; }
  .theme.open .theme-comments { display:block; }
  .rc { margin:10px 0; padding:10px 12px; background:var(--card2); border-radius:8px; }
  .rc-text { font-size:14px; line-height:1.5; margin:4px 0; }
  .rc-trad { font-size:13px; color:var(--muted); border-left:2px solid var(--accent); padding-left:8px; margin:6px 0; }
  .rc-meta { color:var(--muted); font-size:12px; }
  .chip-sent { display:inline-block; font-size:11px; font-weight:700; color:#0a0a0a;
               padding:2px 9px; border-radius:20px; }
</style>
</head>
<body>
<div class="wrap">
  <h1 id="title"></h1>
  <div class="sub" id="subtitle"></div>
  <div class="badge" id="mode"></div>

  <div class="filters">
    <div class="frow"><span class="flabel">Período</span><div id="fdate"></div></div>
    <div class="frow"><span class="flabel">Estrellas</span><div id="fstars"></div></div>
  </div>

  <div class="stats" id="stats"></div>

  <h2>Temas más mencionados</h2>
  <div class="card cloud" id="cloud"></div>

  <h2>Resumen <span class="hint">— período completo</span></h2>
  <div class="card"><p class="resumen" id="resumen"></p></div>

  <h2>Comentarios reales <span class="hint">— textuales (con traducción si están en otro idioma)</span></h2>
  <div class="card carousel" id="carousel"></div>

  <h2>Distribución por estrellas</h2>
  <div class="card" id="stars"></div>

  <h2>Sentimiento por tema</h2>
  <div class="legend">
    <span><i style="background:var(--pos)"></i>Positivo</span>
    <span><i style="background:var(--mix)"></i>Mixto</span>
    <span><i style="background:var(--neu)"></i>Neutro</span>
    <span><i style="background:var(--neg)"></i>Negativo</span>
    <span style="margin-left:auto">Score: 0% (peor) &rarr; 100% (mejor)</span>
  </div>
  <div class="hint" style="margin-bottom:12px">Hacé clic en un tema para ver 5 comentarios reales sobre ese tópico, con su clasificación.</div>
  <div id="themes"></div>

  <h2>4 estrellas <span class="hint">— la crítica más honesta (período completo)</span></h2>
  <div class="card"><p class="resumen" id="cuatro"></p></div>

  <h2>Puntos a mejorar <span class="hint">— sub-temas negativos más mencionados (período completo)</span></h2>
  <div id="amejorar"></div>
</div>

<script>
const DATA = __DATA__;
const THRESHOLD_PCT = 0.10;
const SENTS = ["positivo","negativo","neutro","mixto"];
const DATE_OPTS = [3,7,15,30,60,90,180,360];

// metadatos de temas (descripcion, ejemplos, palabras clave)
const META = {};
DATA.temas.forEach(t => META[t.nombre] = t);
const THEME_NAMES = DATA.temas.map(t => t.nombre);
DATA.reviews_clasificadas.forEach((r, i) => { r._id = i; });  // id para no repetir comentarios

// estado de filtros
let fDays = "all";
let fStars = new Set([1,2,3,4,5]);
let ci = 0;  // índice del carrusel

const refDate = DATA.fecha_referencia ? new Date(DATA.fecha_referencia + "T00:00:00") : new Date();
function scoreColor(s){ return `hsl(${(s/100)*120},70%,45%)`; }
function star(n){ return "★".repeat(n) + "☆".repeat(5-n); }

// ---- filtrado ----
function filtered(){
  let cutoff = null;
  if (fDays !== "all"){ cutoff = new Date(refDate); cutoff.setDate(cutoff.getDate() - fDays); }
  return DATA.reviews_clasificadas.filter(r => {
    if (!fStars.has(r.estrellas)) return false;
    if (cutoff && r.fecha){ if (new Date(r.fecha + "T00:00:00") < cutoff) return false; }
    return true;
  });
}

// ---- agregación sobre un set de reseñas ----
function aggregate(revs){
  const counts = {}; const detr = {};
  THEME_NAMES.forEach(n => { counts[n] = {positivo:0,negativo:0,neutro:0,mixto:0}; detr[n] = 0; });
  revs.forEach(r => (r.tags||[]).forEach(tag => {
    if (counts[tag.tema] && SENTS.includes(tag.sentimiento)){
      counts[tag.tema][tag.sentimiento]++;
      if (tag.sentimiento === "negativo" && (r.estrellas||5) < 5) detr[tag.tema]++;
    }
  }));
  const temas = THEME_NAMES.map(n => {
    const c = counts[n]; const tot = SENTS.reduce((a,s)=>a+c[s],0);
    const p = {}; SENTS.forEach(s => p[s] = tot ? +(100*c[s]/tot).toFixed(1) : 0);
    const score = +(p.positivo + 0.5*(p.mixto + p.neutro)).toFixed(1);
    return {nombre:n, menciones:tot, sentimiento_pct:p, score_0_100:score,
            descripcion:META[n].descripcion, palabras_clave:META[n].palabras_clave, ejemplos:META[n].ejemplos};
  });
  // estrellas + rating promedio
  const dist = {1:0,2:0,3:0,4:0,5:0};
  let sum = 0, cnt = 0;
  revs.forEach(r => { if (r.estrellas>=1 && r.estrellas<=5){ dist[r.estrellas]++; sum+=r.estrellas; cnt++; } });
  return {temas, detr, dist, n:revs.length, ratingProm: cnt ? +(sum/cnt).toFixed(2) : 0};
}

// ---- comentarios reales por tema ----
const SENT_COLOR = {positivo:"var(--pos)", negativo:"var(--neg)", neutro:"var(--neu)", mixto:"var(--mix)"};
const SENT_LABEL = {positivo:"Positivo", negativo:"Negativo", neutro:"Neutro", mixto:"Mixto"};
function esc(s){ return (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function clean(s){ return (s||"").replace(/<br\s*\/?>/gi, " ").replace(/\s+/g, " ").trim(); }
function disp(s){ return esc(clean(s)); }

// Selecciona comentarios variados por sentimiento para un tema, SIN reutilizar
// comentarios ya usados en otros temas (used = Set global de _id).
function themeComments(revs, theme, k, used){
  const groups = {negativo:[], positivo:[], mixto:[], neutro:[]};
  revs.forEach(r => {
    if (used && used.has(r._id)) return;
    (r.tags||[]).forEach(t => {
      if (t.tema === theme && groups[t.sentimiento]) groups[t.sentimiento].push({...r, _sent:t.sentimiento});
    });
  });
  Object.values(groups).forEach(g => g.sort((a,b)=>(b.texto||"").length-(a.texto||"").length));
  const out = []; const order = ["negativo","positivo","mixto","neutro"]; let added = true;
  while (out.length < k && added){
    added = false;
    for (const s of order){
      if (groups[s].length && out.length < k){
        const item = groups[s].shift();
        out.push(item);
        if (used) used.add(item._id);
        added = true;
      }
    }
  }
  return out;
}
function commentHTML(c){
  const trad = (c.traduccion && c.idioma && c.idioma !== "es")
    ? `<div class="rc-trad"><b>Traducción (${c.idioma} → es):</b> ${disp(c.traduccion)}</div>` : "";
  return `<div class="rc">
    <span class="chip-sent" style="background:${SENT_COLOR[c._sent]}">${SENT_LABEL[c._sent]}</span>
    <div class="rc-text">“${disp(c.texto)}”</div>
    ${trad}
    <div class="rc-meta">${star(c.estrellas)} &middot; ${esc(c.usuario||"Usuario")} &middot; ${c.fecha||""}</div>
  </div>`;
}

// ---- carrusel ----
let carPool = [];
function renderCarousel(){
  const car = document.getElementById("carousel");
  if (!carPool.length){ car.innerHTML = '<div class="empty">No hay comentarios para este filtro.</div>'; return; }
  if (ci >= carPool.length) ci = 0;
  const c = carPool[ci];
  const trad = (c.traduccion && c.idioma && c.idioma !== "es")
    ? `<div class="car-trad"><b>Traducción (${c.idioma} → es):</b> ${disp(c.traduccion)}</div>` : "";
  car.innerHTML = `
    <div class="car-stars">${star(c.estrellas)}</div>
    <div class="car-text">“${disp(c.texto)}”</div>
    ${trad}
    <div class="car-meta">— ${c.usuario||"Usuario de Google"} &middot; ${c["reseñas_del_usuario"]??0} reseñas &middot; ${c.fecha||""}</div>
    <div class="car-nav">
      <button class="car-btn" id="prev">‹ Anterior</button>
      <span class="car-count">${ci+1} / ${carPool.length}</span>
      <button class="car-btn" id="next">Siguiente ›</button>
    </div>`;
  document.getElementById("prev").onclick = () => { ci=(ci-1+carPool.length)%carPool.length; renderCarousel(); };
  document.getElementById("next").onclick = () => { ci=(ci+1)%carPool.length; renderCarousel(); };
}

// ---- render principal ----
function render(){
  const revs = filtered();
  const agg = aggregate(revs);
  const umbral = agg.n * THRESHOLD_PCT;
  const visibles = agg.temas.filter(t => t.menciones >= umbral).sort((a,b)=>b.menciones-a.menciones);

  // stats
  const stats = [
    [DATA.rating_global ?? "-", "Rating global (Google)"],
    [agg.n, "Reseñas en el filtro"],
    [agg.ratingProm || "-", "Rating promedio (filtro)"],
    [visibles.length, "Temas mostrados"],
  ];
  document.getElementById("stats").innerHTML = stats.map(s =>
    `<div class="stat"><div class="n">${s[0]}</div><div class="l">${s[1]}</div></div>`).join("");

  // nube
  const maxM = Math.max(...visibles.map(t=>t.menciones), 1);
  document.getElementById("cloud").innerHTML = visibles.length
    ? visibles.map(t => { const size = 16 + (t.menciones/maxM)*40;
        return `<span style="font-size:${size}px;color:${scoreColor(t.score_0_100)}" title="${t.menciones} menciones · score ${t.score_0_100}">${t.nombre}</span>`; }).join("")
    : '<div class="empty">No hay temas suficientes para este filtro.</div>';

  // distribución estrellas
  const totalD = Object.values(agg.dist).reduce((a,b)=>a+b,0) || 1;
  const maxD = Math.max(...Object.values(agg.dist), 1);
  const sc = {5:"#2ecc71",4:"#7ec850",3:"#f1c40f",2:"#e67e22",1:"#e74c3c"};
  document.getElementById("stars").innerHTML = [5,4,3,2,1].map(s => {
    const v = agg.dist[s]||0, pct=(100*v/totalD).toFixed(1), w=(100*v/maxD).toFixed(1);
    return `<div class="star-row"><div class="star-lbl">${s} ★</div>
      <div class="star-track"><div class="star-fill" style="width:${w}%;background:${sc[s]}"></div></div>
      <div class="star-val">${v} reseñas (${pct}%)</div></div>`; }).join("");

  // sentimiento por tema
  const themes = document.getElementById("themes");
  themes.innerHTML = "";
  if (!visibles.length){ themes.innerHTML = '<div class="empty">No hay temas suficientes para este filtro.</div>'; }
  const usedComments = new Set();  // para no repetir el mismo comentario entre temas
  visibles.forEach(t => {
    const p = t.sentimiento_pct;
    const seg = (val,v) => val>0 ? `<div style="width:${val}%;background:var(--${v})">${val>=8?val+"%":""}</div>` : "";
    const coms = themeComments(revs, t.nombre, 5, usedComments);
    const comsHTML = coms.length ? coms.map(commentHTML).join("")
      : '<div class="empty">Sin comentarios para este filtro.</div>';
    const div = document.createElement("div"); div.className="theme";
    div.innerHTML = `
      <div class="theme-head"><span class="theme-name">${t.nombre}</span>
        <span class="theme-meta">${t.menciones} menciones &middot;
          <span class="score" style="color:${scoreColor(t.score_0_100)}">${t.score_0_100}%</span></span></div>
      <div class="theme-desc">${t.descripcion||""}</div>
      <div class="bar">${seg(p.positivo,"pos")}${seg(p.mixto,"mix")}${seg(p.neutro,"neu")}${seg(p.negativo,"neg")}</div>
      ${t.palabras_clave&&t.palabras_clave.length?'<div class="kw">Incluye: '+t.palabras_clave.join(", ")+"</div>":""}
      <div class="toggle">▾ Ver 5 comentarios reales</div>
      <div class="theme-comments">${comsHTML}</div>`;
    div.addEventListener("click", () => {
      div.classList.toggle("open");
      div.querySelector(".toggle").textContent = div.classList.contains("open")
        ? "▴ Ocultar comentarios" : "▾ Ver 5 comentarios reales";
    });
    themes.appendChild(div);
  });

  // carrusel: comentarios con texto sustancioso del set filtrado (más nuevos primero)
  carPool = revs.filter(r => r.texto && r.texto.length >= 40)
                .sort((a,b)=>(b.fecha||"").localeCompare(a.fecha||"")).slice(0, 40);
  ci = 0; renderCarousel();
}

// ---- UI estática ----
document.getElementById("title").textContent = DATA.client_name;
document.getElementById("subtitle").textContent = (DATA.place_name||"") + " · Análisis de reseñas de Google Maps";
document.getElementById("mode").textContent = DATA.modo || "";
document.getElementById("resumen").textContent = DATA.resumen || "";
document.getElementById("cuatro").textContent = DATA.resumen_4_estrellas || "";

// Puntos a mejorar: sub-temas negativos más mencionados (estático, período completo)
(function(){
  const subs = (DATA.subtemas_negativos || []).slice(0, 5);
  const nota = '<div class="nota">Los sub-temas negativos que más se repiten. Qué hacer al respecto queda a tu criterio.</div>';
  document.getElementById("amejorar").innerHTML = nota + (subs.length
    ? subs.map((s,i) => `<div class="concl"><div class="concl-head">
        <b>${i+1}. ${esc(s.subtema)}</b><span class="impacto">${s.menciones} menciones</span></div></div>`).join("")
    : '<div class="empty">No se detectaron sub-temas negativos relevantes.</div>');
})();

// chips de fecha
const fdate = document.getElementById("fdate");
[["all","Todo"]].concat(DATE_OPTS.map(d=>[d, d+" días"])).forEach(([val,lbl]) => {
  const b = document.createElement("span"); b.className = "chip" + (val===fDays?" active":"");
  b.textContent = lbl;
  b.onclick = () => { fDays = val; [...fdate.children].forEach(x=>x.classList.remove("active")); b.classList.add("active"); render(); };
  fdate.appendChild(b);
});
// chips de estrellas
const fstars = document.getElementById("fstars");
[5,4,3,2,1].forEach(s => {
  const b = document.createElement("span"); b.className = "chip active"; b.textContent = s + " ★";
  b.onclick = () => {
    if (fStars.has(s)) fStars.delete(s); else fStars.add(s);
    if (fStars.size === 0){ fStars.add(s); return; }  // no permitir vacío
    b.classList.toggle("active"); render();
  };
  fstars.appendChild(b);
});

render();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python build_dashboard.py <slug>   (ej: don-julio)")
    slug = sys.argv[1]
    path = f"data/{slug}_analysis.json"
    if not os.path.exists(path):
        sys.exit(f"ERROR: no existe {path}. Corré primero analyze_reviews.py")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("reviews_clasificadas"):
        sys.exit("ERROR: el análisis no tiene 'reviews_clasificadas'. Re-corré analyze_reviews.py actualizado.")

    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = f"dashboard_{slug}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard generado: {out}  ({len(data['reviews_clasificadas'])} reseñas, filtros en vivo)")


if __name__ == "__main__":
    main()
