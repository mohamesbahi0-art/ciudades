// Prueba del Ojeador: ¿qué se ve de TikTok e Instagram sin cuenta? Abre unas pocas páginas públicas con un navegador
// normal (sin entrar en ninguna cuenta, sin disfrazarse y despacio), mira si salen vídeos y cifras o un muro de «inicia
// sesión» o un captcha, y guarda una captura y el texto de cada una en el repositorio privado. Si una red bloquea, se
// respeta: no se intenta saltar.
//   node pruebas/probar_redes.js <carpeta de salida>
// En el registro público solo salen el nombre de la prueba y las cuentas (nada privado).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const salida = process.argv[2] || 'privado/pruebas/redes';
const PAGINAS = [
  ['tiktok-hashtag-es', 'https://www.tiktok.com/tag/dinero'],
  ['tiktok-hashtag-nl', 'https://www.tiktok.com/tag/wistjedat'],
  ['tiktok-explorar', 'https://www.tiktok.com/explore'],
  ['tiktok-cuenta', 'https://www.tiktok.com/@tiktok'],
  ['tiktok-centro-hashtags', 'https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/es'],
  ['tiktok-centro-videos', 'https://ads.tiktok.com/business/creativecenter/inspiration/popular/pc/es'],
  ['tiktok-centro-musica', 'https://ads.tiktok.com/business/creativecenter/inspiration/popular/music/pc/es'],
  ['instagram-hashtag', 'https://www.instagram.com/explore/tags/dinero/'],
  ['instagram-cuenta', 'https://www.instagram.com/instagram/reels/'],
];
const MURO = /inicia sesión|iniciar sesión|log in|login|sign up|regístrate|registrarte|continue with/i;
const CAPTCHA = /captcha|verify to continue|drag the slider|arrastra el|verifica que eres|security check|slide to/i;
const espera = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(salida, { recursive: true });
  const navegador = await chromium.launch();
  const contexto = await navegador.newContext({ locale: 'es-ES', viewport: { width: 1280, height: 900 } });
  const informe = [];
  for (const [nombre, url] of PAGINAS) {
    const pagina = await contexto.newPage();
    const r = { nombre, url, fecha: new Date().toISOString() };
    try {
      const resp = await pagina.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      r.http = resp ? resp.status() : null;
      await espera(8000);
      for (let i = 0; i < 3; i++) {        // bajar un poco, como quien mira
        await pagina.mouse.wheel(0, 1400);
        await espera(2500);
      }
      r.final = pagina.url();
      r.titulo = await pagina.title();
      const texto = await pagina.evaluate(() => (document.body ? document.body.innerText : ''));
      r.muro = MURO.test(texto.slice(0, 6000));
      r.captcha = CAPTCHA.test(texto.slice(0, 6000));
      r.videos = await pagina.evaluate(() => [...new Set([...document.querySelectorAll(
        'a[href*="/video/"], a[href*="/reel/"], a[href*="/p/"]')].map((a) => a.href.split('?')[0]))].slice(0, 40));
      r.cifras = (texto.match(/\b\d+(?:[.,]\d+)?\s?[KkMm]\b/g) || []).slice(0, 40);
      r.texto = texto.slice(0, 5000);
      await pagina.screenshot({ path: path.join(salida, `${nombre}.jpg`), type: 'jpeg', quality: 55 });
    } catch (e) {
      r.error = String(e).slice(0, 300);
    }
    informe.push(r);
    console.log(`${nombre}: http ${r.http ?? '-'} · vídeos ${r.videos ? r.videos.length : 0} · cifras ${r.cifras ? r.cifras.length : 0}` +
      ` · muro ${r.muro ? 'sí' : 'no'} · captcha ${r.captcha ? 'sí' : 'no'}${r.error ? ' · error al abrir' : ''}`);
    await pagina.close();
    await espera(6000);                    // despacio entre página y página
  }
  fs.writeFileSync(path.join(salida, 'informe.json'), JSON.stringify(informe, null, 1));
  await navegador.close();
})();
