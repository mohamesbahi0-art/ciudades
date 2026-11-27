// POST /meta/borrado («Data deletion request URL» de la app de Meta): alguien pide que se borren sus datos.
// Apunta una marca en el KV, una por cuenta (el turno de Instagram la recoge, lo confirma y borra las copias de esa
// cuenta), y contesta lo que pide Meta: {url, confirmation_code}, con la página de borrado de esta misma web. Si Meta
// repite el aviso, contesta el mismo código sin escribir otra vez.

import { aleatorio, json } from "../../lib/comun.js";
import { apuntarMarca, leerAviso, noEsAviso } from "../../lib/meta.js";

export async function onRequest({ request, env }) {
  const otra = noEsAviso(request);
  if (otra) return otra;
  const aviso = await leerAviso(request, env.IG_APP_SECRET);
  if (!aviso) return json({ fallo: "aviso" }, 400);
  if (!env.VUELTA) return json({ fallo: "sin_preparar" }, 503);
  let marca;
  try {
    marca = await apuntarMarca(env.VUELTA, "borrado", aviso, { codigo: aleatorio(6).toUpperCase() });
  } catch {
    return json({ fallo: "ocupado" }, 503, { "Retry-After": "3600" });
  }
  return json({ url: `${new URL(request.url).origin}/borrado`, confirmation_code: marca.codigo });
}
