// Simulacro del portero de la app (panel/), sin red y sin Cloudflare: un KV de mentira, un GitHub de mentira (fetch
// simulado) y peticiones de mentira. Comprueba la sesión (buena, mala, caducada y firmada con otra clave), el tope de
// 10 fallos por IP y hora, que sin sesión todo da 401 o manda a /entrar, /api/todo y /api/juicios en streaming con el
// sha del blob como ETag (y el 304 aunque cambie el ETag de GitHub), el 302 de /api/video, la lista cerrada de
// /api/escribir (colección, campo, valor y tamaño), /api/subir (tipo, tamaño, que sea de verdad un vídeo, y que va tal
// cual, como stream, a la estantería «buzon-app»), /api/subido (buzón o rama), el tope de /api/lanzar, y que la llave
// de GitHub no sale nunca en una respuesta (ni los cuerpos de GitHub cuando falla). Tampoco puede haber console.log.
//
//     node pruebas/simulacro_panel.mjs

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { olvidar } from "../panel/lib/comun.js";
import { cookieDeSesion, nuevaSesion, sesionValida } from "../panel/lib/sesion.js";
import { onRequest as portero } from "../panel/functions/_middleware.js";
import { onRequest as entrar } from "../panel/functions/api/entrar.js";
import { onRequest as salir } from "../panel/functions/api/salir.js";
import { onRequest as yo } from "../panel/functions/api/yo.js";
import { onRequest as todo } from "../panel/functions/api/todo.js";
import { onRequest as juicios } from "../panel/functions/api/juicios.js";
import { onRequest as video } from "../panel/functions/api/video/[nombre].js";
import { onRequest as subido } from "../panel/functions/api/subido/[id].js";
import { onRequest as turnos } from "../panel/functions/api/turnos.js";
import { onRequest as escribir } from "../panel/functions/api/escribir.js";
import { onRequest as subir } from "../panel/functions/api/subir.js";
import { onRequest as lanzar } from "../panel/functions/api/lanzar.js";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "panel");
const WEB = "https://panel-de-prueba.pages.dev";
const LLAVE = "github_pat_LLAVE_DE_PRUEBA_0123456789abcdefghijklmnopqrstuvwxyz";
const CLAVE = "contraseña-del-dueño-1234";
const DUENO = "duenoprueba";
const PRIV = `${DUENO}/memoria-prueba`;
const PUB = `${DUENO}/publico-prueba`;

class KVFalso {
  constructor() {
    this.datos = new Map();
    this.escrituras = 0;
  }
  async get(clave, opciones) {
    const v = this.datos.has(clave) ? this.datos.get(clave).valor : null;
    const tipo = typeof opciones === "string" ? opciones : opciones?.type;
    return v !== null && tipo === "json" ? JSON.parse(v) : v;
  }
  async put(clave, valor, opciones = {}) {
    this.escrituras++;
    this.datos.set(clave, { valor, ttl: opciones.expirationTtl });
  }
  async delete(clave) {
    this.datos.delete(clave);
  }
}

function entorno(extra = {}) {
  return { PANEL: new KVFalso(), PANEL_CLAVE: CLAVE, PANEL_FIRMA: "firma-de-prueba-muy-larga-0123456789",
    PANEL_GH_TOKEN: LLAVE, PANEL_DUENO: DUENO, PANEL_PRIVADO: "memoria-prueba", PANEL_PUBLICO: "publico-prueba",
    ...extra };
}

// --- El GitHub de mentira ---
const b64 = (t) => Buffer.from(t).toString("base64");

// El sha de git de un contenido (como lo da GitHub): sha1 de "blob <largo>\0<contenido>".
const shaGit = (texto) => createHash("sha1").update(`blob ${Buffer.byteLength(texto)}\0`).update(texto).digest("hex");

