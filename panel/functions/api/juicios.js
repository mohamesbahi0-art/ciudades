// GET /api/juicios: {juicios: {<id>: {...}}}, app/datos/juicios.json entero, pasado en streaming (sin leerlo).
// El Comisario automático ya lo deja en los últimos 30 días; `desde` se ignora. Lleva ETag como /api/todo.

import { respuestaDeFallo, sinMetodo } from "../../lib/comun.js";
import { servirDatos } from "../../lib/datos.js";

export async function onRequest({ request, env }) {
  if (!["GET", "HEAD"].includes(request.method)) return sinMetodo("GET, HEAD");
  try {
    return await servirDatos(request, env, "juicios.json");
  } catch (e) {
    return respuestaDeFallo(e);
  }
}
