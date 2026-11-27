// Simulacro del Buzón de vuelta (vuelta/), sin red y sin Cloudflare: un KV de mentira y peticiones de mentira.
// Comprueba que /vuelta/instagram guarda 15 minutos lo que manda Instagram sin enseñarlo, que con HEAD o sin nada da
// 200 sin tocar el KV, que solo acepta Instagram, que /recoger pide la llave y sirve una sola vez, que los avisos de
// Meta dejan su marca (una por cuenta; /meta/borrado contesta lo que pide Meta), que con IG_APP_SECRET se tiran sin
// escribir los que no firma Meta, que si el KV falla se contesta «inténtalo dentro de un rato» sin enseñar nada, y que
// no hay console.log ni cosas de fuera.
//
//     node pruebas/simulacro_vuelta.mjs

import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { mismaLlave } from "../vuelta/lib/comun.js";
import { onRequest as vuelta } from "../vuelta/functions/vuelta/[red].js";
import { onRequest as recoger } from "../vuelta/functions/recoger.js";
import { onRequest as baja } from "../vuelta/functions/meta/baja.js";
import { onRequest as borrado } from "../vuelta/functions/meta/borrado.js";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..", "vuelta");
const WEB = "https://buzon-de-prueba.pages.dev";
const LLAVE = "llave-de-prueba-0123456789abcdefghijklmnopqrstuv";
const ESTADO = "Ab3_dE-fGh1JkLmNoPqRsTuV"; // 24 caracteres válidos
const CODIGO = "AQBcodigoDePrueba_123-xyz";

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
  async list({ prefix = "", limit = 1000 } = {}) {
    const keys = [...this.datos.keys()].filter((k) => k.startsWith(prefix)).slice(0, limit).map((name) => ({ name }));
    return { keys, list_complete: true };
  }
}

function pedir(fn, ruta, { metodo = "GET", cabeceras = {}, cuerpo, params = {}, env }) {
  const request = new Request(WEB + ruta, { method: metodo, headers: cabeceras, body: cuerpo });
  return fn({ request, params, env });
}

const SECRETO_APP = "secreto-de-app-de-prueba";

// Un aviso como los de Meta: con `secreto`, firmado como lo firmaría Meta; sin él, con una firma inventada.
function avisoDeMeta(userId, secreto) {
  const carga = Buffer.from(JSON.stringify({ algorithm: "HMAC-SHA256", issued_at: 1, user_id: userId }))
    .toString("base64url");
  const firma = secreto ? createHmac("sha256", secreto).update(carga).digest("base64url") : "firmaFalsa";
  return "signed_request=" + encodeURIComponent(`${firma}.${carga}`);
}

// Un KV que ya no deja escribir ni leer (cupo del día gastado).
class KVRoto extends KVFalso {
  async get() {
    throw new Error("cupo");
  }
  async put() {
    throw new Error("cupo");
  }
  async list() {
    throw new Error("cupo");
  }
}

const pruebas = [];
const prueba = (nombre, fn) => pruebas.push([nombre, fn]);

prueba("la llave se compara bien", async () => {
  assert.equal(await mismaLlave(LLAVE, LLAVE), true);
  assert.equal(await mismaLlave(LLAVE + "x", LLAVE), false);
  assert.equal(await mismaLlave("", LLAVE), false);
  assert.equal(await mismaLlave(LLAVE, ""), false);
});

prueba("/vuelta/instagram sin nada y con HEAD: 200 sin tocar el KV", async () => {
  const env = { VUELTA: new KVFalso() };
  let r = await pedir(vuelta, "/vuelta/instagram", { params: { red: "instagram" }, env });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("Location"), null);
  assert.match(await r.text(), /Dirección de vuelta del Panel de cifras/);
  r = await pedir(vuelta, `/vuelta/instagram?state=${ESTADO}&code=${CODIGO}`,
    { metodo: "HEAD", params: { red: "instagram" }, env });
  assert.equal(r.status, 200);
  assert.equal(await r.text(), "");
  assert.equal(env.VUELTA.escrituras, 0);
});

prueba("solo Instagram, y solo GET o HEAD", async () => {
  const env = { VUELTA: new KVFalso() };
  let r = await pedir(vuelta, `/vuelta/tiktok?state=${ESTADO}&code=${CODIGO}`, { params: { red: "tiktok" }, env });
  assert.equal(r.status, 404);
  r = await pedir(vuelta, "/vuelta/instagram", { metodo: "POST", params: { red: "instagram" }, env });
  assert.equal(r.status, 405);
  assert.equal(env.VUELTA.escrituras, 0);
});

