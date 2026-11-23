// El Ojeador de redes (ciudad de los Influencers): sus «ojos». Abre páginas públicas de TikTok e Instagram como alguien
// que mira el móvil sin cuenta: entra, baja despacio, se para, cambia de categoría y descansa entre página y página.
// No entra en ninguna cuenta, no se disfraza y no se salta nada: si una red dice que no (captcha, «inténtalo más
// tarde», 403/429), apunta «bloqueada» y sigue con otra cosa.
//
//   node bots/influencers/ojeador.js plan.json salida.json
//   plan.json: {"pasos": [{"id": "tiktok-explorar", "url": "...", "categorias": ["Todo", "Educación"], "rondas": 3}]}
//
// En el registro público solo sale el id de cada paso (con alias, nunca nombres de cuentas) y cuántos vídeos ha visto.
const { chromium } = require('playwright');
const fs = require('fs');

const NO_DEJA = /hubo un problema|inténtalo de nuevo más tarde|something went wrong|try again later|captcha|verify to continue|drag the slider|security check|slide to verify|please wait a few minutes|demasiadas solicitudes|too many requests/i;
const CIFRA = /(\d+(?:[.,]\d+)?)\s?(K|M|B|mil|mill\.?)(?![a-z])/i;

const espera = (min, max) => new Promise((r) => setTimeout(r, min + Math.random() * ((max || min) - min)));

async function bajar(pagina, veces) {
  for (let i = 0; i < veces; i++) {          // baja un poco, se para a mirar y sigue
    await pagina.mouse.wheel(0, 700 + Math.random() * 900);
    await espera(2200, 5200);
  }
}

async function recoger(pagina) {
  return pagina.evaluate((patron) => {
    const cifra = new RegExp(patron, 'i');
    const vistos = new Map();
    for (const a of document.querySelectorAll('a[href*="/video/"], a[href*="/reel/"], a[href*="/p/"]')) {
      const url = a.href.split('?')[0];
      if (vistos.has(url)) continue;
      let caja = a;
      for (let n = 0; n < 4 && caja.parentElement && (caja.innerText || '').trim().length < 12; n++) caja = caja.parentElement;
      const texto = (caja.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160);
      const m = texto.match(cifra);
      vistos.set(url, { url, texto, cifra: m ? m[0] : null });
    }
    return [...vistos.values()].slice(0, 60);
  }, CIFRA.source);
}

(async () => {
  const plan = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const salida = { fecha: new Date().toISOString(), pasos: [] };
  const navegador = await chromium.launch();
  const contexto = await navegador.newContext({ locale: plan.idioma || 'es-ES', timezoneId: 'Europe/Madrid',
    viewport: { width: 1280, height: 900 } });
  for (const paso of plan.pasos) {
    const r = { id: paso.id, estado: 'bien', videos: [] };
    const pagina = await contexto.newPage();
    try {
      const resp = await pagina.goto(paso.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      r.http = resp ? resp.status() : null;
      await espera(6000, 9000);
      if (r.http && r.http >= 400) {
        r.estado = 'bloqueada';
        r.motivo = `http ${r.http}`;
      }
      const categorias = paso.categorias && paso.categorias.length ? paso.categorias : [null];
      for (const categoria of categorias) {
        if (r.estado !== 'bien') break;
        if (categoria && categoria !== 'Todo') {        // pulsa la categoría, como haría una persona
          const boton = pagina.getByText(categoria, { exact: true }).first();
          if (!(await boton.count())) {
            r.faltan = (r.faltan || []).concat(categoria);
            continue;
          }
          await boton.click({ timeout: 8000 }).catch(() => {});
          await espera(4000, 7000);
        }
        await bajar(pagina, paso.rondas || 3);
        const texto = await pagina.evaluate(() => (document.body ? document.body.innerText : '').slice(0, 6000));
        const encontrados = await recoger(pagina);
        if (!encontrados.length && NO_DEJA.test(texto)) {
          r.estado = 'bloqueada';
          r.motivo = (texto.match(NO_DEJA) || [''])[0];
          break;
        }
        for (const v of encontrados) {
          if (!r.videos.find((x) => x.url === v.url)) r.videos.push(Object.assign(v, { categoria: categoria || null }));
        }
      }
      if (r.estado === 'bien' && !r.videos.length) r.estado = 'vacia';
    } catch (e) {
      r.estado = 'error';
      r.motivo = String(e).slice(0, 200);
    }
    await pagina.close();
    salida.pasos.push(r);
    console.log(`ojeador: ${r.id}: ${r.estado}${r.http ? ` (http ${r.http})` : ''} · ${r.videos.length} vídeos`);
    await espera(8000, 16000);                   // descansa entre página y página, como quien deja el móvil un rato
  }
  await navegador.close();
  fs.writeFileSync(process.argv[3], JSON.stringify(salida, null, 1));
})();
