// GET /api/turnos: los últimos 30 turnos de GitHub Actions del repositorio público:
// {turnos: [{nombre, estado, resultado, empezado, terminado}]}. Solo el nombre del turno (nunca el título del commit).
// La llave del portero solo tiene «Contents»: si GitHub no la deja leer los turnos, se pregunta sin llave (el
// repositorio es público). Se guarda 30 s en la memoria.

import { FalloGitHub, aMemoria, deMemoria, json, respuestaDeFallo, sinMetodo } from "../../lib/comun.js";
import { gh, repos } from "../../lib/github.js";

const CLAVE = "turnos";

export function resumir(datos) {
  return (datos.workflow_runs || []).slice(0, 30).map((t) => ({
    nombre: t.name || "",
    estado: t.status || "",
    resultado: t.conclusion || null,
    empezado: t.run_started_at || t.created_at || null,
    terminado: t.status === "completed" ? t.updated_at || null : null,
  }));
}

export async function onRequest({ request, env }) {
  if (request.method !== "GET") return sinMetodo("GET");
  try {
    const m = deMemoria(CLAVE, 30);
    if (m) return json({ turnos: m.turnos });
    const { publico } = repos(env);
    const ruta = `/repos/${publico}/actions/runs?per_page=30`;
    let r = await gh(env, "GET", ruta);
    if (r.status === 403 || r.status === 404 || r.status === 401) r = await gh(env, "GET", ruta, { conLlave: false });
    if (!r.ok) throw new FalloGitHub(r.status);
    const turnos = resumir(await r.json());
    aMemoria(CLAVE, { turnos });
    return json({ turnos });
  } catch (e) {
    return respuestaDeFallo(e);
  }
}
