// El portero habla con GitHub con la llave del dueño (PANEL_GH_TOKEN, solo «Contents» de los dos repositorios).
// Nada de aquí devuelve cuerpos de GitHub hacia fuera: quien llama solo ve datos ya leídos o un FalloGitHub(código).

import { Buffer } from "node:buffer";

import { FalloGitHub, SinPreparar } from "./comun.js";

const API = "https://api.github.com";
export const SUBIDAS = "https://uploads.github.com";
const AUTOR = { name: "ciudades-bot", email: "ciudades-bot@users.noreply.github.com" };

// Quién y dónde: por variables del despliegue (PANEL_DUENO sale de github.repository_owner; los nombres de los
// repositorios también los pone el despliegue). Nunca escritos a mano aquí.
export function repos(env) {
  const dueno = (env.PANEL_DUENO || "").trim();
  const privado = (env.PANEL_PRIVADO || "").trim();
  const publico = (env.PANEL_PUBLICO || "").trim();
  if (!env.PANEL_GH_TOKEN || !dueno || !privado || !publico) throw new SinPreparar();
  return { privado: `${dueno}/${privado}`, publico: `${dueno}/${publico}` };
}

function cabeceras(env, extra = {}, conLlave = true) {
  const h = {
    Accept: "application/vnd.github+json",
    "User-Agent": "panel-fabrica",
    "X-GitHub-Api-Version": "2022-11-28",
    ...extra,
  };
  if (conLlave) h.Authorization = `Bearer ${env.PANEL_GH_TOKEN}`;
  return h;
}

// Una petición a la API. Devuelve la Response tal cual (quien llama decide); si no hay red, FalloGitHub(0).
// `cuerpo` va como JSON; `crudo` (un stream o bytes) va tal cual, sin leerlo ni transformarlo (para subir vídeos).
export async function gh(env, metodo, ruta, { cuerpo, crudo, accept, extra = {}, redirect = "follow", conLlave = true,
  base = API } = {}) {
  const h = cabeceras(env, { ...(accept ? { Accept: accept } : {}), ...extra }, conLlave);
  if (cuerpo !== undefined) h["Content-Type"] = "application/json";
  const init = { method: metodo, headers: h, redirect };
  if (cuerpo !== undefined) init.body = JSON.stringify(cuerpo);
  else if (crudo !== undefined) {
    init.body = crudo;
    if (typeof ReadableStream !== "undefined" && crudo instanceof ReadableStream) init.duplex = "half";
  }
  try {
    return await fetch(base + ruta, init);
  } catch {
    throw new FalloGitHub(0);
  }
}

export async function ghJSON(env, metodo, ruta, opciones = {}) {
  const r = await gh(env, metodo, ruta, opciones);
  if (!r.ok) throw new FalloGitHub(r.status);
  try {
    return await r.json();
  } catch {
    throw new FalloGitHub(r.status);
  }
}

export function rutaDeContenido(ruta) {
  return ruta.split("/").map(encodeURIComponent).join("/");
}

// Escribe (o crea) un fichero de texto en la rama principal. `sha` es el del fichero que se cambia (null si es nuevo).
// Devuelve la Response para que quien llama mire el 409/422 (alguien lo cambió a la vez).
export function escribirFichero(env, repo, ruta, texto, mensaje, sha = null) {
  const cuerpo = {
    message: mensaje,
    content: Buffer.from(texto, "utf8").toString("base64"),
    committer: AUTOR,
    author: AUTOR,
  };
  if (sha) cuerpo.sha = sha;
  return gh(env, "PUT", `/repos/${repo}/contents/${rutaDeContenido(ruta)}`, { cuerpo });
}

// Toca un fichero de peticiones/ del público: {…extra, intento: el de antes + 1}. Si alguien lo cambió a la vez
// (409/422 por el sha), lo vuelve a leer y lo intenta otra vez. Devuelve true si quedó escrito.
export async function tocarPeticion(env, ruta, extra = {}, intentos = 4) {
  const { publico } = repos(env);
  for (let i = 0; i < intentos; i++) {
    const r = await gh(env, "GET", `/repos/${publico}/contents/${rutaDeContenido(ruta)}`);
    let sha = null;
    let antes = 0;
    if (r.ok) {
      try {
        const meta = await r.json();
        sha = meta.sha || null;
        const viejo = JSON.parse(Buffer.from(meta.content || "", "base64").toString("utf8") || "{}");
        antes = Number.isInteger(viejo.intento) ? viejo.intento : 0;
      } catch {
        antes = 0;
      }
    } else if (r.status !== 404) {
      throw new FalloGitHub(r.status);
    }
    const texto = JSON.stringify({ ...extra, intento: antes + 1 }) + "\n";
    const w = await escribirFichero(env, publico, ruta, texto, "app: aviso a los turnos", sha);
    if (w.ok) return true;
    if (w.status !== 409 && w.status !== 422) throw new FalloGitHub(w.status);
  }
  return false;
}
