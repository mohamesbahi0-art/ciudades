// POST /api/subir?para=propios|clips&codigo=<codigo>, con el vídeo como cuerpo (video/mp4, video/quicktime o
// video/webm; de 2 KB a 15 MiB, con Content-Length) → {id: "<para>:<codigo>", url: "/api/subido/<para>:<codigo>"}.
// El vídeo NO se lee entero ni se pasa a base64 (el plan gratis da 10 ms de CPU): solo se miran sus primeros bytes y
// después todo el stream va tal cual a la estantería «buzon-app» del privado, como <para>-<codigo>.<ext>. El
// Comisario automático lo pasa en su vuelta a la rama juicio/<codigo> o buzon/<codigo> (con peticion.json para los
// propios). Para que esa vuelta llegue en 1 o 2 minutos se toca peticiones/app.json y, si es un propio, también
// peticiones/juicio.json.

import { error, json, respuestaDeFallo, sinMetodo } from "../../lib/comun.js";
import { subirAlBuzon } from "../../lib/buzon.js";
import { tocarPeticion } from "../../lib/github.js";
import { CODIGO_VALIDO, DESTINOS, MAX_VIDEO, MIN_VIDEO, TIPOS_VIDEO, pareceVideo, tipoDe } from "../../lib/validar.js";

const CABEZA = 12; // los bytes que hacen falta para reconocer el vídeo

// Lee del cuerpo solo hasta tener CABEZA bytes y devuelve {cabeza, cuerpo}: `cuerpo` es un stream que vuelve a dar
// esos primeros trozos y luego el resto tal cual, sin copiarlo. Si trae más bytes de los que dijo, se corta. En
// Cloudflare va por un FixedLengthStream, para que GitHub reciba el tamaño exacto (Content-Length).
export async function abrirVideo(request, largo) {
  const lector = request.body.getReader();
  const primeros = [];
  let leidos = 0;
  while (leidos < CABEZA) {
    const { done, value } = await lector.read();
    if (done) break;
    primeros.push(value);
    leidos += value.byteLength;
  }
  const cabeza = new Uint8Array(Math.min(CABEZA, leidos));
  let i = 0;
  for (const t of primeros) {
    if (i >= cabeza.length) break;
    const parte = t.subarray(0, cabeza.length - i);
    cabeza.set(parte, i);
    i += parte.byteLength;
  }
  let enviados = 0;
  const pasar = (c, trozo) => {
    enviados += trozo.byteLength;
    if (enviados > largo) {
      c.error(new Error("largo"));
      lector.cancel().catch(() => {});
      return false;
    }
    c.enqueue(trozo);
    return true;
  };
  const origen = new ReadableStream({
    start(c) {
      for (const t of primeros) if (!pasar(c, t)) return;
    },
    async pull(c) {
      const { done, value } = await lector.read();
      if (done) c.close();
      else pasar(c, value);
    },
    cancel(motivo) {
      return lector.cancel(motivo);
    },
  });
  const cuerpo = typeof FixedLengthStream === "function" ? origen.pipeThrough(new FixedLengthStream(largo)) : origen;
  return { cabeza, cuerpo, soltar: () => lector.cancel().catch(() => {}) };
}

export async function onRequest({ request, env }) {
  if (request.method !== "POST") return sinMetodo("POST");
  const q = new URL(request.url).searchParams;
  const para = q.get("para") || "";
  const codigo = q.get("codigo") || "";
  if (!Object.hasOwn(DESTINOS, para)) return error("para", 400);
  if (!CODIGO_VALIDO.test(codigo)) return error("codigo", 400);
  const tipo = tipoDe(request);
  const ext = Object.hasOwn(TIPOS_VIDEO, tipo) ? TIPOS_VIDEO[tipo] : "";
  if (!ext) return error("tipo", 415);
  const texto = request.headers.get("Content-Length");
  if (!texto || !/^\d{1,12}$/.test(texto)) return error("falta_tamano", 411);
  const largo = Number(texto);
  if (largo > MAX_VIDEO) return error("demasiado_grande", 413);
  if (largo < MIN_VIDEO || !request.body) return error("demasiado_pequeno", 400);
  const { cabeza, cuerpo, soltar } = await abrirVideo(request, largo);
  if (!pareceVideo(cabeza, tipo)) {
    soltar();
    return error("no_es_video", 415);
  }
  try {
    await subirAlBuzon(env, { para, codigo, ext, tipo, largo, cuerpo });
  } catch (e) {
    soltar();
    return respuestaDeFallo(e);
  }
  let pronto = false;
  try {
    pronto = await tocarPeticion(env, "peticiones/app.json");
    if (para === "propios") pronto = (await tocarPeticion(env, "peticiones/juicio.json", { codigo })) && pronto;
  } catch {
    pronto = false; // el vídeo ya está en el buzón: el Comisario lo recoge en su vuelta de cada 15 minutos
  }
  const id = `${para}:${codigo}`;
  return json({ id, url: `/api/subido/${id}`, pronto });
}
