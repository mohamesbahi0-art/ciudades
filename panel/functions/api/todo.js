// GET /api/todo: {actualizado, colecciones: {...}} tal cual lo deja el Comisario automático en app/datos/todo.json
// del privado, pasado en streaming (sin leerlo). Lleva ETag (el sha del fichero): con If-None-Match igual, 304.

import { respuestaDeFallo, sinMetodo } from "../../lib/comun.js";
import { servirDatos } from "../../lib/datos.js";

export async function onRequest({ request, env }) {
  if (!["GET", "HEAD"].includes(request.method)) return sinMetodo("GET, HEAD");
  try {
    return await servirDatos(request, env, "todo.json");
  } catch (e) {
    return respuestaDeFallo(e);
  }
}
