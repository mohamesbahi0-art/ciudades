// El buzón de la app: la estantería (release) «buzon-app» del privado, donde el portero deja tal cual los vídeos que
// sube el dueño (<para>-<codigo>.<ext>). El Comisario automático (bots/app/comisario.py) los pasa después a su rama
// (juicio/<codigo> o buzon/<codigo>) y los quita de aquí. La estantería se crea si no existe, como en
// bots/comun/almacen.py (mismo tipo de título y nota). Todo con «Contents: write» de la llave fina.

import { FalloGitHub, aMemoria, deMemoria, olvidar } from "./comun.js";
import { SUBIDAS, gh, ghJSON, repos } from "./github.js";
import { TIPOS_VIDEO } from "./validar.js";

export const BUZON = "buzon-app";
const TITULO = "Buzón de la app (vídeos que sube el dueño)";
const NOTA = "La llenan y la vacían los robots de Las 4 Ciudades. No borres nada a mano.";
const CLAVE = "buzon:id";

export function nombreEnBuzon(para, codigo, ext) {
  return `${para}-${codigo}.${ext}`;
}

// El id de la estantería; con `crear`, la crea si no existe. null si no existe y no se pide crearla.
export async function estanteria(env, crear = false) {
  const m = deMemoria(CLAVE, 3600);
  if (m) return m.id;
  const { privado } = repos(env);
  const r = await gh(env, "GET", `/repos/${privado}/releases/tags/${BUZON}`);
  if (r.ok) return aMemoria(CLAVE, { id: (await r.json()).id }).id;
  if (r.status !== 404) throw new FalloGitHub(r.status);
  if (!crear) return null;
  const nueva = await gh(env, "POST", `/repos/${privado}/releases`, {
    cuerpo: { tag_name: BUZON, name: TITULO, body: NOTA, make_latest: "false" },
  });
  if (nueva.ok) return aMemoria(CLAVE, { id: (await nueva.json()).id }).id;
  if (nueva.status === 422) { // la ha creado otra subida a la vez
    const otra = await ghJSON(env, "GET", `/repos/${privado}/releases/tags/${BUZON}`);
    return aMemoria(CLAVE, { id: otra.id }).id;
  }
  throw new FalloGitHub(nueva.status);
}

export async function archivos(env, id) {
  const { privado } = repos(env);
  const todos = [];
  for (let pagina = 1; pagina <= 5; pagina++) {
    const lote = await ghJSON(env, "GET", `/repos/${privado}/releases/${id}/assets?per_page=100&page=${pagina}`);
    todos.push(...lote);
    if (lote.length < 100) break;
  }
  return todos;
}

// El archivo de <para>:<codigo> en el buzón (con cualquiera de las extensiones), o null.
export async function buscarEnBuzon(env, para, codigo) {
  const id = await estanteria(env, false);
  if (!id) return null;
  const nombres = new Set(Object.values(TIPOS_VIDEO).map((ext) => nombreEnBuzon(para, codigo, ext)));
  try {
    return (await archivos(env, id)).find((a) => nombres.has(a.name)) || null;
  } catch (e) {
    if (!(e instanceof FalloGitHub && e.estado === 404)) throw e;
    olvidar(CLAVE); // la estantería ya no está: no hay nada en el buzón
    return null;
  }
}

// Sube el vídeo al buzón sin leerlo: `cuerpo` es un stream que va tal cual a uploads.github.com. Antes borra lo que
// hubiera de ese mismo <para>:<codigo> (en cualquier extensión: el dueño ha vuelto a subirlo).
export async function subirAlBuzon(env, { para, codigo, ext, tipo, largo, cuerpo }) {
  const { privado } = repos(env);
  const id = await estanteria(env, true);
  const nombres = new Set(Object.values(TIPOS_VIDEO).map((e) => nombreEnBuzon(para, codigo, e)));
  for (const viejo of (await archivos(env, id)).filter((a) => nombres.has(a.name))) {
    const b = await gh(env, "DELETE", `/repos/${privado}/releases/assets/${viejo.id}`);
    if (!b.ok && b.status !== 404) throw new FalloGitHub(b.status);
  }
  const nombre = nombreEnBuzon(para, codigo, ext);
  const r = await gh(env, "POST", `/repos/${privado}/releases/${id}/assets?name=${encodeURIComponent(nombre)}`, {
    base: SUBIDAS,
    crudo: cuerpo,
    extra: { "Content-Type": tipo, "Content-Length": String(largo) },
  });
  if (!r.ok) throw new FalloGitHub(r.status);
  return nombre;
}
