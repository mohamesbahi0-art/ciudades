// Todo pasa por aquí, también la app. Sin la cookie de sesión del dueño solo se ven la página de entrar
// (/entrar y lo suyo), /api/entrar y el icono; el resto de /api da 401 {error: "sin_sesion"} y el resto de la app
// manda a /entrar. A todas las respuestas se les ponen las cabeceras de seguridad (y no-store a las de /api).

import { CABECERAS_API, SEGURIDAD, error, mismoOrigen } from "../lib/comun.js";
import { dentro } from "../lib/sesion.js";

const LIBRES = new Set(["/entrar", "/entrar.html", "/api/entrar", "/robots.txt"]);
const ENTRAR = new Set(["/entrar", "/entrar.html"]);

export function esLibre(ruta) {
  return LIBRES.has(ruta) || ruta.startsWith("/favicon");
}

function irA(destino) {
  return new Response(null, { status: 302, headers: { Location: destino, "Cache-Control": "no-store" } });
}

function conCabeceras(respuesta, esApi) {
  const r = new Response(respuesta.body, respuesta); // las de next() no se dejan cambiar
  for (const [k, v] of Object.entries(SEGURIDAD)) r.headers.set(k, v);
  if (esApi) r.headers.set("Cache-Control", CABECERAS_API["Cache-Control"]);
  else if (!r.headers.has("Cache-Control")) r.headers.set("Cache-Control", "private, no-cache");
  return r;
}

export async function onRequest({ request, env, next }) {
  const ruta = new URL(request.url).pathname;
  const esApi = ruta === "/api" || ruta.startsWith("/api/");
  let respuesta;
  try {
    const conSesion = await dentro(request, env);
    if (!conSesion && !esLibre(ruta)) {
      respuesta = esApi ? error("sin_sesion", 401) : irA("/entrar");
    } else if (conSesion && ENTRAR.has(ruta) && request.method === "GET") {
      respuesta = irA("/");
    } else if (esApi && !["GET", "HEAD"].includes(request.method) && !mismoOrigen(request)) {
      respuesta = error("origen", 403);
    } else {
      respuesta = await next();
    }
  } catch {
    respuesta = esApi ? error("interno", 500) : new Response("Algo ha fallado. Prueba otra vez en un momento.",
      { status: 500, headers: { "Content-Type": "text/plain; charset=utf-8" } });
  }
  return conCabeceras(respuesta, esApi);
}
