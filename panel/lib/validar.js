// La lista cerrada de lo que el dueño puede escribir desde la app (panel/API.md, «Escribir») y de lo que puede subir.
// Lo que no está aquí da 400 {error: "no_permitido"}.

export const MAX_CUERPO_ESCRIBIR = 64 * 1024; // el JSON entero de /api/escribir
export const MAX_CAMPOS = 48 * 1024; // los campos, ya en JSON
export const ID_VALIDO = /^[A-Za-z0-9._:-]{1,128}$/;
export const CODIGO_VALIDO = /^[A-Za-z0-9_-]{1,64}$/;

// --- Tipos de valor ---
const texto = (max) => (v) => typeof v === "string" && v.length <= max;
const uno = (...validos) => (v) => validos.includes(v);
const fecha = (v) => v === null || (typeof v === "string" && v.length <= 40 && !Number.isNaN(Date.parse(v)));
const booleano = (v) => typeof v === "boolean";
// Un objeto de datos simples (números, textos, sí/no, null, listas y objetos), poco hondo y no muy grande.
const objeto = (max, hondo = 4) => (v) => v !== null && typeof v === "object" && !Array.isArray(v) &&
  simple(v, hondo) && JSON.stringify(v).length <= max;

function simple(v, hondo) {
  if (v === null || typeof v === "boolean" || typeof v === "string") return true;
  if (typeof v === "number") return Number.isFinite(v);
  if (hondo <= 0 || typeof v !== "object") return false;
  if (Array.isArray(v)) return v.every((x) => simple(x, hondo - 1));
  return Object.entries(v).every(([k, x]) => k.length <= 128 && k !== "__proto__" && simple(x, hondo - 1));
}

// coleccion → {crear: qué valores de «crear» acepta, campos: {campo: comprobación(valor, crear)}}
export const PERMITIDO = {
  charla: {
    crear: [true],
    campos: { de: uno("dueno"), texto: texto(1000), fecha, estado: uno("enviado") },
  },
  ordenes: {
    crear: [true, false],
    campos: {
      texto: texto(600),
      fecha,
      estado: (v, crear) => v === (crear ? "nueva" : "cancelada"),
    },
  },
  propios: {
    crear: [true],
    campos: {
      estado: uno("subido"),
      cuenta: texto(80),
      tipoCuenta: texto(40),
      titulo: texto(300),
      texto: texto(2200),
      subido: fecha,
      archivo: objeto(2000, 3),
    },
  },
  clips: {
    crear: [false],
    campos: { estado: uno("grabado", "por_grabar"), grabadoEl: fecha, archivo: objeto(2000, 3) },
  },
  parasubir: {
    crear: [false],
    campos: {
      estado: uno("subido", "descartado"),
      subidoEl: fecha,
      descartadoEl: fecha,
      motivo: texto(120),
    },
  },
  barrios: {
    crear: [false],
    campos: { cifras: objeto(4000), cifrasPorRed: objeto(8000), historialCifras: objeto(16000) },
  },
  sos: {
    crear: [false],
    campos: { decisionDueno: uno("si", "no"), decididoEl: fecha },
  },
  avisos: {
    crear: [false],
    campos: { hecho: booleano, hechoEn: fecha },
  },
  errores: {
    crear: [true],
    campos: Object.fromEntries(["fecha", "donde", "msg", "pila", "vista", "ua", "app"].map((c) => [c, texto(2000)])),
  },
};

// Devuelve {coleccion, id, campos, crear} limpio, o null si algo no está permitido.
export function validarEscritura(cuerpo) {
  if (!cuerpo || typeof cuerpo !== "object") return null;
  const claves = Object.keys(cuerpo);
  if (claves.some((k) => !["coleccion", "id", "campos", "crear"].includes(k))) return null;
  const { coleccion, id, campos } = cuerpo;
  const crear = cuerpo.crear === undefined ? false : cuerpo.crear;
  if (typeof coleccion !== "string" || !Object.hasOwn(PERMITIDO, coleccion)) return null;
  const regla = PERMITIDO[coleccion];
  if (typeof crear !== "boolean" || !regla.crear.includes(crear)) return null;
  if (typeof id !== "string" || !ID_VALIDO.test(id)) return null;
  if (!campos || typeof campos !== "object" || Array.isArray(campos)) return null;
  const nombres = Object.keys(campos);
  if (!nombres.length) return null;
  for (const n of nombres) {
    if (!Object.hasOwn(regla.campos, n)) return null;
    if (!regla.campos[n](campos[n], crear)) return null;
  }
  if (JSON.stringify(campos).length > MAX_CAMPOS) return null;
  return { coleccion, id, campos, crear };
}

// --- Subir vídeos ---
export const MAX_VIDEO = 15 * 1024 * 1024;
export const MIN_VIDEO = 2 * 1024;
export const TIPOS_VIDEO = { "video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm" };
export const DESTINOS = { propios: "juicio", clips: "buzon" };

const ATOMOS_MOV = new Set(["ftyp", "moov", "mdat", "wide", "free", "skip", "pnot"]);

// Mira los primeros bytes: MP4 y MOV llevan una caja ISO («ftyp»; los MOV viejos, «moov», «wide»…) y WebM la marca
// EBML 1A 45 DF A3.
export function pareceVideo(bytes, tipo) {
  if (!bytes || bytes.length < 12) return false;
  const caja = String.fromCharCode(bytes[4], bytes[5], bytes[6], bytes[7]);
  if (tipo === "video/webm") return bytes[0] === 0x1a && bytes[1] === 0x45 && bytes[2] === 0xdf && bytes[3] === 0xa3;
  if (tipo === "video/mp4") return caja === "ftyp";
  if (tipo === "video/quicktime") return ATOMOS_MOV.has(caja);
  return false;
}

export function tipoDe(request) {
  return (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
}