prueba("guarda el código 15 minutos y no lo enseña", async () => {
  const env = { VUELTA: new KVFalso() };
  const ruta = `/vuelta/instagram?state=${ESTADO}&code=${CODIGO}`;
  const r = await pedir(vuelta, ruta, { params: { red: "instagram" }, env });
  assert.equal(r.status, 200);
  const html = await r.text();
  assert.match(html, /Listo, ya puedes cerrar esta página/);
  assert.ok(!html.includes(CODIGO) && !html.includes(ESTADO), "la página no puede enseñar el código ni el state");
  assert.equal(r.headers.get("Cache-Control"), "no-store");
  assert.equal(r.headers.get("Referrer-Policy"), "no-referrer");
  const guardado = env.VUELTA.datos.get(`vuelta:${ESTADO}`);
  assert.equal(guardado.ttl, 900);
  const datos = JSON.parse(guardado.valor);
  assert.deepEqual(Object.keys(datos).sort(), ["code", "error", "hora", "red"]);
  assert.equal(datos.red, "instagram");
  assert.equal(datos.code, CODIGO);
  assert.equal(datos.error, null);
  await pedir(vuelta, ruta, { params: { red: "instagram" }, env }); // el dueño recarga la página
  assert.equal(env.VUELTA.escrituras, 1, "recargar no gasta otra escritura");
});

prueba("state mal escrito o sin código: 400 y nada guardado", async () => {
  const env = { VUELTA: new KVFalso() };
  for (const q of [`state=corto&code=${CODIGO}`, `state=${ESTADO}`, `state=${ESTADO}!!&code=${CODIGO}`,
    `code=${CODIGO}`, `state=${ESTADO}&code=con%20espacio`]) {
    const r = await pedir(vuelta, `/vuelta/instagram?${q}`, { params: { red: "instagram" }, env });
    assert.equal(r.status, 400, q);
  }
  assert.equal(env.VUELTA.escrituras, 0);
});

prueba("si el dueño no da permiso, se guarda el error (y uno raro queda como «otro»)", async () => {
  const env = { VUELTA: new KVFalso() };
  let r = await pedir(vuelta, `/vuelta/instagram?state=${ESTADO}&error=access_denied&error_reason=user_denied`,
    { params: { red: "instagram" }, env });
  assert.equal(r.status, 200);
  assert.equal(JSON.parse(env.VUELTA.datos.get(`vuelta:${ESTADO}`).valor).error, "access_denied");
  r = await pedir(vuelta, `/vuelta/instagram?state=${ESTADO}&error=%3Cscript%3E`, { params: { red: "instagram" }, env });
  assert.equal(JSON.parse(env.VUELTA.datos.get(`vuelta:${ESTADO}`).valor).error, "otro");
});

prueba("/recoger pide la llave y sirve una sola vez", async () => {
  const env = { VUELTA: new KVFalso(), VUELTA_LLAVE: LLAVE };
  await pedir(vuelta, `/vuelta/instagram?state=${ESTADO}&code=${CODIGO}`, { params: { red: "instagram" }, env });
  let r = await pedir(recoger, `/recoger?state=${ESTADO}`, { env });
  assert.equal(r.status, 401);
  r = await pedir(recoger, `/recoger?state=${ESTADO}`, { env, cabeceras: { Authorization: "Bearer otra" } });
  assert.equal(r.status, 401);
  const conLlave = { Authorization: `Bearer ${LLAVE}` };
  r = await pedir(recoger, "/recoger?state=corto", { env, cabeceras: conLlave });
  assert.equal(r.status, 400);
  r = await pedir(recoger, `/recoger?state=${ESTADO}`, { env, cabeceras: conLlave });
  assert.equal(r.status, 200);
  const datos = await r.json();
  assert.equal(datos.code, CODIGO);
  assert.equal(datos.red, "instagram");
  r = await pedir(recoger, `/recoger?state=${ESTADO}`, { env, cabeceras: conLlave });
  assert.equal(r.status, 404);
  assert.deepEqual(await r.json(), { pendiente: true });
  r = await pedir(recoger, `/recoger?state=${ESTADO}`, { env, metodo: "POST", cabeceras: conLlave });
  assert.equal(r.status, 405);
  r = await pedir(recoger, `/recoger?state=${ESTADO}`, { env: { VUELTA: env.VUELTA }, cabeceras: conLlave });
  assert.equal(r.status, 503, "sin VUELTA_LLAVE en Cloudflare el buzón no se abre");
});

