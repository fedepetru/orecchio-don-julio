"""
Paso 3 del pipeline: generar el dashboard HTML a partir del análisis.

Uso:
    python build_dashboard.py don-julio

Genera dashboard_<slug>.html (se abre con doble clic en cualquier navegador).
"""

import json
import os
import sys

# Temas con menos de este % de las reseñas analizadas se ocultan (ej: 0.10 = 10%)
THRESHOLD_PCT = 0.10

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
  .sub { color:var(--muted); margin-bottom:24px; }
  .badge { display:inline-block; background:var(--card2); color:var(--muted); font-size:12px;
           padding:3px 10px; border-radius:20px; margin-bottom:20px; }
  .stats { display:flex; gap:16px; flex-wrap:wrap; margin-bottom:8px; }
  .stat { background:var(--card); border-radius:12px; padding:16px 20px; flex:1; min-width:150px; }
  .stat .n { font-size:26px; font-weight:700; }
  .stat .l { color:var(--muted); font-size:13px; }
  h2 { font-size:19px; margin:34px 0 14px; }
  .card { background:var(--card); border-radius:12px; padding:20px 22px; }
  .cloud { display:flex; flex-wrap:wrap; gap:14px 22px; align-items:center; justify-content:center; }
  .cloud span { line-height:1; cursor:default; }
  p.resumen { line-height:1.6; margin:0; font-size:15px; }
  /* distribución de estrellas */
  .star-row { display:flex; align-items:center; gap:12px; margin:8px 0; }
  .star-lbl { width:48px; text-align:right; color:var(--muted); font-size:14px; white-space:nowrap; }
  .star-track { flex:1; background:#11141a; border-radius:6px; height:24px; overflow:hidden; }
  .star-fill { height:100%; border-radius:6px; }
  .star-val { width:120px; font-size:13px; color:var(--muted); }
  /* temas */
  .theme { background:var(--card); border-radius:12px; padding:16px 20px; margin-bottom:12px; cursor:default; }
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
  /* carrusel de comentarios reales */
  .carousel { position:relative; }
  .car-stars { color:var(--mix); font-size:17px; letter-spacing:3px; }
  .car-text { font-size:15.5px; line-height:1.6; margin:12px 0; }
  .car-meta { color:var(--muted); font-size:13px; }
  .car-nav { display:flex; justify-content:space-between; align-items:center; margin-top:16px; }
  .car-btn { background:var(--card2); color:var(--txt); border:none; border-radius:8px;
             padding:8px 14px; cursor:pointer; font-size:14px; }
  .car-btn:hover { background:#2a2f3a; }
  .car-dots { display:flex; gap:7px; }
  .car-dot { width:9px; height:9px; border-radius:50%; background:#3a3f4a; cursor:pointer; }
  .car-dot.active { background:var(--accent); }
  /* conclusiones */
  .nota { color:var(--muted); font-size:12.5px; font-style:italic; margin-bottom:14px; line-height:1.55; }
  .concl { background:var(--card); border-left:3px solid var(--accent); border-radius:8px;
           padding:14px 18px; margin-bottom:10px; }
  .concl-head { display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:4px; }
  .concl-head b { font-size:15px; }
  .impacto { background:var(--accent); color:#0a0a0a; font-weight:700; font-size:13px;
             padding:3px 11px; border-radius:20px; white-space:nowrap; }
  .concl span.det { color:var(--muted); font-size:14px; line-height:1.5; }
  /* tooltip flotante */
  #tip { position:fixed; pointer-events:none; z-index:99; background:#0b0d12; border:1px solid #2a2f3a;
         border-radius:10px; padding:12px 14px; max-width:340px; font-size:12.5px; line-height:1.45;
         box-shadow:0 8px 24px rgba(0,0,0,.5); display:none; }
  #tip h4 { margin:0 0 8px; font-size:13px; }
  #tip .ex { margin:6px 0; }
  #tip .tag { font-weight:700; }
</style>
</head>
<body>
<div class="wrap">
  <h1 id="title"></h1>
  <div class="sub" id="subtitle"></div>
  <div class="badge" id="mode"></div>

  <div class="stats" id="stats"></div>

  <h2>Temas más mencionados</h2>
  <div class="card cloud" id="cloud"></div>

  <h2>Resumen</h2>
  <div class="card"><p class="resumen" id="resumen"></p></div>

  <h2>Comentarios reales <span class="hint">— textuales, para verificar que el análisis es consecuente</span></h2>
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
  <div class="hint" style="margin-bottom:12px">Pasá el mouse por encima de una barra para ver qué se considera positivo, mixto, neutro o negativo en ese tema.</div>
  <div id="themes"></div>

  <h2>4 estrellas <span class="hint">— la crítica más honesta</span></h2>
  <div class="card"><p class="resumen" id="cuatro"></p></div>

  <h2>Conclusiones <span class="hint">— quick wins de corto plazo</span></h2>
  <div id="conclusiones"></div>
</div>

<div id="tip"></div>

<script>
const DATA = __DATA__;

function scoreColor(s){ return `hsl(${(s/100)*120},70%,45%)`; }

// Header
document.getElementById('title').textContent = DATA.client_name;
document.getElementById('subtitle').textContent = (DATA.place_name||'') + ' · Análisis de reseñas de Google Maps';
document.getElementById('mode').textContent = DATA.modo || '';
document.getElementById('resumen').textContent = DATA.resumen || '';
document.getElementById('cuatro').textContent = DATA.resumen_4_estrellas || '';

// Stats
const stats = [
  [DATA.rating_global ?? '-', 'Rating global en Google'],
  [(DATA.total_reviews_en_google ?? '-').toLocaleString('es-AR'), 'Reseñas totales en Google'],
  [DATA.reviews_analizadas ?? '-', 'Reseñas analizadas'],
  [DATA.temas.length, 'Temas mostrados'],
];
document.getElementById('stats').innerHTML = stats.map(s =>
  `<div class="stat"><div class="n">${s[0]}</div><div class="l">${s[1]}</div></div>`).join('');

// Nube de temas
const maxM = Math.max(...DATA.temas.map(t => t.menciones), 1);
document.getElementById('cloud').innerHTML = DATA.temas.map(t => {
  const size = 16 + (t.menciones/maxM)*40;
  return `<span style="font-size:${size}px;color:${scoreColor(t.score_0_100)}"
            title="${t.menciones} menciones · score ${t.score_0_100}">${t.nombre}</span>`;
}).join('');

// Distribución por estrellas
const dist = DATA.distribucion_estrellas || {};
const totalD = Object.values(dist).reduce((a,b)=>a+b,0) || 1;
const maxD = Math.max(...Object.values(dist), 1);
const starColor = {5:'#2ecc71',4:'#7ec850',3:'#f1c40f',2:'#e67e22',1:'#e74c3c'};
document.getElementById('stars').innerHTML = [5,4,3,2,1].map(s => {
  const v = dist[s]||0;
  const pct = (100*v/totalD).toFixed(1);
  const w = (100*v/maxD).toFixed(1);
  return `<div class="star-row">
            <div class="star-lbl">${s} ★</div>
            <div class="star-track"><div class="star-fill" style="width:${w}%;background:${starColor[s]}"></div></div>
            <div class="star-val">${v} reseñas (${pct}%)</div>
          </div>`;
}).join('');

// Sentimiento por tema
const tip = document.getElementById('tip');
function showTip(t, e){
  const ex = t.ejemplos || {};
  tip.innerHTML = `<h4>Qué se considera en "${t.nombre}"</h4>
    <div class="ex"><span class="tag" style="color:var(--pos)">Positivo:</span> ${ex.positivo||'—'}</div>
    <div class="ex"><span class="tag" style="color:var(--mix)">Mixto:</span> ${ex.mixto||'—'}</div>
    <div class="ex"><span class="tag" style="color:var(--neu)">Neutro:</span> ${ex.neutro||'—'}</div>
    <div class="ex"><span class="tag" style="color:var(--neg)">Negativo:</span> ${ex.negativo||'—'}</div>`;
  tip.style.display = 'block';
  moveTip(e);
}
function moveTip(e){
  const pad = 16, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > window.innerWidth)  x = e.clientX - w - pad;
  if (y + h > window.innerHeight) y = e.clientY - h - pad;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip(){ tip.style.display = 'none'; }

const themes = document.getElementById('themes');
DATA.temas.forEach(t => {
  const p = t.sentimiento_pct;
  const seg = (val,v) => val > 0 ? `<div style="width:${val}%;background:var(--${v})">${val>=8?val+'%':''}</div>` : '';
  const div = document.createElement('div');
  div.className = 'theme';
  div.innerHTML = `
    <div class="theme-head">
      <span class="theme-name">${t.nombre}</span>
      <span class="theme-meta">${t.menciones} menciones &middot;
        <span class="score" style="color:${scoreColor(t.score_0_100)}">${t.score_0_100}%</span></span>
    </div>
    <div class="theme-desc">${t.descripcion||''}</div>
    <div class="bar">${seg(p.positivo,'pos')}${seg(p.mixto,'mix')}${seg(p.neutro,'neu')}${seg(p.negativo,'neg')}</div>
    ${t.palabras_clave && t.palabras_clave.length ? '<div class="kw">Incluye: ' + t.palabras_clave.join(', ') + '</div>' : ''}
  `;
  div.addEventListener('mouseenter', e => showTip(t, e));
  div.addEventListener('mousemove', moveTip);
  div.addEventListener('mouseleave', hideTip);
  themes.appendChild(div);
});

// Carrusel de comentarios reales
const coms = DATA.comentarios_reales || [];
const car = document.getElementById('carousel');
let ci = 0;
const star = n => '★'.repeat(n) + '☆'.repeat(5 - n);
function renderCar(){
  if (!coms.length){ car.innerHTML = '<div class="car-text">Sin comentarios.</div>'; return; }
  const c = coms[ci];
  car.innerHTML = `
    <div class="car-stars">${star(c.estrellas)}</div>
    <div class="car-text">“${c.texto}”</div>
    <div class="car-meta">— ${c.usuario || 'Usuario de Google'} &middot; ${c['reseñas_del_usuario'] ?? 0} reseñas &middot; ${c.fecha || ''}</div>
    <div class="car-nav">
      <button class="car-btn" id="prev">‹ Anterior</button>
      <div class="car-dots">${coms.map((_,i)=>`<span class="car-dot ${i===ci?'active':''}" data-i="${i}"></span>`).join('')}</div>
      <button class="car-btn" id="next">Siguiente ›</button>
    </div>`;
  document.getElementById('prev').onclick = () => { ci = (ci - 1 + coms.length) % coms.length; renderCar(); };
  document.getElementById('next').onclick = () => { ci = (ci + 1) % coms.length; renderCar(); };
  car.querySelectorAll('.car-dot').forEach(d => d.onclick = () => { ci = +d.dataset.i; renderCar(); });
}
renderCar();

// Conclusiones
const nota = DATA.conclusiones_nota ? `<div class="nota">${DATA.conclusiones_nota}</div>` : '';
document.getElementById('conclusiones').innerHTML = nota + (DATA.conclusiones||[]).map((c,i) =>
  `<div class="concl">
     <div class="concl-head"><b>${i+1}. ${c.titulo}</b>${c.impacto_estimado?`<span class="impacto">${c.impacto_estimado}</span>`:''}</div>
     <span class="det">${c.detalle}</span>
   </div>`).join('');
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

    # Filtro: ocultar temas con menos del THRESHOLD_PCT de las reseñas analizadas
    umbral = (data.get("reviews_analizadas") or 0) * THRESHOLD_PCT
    todos = data["temas"]
    visibles = [t for t in todos if t["menciones"] >= umbral]
    ocultos = [t["nombre"] for t in todos if t["menciones"] < umbral]
    data["temas"] = visibles

    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = f"dashboard_{slug}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generado: {out}  (abrilo con doble clic)")
    print(f"Temas mostrados: {len(visibles)}  (umbral: {umbral:.1f} menciones)")
    if ocultos:
        print(f"Temas ocultados por bajo volumen (<{int(THRESHOLD_PCT*100)}%): {', '.join(ocultos)}")


if __name__ == "__main__":
    main()
