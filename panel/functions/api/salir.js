// POST /api/salir: borra la cookie de sesión.

import { json, sinMetodo } from "../../lib/comun.js";
import { cookieBorrada } from "../../lib/sesion.js";

export async function onRequest({ request }) {
  if (request.method !== "POST") return sinMetodo("POST");
  return json({ ok: true, dentro: false }, 200, { "Set-Cookie": cookieBorrada() });
}
