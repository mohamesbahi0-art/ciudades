// POST /api/lanzar {que}: arranca un turno escribiendo su fichero de peticiones/ en el público.
//   actualizar → peticiones/app.json (el Comisario automático) · cerebro → peticiones/cerebro.json · juicio →
//   peticiones/juicio.json («Juzga mi vídeo»). Como mucho 1 cada 2 minutos por cada «que» (marca en el KV).

import { error, json, leerJSON, respuestaDeFallo, sinMetodo } from "../../lib/comun.js";
import { tocarPeticion } from "../../lib/github.js";

export const LANZAR = { actualizar: "peticiones/app.json", cerebro: "peticiones/cerebro.json",
  juicio: "peticiones/juicio.json" };
export const SEGUNDOS_ENTRE = 120;

export async function onRequest({ request, env }) {
  if (request.method !== "POST") return sinMetodo("POST");
  const { datos } = await leerJSON(request, 1024);
  const que = datos && typeof datos.que === "string" ? datos.que : "";
  if (!Object.hasOwn(LANZAR, que)) return error("no_permitido", 400);
  if (!env.PANEL) return error("sin_preparar", 503);
  const marca = `lanzar:${que}`;
  try {
    const antes = await env.PANEL.get(marca);
    if (antes) {
      const falta = Math.max(1, SEGUNDOS_ENTRE - Math.floor((Date.now() - Number(antes)) / 1000));
      return json({ error: "espera", segundos: falta }, 429, { "Retry-After": String(falta) });
    }
    await env.PANEL.put(marca, String(Date.now()), { expirationTtl: SEGUNDOS_ENTRE });
  } catch {
    return error("ocupado", 503, { "Retry-After": "60" });
  }
  try {
    const hecho = await tocarPeticion(env, LANZAR[que]);
    if (!hecho) return error("ocupado", 503, { "Retry-After": "10" });
    return json({ ok: true, que });
  } catch (e) {
    try {
      await env.PANEL.delete(marca); // no ha salido: que pueda volver a intentarlo
    } catch {
      // da igual
    }
    return respuestaDeFallo(e);
  }
}
