// Graba el muñeco narrador (narrador.html) con fondo transparente, fotograma a fotograma, en un .mov con canal alfa.
// Uso: node narrador.js datos.json salida.mov [fps]     datos = {duracion, palabras: [{i, f}], tramos: [{desde, hasta, emocion}]}
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

(async () => {
  const [rutaDatos, salida, fpsTexto] = process.argv.slice(2);
  const datos = JSON.parse(fs.readFileSync(rutaDatos, "utf8"));
  const fps = Number(fpsTexto) || 15;
  const navegador = await chromium.launch(process.env.CHROMIUM_RUTA ? { executablePath: process.env.CHROMIUM_RUTA } : {});
  const pagina = await navegador.newPage({ viewport: { width: 460, height: 580 }, deviceScaleFactor: 1 });
  await pagina.goto("file://" + path.resolve(__dirname, "narrador.html"));
  await pagina.evaluate(g => { window.GUION = g; }, datos);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png",
                              "-i", "-", "-c:v", "qtrle", "-pix_fmt", "argb", salida], { stdio: ["pipe", "inherit", "inherit"] });
  const total = Math.ceil(datos.duracion * fps);
  for (let i = 0; i < total; i++) {
    await pagina.evaluate(t => window.pintar(t), i / fps);
    const imagen = await pagina.screenshot({ type: "png", omitBackground: true });
    if (!ff.stdin.write(imagen)) await new Promise(r => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  const codigo = await new Promise(r => ff.on("close", r));
  await navegador.close();
  process.exit(codigo);
})().catch(e => { console.error(e); process.exit(1); });