class GitHubFalso {
  constructor() {
    this.peticiones = [];
    this.ficheros = new Map(); // "repo:ruta" → {texto, sha}
    this.blobs = new Map();
    this.arboles = new Map();
    this.commits = new Map();
    this.ramas = new Map(); // "repo:rama" → sha del commit
    this.buzon = null; // la estantería «buzon-app»: {id, assets: [{id, name, content_type, bytes, largo}]}
    this.conflictos = 0; // cuántos PUT de contenidos van a contestar 409 antes de dejar
    this.roto = false; // todo contesta 500 con un cuerpo que no debe salir
    this.n = 0;
    this.carpetas = 0; // cuántas veces se ha pedido la lista de app/datos (su ETag cambia cada vez, como puede pasar)
    this.ficheros.set(`${PRIV}:app/datos/todo.json`, { texto: JSON.stringify({ actualizado: "2026-11-27T10:00:00Z",
      colecciones: { avisos: { a1: { hecho: false } } } }), sha: "s0" });
    const juicios = {};
    for (let i = 0; i < 70; i++) juicios[`j${i}`] = { fecha: new Date(Date.UTC(2026, 10, 1 + (i % 28), i % 24)).toISOString() };
    this.ficheros.set(`${PRIV}:app/datos/juicios.json`, { texto: JSON.stringify({ juicios }), sha: "s1" });
  }
  sha() {
    return (++this.n).toString(16).padStart(40, "0");
  }
  // una rama hecha a mano (la hace el Comisario, no el portero): {ruta: bytes}
  ponerRama(repo, rama, ficheros) {
    const tree = Object.entries(ficheros).map(([path, bytes]) => {
      const sha = this.sha();
      this.blobs.set(sha, Buffer.from(bytes));
      return { path, sha, mode: "100644", type: "blob" };
    });
    const arbol = this.sha();
    this.arboles.set(arbol, tree);
    const commit = this.sha();
    this.commits.set(commit, { tree: arbol, parents: [] });
    this.ramas.set(`${repo}:${rama}`, commit);
  }
  responder(cuerpo, estado = 200, cabeceras = {}) {
    return new Response(cuerpo === null ? null : typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo),
      { status: estado, headers: { "Content-Type": "application/json", ...cabeceras } });
  }
  async fetch(url, init = {}) {
    const u = new URL(url);
    const metodo = init.method || "GET";
    const h = new Headers(init.headers || {});
    let cuerpo = null;
    let crudo = null;
    if (typeof init.body === "string") cuerpo = JSON.parse(init.body);
    else if (init.body) crudo = Buffer.from(await new Response(init.body).arrayBuffer());
    this.peticiones.push({ metodo, origen: u.origin, ruta: u.pathname + u.search, auth: h.get("Authorization"),
      accept: h.get("Accept"), redirect: init.redirect, cuerpo, crudo: !!crudo, cuerpoEsStream: init.body instanceof ReadableStream });
    if (u.origin !== "https://api.github.com" && u.origin !== "https://uploads.github.com") throw new Error("fuera de GitHub");
    if (this.roto) return this.responder({ message: `fallo interno con ${LLAVE}` }, 500);
    const p = decodeURIComponent(u.pathname);
    let m;
    if (u.origin === "https://uploads.github.com") {
      m = /^\/repos\/([^/]+\/[^/]+)\/releases\/(\d+)\/assets$/.exec(p);
      if (!m || metodo !== "POST" || !this.buzon || Number(m[2]) !== this.buzon.id) return this.responder({}, 404);
      if (!h.get("Content-Length") || Number(h.get("Content-Length")) !== crudo.length) return this.responder({}, 400);
      const nombre = u.searchParams.get("name");
      if (this.buzon.assets.some((a) => a.name === nombre)) return this.responder({ errors: [{ code: "already_exists" }] }, 422);
      const a = { id: 5000 + ++this.n, name: nombre, content_type: h.get("Content-Type"), bytes: crudo };
      this.buzon.assets.push(a);
      return this.responder({ id: a.id, name: nombre }, 201);
    }
    if (p === `/repos/${PRIV}/contents/app/datos` && metodo === "GET") {
      this.carpetas++;
      const lista = [...this.ficheros].filter(([k]) => k.startsWith(`${PRIV}:app/datos/`)).map(([k, f]) => {
        const name = k.slice(`${PRIV}:app/datos/`.length);
        return { name, path: `app/datos/${name}`, type: "file", sha: shaGit(f.texto), size: f.texto.length };
      });
      return this.responder(lista, 200, { ETag: `W/"carpeta-${this.carpetas}"` });
    }
    if ((m = /^\/repos\/([^/]+\/[^/]+)\/git\/blobs\/([0-9a-f]{40})$/.exec(p)) && metodo === "GET") {
      if (h.get("Accept") !== "application/vnd.github.raw") return this.responder({}, 400);
      const f = [...this.ficheros.values()].find((x) => shaGit(x.texto) === m[2]);
      if (!f) return this.responder({ message: "Not Found" }, 404);
      return new Response(f.texto, { status: 200, headers: { "Content-Length": String(Buffer.byteLength(f.texto)) } });
    }
    if ((m = /^\/repos\/([^/]+\/[^/]+)\/contents\/(.*)$/.exec(p))) {
      const [, repo, ruta] = m;
      const ref = u.searchParams.get("ref");
      if (ref) {
        const commit = this.ramas.get(`${repo}:${ref}`);
        if (!commit) return this.responder({ message: "No commit found" }, 404);
        const arbol = this.arboles.get(this.commits.get(commit).tree);
        if (ruta === "") return this.responder(arbol.map((f) => ({ name: f.path, path: f.path, type: "file" })));
        const f = arbol.find((x) => x.path === ruta);
        if (!f) return this.responder({}, 404);
        if (h.get("Accept") !== "application/vnd.github.raw") return this.responder({}, 400);
        return new Response(this.blobs.get(f.sha), { status: 200,
          headers: { "Content-Length": String(this.blobs.get(f.sha).length) } });
      }
      const clave = `${repo}:${ruta}`;
      if (metodo === "GET") {
        const f = this.ficheros.get(clave);
        if (!f) return this.responder({ message: "Not Found" }, 404);
        return this.responder({ sha: f.sha, content: b64(f.texto) });
      }
      if (metodo === "PUT") {
        if (this.conflictos > 0) {
          this.conflictos--;
          return this.responder({ message: "is at abc but expected def" }, 409);
        }
        const antes = this.ficheros.get(clave);
        if (antes && cuerpo.sha !== antes.sha) return this.responder({ message: "sha" }, 409);
        if (!antes && cuerpo.sha) return this.responder({ message: "sha" }, 422);
        const f = { texto: Buffer.from(cuerpo.content, "base64").toString("utf8"), sha: this.sha(), commit: cuerpo };
        this.ficheros.set(clave, f);
        return this.responder({ content: { sha: f.sha } }, antes ? 200 : 201);
      }
    }
    if (p === `/repos/${PRIV}/releases/tags/buzon-app`) {
      return this.buzon ? this.responder({ id: this.buzon.id, tag_name: "buzon-app" }) : this.responder({}, 404);
    }
    if (p === `/repos/${PRIV}/releases` && metodo === "POST") {
      if (this.buzon) return this.responder({ errors: [{ code: "already_exists" }] }, 422);
      this.buzon = { id: 77, assets: [], creada: cuerpo };
      return this.responder({ id: 77 }, 201);
    }
    if (p === `/repos/${PRIV}/releases`) {
      const muchos = Array.from({ length: 100 }, (_, i) => ({ id: 1000 + i, name: `toma-${i}.mp4` }));
      return this.responder([
        { id: 2, tag_name: "videoteca", assets: muchos },
        { id: 1, tag_name: "para-subir", assets: [{ id: 11, name: "corto-1.mp4" }, { id: 12, name: "toma-1.mp4" }] },
      ]);
    }
    if (p === `/repos/${PRIV}/releases/77/assets` && this.buzon) {
      return this.responder(this.buzon.assets.map(({ id, name, content_type }) => ({ id, name, content_type })));
    }
    if (p === `/repos/${PRIV}/releases/2/assets`) {
      const pagina = Number(u.searchParams.get("page"));
      const lote = pagina === 1 ? Array.from({ length: 100 }, (_, i) => ({ id: 1000 + i, name: `toma-${i}.mp4` }))
        : [{ id: 2000, name: "toma-extra.mp4" }];
      return this.responder(lote);
    }
    if ((m = /^\/repos\/[^/]+\/[^/]+\/releases\/assets\/(\d+)$/.exec(p))) {
      if (metodo === "DELETE") {
        const antes = this.buzon ? this.buzon.assets.length : 0;
        if (this.buzon) this.buzon.assets = this.buzon.assets.filter((a) => a.id !== Number(m[1]));
        return new Response(null, { status: this.buzon && this.buzon.assets.length < antes ? 204 : 404 });
      }
      if (h.get("Accept") !== "application/octet-stream" || init.redirect !== "manual") return this.responder({}, 400);
      return new Response(null, { status: 302, headers: { Location: `https://objects.githubusercontent.com/firmado/${m[1]}?X-Amz=1` } });
    }
    if (p === `/repos/${PUB}/actions/runs`) {
      if (h.get("Authorization")) return this.responder({ message: "Resource not accessible by personal access token" }, 403);
      return this.responder({ workflow_runs: [
        { name: "Fábrica", status: "completed", conclusion: "success", run_started_at: "2026-11-27T10:00:00Z",
          updated_at: "2026-11-27T10:20:00Z", display_title: "título del commit con cosas", head_commit: { message: "x" } },
        { name: "Cerebro", status: "in_progress", conclusion: null, run_started_at: "2026-11-27T10:30:00Z",
          updated_at: "2026-11-27T10:31:00Z" },
      ] });
    }
    return this.responder({ message: "Not Found" }, 404);
  }
}

