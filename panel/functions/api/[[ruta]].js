// Cualquier otra dirección de /api: 404 en JSON (con sesión; sin ella, el portero ya ha dicho 401).

import { error } from "../../lib/comun.js";

export function onRequest() {
  return error("no_existe", 404);
}
