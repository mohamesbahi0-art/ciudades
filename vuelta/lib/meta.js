// Avisos de Meta (Instagram): «el usuario ha quitado el permiso» (/meta/baja) y «quiere que borremos sus datos»
// (/meta/borrado). Llegan como POST con signed_request=<firma>.<datos>.
// - Si el proyecto tiene el secreto IG_APP_SECRET (lo pone el turno de despliegue), se comprueba la firma
//   HMAC-SHA256 y lo que no venga firmado por Meta se tira SIN escribir nada en el KV (así nadie gasta su cupo).
// - Sin ese secreto, se apunta sin comprobar («sin_comprobar»), pero solo una marca por cuenta y tipo
//   (marca:<tipo>:<usuario>): repetir el aviso no gasta más escrituras.
// En los dos casos el turno de Instagram confirma con la API antes de borrar nada. Las marcas se recogen con
// GET /recoger?marcas=1 (con VUELTA_LLAVE).

import { SEGUNDOS_MARCA, ahora, pagina, sinMetodo } from "./comun.js";

const MAXIMO = 16384; // un aviso de Meta ocupa muy poco: lo que pase de aquí no es de Meta
const texto = new TextEncoder();

// Lo que no es un aviso: GET y HEAD contestan 200 (por si Meta mira que la dirección existe al guardarla en el panel),
// y cualquier otro método que no sea POST, 405. Si es un POST, devuelve null y sigue el aviso.
export function noEsAviso(request) {
  const metodo = request.method;
  if (metodo === "GET" || metodo === "HEAD") {
    return pagina("Avisos de Meta", "Esta dirección solo recibe avisos de Instagram.", 200, metodo);
  }
  return metodo === "POST" ? null : sinMetodo("GET, HEAD, POST");
}

function bytesDeBase64Url(trozo) {
  const base = trozo.replace(/-/g, "+").replace(/_/g, "/");
  const binario = atob(base + "=".repeat((4 - (base.length % 4)) % 4));
  return Uint8Array.from(binario, (c) => c.charCodeAt(0));
}

function firmadoDe(cuerpo) {
  const firmado = new URLSearchParams(cuerpo).get("signed_request");
  if (firmado || !cuerpo.trim().startsWith("{")) return firmado;
  try {
    return JSON.parse(cuerpo).signed_request;
  } catch {
    return null;
  }
}

// ¿La firma es la que haría Meta con la llave de la app? (HMAC-SHA256 de la parte de los datos, tal cual llega).
// crypto.subtle.verify compara sin salir antes de tiempo.
async function firmaBuena(firma, datos, secreto) {
  let bytes;
  try {
    bytes = bytesDeBase64Url(firma);
  } catch {
    return false;
  }
  const llave = await crypto.subtle.importKey("raw", texto.encode(secreto), { name: "HMAC", hash: "SHA-256" },
    false, ["verify"]);
  return crypto.subtle.verify("HMAC", llave, bytes, texto.encode(datos));
}

// Devuelve {usuario, comprobado} si es un aviso de Meta (con su firma buena, si hay secreto); si no, null.
export async function leerAviso(request, secreto) {
  if (Number(request.headers.get("Content-Length") || 0) > MAXIMO) return null;
  const cuerpo = await request.text();
  if (cuerpo.length > MAXIMO) return null;
  const firmado = firmadoDe(cuerpo);
  if (typeof firmado !== "string") return null;
  const partes = firmado.split(".");
  if (partes.length !== 2 || !partes[0] || !partes[1]) return null;
  if (secreto && !(await firmaBuena(partes[0], partes[1], secreto))) return null;
  let carga;
  try {
    carga = JSON.parse(new TextDecoder().decode(bytesDeBase64Url(partes[1])));
  } catch {
    return null;
  }
  if (!carga || String(carga.algorithm || "").toUpperCase() !== "HMAC-SHA256") return null;
  const usuario = String(carga.user_id ?? "");
  if (!/^\d{1,32}$/.test(usuario)) return null;
  return { usuario, comprobado: Boolean(secreto) };
}

// Apunta la marca del aviso, una sola por cuenta y tipo: si ya está, no se escribe otra vez y se devuelve la que había.
// Si el KV falla (por ejemplo, se ha gastado el cupo de escrituras del día), lanza: quien llama contesta «inténtalo
// dentro de un rato» sin enseñar nada.
export async function apuntarMarca(kv, tipo, aviso, extra = {}) {
  const clave = `marca:${tipo}:${aviso.usuario}`;
  const antes = await kv.get(clave, { type: "json" });
  if (antes) return antes;
  const marca = { tipo, hora: ahora(), usuario: aviso.usuario, sin_comprobar: !aviso.comprobado, ...extra };
  await kv.put(clave, JSON.stringify(marca), { expirationTtl: SEGUNDOS_MARCA });
  return marca;
}

// Saca (y borra) las marcas pendientes, como mucho 50 por llamada. Si el KV falla, lanza.
export async function sacarMarcas(kv) {
  const lista = await kv.list({ prefix: "marca:", limit: 50 });
  const marcas = [];
  for (const { name } of lista.keys) {
    const guardado = await kv.get(name);
    if (guardado !== null) {
      try {
        marcas.push(JSON.parse(guardado));
      } catch {
        // una marca rota no se devuelve, pero se borra igual
      }
    }
    await kv.delete(name);
  }
  return marcas;
}