let GH = new GitHubFalso();
globalThis.fetch = (url, init) => GH.fetch(url, init);

// --- Peticiones ---
const RESPUESTAS = [];

async function pedir(fn, ruta, { metodo = "GET", cabeceras = {}, cuerpo, params = {}, env, next } = {}) {
  const init = { method: metodo, headers: { "CF-Connecting-IP": "203.0.113.7", ...cabeceras } };
  if (cuerpo !== undefined) init.body = typeof cuerpo === "string" || cuerpo instanceof Uint8Array ? cuerpo : JSON.stringify(cuerpo);
  if (cuerpo instanceof Uint8Array && !("Content-Length" in cabeceras)) init.headers["Content-Length"] = String(cuerpo.length);
  if (cabeceras["Content-Length"] === null) delete init.headers["Content-Length"];
  const request = new Request(WEB + ruta, init);
  const r = await fn({ request, params, env, next: next || (async () => new Response("la app", { status: 200 })) });
  const copia = r.clone();
  RESPUESTAS.push({ ruta, texto: copia.body ? Buffer.from(await copia.arrayBuffer()).toString("latin1") : "",
    cabeceras: [...r.headers].map(([k, v]) => `${k}: ${v}`).join("\n") });
  return r;
}

async function sesion(env) {
  return `sesion=${await nuevaSesion(env)}`;
}

const pruebas = [];
const prueba = (nombre, fn) => pruebas.push([nombre, fn]);

prueba("sesión: la buena vale; la cambiada, la caducada y la de otra contraseña, no", async () => {
  const env = entorno();
  const valor = await nuevaSesion(env);
  assert.equal(await sesionValida(valor, env), true);
  assert.equal(await sesionValida(valor.slice(0, -2) + (valor.endsWith("AA") ? "BB" : "AA"), env), false);
  const partes = valor.split(".");
  assert.equal(await sesionValida([partes[0], String(Number(partes[1]) + 999), partes[2], partes[3]].join("."), env), false);
  assert.equal(await sesionValida(valor, env, Date.now() + 91 * 24 * 3600 * 1000), false, "a los 90 días caduca");
  assert.equal(await sesionValida(valor, entorno({ PANEL_CLAVE: "otra-contraseña" })), false,
    "si el dueño cambia la contraseña, las sesiones viejas no valen");
  assert.equal(await sesionValida(valor, entorno({ PANEL_FIRMA: "otra-firma" })), false);
  assert.equal(await sesionValida("", env), false);
  assert.equal(await sesionValida("v1.1.2.3", env), false);
  const cookie = cookieDeSesion(valor);
  for (const trozo of ["HttpOnly", "Secure", "SameSite=Strict", "Max-Age=7776000", "Path=/"]) assert.ok(cookie.includes(trozo), trozo);
});

prueba("entrar: con la clave buena pone la cookie; con la mala, 401", async () => {
  const env = entorno();
  let r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: "mala" }, env });
  assert.equal(r.status, 401);
  assert.deepEqual(await r.json(), { error: "clave" });
  assert.equal(r.headers.get("Set-Cookie"), null);
  r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: CLAVE }, env });
  assert.equal(r.status, 200);
  const cookie = r.headers.get("Set-Cookie");
  assert.match(cookie, /^sesion=v1\./);
  assert.match(cookie, /HttpOnly; Secure; SameSite=Strict/);
  const valor = /^sesion=([^;]+)/.exec(cookie)[1];
  r = await pedir(portero, "/api/yo", { cabeceras: { Cookie: `otra=1; sesion=${valor}` }, env,
    next: () => yo({ request: new Request(WEB + "/api/yo") }) });
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { dentro: true });
  r = await pedir(entrar, "/api/entrar", { metodo: "GET", env });
  assert.equal(r.status, 405);
  r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: CLAVE }, env: entorno({ PANEL_CLAVE: "" }) });
  assert.equal(r.status, 503, "sin PANEL_CLAVE no se entra con nada");
  r = await pedir(salir, "/api/salir", { metodo: "POST", env });
  assert.match(r.headers.get("Set-Cookie"), /^sesion=; .*Max-Age=0/);
});

