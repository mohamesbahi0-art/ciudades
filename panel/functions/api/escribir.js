// POST /api/escribir {coleccion, id, campos, crear} → {ok: true, entrada}.
// Solo lo de la lista cerrada (lib/validar.js, como en panel/API.md); lo demás, 400 {error: "no_permitido"}.
// Deja la escritura como fichero en el privado: entrada/<AAAAMMDDhhmmss>-<4 letras>.json = {coleccion, id, campos,
// crear, fecha}, y después toca peticiones/app.json del público para que el Comisario automático la aplique ya.
// (Los «errores» de la app no tocan peticiones/app.json: no corren prisa y así un fallo repetido no lanza turnos.)

import { FalloGitHub, ahora, error, json, leerJSON, letras, respuestaDeFallo, sinMetodo } from "../../lib/comun.js";
import { escribirFichero, repos, tocarPeticion } from "../../lib/github.js";
import { MAX_CUERPO_ESCRIBIR, validarEscritura } from "../../lib/validar.js";

export function nombreDeEntrada(fecha = new Date()) {
  return `${fecha.toISOString().slice(0, 19).replace(/\D/g, "")}-${letras(4)}`;
}

export async function onRequest({ request, env }) {
  if (request.method !== "POST") return sinMetodo("POST");
  const { datos, demasiado } = await leerJSON(request, MAX_CUERPO_ESCRIBIR);
  if (demasiado) return error("demasiado_grande", 413);
  const limpio = validarEscritura(datos);
  if (!limpio) return error("no_permitido", 400);
  try {
    const { privado } = repos(env);
    const contenido = JSON.stringify({ ...limpio, fecha: ahora() }, null, 1) + "\n";
    let entrada = "";
    for (let i = 0; i < 3 && !entrada; i++) {
      const nombre = nombreDeEntrada();
      const r = await escribirFichero(env, privado, `entrada/${nombre}.json`, contenido, "app: entrada del dueño");
      if (r.ok) entrada = nombre;
      else if (r.status !== 409 && r.status !== 422) throw new FalloGitHub(r.status);
    }
    if (!entrada) return error("ocupado", 503, { "Retry-After": "5" });
    let pronto = false;
    if (limpio.coleccion !== "errores") {
      try {
        pronto = await tocarPeticion(env, "peticiones/app.json");
      } catch {
        pronto = false; // la entrada ya está: el Comisario la aplica en su vuelta de cada 15 minutos
      }
    }
    return json({ ok: true, entrada, pronto });
  } catch (e) {
    return respuestaDeFallo(e);
  }
}