prueba("avisos de Meta: baja y borrado dejan su marca y se recogen una vez", async () => {
  const env = { VUELTA: new KVFalso(), VUELTA_LLAVE: LLAVE };
  const form = { "Content-Type": "application/x-www-form-urlencoded" };
  let r = await pedir(baja, "/meta/baja", { metodo: "POST", cabeceras: form, cuerpo: avisoDeMeta("17841400000000001"), env });
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true });
  r = await pedir(borrado, "/meta/borrado", { metodo: "POST", cabeceras: form, cuerpo: avisoDeMeta("17841400000000002"), env });
  assert.equal(r.status, 200);
  const respuesta = await r.json();
  assert.equal(respuesta.url, `${WEB}/borrado`);
  assert.match(respuesta.confirmation_code, /^[0-9A-F]{12}$/);
  for (const k of env.VUELTA.datos.keys()) assert.equal(env.VUELTA.datos.get(k).ttl, 30 * 24 * 3600);
  r = await pedir(baja, "/meta/baja", { metodo: "POST", cabeceras: form, cuerpo: "signed_request=basura", env });
  assert.equal(r.status, 400);
  const antes = env.VUELTA.escrituras;
  r = await pedir(baja, "/meta/baja", { env }); // Meta puede mirar que la dirección existe
  assert.equal(r.status, 200);
  r = await pedir(borrado, "/meta/borrado", { env, metodo: "HEAD" });
  assert.equal(r.status, 200);
  r = await pedir(baja, "/meta/baja", { env, metodo: "PUT", cuerpo: "x" });
  assert.equal(r.status, 405);
  assert.equal(env.VUELTA.escrituras, antes, "mirar la dirección no deja marcas");
  r = await pedir(recoger, "/recoger?marcas=1", { env });
  assert.equal(r.status, 401);
  r = await pedir(recoger, "/recoger?marcas=1", { env, cabeceras: { Authorization: `Bearer ${LLAVE}` } });
  const { marcas } = await r.json();
  assert.equal(marcas.length, 2);
  const tipos = marcas.map((m) => m.tipo).sort();
  assert.deepEqual(tipos, ["baja", "borrado"]);
  const delBorrado = marcas.find((m) => m.tipo === "borrado");
  assert.equal(delBorrado.codigo, respuesta.confirmation_code);
  assert.equal(delBorrado.usuario, "17841400000000002");
  assert.ok(marcas.every((m) => m.sin_comprobar === true));
  assert.equal(env.VUELTA.datos.size, 0, "las marcas recogidas se borran");
});

prueba("un aviso repetido no gasta otra escritura (y /meta/borrado da el mismo código)", async () => {
  const env = { VUELTA: new KVFalso() };
  const form = { "Content-Type": "application/x-www-form-urlencoded" };
  const cuerpo = avisoDeMeta("17841400000000003");
  let r = await pedir(borrado, "/meta/borrado", { metodo: "POST", cabeceras: form, cuerpo, env });
  const primero = (await r.json()).confirmation_code;
  r = await pedir(borrado, "/meta/borrado", { metodo: "POST", cabeceras: form, cuerpo, env });
  assert.equal((await r.json()).confirmation_code, primero);
  await pedir(baja, "/meta/baja", { metodo: "POST", cabeceras: form, cuerpo, env });
  await pedir(baja, "/meta/baja", { metodo: "POST", cabeceras: form, cuerpo, env });
  assert.equal(env.VUELTA.escrituras, 2, "una marca por cuenta y tipo");
  r = await pedir(baja, "/meta/baja", { metodo: "POST", cabeceras: form, env,
    cuerpo: "signed_request=" + encodeURIComponent("x." + Buffer.from('{"algorithm":"HMAC-SHA256"}').toString("base64url")) });
  assert.equal(r.status, 400, "sin número de cuenta no es un aviso de Meta");
  assert.equal(env.VUELTA.escrituras, 2);
});