prueba("tope: 10 fallos por IP y hora; después ni la buena entra (las otras IP sí)", async () => {
  const env = entorno();
  for (let i = 0; i < 9; i++) {
    const r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: `mala${i}` }, env });
    assert.equal(r.status, 401, `intento ${i + 1}`);
  }
  let r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: "mala10" }, env });
  assert.equal(r.status, 429);
  r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: CLAVE }, env });
  assert.equal(r.status, 429, "con el tope gastado no se comprueba la clave");
  assert.equal(r.headers.get("Set-Cookie"), null);
  assert.equal(env.PANEL.escrituras, 10, "solo los fallos gastan escrituras");
  for (const [k, v] of env.PANEL.datos) {
    assert.ok(!k.includes("203.0.113.7"), "la IP no se guarda tal cual");
    assert.equal(v.ttl, 3600);
  }
  r = await pedir(entrar, "/api/entrar", { metodo: "POST", cuerpo: { clave: CLAVE }, env,
    cabeceras: { "CF-Connecting-IP": "198.51.100.9" } });
  assert.equal(r.status, 200);
});

prueba("sin sesión: /api da 401 sin_sesion, la app manda a /entrar, y /entrar se ve", async () => {
  const env = entorno();
  let llamado = false;
  const next = async () => {
    llamado = true;
    return new Response("dentro", { status: 200 });
  };
  for (const ruta of ["/api/todo", "/api/yo", "/api/video/x.mp4", "/api/escribir", "/api/cualquiera"]) {
    const r = await pedir(portero, ruta, { env, next });
    assert.equal(r.status, 401, ruta);
    assert.deepEqual(await r.json(), { error: "sin_sesion" });
    assert.equal(r.headers.get("Cache-Control"), "no-store");
  }
  for (const ruta of ["/", "/index.html", "/torre.html", "/robot-glb.js", "/espera"]) {
    const r = await pedir(portero, ruta, { env, next });
    assert.equal(r.status, 302, ruta);
    assert.equal(r.headers.get("Location"), "/entrar");
  }
  assert.equal(llamado, false, "sin sesión no se llega ni a la app ni a la API");
  let r = await pedir(portero, "/api/yo", { env, next, cabeceras: { Cookie: "sesion=v1.9999999999.AAAAAAAAAAAAAAAAAAAAAAAA.BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB" } });
  assert.equal(r.status, 401, "una cookie inventada no vale");
  for (const ruta of ["/entrar", "/api/entrar", "/favicon.ico"]) {
    llamado = false;
    r = await pedir(portero, ruta, { env, next, metodo: ruta === "/api/entrar" ? "POST" : "GET" });
    assert.equal(r.status, 200, ruta);
    assert.equal(llamado, true);
  }
  for (const [k, v] of [["X-Frame-Options", "DENY"], ["Referrer-Policy", "no-referrer"], ["X-Content-Type-Options", "nosniff"]]) {
    assert.equal(r.headers.get(k), v, k);
  }
  const csp = r.headers.get("Content-Security-Policy");
  for (const trozo of ["cdnjs.cloudflare.com", "cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com",
    "frame-ancestors 'none'", "blob:", "objects.githubusercontent.com"]) assert.ok(csp.includes(trozo), trozo);
  const cookie = await sesion(env);
  r = await pedir(portero, "/entrar", { env, next, cabeceras: { Cookie: cookie } });
  assert.equal(r.status, 302, "ya dentro, /entrar lleva a la app");
  r = await pedir(portero, "/", { env, next, cabeceras: { Cookie: cookie } });
  assert.equal(r.status, 200);
  r = await pedir(portero, "/api/escribir", { env, next, metodo: "POST", cabeceras: { Cookie: cookie, Origin: "https://otra.web" } });
  assert.equal(r.status, 403, "un POST desde otra web no pasa");
});

prueba("/api/todo: el fichero tal cual, en streaming, con ETag = sha del blob y 304", async () => {
  GH = new GitHubFalso();
  olvidar("datos:carpeta");
  const env = entorno();
  const texto = GH.ficheros.get(`${PRIV}:app/datos/todo.json`).texto;
  let r = await pedir(todo, "/api/todo", { env });
  assert.equal(r.status, 200);
  assert.equal(await r.text(), texto, "byte a byte lo que hay en el privado");
  const etag = r.headers.get("ETag");
  assert.equal(etag, `"${shaGit(texto)}"`, "el ETag es el sha del blob");
  const blob = GH.peticiones.find((p) => p.ruta.includes("/git/blobs/"));
  assert.equal(blob.accept, "application/vnd.github.raw", "en crudo: vale para más de 1 MB");
  assert.equal(blob.auth, `Bearer ${LLAVE}`);
  r = await pedir(todo, "/api/todo", { env, cabeceras: { "If-None-Match": etag } });
  assert.equal(r.status, 304);
  assert.equal(await r.text(), "");
  assert.equal(GH.carpetas, 1, "dentro de los 30 s no se pregunta otra vez la lista");
  assert.equal(GH.peticiones.filter((p) => p.ruta.includes("/git/blobs/")).length, 1, "con 304 no se baja el cuerpo");
  // pasados los 30 s la lista se vuelve a pedir y GitHub da OTRO ETag con el mismo contenido: sigue siendo 304
  olvidar("datos:carpeta");
  r = await pedir(todo, "/api/todo", { env, cabeceras: { "If-None-Match": `W/${etag}` } });
  assert.equal(r.status, 304, "el ETag de GitHub cambia pero el sha no");
  assert.equal(GH.carpetas, 2);
  GH.ficheros.get(`${PRIV}:app/datos/todo.json`).texto = JSON.stringify({ actualizado: "nuevo", colecciones: {} });
  olvidar("datos:carpeta");
  r = await pedir(todo, "/api/todo", { env, cabeceras: { "If-None-Match": etag } });
  assert.equal(r.status, 200);
  assert.notEqual(r.headers.get("ETag"), etag);
  assert.equal((await r.json()).actualizado, "nuevo");
  const codigo = readFileSync(join(RAIZ, "lib", "datos.js"), "utf8");
  assert.ok(!/JSON\.parse|\.text\(\)|arrayBuffer|digest/.test(codigo.replace(/await r\.json\(\)/, "")),
    "el cuerpo de los datos no se lee, ni se parsea, ni se le saca la huella");
});

