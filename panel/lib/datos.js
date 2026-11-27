// Los datos que prepara el Comisario automático en el privado (app/datos/todo.json y app/datos/juicios.json).
// Nada pesado en el Worker (el plan gratis da 10 ms de CPU): el cuerpo no se lee ni se parsea, se pasa tal cual en
// streaming desde GitHub. El ETag que ve la app es el sha del blob de git del fichero, que solo cambia si cambia el
// contenido (el ETag de GitHub puede cambiar sin que cambie nada). Los sha salen de la lista de la carpeta app/datos
// (una respuesta pequeña, sin contenidos), que se guarda 30 s en la memoria y después se pregunta a GitHub con su ETag
// (si no ha cambiado, contesta 304 y no gasta cupo). El cuerpo se pide por ese sha (git/blobs en crudo): así el ETag y
// el cuerpo son siempre del mismo contenido.

import { CABECERAS_API, FalloGitHub, aMemoria, deMemoria, ultimoDeMemoria } from "./comun.js";
import { gh, repos } from "./github.js";

export const SEGUNDOS_DATOS = 30;
const CARPETA = "app/datos";
const CLAVE = "datos:carpeta";

// {nombre: sha} de los ficheros de app/datos.
export async function shas(env) {
  const fresco = deMemoria(CLAVE, SEGUNDOS_DATOS);
  if (fresco) return fresco.shas;
  const viejo = ultimoDeMemoria(CLAVE);
  const { privado } = repos(env);
  const r = await gh(env, "GET", `/repos/${privado}/contents/${CARPETA}`, {
    extra: viejo?.etag ? { "If-None-Match": viejo.etag } : {},
  });
  if (r.status === 304 && viejo) return aMemoria(CLAVE, viejo).shas;
  if (!r.ok) throw new FalloGitHub(r.status);
  const lista = await r.json();
  const valor = { etag: r.headers.get("ETag") || "", shas: {} };
  for (const f of Array.isArray(lista) ? lista : []) {
    if (f && f.type === "file" && typeof f.name === "string" && typeof f.sha === "string") valor.shas[f.name] = f.sha;
  }
  return aMemoria(CLAVE, valor).shas;
}

export function coincide(request, etag) {
  const pedido = request.headers.get("If-None-Match") || "";
  return !!etag && pedido.split(",").map((x) => x.trim().replace(/^W\//, "")).includes(etag);
}

// La respuesta entera para /api/todo y /api/juicios: 304 si la app ya lo tiene; si no, el fichero en streaming.
export async function servirDatos(request, env, nombre) {
  const sha = (await shas(env))[nombre];
  if (!sha) throw new FalloGitHub(404);
  const etag = `"${sha}"`;
  const h = { ...CABECERAS_API, "Cache-Control": "no-cache", ETag: etag };
  if (coincide(request, etag)) return new Response(null, { status: 304, headers: h });
  const { privado } = repos(env);
  const r = await gh(env, "GET", `/repos/${privado}/git/blobs/${sha}`, { accept: "application/vnd.github.raw" });
  if (!r.ok) throw new FalloGitHub(r.status);
  if (r.headers.get("Content-Length")) h["Content-Length"] = r.headers.get("Content-Length");
  return new Response(request.method === "HEAD" ? null : r.body, { status: 200, headers: h });
}
