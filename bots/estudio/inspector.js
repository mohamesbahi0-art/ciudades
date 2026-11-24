// El Inspector de imagen: mira un guion ya con tiempos igual que render.js (mismo HTML, mismo navegador), se para en
// varios momentos de cada escena y MIDE lo que hay en pantalla, sin IA: textos fuera del marco, recortados, pisados,
// pegados, repetidos, tapados, diminutos o apagados, y dibujos que se salen. No opina: solo cuenta lo que mide.
// Uso: node inspector.js guion_estudio.json [--capturas carpeta] [--sin-pixeles]   → un JSON (lista de defectos) por stdout
//
// Pistas que puede dar el HTML del formato (todas opcionales):
//   data-adorno   en un texto (o en su grupo): es parte de un dibujo o un adorno, no un texto que haya que leer
//   data-pieza    en un grupo: un dibujo, emoji, tarjeta o icono (se mira que no se salga y que no tape textos)
//   data-sangra   en una pieza: se sale del marco a propósito (una franja a todo lo ancho)
//   data-bloque   en un grupo: sus textos forman una sola frase (varias líneas o palabras sueltas)
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

function momentos(g) {
  const d = g.duracion, lista = [];
  const pon = (t, por) => { t = Math.max(0, Math.min(d - 0.05, t)); if (!lista.some(x => Math.abs(x.t - t) < 0.04)) lista.push({ t: Math.round(t * 100) / 100, por }); };
  [0.3, 1.2, 2.5].forEach(t => pon(t, "juez"));                       // los fotogramas que miran los jueces
  [0.30, 0.55, 0.80].forEach(f => pon(d * f, "juez"));
  pon(d - 0.2, "juez");
  g.escenas.forEach(e => {
    const largo = e.fin - e.inicio;
    pon(e.inicio + 0.1, "corte");                                       // en pleno cambio de escena
    pon(e.inicio + Math.min(0.6, largo / 3), "entrada");
    pon(e.inicio + largo / 2, "mitad");
    pon(e.fin - 0.12, "final");
  });
  return lista.sort((a, b) => a.t - b.t);
}