prueba("/api/juicios: el fichero entero (desde se ignora)", async () => {
  GH = new GitHubFalso();
  olvidar("datos:carpeta");
  const env = entorno();
  const texto = GH.ficheros.get(`${PRIV}:app/datos/juicios.json`).texto;
  let r = await pedir(juicios, "/api/juicios?desde=2026-11-27T00:00:00Z", { env });
  assert.equal(r.status, 200);
  assert.equal(await r.text(), texto);
  assert.equal(Object.keys(JSON.parse(texto).juicios).length, 70);
  r = await pedir(juicios, "/api/juicios", { env, cabeceras: { "If-None-Match": r.headers.get("ETag") } });
  assert.equal(r.status, 304);
});

prueba("/api/video: busca en las estanterías y redirige 302 a la descarga firmada", async () => {
  GH = new GitHubFalso();
  const env = entorno();
  let r = await pedir(video, "/api/video/corto-1.mp4", { env, params: { nombre: "corto-1.mp4" } });
  assert.equal(r.status, 302);
  assert.equal(r.headers.get("Location"), "https://objects.githubusercontent.com/firmado/11?X-Amz=1");
  const pedida = GH.peticiones.find((p) => p.ruta.endsWith("/releases/assets/11"));
  assert.equal(pedida.accept, "application/octet-stream");
  assert.equal(pedida.redirect, "manual");
  r = await pedir(video, "/api/video/toma-1.mp4", { env, params: { nombre: "toma-1.mp4" } });
  assert.match(r.headers.get("Location"), /\/12\?/, "«para-subir» gana a «videoteca» si se llaman igual");
  r = await pedir(video, "/api/video/toma-extra.mp4", { env, params: { nombre: "toma-extra.mp4" } });
  assert.match(r.headers.get("Location"), /\/2000\?/, "una estantería llena se lee página a página");
  const indices = GH.peticiones.filter((p) => p.ruta.startsWith(`/repos/${PRIV}/releases?`)).length;
  assert.equal(indices, 1, "el índice se guarda unos minutos");
  assert.ok(env.PANEL.datos.has("indice:estanterias"));
  r = await pedir(video, "/api/video/no-existe.mp4", { env, params: { nombre: "no-existe.mp4" } });
  assert.equal(r.status, 404);
  r = await pedir(video, "/api/video/..%2Fx", { env, params: { nombre: "..%2Fx" } });
  assert.equal(r.status, 400);
});

prueba("/api/turnos: los turnos del público, solo con su nombre (sin títulos de commit)", async () => {
  GH = new GitHubFalso();
  const env = entorno();
  const r = await pedir(turnos, "/api/turnos", { env });
  assert.equal(r.status, 200);
  const { turnos: t } = await r.json();
  assert.deepEqual(t[0], { nombre: "Fábrica", estado: "completed", resultado: "success",
    empezado: "2026-11-27T10:00:00Z", terminado: "2026-11-27T10:20:00Z" });
  assert.equal(t[1].terminado, null);
  assert.ok(!JSON.stringify(t).includes("título del commit"));
});