prueba("con IG_APP_SECRET, solo valen los avisos que firma Meta (los falsos no escriben nada)", async () => {
  const env = { VUELTA: new KVFalso(), VUELTA_LLAVE: LLAVE, IG_APP_SECRET: SECRETO_APP };
  const form = { "Content-Type": "application/x-www-form-urlencoded" };
  for (const cuerpo of [avisoDeMeta("17841400000000004"), avisoDeMeta("17841400000000004", "otro-secreto")]) {
    for (const fn of [baja, borrado]) {
      const r = await pedir(fn, "/meta/x", { metodo: "POST", cabeceras: form, cuerpo, env });
      assert.equal(r.status, 400);
    }
  }
  assert.equal(env.VUELTA.escrituras, 0, "un aviso sin la firma de Meta no gasta escrituras");
  let r = await pedir(baja, "/meta/baja", { metodo: "POST", cabeceras: form, env,
    cuerpo: avisoDeMeta("17841400000000004", SECRETO_APP) });
  assert.equal(r.status, 200);
  r = await pedir(borrado, "/meta/borrado", { metodo: "POST", cabeceras: form, env,
    cuerpo: avisoDeMeta("17841400000000005", SECRETO_APP) });
  assert.equal(r.status, 200);
  assert.match((await r.json()).confirmation_code, /^[0-9A-F]{12}$/);
  r = await pedir(recoger, "/recoger?marcas=1", { env, cabeceras: { Authorization: `Bearer ${LLAVE}` } });
  const { marcas } = await r.json();
  assert.equal(marcas.length, 2);
  assert.ok(marcas.every((m) => m.sin_comprobar === false), "las firmadas por Meta van comprobadas");
});

prueba("si el KV falla: «inténtalo dentro de un rato», sin enseñar nada (ni un 500)", async () => {
  const env = { VUELTA: new KVRoto(), VUELTA_LLAVE: LLAVE };
  let r = await pedir(vuelta, `/vuelta/instagram?state=${ESTADO}&code=${CODIGO}`, { params: { red: "instagram" }, env });
  assert.equal(r.status, 503);
  const html = await r.text();
  assert.match(html, /Inténtalo dentro de un rato/);
  assert.ok(!html.includes(CODIGO) && !html.includes(ESTADO));
  const form = { "Content-Type": "application/x-www-form-urlencoded" };
  for (const fn of [baja, borrado]) {
    r = await pedir(fn, "/meta/x", { metodo: "POST", cabeceras: form, cuerpo: avisoDeMeta("17841400000000006"), env });
    assert.equal(r.status, 503);
    assert.deepEqual(await r.json(), { fallo: "ocupado" });
  }
  const conLlave = { Authorization: `Bearer ${LLAVE}` };
  for (const q of [`state=${ESTADO}`, "marcas=1"]) {
    r = await pedir(recoger, `/recoger?${q}`, { env, cabeceras: conLlave });
    assert.equal(r.status, 503, q);
    assert.deepEqual(await r.json(), { fallo: "kv" });
  }
});

function archivos(carpeta) {
  return readdirSync(carpeta, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? archivos(join(carpeta, e.name)) : [join(carpeta, e.name)]);
}

prueba("sin console.log, sin cosas de fuera y con las páginas que pide Meta", async () => {
  for (const f of [...archivos(join(RAIZ, "functions")), ...archivos(join(RAIZ, "lib"))]) {
    assert.ok(!/console\./.test(readFileSync(f, "utf8")), `${f} no puede usar console`);
  }
  for (const nombre of ["index", "privacidad", "condiciones", "borrado", "404"]) {
    const html = readFileSync(join(RAIZ, "public", `${nombre}.html`), "utf8");
    assert.match(html, /Panel de cifras/);
    assert.ok(!/https?:\/\//.test(html), `${nombre}.html no puede cargar ni enlazar nada de fuera`);
    assert.ok(!/[\w.+-]+@[\w-]+\.[\w.]+/.test(html), `${nombre}.html no puede llevar correos`);
    assert.ok(!/<script/i.test(html), `${nombre}.html no necesita scripts`);
  }
  const portada = readFileSync(join(RAIZ, "public", "index.html"), "utf8");
  for (const enlace of ["/privacidad", "/condiciones", "/borrado"]) assert.ok(portada.includes(`href="${enlace}"`));
  const toml = readFileSync(join(RAIZ, "wrangler.toml"), "utf8");
  assert.match(toml, /id = "ID_DEL_KV"/, "el id de verdad del KV no va en el repositorio");
  assert.match(toml, /binding = "VUELTA"/);
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
