// Dibuja el vídeo fotograma a fotograma con el navegador (escena.html) y lo pasa a ffmpeg.
// Uso: node render.js guion.json salida.mp4 [fps]
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

(async () => {
  const [rutaGuion, salida, fpsTexto] = process.argv.slice(2);
  const guion = JSON.parse(fs.readFileSync(rutaGuion, "utf8"));
  const fps = Number(fpsTexto) || 30;
  const navegador = await chromium.launch(process.env.CHROMIUM_RUTA ? { executablePath: process.env.CHROMIUM_RUTA } : {});
  const pagina = await navegador.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await pagina.goto("file://" + path.resolve(__dirname, "escena.html"));
  await pagina.evaluate(g => { window.GUION = g; }, guion);
  await pagina.evaluate(() => document.fonts.ready);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg",
                              "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "veryfast",
                              salida], { stdio: ["pipe", "inherit", "inherit"] });
  const total = Math.ceil(guion.duracion * fps);
  for (let i = 0; i < total; i++) {
    await pagina.evaluate(t => window.pintar(t), i / fps);
    const imagen = await pagina.screenshot({ type: "jpeg", quality: 92 });
    if (!ff.stdin.write(imagen)) await new Promise(r => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  const codigo = await new Promise(r => ff.on("close", r));
  await navegador.close();
  process.exit(codigo);
})().catch(e => { console.error(e); process.exit(1); });