prueba("/api/escribir: lo permitido deja la entrada en el privado y avisa al Comisario", async () => {
  GH = new GitHubFalso();
  GH.conflictos = 0;
  const env = entorno();
  let r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "ordenes", id: "p123", crear: true, campos: { texto: "Haz más vídeos", fecha: "2026-11-27T10:00:00Z", estado: "nueva" } } });
  assert.equal(r.status, 200);
  const res = await r.json();
  assert.equal(res.ok, true);
  assert.match(res.entrada, /^\d{14}-[a-z]{4}$/);
  const f = GH.ficheros.get(`${PRIV}:entrada/${res.entrada}.json`);
  assert.ok(f, "la entrada está en el privado");
  const e = JSON.parse(f.texto);
  assert.deepEqual(Object.keys(e).sort(), ["campos", "coleccion", "crear", "fecha", "id"]);
  assert.equal(e.coleccion, "ordenes");
  assert.equal(e.crear, true);
  assert.equal(e.campos.texto, "Haz más vídeos");
  assert.deepEqual(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/app.json`).texto), { intento: 1 });
  assert.ok(!GH.ficheros.get(`${PUB}:peticiones/app.json`).commit.message.includes("Haz"), "el commit público no lleva textos");
  // otra, con el sha cambiado a la vez (409): se vuelve a leer y sube el intento
  GH.conflictos = 1;
  r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "avisos", id: "a1", campos: { hecho: true, hechoEn: "2026-11-27T10:01:00Z" } } });
  assert.equal(r.status, 200, "el 409 de la entrada se reintenta con otro nombre");
  GH.conflictos = 0;
  r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "clips", id: "c1", campos: { estado: "por_grabar", grabadoEl: null } } });
  assert.equal(r.status, 200);
  const intento = JSON.parse(GH.ficheros.get(`${PUB}:peticiones/app.json`).texto).intento;
  assert.equal(intento, 3);
  r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "errores", id: "e1", crear: true, campos: { msg: "x", fecha: "2026-11-27T10:00:00Z" } } });
  assert.equal(r.status, 200);
  assert.equal(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/app.json`).texto).intento, 3,
    "los errores de la app no lanzan al Comisario");
  for (const [coleccion, campos, id] of [["barrios", { cifras: { seguidores: 10, fecha: "2026-11-27T10:00:00Z" },
    historialCifras: { "2026-11-27": { seguidores: 10 } } }, "barrio-1"],
  ["sos", { decisionDueno: "si", decididoEl: "2026-11-27T10:00:00Z" }, "s1"],
  ["parasubir", { estado: "descartado", descartadoEl: "2026-11-27T10:00:00Z", motivo: "no me gusta" }, "v1"]]) {
    r = await pedir(escribir, "/api/escribir", { metodo: "POST", env, cuerpo: { coleccion, id, campos } });
    assert.equal(r.status, 200, coleccion);
  }
});

prueba("/api/escribir: lo no permitido da 400 no_permitido (colección, campo, valor, crear, tamaño)", async () => {
  GH = new GitHubFalso();
  const env = entorno();
  const malos = [
    { coleccion: "canales", id: "x", campos: { estado: "a" } },
    { coleccion: "__proto__", id: "x", campos: { a: 1 } },
    { coleccion: "avisos", id: "a1", campos: { hecho: true, borrar: true } },
    { coleccion: "avisos", id: "a1", campos: { hecho: "sí" } },
    { coleccion: "avisos", id: "a1", crear: true, campos: { hecho: true } },
    { coleccion: "charla", id: "c1", campos: { texto: "hola" } }, // charla solo se crea
    { coleccion: "charla", id: "c1", crear: true, campos: { de: "otro", texto: "hola" } },
    { coleccion: "charla", id: "c1", crear: true, campos: { texto: "x".repeat(1001) } },
    { coleccion: "ordenes", id: "o1", crear: true, campos: { estado: "cancelada" } },
    { coleccion: "ordenes", id: "o1", campos: { estado: "nueva" } },
    { coleccion: "ordenes", id: "o1", crear: true, campos: { texto: "x".repeat(601) } },
    { coleccion: "parasubir", id: "v1", campos: { estado: "publicado" } },
    { coleccion: "parasubir", id: "v1", campos: { motivo: "x".repeat(121) } },
    { coleccion: "sos", id: "s1", campos: { decisionDueno: "quizá" } },
    { coleccion: "clips", id: "c1", campos: { estado: "en_videoteca" } },
    { coleccion: "propios", id: "p1", crear: true, campos: { estado: "aprobado" } },
    { coleccion: "errores", id: "e1", crear: true, campos: { msg: "x".repeat(2001) } },
    { coleccion: "avisos", id: "a/../b", campos: { hecho: true } },
    { coleccion: "avisos", id: "a1", campos: {} },
    { coleccion: "avisos", id: "a1", campos: { hechoEn: "no es una fecha" } },
    { coleccion: "barrios", id: "b1", campos: { cifras: "texto" } },
    { coleccion: "barrios", id: "b1", campos: { cifras: { a: { b: { c: { d: { e: 1 } } } } } } },
    { coleccion: "avisos", id: "a1", campos: { hecho: true }, extra: 1 },
  ];
  for (const cuerpo of malos) {
    const r = await pedir(escribir, "/api/escribir", { metodo: "POST", env, cuerpo });
    assert.equal(r.status, 400, JSON.stringify(cuerpo).slice(0, 120));
    assert.deepEqual(await r.json(), { error: "no_permitido" });
  }
  let r = await pedir(escribir, "/api/escribir", { metodo: "POST", env, cuerpo: "esto no es JSON" });
  assert.equal(r.status, 400);
  r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "barrios", id: "b1", campos: { historialCifras: { x: "y".repeat(70000) } } } });
  assert.equal(r.status, 413, "un cuerpo enorme ni se lee");
  r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "barrios", id: "b1", campos: { historialCifras: { x: "y".repeat(20000) } } } });
  assert.equal(r.status, 400, "un campo que pasa de su tamaño");
  assert.equal(GH.peticiones.length, 0, "nada de lo no permitido llega a GitHub");
});

// Un MP4 de mentira: la caja «ftyp» y relleno hasta el tamaño pedido.
function mp4(bytes) {
  const v = new Uint8Array(bytes);
  v.set([0, 0, 0, 0x18, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d]);
  for (let i = 12; i < bytes; i++) v[i] = i % 251;
  return v;
}

