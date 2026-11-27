// GET /recoger?state=<state> con «Authorization: Bearer <VUELTA_LLAVE>»: lo usa el turno de conectar para recoger lo
// que dejó Instagram en el buzón. Devuelve el JSON guardado ({red, code, error, hora}) y lo borra: sirve una sola vez.
//   200 → la respuesta · 404 {"pendiente": true} → aún no ha llegado · 401 → llave mala · 400 → state mal escrito
// GET /recoger?marcas=1 (misma llave) → {"marcas": [...]}: los avisos de Meta (baja o borrado) pendientes, y los borra.
// Las respuestas que no son 200 llevan «fallo», nunca «error», para no confundirlas con el error que manda Instagram.
// Si el KV falla: 503 {"fallo": "kv"} (el turno de conectar sigue esperando y lo vuelve a pedir).

import { ESTADO_VALIDO, json, llaveDe, mismaLlave, sinMetodo } from "../lib/comun.js";
import { sacarMarcas } from "../lib/meta.js";

async function sacarRespuesta(kv, estado) {
  const clave = `vuelta:${estado}`;
  const texto = await kv.get(clave);
  if (texto === null) return json({ pendiente: true }, 404);
  await kv.delete(clave);
  return json(JSON.parse(texto));
}

export async function onRequest({ request, env }) {
  if (request.method !== "GET") return sinMetodo("GET");
  if (!env.VUELTA_LLAVE || !env.VUELTA) return json({ fallo: "sin_preparar" }, 503);
  if (!(await mismaLlave(llaveDe(request), env.VUELTA_LLAVE))) return json({ fallo: "llave" }, 401);
  const url = new URL(request.url);
  const marcas = url.searchParams.get("marcas") === "1";
  const estado = url.searchParams.get("state") || "";
  if (!marcas && !ESTADO_VALIDO.test(estado)) return json({ fallo: "state" }, 400);
  try {
    return marcas ? json({ marcas: await sacarMarcas(env.VUELTA) }) : await sacarRespuesta(env.VUELTA, estado);
  } catch {
    return json({ fallo: "kv" }, 503, { "Retry-After": "60" });
  }
}
