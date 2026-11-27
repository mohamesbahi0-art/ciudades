// POST /meta/baja («Deauthorize callback URL» de la app de Meta): alguien ha quitado el permiso al Panel de cifras.
// Solo apunta una marca en el KV (una por cuenta); el turno de Instagram la recoge (/recoger?marcas=1), lo confirma
// con la API y deja de leer esa cuenta.

import { json } from "../../lib/comun.js";
import { apuntarMarca, leerAviso, noEsAviso } from "../../lib/meta.js";

export async function onRequest({ request, env }) {
  const otra = noEsAviso(request);
  if (otra) return otra;
  const aviso = await leerAviso(request, env.IG_APP_SECRET);
  if (!aviso) return json({ fallo: "aviso" }, 400);
  if (!env.VUELTA) return json({ fallo: "sin_preparar" }, 503);
  try {
    await apuntarMarca(env.VUELTA, "baja", aviso);
  } catch {
    return json({ fallo: "ocupado" }, 503, { "Retry-After": "3600" });
  }
  return json({ ok: true });
}
