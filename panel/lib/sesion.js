// La sesión del dueño: una cookie «sesion» firmada con HMAC-SHA256.
//
//   sesion = v1.<caduca (segundos)>.<azar>.<firma>
//
// La clave de la firma sale de PANEL_FIRMA (un secreto al azar que crea el despliegue) y de PANEL_CLAVE (la contraseña
// del dueño): si el dueño cambia la contraseña, todas las sesiones viejas dejan de valer. La comprobación de la firma la
// hace crypto.subtle.verify, que compara en tiempo constante.

import { aB64url, azar, mismoTexto } from "./comun.js";

export const SEGUNDOS_SESION = 90 * 24 * 3600;
export const MAX_FALLOS = 10; // intentos fallidos por IP y hora

const VERSION = "v1";
const CLAVES = new Map(); // la clave derivada, por proceso

async function claveDeFirma(env) {
  const firma = env.PANEL_FIRMA || "";
  const clave = env.PANEL_CLAVE || "";
  if (!firma || !clave) return null;
  const id = await huella(`${firma}\n${clave}`);
  if (CLAVES.has(id)) return CLAVES.get(id);
  const texto = new TextEncoder();
  const madre = await crypto.subtle.importKey("raw", texto.encode(firma), { name: "HMAC", hash: "SHA-256" }, false,
    ["sign"]);
  const derivada = await crypto.subtle.sign("HMAC", madre, texto.encode(`sesion:${clave}`));
  const k = await crypto.subtle.importKey("raw", derivada, { name: "HMAC", hash: "SHA-256" }, false,
    ["sign", "verify"]);
  if (CLAVES.size > 4) CLAVES.clear();
  CLAVES.set(id, k);
  return k;
}

async function huella(texto) {
  return aB64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto)));
}

function b64urlABytes(texto) {
  const b = texto.replace(/-/g, "+").replace(/_/g, "/");
  const s = atob(b + "=".repeat((4 - (b.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

export async function nuevaSesion(env, ahoraMs = Date.now()) {
  const k = await claveDeFirma(env);
  if (!k) return null;
  const caduca = Math.floor(ahoraMs / 1000) + SEGUNDOS_SESION;
  const cuerpo = `${VERSION}.${caduca}.${azar(18)}`;
  const firma = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(cuerpo));
  return `${cuerpo}.${aB64url(firma)}`;
}

export async function sesionValida(valor, env, ahoraMs = Date.now()) {
  if (typeof valor !== "string" || valor.length > 200) return false;
  const m = /^(v1)\.(\d{1,12})\.([A-Za-z0-9_-]{16,64})\.([A-Za-z0-9_-]{43})$/.exec(valor);
  if (!m) return false;
  if (Number(m[2]) * 1000 <= ahoraMs) return false;
  const k = await claveDeFirma(env);
  if (!k) return false;
  try {
    return await crypto.subtle.verify("HMAC", k, b64urlABytes(m[4]), new TextEncoder().encode(`${m[1]}.${m[2]}.${m[3]}`));
  } catch {
    return false;
  }
}

export function leerCookie(request, nombre = "sesion") {
  const texto = request.headers.get("Cookie") || "";
  for (const trozo of texto.split(";")) {
    const i = trozo.indexOf("=");
    if (i > 0 && trozo.slice(0, i).trim() === nombre) return trozo.slice(i + 1).trim();
  }
  return "";
}

export async function dentro(request, env) {
  return sesionValida(leerCookie(request), env);
}

export function cookieDeSesion(valor) {
  return `sesion=${valor}; Path=/; Max-Age=${SEGUNDOS_SESION}; HttpOnly; Secure; SameSite=Strict`;
}

export function cookieBorrada() {
  return "sesion=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict";
}

export async function claveBuena(dada, env) {
  return mismoTexto(dada, env.PANEL_CLAVE || "");
}

// El tope de intentos: una cuenta por IP (su huella, nunca la IP tal cual) y por hora, en el KV. Solo los fallos
// gastan escrituras.
function claveDeFallos(ip, ahoraMs) {
  const hora = new Date(ahoraMs).toISOString().slice(0, 13).replace(/\D/g, "");
  return huella(`ip:${ip}`).then((h) => `fallos:${hora}:${h.slice(0, 22)}`);
}

export function ipDe(request) {
  return request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "sin-ip";
}

export async function fallosDe(kv, ip, ahoraMs = Date.now()) {
  const n = Number(await kv.get(await claveDeFallos(ip, ahoraMs)));
  return Number.isFinite(n) ? n : 0;
}

export async function apuntarFallo(kv, ip, ahoraMs = Date.now()) {
  const clave = await claveDeFallos(ip, ahoraMs);
  const n = Number(await kv.get(clave)) || 0;
  await kv.put(clave, String(n + 1), { expirationTtl: 3600 });
  return n + 1;
}