prueba("/api/subir: tipo malo, tamaño malo y bytes que no son vídeo, no (sin tocar GitHub)", async () => {
  GH = new GitHubFalso();
  const env = entorno();
  const casos = [
    ["?para=propios&codigo=abc", "image/png", mp4(4096), {}, 415],
    ["?para=propios&codigo=abc", "video/mp4", mp4(1000), {}, 400],
    ["?para=propios&codigo=abc", "video/mp4", mp4(15 * 1024 * 1024 + 1), {}, 413],
    ["?para=propios&codigo=abc", "video/mp4", mp4(4096), { "Content-Length": null }, 411],
    ["?para=propios&codigo=abc", "video/mp4", new Uint8Array(4096).fill(65), {}, 415],
    ["?para=propios&codigo=abc", "video/webm", mp4(4096), {}, 415],
    ["?para=otros&codigo=abc", "video/mp4", mp4(4096), {}, 400],
    ["?para=clips&codigo=a%2Fb", "video/mp4", mp4(4096), {}, 400],
    ["?para=clips&codigo=" + "a".repeat(65), "video/mp4", mp4(4096), {}, 400],
  ];
  for (const [q, tipo, cuerpo, extra, estado] of casos) {
    const r = await pedir(subir, `/api/subir${q}`, { metodo: "POST", env, cuerpo,
      cabeceras: { "Content-Type": tipo, ...extra } });
    assert.equal(r.status, estado, `${q} ${tipo} ${cuerpo.length}`);
  }
  assert.equal(GH.peticiones.length, 0);
});

prueba("/api/subir: el bueno va tal cual (en streaming) a «buzon-app» y avisa al Comisario", async () => {
  GH = new GitHubFalso();
  const env = entorno();
  const video1 = mp4(300 * 1024);
  let r = await pedir(subir, "/api/subir?para=propios&codigo=p-abc_1", { metodo: "POST", env, cuerpo: video1,
    cabeceras: { "Content-Type": "video/mp4" } });
  assert.equal(r.status, 200);
  const res = await r.json();
  assert.equal(res.id, "propios:p-abc_1");
  assert.equal(res.url, "/api/subido/propios:p-abc_1");
  assert.ok(GH.buzon, "la estantería se crea si no existe");
  assert.equal(GH.buzon.creada.tag_name, "buzon-app");
  assert.equal(GH.buzon.creada.make_latest, "false");
  const a = GH.buzon.assets.find((x) => x.name === "propios-p-abc_1.mp4");
  assert.ok(a, "el vídeo está en el buzón como <para>-<codigo>.<ext>");
  assert.equal(a.content_type, "video/mp4");
  assert.ok(a.bytes.equals(Buffer.from(video1)), "el vídeo llega entero y sin tocar");
  const subida = GH.peticiones.find((p) => p.origen === "https://uploads.github.com");
  assert.equal(subida.cuerpoEsStream, true, "el cuerpo va como stream, no leído en memoria ni en base64");
  assert.equal(subida.auth, `Bearer ${LLAVE}`);
  assert.equal(GH.peticiones.filter((p) => p.ruta.includes("/git/")).length, 0, "el portero ya no hace ramas");
  assert.deepEqual(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/juicio.json`).texto), { codigo: "p-abc_1", intento: 1 });
  assert.deepEqual(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/app.json`).texto), { intento: 1 });
  // mientras está en el buzón, /api/subido redirige a su descarga
  r = await pedir(subido, "/api/subido/propios:p-abc_1", { env, params: { id: "propios:p-abc_1" } });
  assert.equal(r.status, 302);
  assert.equal(r.headers.get("Location"), `https://objects.githubusercontent.com/firmado/${a.id}?X-Amz=1`);
  // subirlo otra vez (ahora MOV) quita el de antes
  r = await pedir(subir, "/api/subir?para=propios&codigo=p-abc_1", { metodo: "POST", env, cuerpo: mp4(4096),
    cabeceras: { "Content-Type": "video/quicktime; codecs=x" } });
  assert.equal(r.status, 200);
  assert.deepEqual(GH.buzon.assets.map((x) => x.name), ["propios-p-abc_1.mov"]);
  assert.equal(GH.peticiones.filter((p) => p.origen === "https://api.github.com" && p.ruta === `/repos/${PRIV}/releases` &&
    p.metodo === "POST").length, 1,
    "la estantería se crea una sola vez");
  // un clip WebM: al buzón, toca app.json pero no lanza el juicio
  const webm = new Uint8Array(4096);
  webm.set([0x1a, 0x45, 0xdf, 0xa3]);
  r = await pedir(subir, "/api/subir?para=clips&codigo=w1", { metodo: "POST", env, cuerpo: webm,
    cabeceras: { "Content-Type": "video/webm" } });
  assert.equal(r.status, 200);
  assert.ok(GH.buzon.assets.some((x) => x.name === "clips-w1.webm"));
  assert.equal(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/app.json`).texto).intento, 3);
  assert.equal(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/juicio.json`).texto).intento, 2);
  // un cuerpo que trae más bytes de los que dice no pasa entero
  r = await pedir(subir, "/api/subir?para=clips&codigo=w2", { metodo: "POST", env, cuerpo: mp4(8192),
    cabeceras: { "Content-Type": "video/mp4", "Content-Length": "4096" } }).catch(() => null);
  assert.ok(!GH.buzon.assets.some((x) => x.name === "clips-w2.mp4" && x.bytes.length > 4096));
});

prueba("/api/subido: si el Comisario ya lo pasó a su rama, el fichero de la rama en crudo", async () => {
  GH = new GitHubFalso();
  const env = entorno();
  const video1 = mp4(5000);
  GH.buzon = { id: 77, assets: [] };
  GH.ponerRama(PRIV, "juicio/p9", { "p9.mp4": video1, "peticion.json": Buffer.from('{"codigo":"p9"}') });
  let r = await pedir(subido, "/api/subido/propios:p9", { env, params: { id: "propios:p9" } });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Content-Type"), "video/mp4");
  assert.ok(Buffer.from(await r.arrayBuffer()).equals(Buffer.from(video1)));
  r = await pedir(subido, "/api/subido/clips:nada", { env, params: { id: "clips:nada" } });
  assert.equal(r.status, 404);
  r = await pedir(subido, "/api/subido/otra:cosa", { env, params: { id: "otra:cosa" } });
  assert.equal(r.status, 400);
  GH.buzon = null;
  r = await pedir(subido, "/api/subido/propios:p9", { env, params: { id: "propios:p9" } });
  assert.equal(r.status, 200, "sin estantería también busca la rama");
});

