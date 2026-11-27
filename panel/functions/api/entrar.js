// POST /api/entrar {clave}: si es PANEL_CLAVE, pone la cookie «sesion» (90 días). Como mucho 10 fallos por IP y hora
// (se cuentan en el KV; solo los fallos gastan escrituras). La clave se compara en tiempo constante.

import { error, json, leerJSON, sinMetodo } from "../../lib/comun.js";
import { MAX_FALLOS, apuntarFallo, claveBuena, cookieDeSesion, fallosDe, ipDe, nuevaSesion } from "../../lib/sesion.js";

export async function onRequest({ request, env }) {
  if (request.method !== "POST") return sinMetodo("POST");
  if (!env.PANEL_CLAVE || !env.PANEL_FIRMA || !env.PANEL) return error("sin_preparar", 503);
  const ip = ipDe(request);
  try {
    if ((await fallosDe(env.PANEL, ip)) >= MAX_FALLOS) return error("demasiados", 429, { "Retry-After": "3600" });
  } catch {
    return error("ocupado", 503, { "Retry-After": "60" });
  }
  const { datos } = await leerJSON(request, 4096);
  const clave = datos && typeof datos.clave === "string" ? datos.clave : "";
  if (!(await claveBuena(clave, env))) {
    try {
      const n = await apuntarFallo(env.PANEL, ip);
      if (n >= MAX_FALLOS) return error("demasiados", 429, { "Retry-After": "3600" });
    } catch {
      // si el KV no deja apuntar, se dice que no igual
    }
    return error("clave", 401);
  }
  const sesion = await nuevaSesion(env);
  return json({ ok: true, dentro: true }, 200, { "Set-Cookie": cookieDeSesion(sesion) });
}
