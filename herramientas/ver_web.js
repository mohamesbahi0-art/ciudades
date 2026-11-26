// Abre una página pública de referencia que eligió el dueño (su dirección está solo en el repositorio privado) y guarda
// capturas, sus enlaces y sus imágenes más grandes, para copiar el ESTILO (nunca el contenido). Sin cuenta ni disfraces.
// Uso: node herramientas/ver_web.js <url> <carpeta>     En el registro público solo salen cifras.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

(async () => {
  const [url, carpeta] = process.argv.slice(2);
  fs.mkdirSync(carpeta, { recursive: true });
  const nav = await chromium.launch();
  const pag = await nav.newPage({ viewport: { width: 1280, height: 1600 } });
  let estado = "ok";
  try { await pag.goto(url, { waitUntil: "networkidle", timeout: 60000 }); } catch (e) { estado = String(e).slice(0, 200); }
  await pag.waitForTimeout(3000);
  const alto = await pag.evaluate(() => document.documentElement.scrollHeight).catch(() => 1600);
  let n = 0;
  for (let y = 0; y < Math.min(alto, 15000) && n < 10; y += 1500) {
    await pag.evaluate(v => window.scrollTo(0, v), y).catch(() => {});
    await pag.waitForTimeout(900);
    await pag.screenshot({ path: path.join(carpeta, `web-${++n}.jpg`), type: "jpeg", quality: 78 }).catch(() => {});
  }
  const datos = await pag.evaluate(() => ({
    titulo: document.title,
    texto: document.body.innerText.slice(0, 8000),
    enlaces: [...document.querySelectorAll("a[href]")].map(a => a.href).filter((v, i, l) => l.indexOf(v) === i).slice(0, 200),
    imagenes: [...document.querySelectorAll("img")].map(i => ({ src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, alt: i.alt }))
      .filter(i => i.w >= 200 && i.src.startsWith("http")).slice(0, 80),
    videos: [...document.querySelectorAll("video, video source, iframe")].map(v => v.currentSrc || v.src).filter(Boolean).slice(0, 30),
  })).catch(() => ({ titulo: "", texto: "", enlaces: [], imagenes: [], videos: [] }));
  let k = 0;
  const vistas = new Set();
  for (const im of datos.imagenes.sort((a, b) => b.w * b.h - a.w * a.h)) {
    if (k >= 14 || vistas.has(im.src)) continue;
    vistas.add(im.src);
    try {
      const r = await pag.request.get(im.src, { timeout: 30000 });
      const cuerpo = r.ok() ? await r.body() : null;
      if (!cuerpo || cuerpo.length > 3_000_000) continue;
      const ext = (im.src.split("?")[0].split(".").pop() || "jpg").toLowerCase();
      fs.writeFileSync(path.join(carpeta, `img-${++k}.${/^(png|jpe?g|webp|gif|svg|avif)$/.test(ext) ? ext : "jpg"}`), cuerpo);
    } catch (e) { /* esa imagen no se deja bajar: se salta */ }
  }
  fs.writeFileSync(path.join(carpeta, "web.json"), JSON.stringify({ estado, ...datos }, null, 1));
  await nav.close();
  console.log(`capturas: ${n}, enlaces: ${datos.enlaces.length}, imágenes guardadas: ${k}, vídeos: ${datos.videos.length}`);
})().catch(e => { console.error(String(e).slice(0, 200)); process.exit(1); });
