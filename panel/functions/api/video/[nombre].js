// GET /api/video/<nombre>: un vídeo o una foto de las estanterías del privado («para-subir», «videoteca»,
// «canales»…). Redirige 302 a la descarga firmada de GitHub (caduca a los pocos minutos). `nombre` es el final del
// enlace `video`/`videoGithub` de la app. Con ?descargar=1 la descarga lleva el nombre del fichero (la de GitHub ya
// lo lleva siempre).

import { error, respuestaDeFallo, sinMetodo } from "../../../lib/comun.js";
import { buscar, descarga } from "../../../lib/estanterias.js";

export const NOMBRE_VALIDO = /^[A-Za-z0-9][A-Za-z0-9._@+-]{0,199}$/;

const TIPOS = { mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm", jpg: "image/jpeg", jpeg: "image/jpeg",
  png: "image/png", webp: "image/webp", mp3: "audio/mpeg", m4a: "audio/mp4", json: "application/json" };

export async function onRequest({ request, env, params }) {
  if (!["GET", "HEAD"].includes(request.method)) return sinMetodo("GET, HEAD");
  let nombre = Array.isArray(params.nombre) ? params.nombre.join("/") : String(params.nombre || "");
  try {
    nombre = decodeURIComponent(nombre);
  } catch {
    return error("nombre", 400);
  }
  if (!NOMBRE_VALIDO.test(nombre) || nombre.includes("..")) return error("nombre", 400);
  try {
    const id = await buscar(env, nombre);
    if (!id) return error("no_esta", 404);
    const d = await descarga(env, id);
    if (d.location) return new Response(null, { status: 302, headers: { Location: d.location, "Cache-Control": "no-store" } });
    const ext = nombre.split(".").pop().toLowerCase();
    const h = { "Content-Type": TIPOS[ext] || "application/octet-stream", "Cache-Control": "private, max-age=300" };
    if (new URL(request.url).searchParams.get("descargar") === "1") h["Content-Disposition"] = `attachment; filename="${nombre}"`;
    const largo = d.respuesta.headers.get("Content-Length");
    if (largo) h["Content-Length"] = largo;
    return new Response(request.method === "HEAD" ? null : d.respuesta.body, { status: 200, headers: h });
  } catch (e) {
    return respuestaDeFallo(e);
  }
}
