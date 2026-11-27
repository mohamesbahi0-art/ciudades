// Piezas comunes del portero de la app (Cloudflare Pages Functions).
// Por aquí pasan la llave de GitHub y lo que escribe el dueño: no se escribe nada en el registro de Cloudflare (ni una
// línea de registro), y ninguna respuesta lleva la llave, cuerpos de GitHub ni mensajes de error de dentro.

export const CABECERAS_API = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json; charset=utf-8",
};

// La CSP deja lo que usa la app: sus scripts de cdnjs y jsDelivr, las letras de Google, y los vídeos y fotos que llegan
// redirigidos desde las estanterías de GitHub (las descargas firmadas viven en estos dominios).
const GITHUB_MEDIOS =
  "https://github.com https://objects.githubusercontent.com https://release-assets.githubusercontent.com";
export const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' data: https://fonts.gstatic.com",
  `img-src 'self' data: blob: ${GITHUB_MEDIOS}`,
  `media-src 'self' data: blob: ${GITHUB_MEDIOS}`,
  "connect-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

export const SEGURIDAD = {
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow",
  "Strict-Transport-Security": "max-age=31536000",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Content-Security-Policy": CSP,
};

// Algo que falta en Cloudflare (la llave, la contraseña, el KV…): el despliegue aún no lo ha puesto.
export class SinPreparar extends Error {}

// GitHub ha dicho que no o no contesta. `estado` es lo único que sale (nunca el cuerpo).
export class FalloGitHub extends Error {
  constructor(estado) {
    super("github");
    this.estado = estado;
  }
}

export function json(datos, estado = 200, extra = {}) {
  return new Response(JSON.stringify(datos), { status: estado, headers: { ...CABECERAS_API, ...extra } });
}

export function error(codigo, estado, extra = {}) {
  return json({ error: codigo }, estado, extra);
}

export function sinMetodo(permitidos) {
  return error("metodo", 405, { Allow: permitidos });
}

// Lo que se contesta cuando algo de dentro falla: un código fijo, sin detalles.
export function respuestaDeFallo(e) {
  if (e instanceof SinPreparar) return error("sin_preparar", 503);
  if (e instanceof FalloGitHub) return error(e.estado === 404 ? "no_esta" : "github", e.estado === 404 ? 404 : 502);
  return error("interno", 500);
}

export function ahora() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

// n letras minúsculas al azar (sin sesgo: 256 no es múltiplo de 26, así que se tiran los bytes de más).
export function letras(n) {
  let salida = "";
  while (salida.length < n) {
    for (const b of crypto.getRandomValues(new Uint8Array(n * 2))) {
      if (b < 234 && salida.length < n) salida += String.fromCharCode(97 + (b % 26));
    }
  }
  return salida;
}

// n bytes al azar, en base64url.
export function azar(n) {
  return aB64url(crypto.getRandomValues(new Uint8Array(n)));
}

export function aB64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Compara dos textos en tiempo constante: se comparan sus huellas SHA-256 (siempre 32 bytes) byte a byte, sin salir
// antes de tiempo, para que el tiempo de respuesta no diga cuántas letras se han acertado.
export async function mismoTexto(dado, bueno) {
  if (typeof dado !== "string" || typeof bueno !== "string" || !dado || !bueno) return false;
  const texto = new TextEncoder();
  const [x, y] = await Promise.all([dado, bueno].map((t) => crypto.subtle.digest("SHA-256", texto.encode(t))));
  const a = new Uint8Array(x);
  const b = new Uint8Array(y);
  let diferencia = 0;
  for (let i = 0; i < a.length; i++) diferencia |= a[i] ^ b[i];
  return diferencia === 0;
}

// Lee el cuerpo sin pasar de `tope` bytes (aunque no venga Content-Length). Devuelve un Uint8Array, o null si pasa.
export async function leerConTope(request, tope) {
  const largo = Number(request.headers.get("Content-Length") || "0");
  if (largo > tope) return null;
  if (!request.body) return new Uint8Array(0);
  const lector = request.body.getReader();
  const trozos = [];
  let total = 0;
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    total += value.byteLength;
    if (total > tope) {
      try {
        await lector.cancel();
      } catch {
        // da igual: ya se ha dicho que no
      }
      return null;
    }
    trozos.push(value);
  }
  const todo = new Uint8Array(total);
  let i = 0;
  for (const t of trozos) {
    todo.set(t, i);
    i += t.byteLength;
  }
  return todo;
}

// El cuerpo como JSON (un objeto), o null si no lo es o pasa del tope.
export async function leerJSON(request, tope) {
  const bytes = await leerConTope(request, tope);
  if (!bytes) return { demasiado: true };
  try {
    const datos = JSON.parse(new TextDecoder().decode(bytes));
    return datos && typeof datos === "object" && !Array.isArray(datos) ? { datos } : {};
  } catch {
    return {};
  }
}

// Una caché pequeña en la memoria del proceso (dura lo que dure ese proceso de Cloudflare).
const MEMORIA = new Map();

export function deMemoria(clave, segundos) {
  const v = MEMORIA.get(clave);
  return v && Date.now() - v.t < segundos * 1000 ? v : null;
}

export function aMemoria(clave, valor) {
  if (MEMORIA.size > 50) MEMORIA.clear();
  const v = { ...valor, t: Date.now() };
  MEMORIA.set(clave, v);
  return v;
}

export function olvidar(clave) {
  MEMORIA.delete(clave);
}

export function ultimoDeMemoria(clave) {
  return MEMORIA.get(clave) || null;
}

// Mismo origen en lo que cambia algo (POST): la cookie ya es SameSite=Strict; esto es una segunda cerradura.
export function mismoOrigen(request) {
  const origen = request.headers.get("Origin");
  if (!origen) return true;
  try {
    return new URL(origen).host === new URL(request.url).host;
  } catch {
    return false;
  }
}