prueba("/api/lanzar: lista cerrada y 1 cada 2 minutos por cada «que»", async () => {
  GH = new GitHubFalso();
  GH.ficheros.set(`${PUB}:peticiones/cerebro.json`, { texto: '{"intento": 4}', sha: "c4" });
  const env = entorno();
  let r = await pedir(lanzar, "/api/lanzar", { metodo: "POST", env, cuerpo: { que: "cerebro" } });
  assert.equal(r.status, 200);
  assert.deepEqual(JSON.parse(GH.ficheros.get(`${PUB}:peticiones/cerebro.json`).texto), { intento: 5 });
  r = await pedir(lanzar, "/api/lanzar", { metodo: "POST", env, cuerpo: { que: "cerebro" } });
  assert.equal(r.status, 429);
  const espera = await r.json();
  assert.equal(espera.error, "espera");
  assert.ok(espera.segundos > 0 && espera.segundos <= 120);
  assert.equal(env.PANEL.datos.get("lanzar:cerebro").ttl, 120);
  r = await pedir(lanzar, "/api/lanzar", { metodo: "POST", env, cuerpo: { que: "actualizar" } });
  assert.equal(r.status, 200, "cada «que» lleva su propio tope");
  assert.ok(GH.ficheros.has(`${PUB}:peticiones/app.json`));
  r = await pedir(lanzar, "/api/lanzar", { metodo: "POST", env, cuerpo: { que: "juicio" } });
  assert.equal(r.status, 200);
  for (const que of ["fabrica", "constructor", "", 5, null]) {
    r = await pedir(lanzar, "/api/lanzar", { metodo: "POST", env, cuerpo: { que } });
    assert.equal(r.status, 400, String(que));
  }
});

prueba("si GitHub falla: 502 sin su cuerpo; sin llave: 503 sin_preparar", async () => {
  GH = new GitHubFalso();
  GH.roto = true;
  olvidar("datos:carpeta");
  const env = entorno();
  let r = await pedir(todo, "/api/todo", { env });
  assert.equal(r.status, 502);
  assert.deepEqual(await r.json(), { error: "github" });
  r = await pedir(escribir, "/api/escribir", { metodo: "POST", env,
    cuerpo: { coleccion: "avisos", id: "a1", campos: { hecho: true } } });
  assert.equal(r.status, 502);
  r = await pedir(subir, "/api/subir?para=clips&codigo=z", { metodo: "POST", env, cuerpo: mp4(4096),
    cabeceras: { "Content-Type": "video/mp4" } });
  assert.equal(r.status, 502);
  r = await pedir(juicios, "/api/juicios", { env });
  assert.equal(r.status, 502);
  r = await pedir(turnos, "/api/turnos", { env });
  assert.ok([200, 502].includes(r.status));
  olvidar("datos:carpeta");
  r = await pedir(todo, "/api/todo", { env: entorno({ PANEL_GH_TOKEN: "" }) });
  assert.equal(r.status, 503);
  assert.deepEqual(await r.json(), { error: "sin_preparar" });
});

function archivos(carpeta) {
  return readdirSync(carpeta, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? archivos(join(carpeta, e.name)) : [join(carpeta, e.name)]);
}

prueba("la llave de GitHub nunca sale en una respuesta, y no hay console.log ni datos escritos a mano", async () => {
  assert.ok(RESPUESTAS.length > 50);
  for (const { ruta, texto, cabeceras } of RESPUESTAS) {
    assert.ok(!texto.includes(LLAVE) && !cabeceras.includes(LLAVE), `${ruta} enseña la llave`);
    assert.ok(!texto.includes(CLAVE) && !cabeceras.includes(CLAVE), `${ruta} enseña la contraseña`);
    assert.ok(!texto.includes("fallo interno"), `${ruta} enseña un cuerpo de GitHub`);
  }
  for (const p of GH.peticiones) assert.ok(!p.ruta.includes(LLAVE), "la llave no va en la dirección");
  for (const f of [...archivos(join(RAIZ, "functions")), ...archivos(join(RAIZ, "lib"))]) {
    const codigo = readFileSync(f, "utf8");
    assert.ok(!/console\./.test(codigo), `${f} no puede usar console`);
    assert.ok(!/ciudades-memoria|github\.com\/[A-Za-z0-9-]+\//i.test(codigo), `${f} no puede llevar el repositorio ni el dueño escritos a mano`);
  }
  const toml = readFileSync(join(RAIZ, "wrangler.toml"), "utf8");
  assert.match(toml, /id = "ID_DEL_KV"/, "el id de verdad del KV no va en el repositorio");
  assert.match(toml, /binding = "PANEL"/);
  assert.ok(!/\[vars\]/.test(toml), "las variables las pone el despliegue");
  for (const nombre of ["entrar", "espera"]) {
    const html = readFileSync(join(RAIZ, "public", `${nombre}.html`), "utf8");
    assert.match(html, /lang="es"/);
    assert.match(html, /name="viewport"/);
    assert.ok(!/https?:\/\/(?!www\.w3\.org)/.test(html), `${nombre}.html no carga nada de fuera`);
  }
});

let fallos = 0;
for (const [nombre, fn] of pruebas) {
  try {
    await fn();
    process.stdout.write(`bien  ${nombre}\n`);
  } catch (e) {
    fallos++;
    process.stdout.write(`MAL   ${nombre}\n      ${e.message}\n`);
  }
}
process.stdout.write(fallos ? `\n${fallos} pruebas han fallado\n` : `\nTodo bien (${pruebas.length} pruebas)\n`);
process.exit(fallos ? 1 : 0);
