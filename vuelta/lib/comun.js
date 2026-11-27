// Piezas comunes del Buzón de vuelta (Cloudflare Pages Functions).
// Por aquí pasan códigos de permiso: no se escribe nada en el registro de Cloudflare, y ninguna página enseña el
// código ni el «state».

export const ESTADO_VALIDO = /^[A-Za-z0-9_-]{20,64}$/;
export const SEGUNDOS_VUELTA = 900; // lo que dura una respuesta en el buzón (15 minutos)
export const SEGUNDOS_MARCA = 30 * 24 * 3600; // lo que dura un aviso de Meta (baja o borrado) sin recoger

const CABECERAS = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-Robots-Tag": "noindex, nofollow",
};

const ESTILO = `body{margin:0;font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:#f4f6f8;color:#1c2733}
main{max-width:34rem;margin:0 auto;padding:3rem 1rem}h1{font-size:1.5rem;line-height:1.25;margin:0 0 .75rem}
p{margin:0 0 1rem}footer{margin-top:2.5rem;font-size:.9rem;color:#5b6b7b}a{color:#1d5fa8}
@media (prefers-color-scheme:dark){body{background:#121a22;color:#e5ebf0}footer{color:#9fb0c0}a{color:#7fb6ff}}`;

// Quita del historial del navegador la dirección con el código (no se ve en la barra ni al volver atrás).
const LIMPIAR_DIRECCION = `history.replaceState(null,"",location.pathname)`;

export function escapar(texto) {
  return String(texto).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function json(datos, estado = 200, extra = {}) {
  return new Response(JSON.stringify(datos), {
    status: estado,
    headers: { ...CABECERAS, "Content-Type": "application/json; charset=utf-8", ...extra },
  });
}

export function sinMetodo(permitidos) {
  return json({ fallo: "metodo" }, 405, { Allow: permitidos });
}

// Página sencilla para el navegador del dueño. Solo lleva textos fijos (nunca nada que venga en la dirección).
export function pagina(titulo, texto, estado = 200, metodo = "GET") {
  const html = `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapar(titulo)} · Panel de cifras</title>
<link rel="icon" href="/icono.png"><style>${ESTILO}</style><script>${LIMPIAR_DIRECCION}</script></head>
<body><main><h1>${escapar(titulo)}</h1><p>${escapar(texto)}</p>
<footer>Panel de cifras · <a href="/">Qué es</a> · <a href="/privacidad">Privacidad</a></footer></main></body></html>`;
  return new Response(metodo === "HEAD" ? null : html, {
    status: estado,
    headers: {
      ...CABECERAS,
      "Content-Type": "text/html; charset=utf-8",
      "Content-Security-Policy":
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self'; " +
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    },
  });
}

export function ahora() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

// n bytes al azar, en hexadecimal (2n caracteres).
export function aleatorio(n) {
  const bytes = crypto.getRandomValues(new Uint8Array(n));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function llaveDe(request) {
  const m = /^Bearer\s+(\S+)$/.exec(request.headers.get("Authorization") || "");
  return m ? m[1] : "";
}

// Compara dos llaves en tiempo constante: se comparan sus huellas SHA-256 (siempre 32 bytes) byte a byte, sin salir
// antes de tiempo, para que el tiempo de respuesta no diga cuántas letras se han acertado.
export async function mismaLlave(dada, buena) {
  if (!dada || !buena) return false;
  const texto = new TextEncoder();
  const [x, y] = await Promise.all(
    [dada, buena].map((t) => crypto.subtle.digest("SHA-256", texto.encode(t))),
  );
  const a = new Uint8Array(x);
  const b = new Uint8Array(y);
  let diferencia = 0;
  for (let i = 0; i < a.length; i++) diferencia |= a[i] ^ b[i];
  return diferencia === 0;
}
