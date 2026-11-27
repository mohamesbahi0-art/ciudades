// GET /vuelta/instagram: adonde vuelve el dueño desde Instagram cuando da (o no da) el permiso para LEER sus cifras.
// Lee code, state y error de la dirección y los deja 15 minutos en el KV (vuelta:<state>) para que el turno de conectar
// los recoja con /recoger. Al dueño solo le dice «Listo»: nunca enseña el código. Con HEAD, o sin nada en la
// dirección, contesta 200 sin tocar el KV (así se comprueba que la dirección vale, sin redirecciones).

import { ESTADO_VALIDO, SEGUNDOS_VUELTA, ahora, pagina } from "../../lib/comun.js";

const REDES = new Set(["instagram"]); // TikTok no se hace
const ERROR_VALIDO = /^[a-z0-9_]{1,64}$/;
const CODIGO_VALIDO = /^[\x21-\x7E]{1,4096}$/; // letras, números y signos, sin espacios

const LISTO = "Listo, ya puedes cerrar esta página";

function leer(url) {
  const p = url.searchParams;
  return {
    estado: p.get("state") || "",
    codigo: (p.get("code") || "").replace(/#_$/, ""),
    error: p.get("error") || "",
  };
}

async function guardar(kv, red, { estado, codigo, error }) {
  const respuesta = {
    red,
    code: codigo || null,
    error: error ? (ERROR_VALIDO.test(error) ? error : "otro") : null,
    hora: ahora(),
  };
  const clave = `vuelta:${estado}`;
  const antes = await kv.get(clave, { type: "json" });
  // si el dueño recarga la página llega lo mismo: no se gasta otra escritura
  if (!antes || antes.code !== respuesta.code || antes.error !== respuesta.error) {
    await kv.put(clave, JSON.stringify(respuesta), { expirationTtl: SEGUNDOS_VUELTA });
  }
  return respuesta;
}

export async function onRequest({ request, params, env }) {
  const metodo = request.method;
  if (metodo !== "GET" && metodo !== "HEAD") {
    return new Response(null, { status: 405, headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" } });
  }
  if (!REDES.has(params.red)) {
    return pagina("Esta página no existe", "Vuelve a la app y abre el enlace desde allí.", 404, metodo);
  }
  const datos = leer(new URL(request.url));
  if (metodo === "HEAD" || (!datos.estado && !datos.codigo && !datos.error)) {
    return pagina(
      "Dirección de vuelta del Panel de cifras",
      "Esta página solo sirve para volver desde Instagram después de dar permiso. Ábrela con el enlace de la app.",
      200,
      metodo,
    );
  }
  if (!ESTADO_VALIDO.test(datos.estado) || (!datos.codigo && !datos.error) ||
      (datos.codigo && !CODIGO_VALIDO.test(datos.codigo))) {
    return pagina("Este enlace no vale", "Vuelve a la app y abre otra vez el enlace para conectar la cuenta.", 400);
  }
  if (!env.VUELTA) {
    return pagina("El buzón no está listo", "Inténtalo dentro de un rato desde el enlace de la app.", 503);
  }
  let respuesta;
  try {
    respuesta = await guardar(env.VUELTA, params.red, datos);
  } catch {
    // el KV no deja guardar (por ejemplo, se ha gastado el cupo del día): se dice sin enseñar nada
    return pagina("Ahora no se puede", "Inténtalo dentro de un rato: vuelve a la app y abre otra vez el enlace.", 503);
  }
  if (respuesta.code) {
    return pagina(LISTO, "El permiso ha llegado. En unos minutos la app te dirá si la cuenta ha quedado conectada.");
  }
  return pagina(LISTO, "No se ha dado el permiso. Si quieres conectar la cuenta, abre otra vez el enlace de la app y pulsa «Permitir».");
}