// ---------------------------------------------------------------------------------------------------------------
// Lo que corre dentro de la página: mide el fotograma que está pintado y devuelve los defectos que ve.
function medir(arg) {
  const { W, H, pixeles } = arg;
  const MARGEN = 6, MIN_LETRA = 24, MIN_CONTRASTE = 2.6;
  const svgs = [...document.querySelectorAll("svg")];
  const num = (v, def = 1) => { const n = parseFloat(v); return Number.isFinite(n) ? n : def; };

  function opacidad(el) {          // opacidad real: la suya por la de todos sus grupos
    let o = 1;
    for (let x = el; x && x.nodeType === 1; x = x.parentElement) {
      const cs = getComputedStyle(x);
      if (cs.visibility === "hidden" || cs.display === "none") return 0;
      o *= num(cs.opacity);
    }
    return o;
  }
  function filtroBorroso(el) {     // un texto o forma con un desenfoque puro es un brillo, no algo que se lea
    for (let x = el; x && x.nodeType === 1; x = x.parentElement) {
      const f = x.getAttribute && x.getAttribute("filter");
      const m = f && /url\(#([^)]+)\)/.exec(f);
      if (!m) continue;
      const def = document.getElementById(m[1]);
      if (def && def.querySelector("feGaussianBlur") && !def.querySelector("feMergeNode[in=SourceGraphic]") &&
          num(def.querySelector("feGaussianBlur").getAttribute("stdDeviation"), 0) >= 2) return true;
    }
    return false;
  }
  const caja = (x0, y0, x1, y1) => ({ x0, y0, x1, y1, w: x1 - x0, h: y1 - y0 });
  const corta = (a, b) => caja(Math.max(a.x0, b.x0), Math.max(a.y0, b.y0), Math.min(a.x1, b.x1), Math.min(a.y1, b.y1));
  function aPantalla(el, x0, y0, x1, y1) {
    const m = el.getScreenCTM();
    if (!m) return null;
    const ps = [[x0, y0], [x1, y0], [x0, y1], [x1, y1]].map(([x, y]) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]);
    return caja(Math.min(...ps.map(p => p[0])), Math.min(...ps.map(p => p[1])), Math.max(...ps.map(p => p[0])), Math.max(...ps.map(p => p[1])));
  }
  function recorte(el) {           // la caja (en pantalla) que dejan ver las máscaras de sus grupos, o null
    let r = null;
    for (let x = el; x && x.nodeType === 1; x = x.parentElement) {
      const c = x.getAttribute && x.getAttribute("clip-path"), m = c && /url\(#([^)]+)\)/.exec(c);
      const def = m && document.getElementById(m[1]);
      if (!def || !def.firstElementChild) continue;
      let u = null;
      for (const hijo of def.children) {
        let bb; try { bb = hijo.getBBox(); } catch (e) { continue; }
        const p = aPantalla(x, bb.x, bb.y, bb.x + bb.width, bb.y + bb.height);
        if (p) u = u ? caja(Math.min(u.x0, p.x0), Math.min(u.y0, p.y0), Math.max(u.x1, p.x1), Math.max(u.y1, p.y1)) : p;
      }
      if (u) r = r ? corta(r, u) : u;
    }
    return r;
  }
  const lienzo = document.createElement("canvas").getContext("2d");
  const esEmoji = s => /\p{Extended_Pictographic}/u.test(s) && !/[\p{L}\p{N}]/u.test(s);

  // ---- textos que se leen ----
  const textos = [];
  for (const el of document.querySelectorAll("svg text")) {
    if (el.closest("defs") || el.closest("[data-adorno]")) continue;
    const s = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (!s || esEmoji(s) || filtroBorroso(el)) continue;
    const cs = getComputedStyle(el), o = opacidad(el) * num(cs.fillOpacity);
    if (o < 0.5 || cs.fill === "none") continue;                // aún está entrando (o ya se va): todavía no es un texto que se lea
    const m = el.getScreenCTM();
    if (!m) continue;
    const escala = Math.sqrt(Math.abs(m.a * m.d - m.b * m.c)), tam = num(cs.fontSize, 0);
    let bb; try { bb = el.getBBox(); } catch (e) { continue; }
    if (!bb.width || !tam) continue;
    lienzo.font = `${cs.fontStyle} ${cs.fontWeight} ${tam}px ${cs.fontFamily}`;
    const mt = lienzo.measureText(s), sube = mt.actualBoundingBoxAscent || tam * 0.74, baja = mt.actualBoundingBoxDescent || 0;
    const y = el.hasAttribute("y") && !el.querySelector("tspan") ? num(el.getAttribute("y"), bb.y + bb.height * 0.75) : bb.y + bb.height * 0.75;
    const tinta = aPantalla(el, bb.x, y - sube, bb.x + bb.width, y + baja);
    if (!tinta || tinta.w < 1 || tinta.h < 1) continue;
    const bloque = el.closest("[data-bloque]");
    textos.push({ el, s, o, tinta, tam: tam * escala, peso: cs.fontWeight, color: cs.fill, pieza: el.closest("[data-pieza]"),
                  bloque: bloque ? bloque.getAttribute("data-bloque") : null });
  }
  // el mismo texto dos veces en el mismo sitio es un brillo o una sombra: se queda el más visible
  textos.sort((a, b) => b.o - a.o);
  const unicos = [];
  for (const t of textos) {
    const gemelo = unicos.find(u => u.s === t.s && Math.abs(u.tinta.x0 - t.tinta.x0) < 8 && Math.abs(u.tinta.y0 - t.tinta.y0) < 8 &&
                                    Math.abs(u.tinta.w - t.tinta.w) < 16);
    if (!gemelo) unicos.push(t);
  }
  const orden = (a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
  unicos.sort((a, b) => orden(a.el, b.el));

  // ---- qué formas tapan (opacas y pintadas después) ----
  const opaca = new Map();
  function esOpaca(x) {
    if (opaca.has(x)) return opaca.get(x);
    let r = false;
    const nombre = x.tagName.toLowerCase();
    if (["rect", "circle", "ellipse", "path", "polygon", "image", "text"].includes(nombre) && !x.closest("defs") && !filtroBorroso(x)) {
      const cs = getComputedStyle(x), o = opacidad(x) * num(cs.fillOpacity);
      if (nombre === "text") r = o >= 0.7 && esEmoji(x.textContent || "") && num(cs.fontSize, 0) >= 100;
      else if (o >= 0.7 && cs.fill && cs.fill !== "none") {
        const u = /url\(["']?#([^"')]+)["']?\)/.exec(cs.fill), a = /rgba\([^)]*,\s*([\d.]+)\)/.exec(cs.fill);
        if (u) { const gr = document.getElementById(u[1]); r = !!gr && [...gr.querySelectorAll("stop")].every(st => num(st.getAttribute("stop-opacity")) >= 0.7); }
        else r = !a || parseFloat(a[1]) >= 0.7;
      }
    }
    opaca.set(x, r);
    return r;
  }
  const defectos = [];
  const pon = (tipo, lista, detalle) => defectos.push({ tipo, textos: lista, detalle });
  const dentro = caja(0, 0, W, H);
  const vistos = [];
  for (const t of unicos) {
    const k = t.tinta, visto = corta(k, dentro);
    if (visto.w <= 0 || visto.h <= 0) continue;                   // del todo fuera: no se ve
    // tapado por una forma opaca pintada encima (o por otra escena durante un cambio)
    let libres = 0, total = 0, quien = null;
    for (let i = 0; i < 7; i++) for (let j = 0; j < 3; j++) {
      const px = k.x0 + k.w * (i + 0.5) / 7, py = k.y0 + k.h * (j + 0.5) / 3;
      if (px < 0 || py < 0 || px >= W || py >= H) continue;
      total++;
      const encima = document.elementsFromPoint(px, py).find(x => x !== t.el && x.ownerSVGElement && esOpaca(x) &&
        (t.el.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING) && !t.el.contains(x));
      if (encima) quien = encima; else libres++;
    }
    t.libre = total ? libres / total : 1;
    if (t.libre < 0.15) continue;                                 // tapado del todo: no cuenta como texto visible
    const rc = recorte(t.el);
    t.visto = rc ? corta(k, rc) : k;
    if (rc && (t.visto.w <= 1 || t.visto.h <= 1)) continue;       // escondido del todo tras su máscara
    vistos.push(t);
    if (t.pieza) continue;                                        // letras de un dibujo: cuentan como dibujo
    if (rc && t.visto.w * t.visto.h < 0.93 * k.w * k.h) pon("recortado", [t.s], `«${t.s}» sale cortado por su recuadro o su máscara`);
    else if (t.libre < 0.85) {
      const p = quien && quien.closest("[data-pieza]");
      pon("tapado", [t.s], `${p ? "el dibujo «" + p.getAttribute("data-pieza") + "»" : "una forma"} tapa a medias «${t.s}»`);
    }
    const fuera = Math.max(MARGEN - k.x0, k.x1 - (W - MARGEN), MARGEN - k.y0, k.y1 - (H - MARGEN));
    if (fuera > 3) pon("fuera_de_marco", [t.s], `«${t.s}» se sale del marco o queda pegado al borde (${Math.round(fuera)} px)`);
    if (t.tam < MIN_LETRA) pon("letra_pequena", [t.s], `«${t.s}» mide ${Math.round(t.tam)} px: no se lee en un móvil`);
    // el recuadro que lleva debajo (píldora, tarjeta, caja de palabra clave): el texto tiene que caber dentro
    const cx = (k.x0 + k.x1) / 2, cy = (k.y0 + k.y1) / 2;
    if (cx >= 0 && cy >= 0 && cx < W && cy < H) {
      const debajo = document.elementsFromPoint(cx, cy).find(x => x.tagName.toLowerCase() === "rect" && !x.closest("defs") &&
        (t.el.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_PRECEDING) && opacidad(x) > 0.5 && !filtroBorroso(x));
      if (debajo) {
        const r = debajo.getBoundingClientRect(), cs = getComputedStyle(debajo);
        const pintado = (cs.fill && cs.fill !== "none") || (cs.stroke && cs.stroke !== "none");
        if (pintado && r.width * r.height < 0.5 * W * H && r.height >= k.h * 0.9 && r.height < k.h * 6 &&
            (k.x0 < r.left - 4 || k.x1 > r.right + 4))
          pon("fuera_de_recuadro", [t.s], `«${t.s}» no cabe en su recuadro (se sale ${Math.round(Math.max(r.left - k.x0, k.x1 - r.right))} px)`);
      }
    }
  }
  const leibles = vistos.filter(t => !t.pieza);

  // ---- pares: pisados y pegados ----
  for (let i = 0; i < leibles.length; i++) for (let j = i + 1; j < leibles.length; j++) {
    const a = leibles[i], b = leibles[j], x = corta(a.visto, b.visto);
    if (x.w > 4 && x.h > 4 && x.w * x.h > 0.1 * Math.min(a.visto.w * a.visto.h, b.visto.w * b.visto.h)) {
      pon("pisados", [a.s, b.s], `«${a.s}» y «${b.s}» se pisan`);
      continue;
    }
    const alto = Math.min(a.tinta.h, b.tinta.h), comun = Math.min(a.tinta.y1, b.tinta.y1) - Math.max(a.tinta.y0, b.tinta.y0);
    if (comun > 0.5 * alto) {
      const [iz, de] = a.tinta.x0 <= b.tinta.x0 ? [a, b] : [b, a], hueco = de.tinta.x0 - iz.tinta.x1;
      if (hueco > -5 && hueco < 0.1 * Math.min(a.tam, b.tam) && /[\p{L}\p{N}]$/u.test(iz.s) && /^[\p{L}\p{N}]/u.test(de.s))
        pon("pegados", [iz.s, de.s], `«${iz.s}» y «${de.s}» salen pegados, sin espacio: se lee «${iz.s}${de.s}»`);
    }
  }
  for (const t of leibles) {
    if (/\p{L}{2,}\d{2,}/u.test(t.s) || /\d\p{L}{4,}/u.test(t.s))
      pon("pegados", [t.s], `en «${t.s}» van pegadas una palabra y una cifra, sin espacio`);
  }

  // ---- frases (bloques o renglones) para lo repetido y lo que queda colgando ----
  const frases = [], usados = new Set();
  const une = lista => {
    lista.sort((a, b) => Math.abs(a.tinta.y0 + a.tinta.y1 - b.tinta.y0 - b.tinta.y1) > Math.min(a.tinta.h, b.tinta.h) ? a.tinta.y0 - b.tinta.y0 : a.tinta.x0 - b.tinta.x0);
    return { s: lista.map(t => t.s).join(" "), tam: Math.max(...lista.map(t => t.tam)), partes: lista };
  };
  const porBloque = new Map();
  leibles.forEach(t => { if (t.bloque !== null) { if (!porBloque.has(t.bloque)) porBloque.set(t.bloque, []); porBloque.get(t.bloque).push(t); usados.add(t); } });
  porBloque.forEach(lista => frases.push(une(lista)));
  const sueltos = leibles.filter(t => !usados.has(t)).sort((a, b) => a.tinta.x0 - b.tinta.x0);
  for (const t of sueltos) {
    if (usados.has(t)) continue;
    const fila = [t];
    usados.add(t);
    for (const u of sueltos) {
      if (usados.has(u)) continue;
      const ult = fila[fila.length - 1], comun = Math.min(ult.tinta.y1, u.tinta.y1) - Math.max(ult.tinta.y0, u.tinta.y0);
      const hueco = u.tinta.x0 - ult.tinta.x1;
      if (Math.abs(u.tam - ult.tam) < 2 && u.peso === ult.peso && comun > 0.5 * Math.min(ult.tinta.h, u.tinta.h) && hueco > -2 && hueco < 0.6 * u.tam) { fila.push(u); usados.add(u); }
    }
    frases.push(une(fila));
  }
  const fichas = s => (s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/(\d)\.(?=\d{3}(\D|$))/g, "$1")
    .match(/\d+(?:,\d+)?|[a-zñ]+/g) || []);
  const idioma = (document.documentElement.lang || "es").slice(0, 2);
  const COLGANTES = new Set(({ nl: "de het een van voor met en of om te naar bij tot dan per zonder tussen tegen omdat maar want",
    es: "de del la el los las un una unos unas y o que a al con por para sin su sus e u ni pero porque entre sobre hasta desde lo",
    en: "the a an of to and or for with from than" }[idioma] || "").split(" "));
  frases.forEach(f => { f.fichas = fichas(f.s); });
  for (const f of frases) {
    if (/(…|\.\.\.)\s*$/.test(f.s)) pon("frase_sin_terminar", [f.s], `«${f.s}» acaba en puntos suspensivos: parece una frase cortada`);
    else if (f.fichas.length >= 2 && !/[.!?:»”"]\s*$/.test(f.s) && /\p{L}$/u.test(f.s) && COLGANTES.has(f.fichas[f.fichas.length - 1]))
      pon("frase_colgando", [f.s], `«${f.s}» se queda a medias (acaba en «${f.fichas[f.fichas.length - 1]}»)`);
  }
  const contiene = (larga, corta2) => { for (let i = 0; i + corta2.length <= larga.length; i++) if (corta2.every((x, k) => larga[i + k] === x)) return true; return false; };
  for (let i = 0; i < frases.length; i++) for (let j = 0; j < frases.length; j++) {
    const a = frases[i], b = frases[j];
    if (i === j || !a.fichas.length || a.fichas.length > b.fichas.length) continue;
    if (a.fichas.length === b.fichas.length && i > j) continue;       // dos iguales: se cuenta una vez
    const cifra = a.fichas.length === 1 && /^\d{2,}/.test(a.fichas[0]);
    const palabra = a.fichas.length === 1 && a.fichas[0].length >= 4 && a.tam >= 60 && b.tam >= 60;
    if ((a.fichas.length >= 2 || cifra || palabra) && contiene(b.fichas, a.fichas))
      pon("repetido", [a.s, b.s], a.fichas.length === b.fichas.length ? `«${a.s}» sale dos veces a la vez` : `«${a.s}» sale dos veces a la vez: suelto y dentro de «${b.s}»`);
  }

  // ---- dibujos que se salen del marco ----
  for (const p of document.querySelectorAll("svg [data-pieza]")) {
    if (p.closest("defs") || p.hasAttribute("data-sangra") || p.parentElement.closest("[data-pieza]") || opacidad(p) < 0.5) continue;
    let u = null;
    for (const x of p.querySelectorAll("rect,circle,ellipse,path,polygon,polyline,line,text,image")) {
      if (filtroBorroso(x) || opacidad(x) < 0.45) continue;
      const cs = getComputedStyle(x);
      if ((cs.fill === "none" || num(cs.fillOpacity) < 0.3) && (cs.stroke === "none" || num(cs.strokeOpacity) < 0.3)) continue;
      const r = x.getBoundingClientRect();
      if (!r.width && !r.height) continue;
      let c = caja(r.left, r.top, r.right, r.bottom);
      const rc = recorte(x);
      if (rc) c = corta(c, rc);
      if (c.w <= 0 || c.h <= 0) continue;
      u = u ? caja(Math.min(u.x0, c.x0), Math.min(u.y0, c.y0), Math.max(u.x1, c.x1), Math.max(u.y1, c.y1)) : c;
    }
    if (!u) continue;
    const sale = Math.max(-u.x0, u.x1 - W, -u.y0, u.y1 - H);
    if (sale > 40 || sale > 0.12 * Math.min(u.w, u.h))
      pon("dibujo_fuera", [p.getAttribute("data-pieza")], `el dibujo «${p.getAttribute("data-pieza")}» se sale del marco (${Math.round(sale)} px)`);
  }

  // ---- cajas de HTML que recortan su texto (formatos que no sean SVG) ----
  for (const x of document.querySelectorAll("body *:not(svg):not(svg *):not(script):not(style)")) {
    const cs = getComputedStyle(x), s = (x.textContent || "").trim();
    if (!s || x.children.length || cs.display === "none" || cs.visibility === "hidden" || num(cs.opacity) < 0.2) continue;
    if (["hidden", "clip"].includes(cs.overflowX) && x.scrollWidth > x.clientWidth + 1 || ["hidden", "clip"].includes(cs.overflowY) && x.scrollHeight > x.clientHeight + 1)
      pon("recortado", [s], `«${s}» no cabe en su caja y sale cortado`);
    const r = x.getBoundingClientRect();
    if (r.width && (r.left < -3 || r.right > W + 3 || r.top < -3 || r.bottom > H + 3)) pon("fuera_de_marco", [s], `«${s}» se sale del marco`);
  }

  // ---- contraste, medido en los píxeles de verdad ----
  if (pixeles) {
    const D = pixeles.data, lum = (r, g, b) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
    const mediana = v => { v.sort((a, b) => a - b); return v.length ? v[v.length >> 1] : 0; };
    for (const t of leibles) {
      if (t.libre < 0.85) continue;
      const k = corta(t.visto, dentro), x0 = Math.floor(k.x0), y0 = Math.floor(k.y0), x1 = Math.ceil(k.x1), y1 = Math.ceil(k.y1);
      if (x1 - x0 < 6 || y1 - y0 < 6) continue;
      const fondo = [], letra = [];
      for (let y = Math.max(0, y0 - 7); y < Math.min(H, y1 + 7); y++) for (let x = Math.max(0, x0 - 7); x < Math.min(W, x1 + 7); x++) {
        const i = (y * W + x) * 4, l = lum(D[i], D[i + 1], D[i + 2]);
        if (x < x0 - 2 || x >= x1 + 2 || y < y0 - 2 || y >= y1 + 2) fondo.push(l); else if (x >= x0 && x < x1 && y >= y0 && y < y1) letra.push(l);
      }
      const lf = mediana(fondo);
      letra.sort((a, b) => Math.abs(b - lf) - Math.abs(a - lf));
      const fuerte = letra.slice(0, Math.max(4, Math.floor(letra.length * 0.06))), ll = mediana(fuerte);
      const c = (Math.max(lf, ll) + 0.05) / (Math.min(lf, ll) + 0.05);
      if (c < MIN_CONTRASTE) pon("poco_contraste", [t.s], `«${t.s}» casi no se distingue del fondo (contraste ${c.toFixed(1)}:1)`);
    }
  }
  return defectos;
}

(async () => {
  const args = process.argv.slice(2), rutaGuion = args[0];
  const dirCapturas = args.includes("--capturas") ? args[args.indexOf("--capturas") + 1] : null;
  const conPixeles = !args.includes("--sin-pixeles");
  const guion = JSON.parse(fs.readFileSync(rutaGuion, "utf8"));
  const W = 1080, H = 1920;
  const navegador = await chromium.launch(process.env.CHROMIUM_RUTA ? { executablePath: process.env.CHROMIUM_RUTA } : {});
  const pagina = await navegador.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const errores = [];
  pagina.on("pageerror", e => errores.push(e.message));
  await pagina.goto("file://" + path.resolve(__dirname, guion.html || "plato.html"));
  await pagina.evaluate(g => { window.GUION = g; }, guion);
  await pagina.evaluate(() => window.listo || document.fonts.ready);
  if (dirCapturas) fs.mkdirSync(dirCapturas, { recursive: true });
  const salida = new Map();
  const miniaturas = {};
  for (const { t, por } of momentos(guion)) {
    await pagina.evaluate(x => window.pintar(x), t);
    let foto = null;
    if (conPixeles || dirCapturas) foto = await pagina.screenshot({ type: "png" });
    if (dirCapturas) fs.writeFileSync(path.join(dirCapturas, `t${t.toFixed(2).padStart(6, "0")}.png`), foto);
    const hallados = await pagina.evaluate(async ({ medirTexto, W, H, b64 }) => {
      let pixeles = null, mini = null;
      if (b64) {
        const img = new Image();
        img.src = "data:image/png;base64," + b64;
        await img.decode();
        const c = document.createElement("canvas");
        c.width = W; c.height = H;
        const x = c.getContext("2d", { willReadFrequently: true });
        x.drawImage(img, 0, 0);
        pixeles = x.getImageData(0, 0, W, H);
        const m = document.createElement("canvas");
        m.width = 54; m.height = 96;
        const mx = m.getContext("2d");
        mx.drawImage(img, 0, 0, 54, 96);
        mini = Array.from(mx.getImageData(0, 0, 54, 96).data);
      }
      return { defectos: (new Function("return " + medirTexto)())({ W, H, pixeles }), mini };
    }, { medirTexto: medir.toString(), W, H, b64: conPixeles && foto ? foto.toString("base64") : null });
    if (hallados.mini) miniaturas[t] = hallados.mini;
    let n = guion.escenas.findIndex(e => t < e.fin);
    if (n < 0) n = guion.escenas.length - 1;
    for (const d of hallados.defectos) {
      const clave = `${n}|${d.tipo}|${d.textos.join("|")}`;
      if (salida.has(clave)) salida.get(clave).veces++;
      else salida.set(clave, { escena: n + 1, segundo: t, tipo: d.tipo, textos: d.textos, detalle: d.detalle, momento: por, veces: 1 });
    }
  }
  // arranque: entre el fotograma del 0,3 y el del 1,2 tiene que haber cambiado algo que se vea
  const dif = (a, b) => { let s = 0; for (let i = 0; i < a.length; i += 4) s += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]); return s / (a.length / 4 * 3); };
  const ts = Object.keys(miniaturas).map(Number);
  const cerca = x => ts.find(t => Math.abs(t - x) < 0.03);
  if (cerca(0.3) !== undefined && cerca(1.2) !== undefined && guion.duracion > 2) {
    const cambio = dif(miniaturas[cerca(0.3)], miniaturas[cerca(1.2)]);
    if (cambio < 2.0) salida.set("quieto", { escena: 1, segundo: 1.2, tipo: "arranque_quieto", textos: [], momento: "juez", veces: 1,
      detalle: `entre el segundo 0,3 y el 1,2 la imagen casi no cambia (${cambio.toFixed(1)} sobre 255): el arranque se ve quieto` });
  }
  for (const e of errores) salida.set("error|" + e, { escena: 0, segundo: 0, tipo: "error_al_dibujar", textos: [], detalle: e, momento: "", veces: 1 });
  await navegador.close();
  process.stdout.write(JSON.stringify([...salida.values()], null, 1) + "\n");
})().catch(e => { console.error(e); process.exit(1); });
