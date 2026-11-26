// Graba El Show (show.html) fotograma a fotograma, sin sonido. Uso: node show.js datos.json salida.mp4 [fps]
// datos = {duracion, fotos: [rutas], palabras: [{i, f}], tramos: [{desde, hasta, emocion, accion?, foto?}]}
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

(async () => {
  const [rutaDatos, salida, fpsTexto] = process.argv.slice(2);
  const datos = JSON.parse(fs.readFileSync(rutaDatos, "utf8"));
  const fps = Number(fpsTexto) || 30;
  const navegador = await chromium.launch(Object.assign({ args: ["--allow-file-access-from-files"] },
    process.env.CHROMIUM_RUTA ? { executablePath: process.env.CHROMIUM_RUTA } : {}));
  const pagina = await navegador.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await pagina.goto("file://" + path.resolve(__dirname, "show.html"));
  await pagina.evaluate(g => { window.GUION = g; }, datos);
  await pagina.evaluate(() => window.preparar());
  await pagina.evaluate(() => document.fonts.ready);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg",
                              "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "veryfast",
                              salida], { stdio: ["pipe", "inherit", "inherit"] });
  const total = Math.ceil(datos.duracion * fps);
  for (let i = 0; i < total; i++) {
    await pagina.evaluate(t => window.pintar(t), i / fps);
    const imagen = await pagina.screenshot({ type: "jpeg", quality: 90 });
    if (!ff.stdin.write(imagen)) await new Promise(r => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  const codigo = await new Promise(r => ff.on("close", r));
  await navegador.close();
  process.exit(codigo);
})().catch(e => { console.error(e); process.exit(1); });
