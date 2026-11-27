// GET /api/yo: {dentro: true}. Sin sesión ni llega aquí: el portero (_middleware.js) contesta 401.

import { json, sinMetodo } from "../../lib/comun.js";

export async function onRequest({ request }) {
  if (request.method !== "GET") return sinMetodo("GET");
  return json({ dentro: true });
}
