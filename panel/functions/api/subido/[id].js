// GET /api/subido/<para>:<codigo>: el vídeo que subió el dueño con /api/subir.
// 1) Si sigue en la estantería «buzon-app» del privado: 302 a su descarga firmada, como /api/video.
// 2) Si el Comisario automático ya lo ha pasado a su rama (juicio/<codigo> o buzon/<codigo>): el fichero de la rama en
//    crudo y en streaming, sin transformarlo (con la cabecera Range, para que el móvil pueda ir saltando).
// Cuando la fábrica ya lo ha usado y ha borrado la rama, 404.

import { FalloGitHub, error, respuestaDeFallo, sinMetodo } from "../../../lib/comun.js";
import { buscarEnBuzon } from "../../../lib/buzon.js";
import { descarga } from "../../../lib/estanterias.js";
import { gh, ghJSON, repos } from "../../../lib/github.js";
import { CODIGO_VALIDO, DESTINOS, TIPOS_VIDEO } from "../../../lib/validar.js";

const TIPO_DE_EXT = Object.fromEntries(Object.entries(TIPOS_VIDEO).map(([t, e]) => [e, t]));

export function leerId(texto) {
  let id = String(texto || "");
  try {
    id = decodeURIComponent(id);
  } catch {
    return null;
  }
  const m = /^(propios|clips):([A-Za-z0-9_-]{1,64})$/.exec(id);
  return m && CODIGO_VALIDO.test(m[2]) ? { para: m[1], codigo: m[2] } : null;
}

export async function onRequest({ request, env, params }) {
  if (!["GET", "HEAD"].includes(request.method)) return sinMetodo("GET, HEAD");
  const id = leerId(Array.isArray(params.id) ? params.id.join("/") : params.id);
  if (!id) return error("id", 400);
  try {
    const enBuzon = await buscarEnBuzon(env, id.para, id.codigo);
    if (enBuzon) {
      const d = await descarga(env, enBuzon.id);
      if (d.location) return new Response(null, { status: 302, headers: { Location: d.location, "Cache-Control": "no-store" } });
      return new Response(request.method === "HEAD" ? null : d.respuesta.body, { status: 200, headers: {
        "Content-Type": enBuzon.content_type || "application/octet-stream", "Cache-Control": "private, max-age=300" } });
    }
    const { privado } = repos(env);
    const rama = `${DESTINOS[id.para]}/${id.codigo}`;
    let arbol; // lo que hay en la raíz de la rama
    try {
      arbol = await ghJSON(env, "GET", `/repos/${privado}/contents/?ref=${encodeURIComponent(rama)}`);
    } catch (e) {
      if (e instanceof FalloGitHub && (e.estado === 404 || e.estado === 409 || e.estado === 422)) {
        return error("no_esta", 404);
      }
      throw e;
    }
    const fichero = (Array.isArray(arbol) ? arbol : []).find((f) => f.type === "file" &&
      Object.keys(TIPO_DE_EXT).some((ext) => f.path === `${id.codigo}.${ext}`));
    if (!fichero) return error("no_esta", 404);
    const ext = fichero.path.split(".").pop();
    const extra = request.headers.get("Range") ? { Range: request.headers.get("Range") } : {};
    const r = await gh(env, "GET",
      `/repos/${privado}/contents/${encodeURIComponent(fichero.path)}?ref=${encodeURIComponent(rama)}`,
      { accept: "application/vnd.github.raw", extra });
    if (r.status === 404) return error("no_esta", 404);
    if (!r.ok) throw new FalloGitHub(r.status);
    const h = { "Content-Type": TIPO_DE_EXT[ext], "Cache-Control": "private, max-age=300", "Accept-Ranges": "bytes" };
    for (const k of ["Content-Length", "Content-Range"]) if (r.headers.get(k)) h[k] = r.headers.get(k);
    return new Response(request.method === "HEAD" ? null : r.body, { status: r.status === 206 ? 206 : 200, headers: h });
  } catch (e) {
    return respuestaDeFallo(e);
  }
}
