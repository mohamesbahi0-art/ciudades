// Las estanterías del privado: los archivos («assets») de sus «releases» de GitHub (bots/comun/almacen.py).
// El índice nombre → archivo se hace una vez cada 10 minutos (memoria del proceso y KV) y, si un nombre no está, se
// rehace una vez como mucho cada minuto, por si es un vídeo recién subido.

import { aMemoria, deMemoria, FalloGitHub } from "./comun.js";
import { gh, ghJSON, repos } from "./github.js";

export const SEGUNDOS_INDICE = 600;
const CLAVE = "indice:estanterias";
// Si dos estanterías tienen un archivo con el mismo nombre, gana la que va antes aquí.
export const PREFERENCIA = ["para-subir", "videoteca", "canales", "espera", "cola", "buzon-clips"];
const MAX_PETICIONES = 40; // Cloudflare deja 50 por visita en el plan gratis

export async function construirIndice(env) {
  const { privado } = repos(env);
  let peticiones = 0;
  const estanterias = [];
  for (let pagina = 1; pagina <= 3; pagina++) {
    peticiones++;
    const lote = await ghJSON(env, "GET", `/repos/${privado}/releases?per_page=100&page=${pagina}`);
    estanterias.push(...lote);
    if (lote.length < 100) break;
  }
  const orden = (tag) => {
    const i = PREFERENCIA.indexOf(tag);
    return i < 0 ? PREFERENCIA.length : i;
  };
  estanterias.sort((a, b) => orden(a.tag_name) - orden(b.tag_name));
  const indice = {};
  for (const e of estanterias) {
    let archivos = Array.isArray(e.assets) ? e.assets : [];
    // la lista que viene con la estantería puede ir cortada: si parece llena, se pide página a página
    if (archivos.length >= 100 || (e.assets === undefined && e.id)) {
      archivos = [];
      for (let pagina = 1; pagina <= 20 && peticiones < MAX_PETICIONES; pagina++) {
        peticiones++;
        const lote = await ghJSON(env, "GET", `/repos/${privado}/releases/${e.id}/assets?per_page=100&page=${pagina}`);
        archivos.push(...lote);
        if (lote.length < 100) break;
      }
    }
    for (const a of archivos) {
      if (a && typeof a.name === "string" && Number.isInteger(a.id) && !indice[a.name]) indice[a.name] = a.id;
    }
  }
  return indice;
}

async function leerIndice(env, forzar) {
  if (!forzar) {
    const m = deMemoria(CLAVE, SEGUNDOS_INDICE);
    if (m) return m.indice;
    try {
      const kv = env.PANEL ? await env.PANEL.get(CLAVE, "json") : null;
      if (kv && kv.indice && Date.now() - kv.t < SEGUNDOS_INDICE * 1000) return aMemoria(CLAVE, kv).indice;
    } catch {
      // sin KV se pregunta a GitHub
    }
  }
  const indice = await construirIndice(env);
  const valor = aMemoria(CLAVE, { indice });
  try {
    if (env.PANEL) await env.PANEL.put(CLAVE, JSON.stringify(valor), { expirationTtl: SEGUNDOS_INDICE * 2 });
  } catch {
    // el KV puede estar sin cupo: el índice sigue en la memoria
  }
  return indice;
}

export async function buscar(env, nombre) {
  let indice = await leerIndice(env, false);
  if (indice[nombre]) return indice[nombre];
  if (deMemoria(`${CLAVE}:rehecho`, 60)) return null;
  aMemoria(`${CLAVE}:rehecho`, {});
  indice = await leerIndice(env, true);
  return indice[nombre] || null;
}

// La dirección de descarga firmada del archivo (caduca a los pocos minutos). GitHub la da como redirección: no se
// sigue, se devuelve. Si GitHub diera el archivo directamente, se devuelve la Response para pasarla tal cual.
export async function descarga(env, id) {
  const { privado } = repos(env);
  const r = await gh(env, "GET", `/repos/${privado}/releases/assets/${id}`, {
    accept: "application/octet-stream",
    redirect: "manual",
  });
  if (r.status >= 300 && r.status < 400 && r.headers.get("Location")) return { location: r.headers.get("Location") };
  if (r.ok) return { respuesta: r };
  throw new FalloGitHub(r.status);
}
