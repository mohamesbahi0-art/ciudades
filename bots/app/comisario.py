"""El Comisario automático: la ronda que hacía Claude para la app, hecha por un robot de GitHub sin IA y sin dinero.

Cada pasada (app.yml, cada 15 minutos, o con peticiones/app.json):
  0. Recoge los vídeos que el dueño ha subido en la app (estantería «buzon-app», <para>-<codigo>.<ext>): comprueba con
     ffprobe que son vídeo y su duración, los deja en su rama temporal del privado (juicio/<codigo> o buzon/<codigo>,
     un commit suelto, como en RONDA.md k y k3) y los borra de la estantería.
  1. Aplica lo que el dueño ha hecho en la app: los ficheros entrada/*.json del repositorio privado que deja el portero
     (panel/API.md). Cada uno se vuelve a validar (colección, campos y valores, lista cerrada), se aplica a su fichero de
     estado (lo que hacía la ronda de Claude, RONDA.md del privado) y se mueve a entrada/hechas/ (7 días).
  2. Hace la foto que lee la app: app/datos/todo.json ({actualizado, colecciones}) y app/datos/juicios.json ({juicios},
     los de los últimos 30 días), con las mismas colecciones, ids y campos que tenía la base de la app. Lo que no sale de
     ningún fichero (fichas, ayudas, misiones…) viene de app/base/<coleccion>.json. Solo escribe si algo ha cambiado.
  3. Lo que solo puede hacer Claude (código, Policía, avisos a «fabrica 2.0») no lo hace: lo deja apuntado en
     estado/app/para_claude.json y en un aviso de la app.

Lo del dueño manda: lo que marca en la app queda en app/estado_app.json y se respeta en cada foto, aunque el fichero de
origen todavía no lo tenga.

En los registros públicos solo salen cifras y nombres de colección: nunca nombres de cuentas, títulos ni textos.
Las cuentas (barrio-N) se cambian por su nombre SOLO dentro de los ficheros del repositorio privado.

    python bots/app/comisario.py            (PRIVADO = carpeta del repositorio privado)
    python bots/app/comisario.py --sin-entradas   (solo la foto)
"""
import argparse
import collections
import datetime as dt
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
from bots.comun import almacen, privado  # noqa: E402

ROBOT = "comisario"
TODO = os.path.join("app", "datos", "todo.json")
JUICIOS = os.path.join("app", "datos", "juicios.json")
ESTADO_APP = os.path.join("app", "estado_app.json")
BASE = os.path.join("app", "base")
ENTRADA = "entrada"
HECHAS = os.path.join("entrada", "hechas")
PARA_CLAUDE = os.path.join("estado", "app", "para_claude.json")
ERRORES = os.path.join("estado", "app", "errores.json")
BUZON = os.path.join("estado", "cerebro", "buzon.json")
CHAT = os.path.join("estado", "cerebro", "chat.json")
SOS = os.path.join("estado", "derechos", "sos.json")
PARA_GRABAR = os.path.join("estado", "clips", "para_grabar.json")
CIFRAS_DUENO = os.path.join("estado", "redes", "cifras.json")

# Las 42 colecciones que lee la app (juicios va aparte, en juicios.json).
COLECCIONES = ["propios", "obras", "taller", "cine", "elite", "ia", "cerebro", "charla", "cerebro_chat", "directos",
               "constructor", "videoteca", "coliseo", "ojeador", "derechos", "entrenador", "ciudades", "robots",
               "canales", "barrios", "avisos", "diario", "juicios", "liga", "casos", "recetas", "skills", "plugins",
               "parasubir", "memoria", "analisis", "fichas", "clips", "ayuda", "historial", "mejoras", "radar",
               "cuaderno", "ordenes", "calendario", "sos", "decisiones"]

# Lo que el portero deja escribir (panel/API.md). Aquí se vuelve a comprobar: lo demás se rechaza.
# campo: (tipo, largo máximo o valores permitidos)
TEXTO, FECHA, OBJETO, BOOL = "texto", "fecha", "objeto", "bool"
PERMITIDO = {
    "charla": {"crear": (True,), "campos": {"de": (TEXTO, {"dueno"}), "texto": (TEXTO, 1000), "fecha": (FECHA, 40),
                                             "estado": (TEXTO, {"enviado"})}, "obligatorio": ("texto",)},
    "ordenes": {"crear": (True, False), "campos": {"texto": (TEXTO, 600), "fecha": (FECHA, 40),
                                                    "estado": (TEXTO, {"nueva", "cancelada"})}},
    "propios": {"crear": (True,), "campos": {"estado": (TEXTO, {"subido"}), "cuenta": (TEXTO, 100),
                                             "tipoCuenta": (TEXTO, 40), "titulo": (TEXTO, 300), "texto": (TEXTO, 3000),
                                             "subido": (FECHA, 40), "archivo": (OBJETO, 2000)}, "obligatorio": ("cuenta",)},
    "clips": {"crear": (False,), "campos": {"estado": (TEXTO, {"grabado", "por_grabar"}), "grabadoEl": (FECHA, 40),
                                            "archivo": (OBJETO, 2000)}, "obligatorio": ("estado",)},
    "parasubir": {"crear": (False,), "campos": {"estado": (TEXTO, {"subido", "descartado"}), "subidoEl": (FECHA, 40),
                                                "descartadoEl": (FECHA, 40), "motivo": (TEXTO, 120)}},
    "barrios": {"crear": (False,), "campos": {"cifras": (OBJETO, 20000), "cifrasPorRed": (OBJETO, 20000),
                                              "historialCifras": (OBJETO, 60000)}},
    "sos": {"crear": (False,), "campos": {"decisionDueno": (TEXTO, {"si", "no"}), "decididoEl": (FECHA, 40)}},
    "avisos": {"crear": (False,), "campos": {"hecho": (BOOL, None), "hechoEn": (FECHA, 40)}},
    "errores": {"crear": (True,), "campos": {k: (TEXTO, 2000) for k in ("fecha", "donde", "msg", "pila", "vista",
                                                                          "ua", "app")}},
}
ID_VALIDO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,119}")
CODIGO_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,64}")
EXTENSIONES = (".mp4", ".mov", ".webm", ".m4v", ".mkv")
BUZON_APP = "buzon-app"            # la estantería donde el portero deja lo que sube el dueño: <para>-<codigo>.<ext>
DURACION = {"propios": (2, 180), "clips": (3, 60)}    # segundos (RONDA.md, k y k3)
JUICIOS_MAX = 1_900_000            # bytes de juicios.json (el portero lo devuelve entero)

# Cuánto cabe de cada lista (la foto entera ronda los 0,7 MB).
TOPE = {"diario": 200, "charla": 300, "cine": 40, "coliseo": 30, "historial": 120, "cuaderno": 300, "decisiones": 60,
        "sos": 100, "ordenes": 200, "propios": 100, "avisos": 150}
CUANDO = {   # minuto(s) y cada cuántas horas trabaja cada grupo de robots (UTC), para «siguienteVez»
    "fabrica": ((17, 47), 1), "revision": ((37,), 3), "cerebro": ((10, 25, 40, 55), 1), "mecanicos": ((13, 43), 1),
    "elite": ((27,), 1), "app": ((4, 19, 34, 49), 1), "ventanilla": ((0, 15, 30, 45), 1), "ojeador": ((7,), 3)}
GRUPO_DE = {"cerebro": "cerebro", "elite_espia": "elite", "elite_estratega": "elite", "elite_arquitecto": "elite",
            "jefe_taller": "mecanicos", "mecanico_rondas": "mecanicos", "mecanica_canales": "mecanicos",
            "mecanico_limpieza": "mecanicos", "comisario": "app", "director_general": "app", "ventanilla": "ventanilla",
            "ojeador_redes": "ojeador"}


# ------------------------------------------------------------------ utilidades
def ahora():
    return dt.datetime.now(dt.timezone.utc)


def iso(t=None):
    return (t or ahora()).strftime("%Y-%m-%dT%H:%M:%SZ")


def fecha(s):
    """Una fecha ISO de cualquier robot (con Z, con milésimas o sin zona) o None."""
    if not isinstance(s, str) or len(s) < 10:
        return None
    try:
        t = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            t = dt.datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def horas_desde(s):
    t = fecha(s)
    return (ahora() - t).total_seconds() / 3600 if t else None


def ruta(rel):
    return os.path.join(privado.carpeta(), rel)


def leer(rel, defecto=None):
    v = privado.leer(rel, defecto)
    return defecto if v is None else v


def ficheros(patron):
    return sorted(glob.glob(ruta(patron)))


def sin_ext(f):
    return os.path.splitext(os.path.basename(f))[0]


def quitar(d, *campos):
    return {k: v for k, v in (d or {}).items() if k not in campos and k != "id"}


def ultimos(lista, n, clave="fecha"):
    lista = [x for x in (lista or []) if isinstance(x, dict)]
    return sorted(lista, key=lambda x: str(x.get(clave) or ""))[-n:]


def hash8(texto):
    return hashlib.sha1(str(texto).encode("utf-8")).hexdigest()[:8]


def id_doc(texto):
    """Un id de documento sin barras ni espacios."""
    return re.sub(r"[^A-Za-z0-9_.@-]+", "-", str(texto)).strip("-")[:120] or hash8(texto)


def _git(*args, texto=True, entrada=None):
    return subprocess.run(["git", "-C", privado.carpeta(), *args], capture_output=True, text=texto, input=entrada)


def _cifra(texto):
    """Para los registros públicos: solo el tipo de un fallo, nunca su texto (podría llevar un nombre)."""
    return type(texto).__name__ if isinstance(texto, BaseException) else "?"


# ------------------------------------------------------------------ nombres (solo dentro del privado)
class Nombres:
    """Cambia los alias (barrio-N) por la clave de la cuenta (en los campos que la nombran) o por su nombre (en los
    textos que lee el dueño), y las palabras internas por otras en sencillo."""
    CAMPOS_CLAVE = {"canal", "cuenta", "barrio", "clave", "alias"}

    def __init__(self):
        cfg = privado.config()
        self.canales = cfg.get("canales", {}) or {}
        self.barrios = cfg.get("barrios", {}) or {}
        self.por_alias = {privado.alias(k): k for k in self.barrios}

    def clave(self, x):
        x = str(x or "")
        return self.por_alias.get(x, x)

    def nombre(self, clave):
        clave = self.clave(clave)
        c = self.canales.get(clave) or self.barrios.get(clave) or {}
        return c.get("nombre") or c.get("cuenta") or clave

    def texto(self, s):
        if not isinstance(s, str) or not s:
            return s
        s = re.sub(r"\bbarrio-(\d+)\b", lambda m: self.nombre(m.group(0)) if m.group(0) in self.por_alias else m.group(0), s)
        if " " in s:            # en las frases (no en los estados), lo interno en sencillo
            s = s.replace("→ para_claude", "→ lo pasa a Claude").replace("para_claude", "lo pasa a Claude")
        return s

    def sencillo(self, x, clave=None):
        if isinstance(x, dict):
            return {(self.nombre(k) if k in self.por_alias else k): self.sencillo(v, k) for k, v in x.items()}
        if isinstance(x, list):
            return [self.sencillo(v, clave) for v in x]
        if isinstance(x, str):
            if clave in self.CAMPOS_CLAVE and x in self.por_alias:
                return self.por_alias[x]
            return self.texto(x)
        return x


# ------------------------------------------------------------------ lo que el dueño ha cambiado (manda)
class EstadoApp:
    """app/estado_app.json: {"docs": {coleccion: {id: {"dueno": {...}, "nuestro": {...}, "creado": fecha,
    "cambiado": fecha}}}}. «dueno» es lo que él marcó (manda); «nuestro», lo que el Comisario puso (p. ej. en_juzgado)."""

    def __init__(self):
        self.datos = leer(ESTADO_APP, {}) or {}
        self.datos.setdefault("docs", {})
        self._antes = json.dumps(self.datos, sort_keys=True, ensure_ascii=False)

    def doc(self, col, id_):
        return self.datos["docs"].setdefault(col, {}).setdefault(id_, {"dueno": {}, "nuestro": {}})

    def poner(self, col, id_, dueno=None, nuestro=None, creado=None):
        d = self.doc(col, id_)
        for parte, cambios in (("dueno", dueno), ("nuestro", nuestro)):
            for k, v in (cambios or {}).items():
                if v is None:
                    d[parte].pop(k, None)
                else:
                    d[parte][k] = v
        if creado:
            d.setdefault("creado", creado)
        d["cambiado"] = iso()

    def de(self, col):
        return self.datos["docs"].get(col, {})

    def recortar(self):
        for col, docs in self.datos["docs"].items():
            tope = TOPE.get(col, 400)
            if len(docs) > tope:
                orden = sorted(docs, key=lambda i: str(docs[i].get("creado") or docs[i].get("cambiado") or ""))
                for i in orden[:-tope]:
                    docs.pop(i, None)

    def guardar(self):
        self.recortar()
        if json.dumps(self.datos, sort_keys=True, ensure_ascii=False) != self._antes:
            self.datos["actualizado"] = iso()
            privado.escribir(ESTADO_APP, self.datos)


# ------------------------------------------------------------------ ramas temporales del privado (juicio/, buzon/)
def rama_sha(rama):
    r = _git("ls-remote", "origin", f"refs/heads/{rama}")
    if r.returncode != 0:
        return None
    linea = next((l for l in r.stdout.splitlines() if l.endswith(f"refs/heads/{rama}")), "")
    return linea.split()[0] if linea else None


def rama_ficheros(rama):
    """[(modo, tipo, sha, nombre)] de lo que hay en la rama (sin bajar los vídeos: solo el árbol)."""
    if _git("fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", f"refs/heads/{rama}").returncode != 0 and \
            _git("fetch", "-q", "--depth", "1", "origin", f"refs/heads/{rama}").returncode != 0:
        return None
    r = _git("ls-tree", "FETCH_HEAD")
    if r.returncode != 0:
        return None
    filas = []
    for l in r.stdout.splitlines():
        cabeza, _, nombre = l.partition("\t")
        partes = cabeza.split()
        if len(partes) == 3:
            filas.append((partes[0], partes[1], partes[2], nombre))
    return filas


def completar_peticion(codigo, peticion):
    """Añade peticion.json a la rama juicio/<codigo> que dejó el portero con el vídeo (un commit suelto encima, sin
    tocar main). Devuelve "ya" si ya la tenía, "hecho" o None si no se ha podido."""
    rama = f"juicio/{codigo}"
    sha = rama_sha(rama)
    filas = rama_ficheros(rama) if sha else None
    if filas is None:
        return None
    if any(f[3] == "peticion.json" for f in filas):
        return "ya"
    blob = _git("hash-object", "-w", "--stdin", entrada=json.dumps(peticion, ensure_ascii=False, indent=1))
    if blob.returncode != 0:
        return None
    lineas = [f"{m} {t} {s}\t{n}" for m, t, s, n in filas] + [f"100644 blob {blob.stdout.strip()}\tpeticion.json"]
    arbol = _git("mktree", "--missing", entrada="\n".join(lineas) + "\n")
    if arbol.returncode != 0:
        return None
    commit = _git("-c", "user.name=ciudades-bot", "-c", "user.email=ciudades-bot@users.noreply.github.com",
                  "commit-tree", arbol.stdout.strip(), "-p", sha, "-m", f"petición del vídeo {codigo} del dueño")
    if commit.returncode != 0:
        return None
    r = _git("push", "-q", f"--force-with-lease=refs/heads/{rama}:{sha}", "origin",
             f"{commit.stdout.strip()}:refs/heads/{rama}")
    return "hecho" if r.returncode == 0 else None


def crear_rama(rama, ficheros_):
    """Deja en la rama un commit suelto (sin tocar main) con estos ficheros {nombre: ruta o texto}; si ya existía (el
    dueño ha vuelto a subir), la sustituye."""
    lineas = []
    for nombre, contenido in ficheros_.items():
        if os.path.isfile(contenido):
            blob = _git("hash-object", "-w", contenido)
        else:
            blob = _git("hash-object", "-w", "--stdin", entrada=contenido)
        if blob.returncode != 0:
            return False
        lineas.append(f"100644 blob {blob.stdout.strip()}\t{nombre}")
    arbol = _git("mktree", entrada="\n".join(lineas) + "\n")
    if arbol.returncode != 0:
        return False
    commit = _git("-c", "user.name=ciudades-bot", "-c", "user.email=ciudades-bot@users.noreply.github.com",
                  "commit-tree", arbol.stdout.strip(), "-m", f"vídeo del dueño ({rama.split('/')[0]})")
    if commit.returncode != 0:
        return False
    return _git("push", "-q", "origin", f"+{commit.stdout.strip()}:refs/heads/{rama}").returncode == 0


def probar_video(ruta):
    """(es vídeo, segundos) con ffprobe."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json",
                        ruta], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout or "{}")
    except ValueError:
        return False, 0.0
    video = any(x.get("codec_type") == "video" for x in d.get("streams") or [])
    try:
        segundos = float((d.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        segundos = 0.0
    return video and r.returncode == 0, segundos


def _peticion(codigo, dueno, cuando=None):
    p = {"codigo": codigo, "cuenta": str(dueno.get("cuenta") or ""), "titulo": str(dueno.get("titulo") or ""),
         "texto": str(dueno.get("texto") or ""), "subido": dueno.get("subido") or cuando or iso()}
    if dueno.get("tipoCuenta"):
        p["tipoCuenta"] = dueno["tipoCuenta"]
    return p


def recoger_buzon(est, lanzar):
    """Los vídeos que el dueño ha subido en la app: a su rama temporal (o fuera, si no valen). Devuelve las cuentas
    por resultado (para el registro: nada de códigos ni nombres)."""
    cuenta = collections.Counter()
    try:
        nombres = almacen.lista(BUZON_APP)
    except Exception as e:
        print(f"comisario: no he podido mirar el buzón de la app ({_cifra(e)})", flush=True)
        return cuenta
    for nombre in nombres:
        m = re.fullmatch(r"(propios|clips)-([A-Za-z0-9_-]{1,64})(\.[A-Za-z0-9]{2,5})", nombre)
        if not m or m.group(3).lower() not in EXTENSIONES:
            cuenta[("otro", "raro")] += 1          # no es de la app: no se toca
            continue
        para, codigo, ext = m.group(1), m.group(2), m.group(3).lower()
        try:
            with tempfile.TemporaryDirectory() as t:
                ruta_v = almacen.bajar(BUZON_APP, nombre, t)
                es_video, seg = probar_video(ruta_v)
                minimo, maximo = DURACION[para]
                problema = None
                if not es_video:
                    problema = "No es un vídeo."
                elif not minimo <= seg <= maximo:
                    problema = (f"Dura {round(seg)} segundos: tiene que durar entre {minimo} segundos y 3 minutos."
                                if para == "propios" else f"Dura {round(seg)} segundos: tiene que durar entre 3 y 60.")
                if problema:
                    if para == "propios":
                        est.poner("propios", codigo, nuestro={"estado": "rechazado", "problema": problema})
                    else:
                        est.poner("clips", codigo, nuestro={"enBuzon": False, "problema": problema})
                    est.doc(para, codigo)["video"] = {"estado": "rechazado", "fecha": iso()}
                    almacen.borrar(BUZON_APP, nombre)
                    cuenta[(para, "no vale")] += 1
                    continue
                ficheros_ = {f"{codigo}{ext}": ruta_v}
                dueno = (est.de("propios").get(codigo) or {}).get("dueno") or {}
                if para == "propios" and dueno.get("cuenta"):      # su entrada ya ha llegado: va con su petición
                    ficheros_["peticion.json"] = json.dumps(_peticion(codigo, dueno), ensure_ascii=False, indent=1)
                rama = f"{'juicio' if para == 'propios' else 'buzon'}/{codigo}"
                if not crear_rama(rama, ficheros_):
                    cuenta[(para, "fallo")] += 1         # el archivo se queda: se reintenta en la siguiente pasada
                    continue
                est.doc(para, codigo)["video"] = {"estado": "en_rama", "fecha": iso()}
                if para == "propios":
                    if "peticion.json" in ficheros_:
                        est.poner("propios", codigo, nuestro={"estado": "en_juzgado", "enJuzgadoEl": iso(), "problema": None})
                        lanzar.add("ventanilla")
                    else:
                        est.poner("propios", codigo, nuestro={"problema": None})
                else:
                    est.poner("clips", codigo, nuestro={"problema": None})
                almacen.borrar(BUZON_APP, nombre)
                cuenta[(para, "a su rama")] += 1
        except Exception as e:                      # un vídeo roto no para a los demás
            print(f"comisario: buzón de la app ({para}): fallo {_cifra(e)}", flush=True)
            cuenta[(para, "fallo")] += 1
    return cuenta


def _video_rechazado(est, col, codigo):
    v = est.doc(col, codigo).get("video") or {}
    return v.get("estado") == "rechazado"


# ------------------------------------------------------------------ 1. aplicar las entradas del dueño
def validar(e):
    """(bien, motivo). Lo mismo que comprueba el portero, otra vez: lo que no está en la lista cerrada no entra."""
    if not isinstance(e, dict):
        return False, "no es un JSON"
    col, id_, campos, crear = e.get("coleccion"), e.get("id"), e.get("campos"), bool(e.get("crear"))
    regla = PERMITIDO.get(col)
    if not regla:
        return False, "colección no permitida"
    if not isinstance(id_, str) or not ID_VALIDO.fullmatch(id_):
        return False, "id no válido"
    if col in ("propios", "clips") and not CODIGO_VALIDO.fullmatch(id_):
        return False, "código no válido"
    if crear not in regla["crear"]:
        return False, "crear no permitido"
    if not isinstance(campos, dict) or not campos:
        return False, "sin campos"
    for k, v in campos.items():
        if k not in regla["campos"]:
            return False, "campo no permitido"
        tipo, limite = regla["campos"][k]
        if tipo in (TEXTO, FECHA):
            if not isinstance(v, str):
                return False, "valor no válido"
            if isinstance(limite, set) and v not in limite:
                return False, "valor no permitido"
            if isinstance(limite, int) and len(v) > limite:
                return False, "texto demasiado largo"
            if tipo == FECHA and v and not fecha(v):
                return False, "fecha no válida"
        elif tipo == OBJETO:
            if not isinstance(v, (dict, list)) or len(json.dumps(v, ensure_ascii=False)) > limite:
                return False, "valor no válido"
        elif tipo == BOOL and not isinstance(v, bool):
            return False, "valor no válido"
    for k in regla.get("obligatorio", ()):
        if not str(campos.get(k) or "").strip():
            return False, "falta un campo"
    if col == "ordenes":
        if crear and (campos.get("estado", "nueva") != "nueva" or not str(campos.get("texto") or "").strip()):
            return False, "orden nueva sin texto"
        if not crear and set(campos) != {"estado"} | (set(campos) & {"fecha"}) or (not crear and campos.get("estado") != "cancelada"):
            return False, "solo se puede cancelar"
    return True, ""


class Entradas:
    def __init__(self, est, nombres, lanzar):
        self.est, self.n, self.lanzar = est, nombres, lanzar

    # charla: lo que el dueño le escribe al Cerebro → su buzón
    def charla(self, e, c):
        cuando = c.get("fecha") or e.get("fecha") or iso()
        _al_buzon(e["id"], cuando, c["texto"])
        self.est.poner("charla", e["id"], dueno={"de": "dueno", "texto": c["texto"], "fecha": cuando},
                       nuestro={"estado": "leido"}, creado=cuando)
        self.lanzar.add("cerebro")
        return "hecha"

    # ordenes: sin Claude, se guardan como antes y se las pasa al Cerebro (las hace dentro de sus límites)
    def ordenes(self, e, c):
        id_ = id_doc(e["id"])
        rel = os.path.join("ordenes", f"{id_}.json")
        orden = leer(rel, {}) or {}
        if e.get("crear"):
            cuando = c.get("fecha") or e.get("fecha") or iso()
            orden = dict(orden, texto=c["texto"], fecha=cuando, estado="leida", quien="comisario", leidaEl=iso())
            privado.escribir(rel, orden)
            _al_buzon(f"orden-{id_}", cuando, c["texto"])
            self.est.poner("ordenes", id_, dueno={"texto": c["texto"], "fecha": cuando},
                           nuestro={"estado": "leida", "quien": "comisario"}, creado=cuando)
            self.lanzar.add("cerebro")
        else:                                       # el dueño la cancela: no se toca más
            orden = dict(orden, estado="cancelada", canceladaEl=iso())
            privado.escribir(rel, orden)
            _fuera_del_buzon(f"orden-{id_}")
            self.est.poner("ordenes", id_, dueno={"estado": "cancelada"})
        return "hecha"

    # propios: «Juzga mi vídeo». El portero dejó la rama juicio/<codigo> con el vídeo; aquí va su petición.
    def propios(self, e, c):
        codigo = e["id"]
        dueno = {k: v for k, v in c.items() if k != "estado"}
        self.est.poner("propios", codigo, dueno=dueno, creado=c.get("subido") or e.get("fecha") or iso())
        if _video_rechazado(self.est, "propios", codigo):
            return "hecha"                          # el vídeo no valía: ya tiene su «problema» en la app
        peticion = {"codigo": codigo, "cuenta": str(c.get("cuenta") or ""), "titulo": str(c.get("titulo") or ""),
                    "texto": str(c.get("texto") or ""), "subido": c.get("subido") or e.get("fecha") or iso()}
        if c.get("tipoCuenta"):
            peticion["tipoCuenta"] = c["tipoCuenta"]
        hecho = completar_peticion(codigo, peticion)
        if hecho:
            self.est.poner("propios", codigo, nuestro={"estado": "en_juzgado", "enJuzgadoEl": iso(), "problema": None})
            self.lanzar.add("ventanilla")
            return "hecha"
        if rama_sha(f"juicio/{codigo}") is None:
            if (horas_desde(e.get("fecha")) or 0) < 1:
                return "pendiente"                  # el vídeo puede estar subiendo todavía
            self.est.poner("propios", codigo, nuestro={"estado": "rechazado",
                                                       "problema": "No ha llegado el vídeo. Súbelo otra vez, por favor."})
            return "hecha"
        return "fallo"

    # clips: el dueño ha grabado (o deshace) un clip de la lista «Para grabar»
    def clips(self, e, c):
        codigo = e["id"]
        pg = leer(PARA_GRABAR, {}) or {}
        m = next((x for x in pg.get("momentos") or [] if isinstance(x, dict) and x.get("codigo") == codigo), None)
        if m is None:
            return "rechazada"
        if c["estado"] == "grabado":
            if m.get("estado") != "por_grabar":
                return "hecha"                      # ya iba más avanzado: no se le hace retroceder
            if _video_rechazado(self.est, "clips", codigo):
                return "hecha"                      # el clip no valía: sigue por grabar, con su «problema»
            rama = f"buzon/{codigo}"
            filas = rama_ficheros(rama) if rama_sha(rama) else None
            if not filas:
                if (horas_desde(e.get("fecha")) or 0) < 1:
                    return "pendiente"
                self.est.poner("clips", codigo, nuestro={"enBuzon": False,
                                                         "problema": "No ha llegado el clip: súbelo otra vez, por favor."})
                return "hecha"
            video = next((f[3] for f in filas if f[3].lower().endswith(EXTENSIONES)), f"{codigo}.mp4")
            m.update(estado="grabado", archivo=video, rama=rama, grabadoEl=iso())
            recorte = (c.get("archivo") or {}).get("recorte") if isinstance(c.get("archivo"), dict) else None
            if isinstance(recorte, dict) and all(isinstance(recorte.get(k), (int, float)) for k in ("desde", "hasta")) \
                    and 0 <= recorte["desde"] < recorte["hasta"]:
                m["corte"] = {"desde": recorte["desde"], "hasta": recorte["hasta"]}
            privado.escribir(PARA_GRABAR, pg)
            self.est.poner("clips", codigo, dueno={"archivo": c.get("archivo"), "grabadoEl": c.get("grabadoEl")},
                           nuestro={"enBuzon": True, "problema": None})
            return "hecha"
        # por_grabar: lo deshace (solo si aún no lo ha usado la fábrica)
        if m.get("estado") == "grabado" and not m.get("en_videoteca"):
            m["estado"] = "por_grabar"
            for k in ("archivo", "rama", "grabadoEl", "corte"):
                m.pop(k, None)
            privado.escribir(PARA_GRABAR, pg)
        self.est.poner("clips", codigo, dueno={"archivo": None, "grabadoEl": None}, nuestro={"enBuzon": False})
        return "hecha"

    # parasubir: subido o descartado (lo del dueño manda)
    def parasubir(self, e, c):
        id_ = e["id"]
        rel = os.path.join("parasubir", f"{id_}.json")
        d = leer(rel, None)
        if not isinstance(d, dict) or "/" in id_:
            return "rechazada"
        d.update(c)
        privado.escribir(rel, d)
        self.est.poner("parasubir", id_, dueno=c)
        return "hecha"

    # barrios: las cifras que apunta el dueño → estado/redes/cifras.json
    def barrios(self, e, c):
        clave = self.n.clave(e["id"])
        if clave not in self.n.barrios:
            return "rechazada"
        todas = leer(CIFRAS_DUENO, {}) or {}
        fila = todas.setdefault(clave, {})
        dueno = {}
        if isinstance(c.get("cifrasPorRed"), dict):
            por_red = dict(fila.get("cifrasPorRed") or {})
            for red, cif in c["cifrasPorRed"].items():
                if isinstance(cif, dict):
                    por_red[str(red)[:20]] = dict(cif, fecha=cif.get("fecha") or e.get("fecha") or iso())
            fila["cifrasPorRed"] = dueno["cifrasPorRed"] = por_red
        if isinstance(c.get("cifras"), dict):
            fila["cifras"] = dueno["cifras"] = dict(c["cifras"], fecha=c["cifras"].get("fecha") or e.get("fecha") or iso())
        if "historialCifras" in c:
            fila["historialCifras"] = dueno["historialCifras"] = c["historialCifras"]
        fila["cambiado"] = iso()
        privado.escribir(CIFRAS_DUENO, todas)
        self.est.poner("barrios", clave, dueno=dueno)
        return "hecha"

    # sos: el dueño contesta sí o no
    def sos(self, e, c):
        s = leer(SOS, {}) or {}
        mensajes = s.setdefault("mensajes", [])
        m = next((x for x in mensajes if isinstance(x, dict) and x.get("id") == e["id"]), None)
        if m is None:
            m = {"id": e["id"]}
            mensajes.append(m)
        m.update(decisionDueno=c.get("decisionDueno", m.get("decisionDueno")),
                 decididoEl=c.get("decididoEl") or e.get("fecha") or iso())
        s["actualizado"] = iso()
        privado.escribir(SOS, s)
        self.est.poner("sos", e["id"], dueno={k: m[k] for k in ("decisionDueno", "decididoEl")})
        return "hecha"

    def avisos(self, e, c):
        self.est.poner("avisos", e["id"], dueno=c)
        return "hecha"

    def errores(self, e, c):
        d = leer(ERRORES, {}) or {}
        lista = d.get("errores") or []
        lista.append(dict(c, id=e["id"], recibido=iso()))
        privado.escribir(ERRORES, {"errores": lista[-200:], "actualizado": iso()})
        return "hecha"


def _al_buzon(id_, cuando, texto):
    b = leer(BUZON, {}) or {}
    mensajes = [m for m in b.get("mensajes") or [] if isinstance(m, dict)]
    if not any(m.get("id") == id_ for m in mensajes):
        mensajes.append({"id": id_, "fecha": cuando, "texto": texto})
    b["mensajes"] = mensajes[-200:]
    privado.escribir(BUZON, b)


def _fuera_del_buzon(id_):
    chat = leer(CHAT, {}) or {}
    if any(m.get("responde_a") == id_ for m in chat.get("conversacion") or [] if isinstance(m, dict)):
        return                                   # ya la contestó: queda como estaba
    b = leer(BUZON, {}) or {}
    antes = b.get("mensajes") or []
    b["mensajes"] = [m for m in antes if not (isinstance(m, dict) and m.get("id") == id_)]
    if len(b["mensajes"]) != len(antes):
        privado.escribir(BUZON, b)


def aplicar_entradas(est, nombres, lanzar, maximo=200):
    """Aplica cada entrada/*.json en orden de nombre. Devuelve las cuentas por resultado y colección (para el registro)."""
    hacer = Entradas(est, nombres, lanzar)
    cuenta = collections.Counter()
    for f in ficheros(os.path.join(ENTRADA, "*.json"))[:maximo]:
        try:
            with open(f, encoding="utf-8") as fh:
                e = json.load(fh)
        except (OSError, ValueError):
            e = None
        bien, motivo = validar(e)
        col = e.get("coleccion") if isinstance(e, dict) and e.get("coleccion") in PERMITIDO else "otra"
        if not bien:
            resultado = "rechazada"
        else:
            if not e.get("fecha"):
                m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", os.path.basename(f))
                e["fecha"] = f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}Z" if m else iso()
            try:
                resultado = getattr(hacer, e["coleccion"])(e, e["campos"])
            except Exception as x:                  # una entrada rota no para a las demás
                print(f"comisario: entrada de {col}: fallo {_cifra(x)}", flush=True)
                resultado = "fallo"
            if resultado == "rechazada":
                motivo = motivo or "el documento no existe"
        cuenta[(col, resultado)] += 1
        if resultado == "pendiente" or (resultado == "fallo" and (horas_desde(e.get("fecha")) or 0) < 24):
            continue                                # se reintenta en la siguiente pasada
        hecha = dict(e) if isinstance(e, dict) else {"roto": True}
        hecha.update(resultado=resultado, aplicada=iso())
        if motivo:
            hecha["motivo_rechazo"] = motivo
        privado.escribir(os.path.join(HECHAS, os.path.basename(f)), hecha)
        os.remove(f)
    for f in ficheros(os.path.join(HECHAS, "*.json")):           # las hechas, 7 días
        d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
        h = horas_desde(d.get("aplicada"))
        if h is None:
            h = (ahora().timestamp() - os.path.getmtime(f)) / 3600
        if h > 24 * 7:
            os.remove(f)
    return cuenta


# ------------------------------------------------------------------ 2. la foto de la app
def _base(col):
    d = leer(os.path.join(BASE, f"{col}.json"), {}) or {}
    return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


_MOD_ROBOTS = []


def _robots_privado():
    if not _MOD_ROBOTS:
        _MOD_ROBOTS.append(_cargar_robots_privado())
    return _MOD_ROBOTS[0]


def _cargar_robots_privado():
    """La lógica de ronda/estado_robots.py del privado (frases y motivos), si está; si no, una sencilla."""
    r = ruta(os.path.join("ronda", "estado_robots.py"))
    if os.path.exists(r):
        try:
            spec = importlib.util.spec_from_file_location("estado_robots_privado", r)
            mod = importlib.util.module_from_spec(spec)
            antes, sys.dont_write_bytecode = sys.dont_write_bytecode, True   # sin __pycache__ en el privado
            try:
                spec.loader.exec_module(mod)
            finally:
                sys.dont_write_bytecode = antes
            return mod
        except Exception as e:
            print(f"comisario: no he podido leer la lógica de los robots ({_cifra(e)}): uso la sencilla", flush=True)
    return None


def _siguiente(grupo):
    minutos, cada = CUANDO[grupo]
    t = ahora().replace(second=0, microsecond=0)
    for paso in range(0, 60 * 24):
        h = t + dt.timedelta(minutes=paso + 1)
        if h.minute in minutos and h.hour % cada == 0:
            return iso(h)
    return None


class Foto:
    def __init__(self, nombres, est, antes):
        self.n, self.est = nombres, est
        self.antes = (antes or {}).get("colecciones") or {}
        self.man = leer("manifiesto.json", {}) or {}
        self.cfg_fabrica = leer(os.path.join("config", "fabrica.json"), {}) or {}
        self.cifras = leer(os.path.join("estado", "app", "cifras.json"), {}) or {}
        self.para_claude = []
        self.avisos_nuevos = {}
        self.diario_nuevo = {}
        self.errores = []

    # --- las que lee la app, una por una ---------------------------------------------------
    def ciudades(self):
        base = _base("ciudades")
        bots = self.man.get("bots") or []
        docs = {}
        for c in self.man.get("ciudades") or []:
            if not c.get("id"):
                continue
            hechos = [b for b in bots if b.get("ciudad") == c["id"] and b.get("reconstruido")]
            docs[c["id"]] = dict(quitar(c), fase="funcionando" if hechos else "plano")
            docs[c["id"]].update(base.get(c["id"], {}))      # la fase y la nota que puso «app ciudad» mandan
        for k, v in base.items():
            docs.setdefault(k, dict(v))
        for k in ("derechos", "coliseo"):
            if k in docs and leer(os.path.join("estado", "derechos" if k == "derechos" else "coliseo",
                                               "salud.json" if k == "derechos" else "resumen.json")):
                docs[k]["fase"] = "funcionando"
        return docs

    def skills(self):
        base = _base("skills")             # la lista de «app ciudad» manda; si falta, la del manifiesto
        return base or {s["id"]: quitar(s) for s in self.man.get("skills") or [] if s.get("id")}

    def plugins(self):
        base = _base("plugins")
        return base or {id_doc(p.get("nombre", "").lower()): quitar(p) for p in self.man.get("plugins_recomendados") or []
                        if p.get("nombre")}

    def fichas(self):
        return _base("fichas")

    def robots(self):
        mod = _robots_privado()
        frase = getattr(mod, "frase", None) or (lambda e: str(e.get("accion") or ""))
        no_se_puede = getattr(mod, "NO_SE_PUEDE", {}) or {}
        fabrica = getattr(mod, "FABRICA", set()) or set()
        revision = getattr(mod, "REVISION", set()) or set()
        salud = (leer(os.path.join("estado", "derechos", "salud.json"), {}) or {}).get("robots") or {}
        base = _base("robots")
        docs = {}
        for bot in self.man.get("bots") or []:
            bid = bot.get("id")
            if not bid:
                continue
            datos = dict(base.get(bid, {}))     # lo de «app ciudad» (nombre, ficha…); lo vivo de aquí lo pisa
            for k in ("estado", "detalle", "ultimaAccion", "ultimaVez", "siguienteVez", "porCanal"):
                datos.pop(k, None)
            datos.update(quitar(bot, "memoria"))
            cuaderno = leer(os.path.join("memoria", f"{bid}.json"), {}) or {}
            diario = [e for e in cuaderno.get("diario") or [] if isinstance(e, dict) and e.get("fecha")]
            if not diario:
                datos.update(estado="parado", detalle=no_se_puede.get(bid, "Todavía no ha trabajado."))
            else:
                ultima = diario[-1]
                h = horas_desde(ultima["fecha"]) or 99
                datos["estado"] = (("atasco" if ultima.get("accion") == "error" else
                                    "espera" if ultima.get("accion") == "espera_ia" else "trabaja") if h <= 6 else "espera")
                texto = _frase(frase, ultima)
                datos.update(ultimaAccion=texto, ultimaVez=ultima["fecha"], detalle={
                    "trabaja": f"Trabajando. Lo último: {texto}.", "atasco": f"Su último intento falló: {texto}.",
                    "espera": f"Espera su turno. Lo último que hizo: {texto}."}[datos["estado"]])
                por_canal = {}
                for e in reversed(diario[-60:]):
                    det = e.get("detalle") if isinstance(e.get("detalle"), dict) else {}
                    canal = det.get("canal") or det.get("barrio")
                    if canal and isinstance(canal, str) and self.n.clave(canal) not in por_canal:
                        hc = horas_desde(e["fecha"]) or 99
                        por_canal[self.n.clave(canal)] = {
                            "estado": ("atasco" if e.get("accion") == "error" else "espera" if e.get("accion") == "espera_ia"
                                       else "trabaja") if hc <= 6 else "espera",
                            "ultimaAccion": _frase(frase, e), "ultimaVez": e["fecha"]}
                if por_canal:
                    datos["porCanal"] = por_canal
            grupo = GRUPO_DE.get(bid) or ("fabrica" if bid in fabrica else "revision" if bid in revision else None)
            if grupo and datos["estado"] != "parado":
                datos["siguienteVez"] = _siguiente(grupo)
            if bid in salud and isinstance(salud[bid], dict):
                datos["salud"] = {k: v for k, v in salud[bid].items() if k not in ("nombre", "ciudad")}
            docs[bid] = datos
        for bid, v in base.items():             # los que solo están en la base (sin cuaderno ni manifiesto)
            docs.setdefault(bid, dict(v))
        self._robots_trabajan(docs)
        return docs

    def _robots_trabajan(self, docs):
        """Los que no apuntan en su cuaderno pero se ve su trabajo en su fichero (RONDA.md: k6, q, r, t, u, v, w)."""
        def trabaja(ids, cuando, que):
            if (horas_desde(cuando) or 99) > 6:
                return
            for bid in ids:
                if bid in docs and docs[bid].get("estado") != "trabaja":
                    docs[bid].update(estado="trabaja", ultimaAccion=que, ultimaVez=cuando,
                                     detalle=f"Trabajando. Lo último: {que}.")
        t = leer(os.path.join("estado", "mecanicos", "taller.json"), {}) or {}
        arr = ultimos(t.get("arreglos"), 1)
        trabaja(["jefe_taller", "mecanico_rondas", "mecanica_canales", "mecanico_limpieza"], t.get("ultimo"),
                self.n.texto(arr[0].get("que")) if arr else "Revisó el taller")
        c = leer(os.path.join("estado", "coliseo", "resumen.json"), {}) or {}
        trabaja(["organizador_juegos", "gladiadores", "juez_ciego"], c.get("actualizado"), "Organizó un torneo")
        e = leer(os.path.join("estado", "elite", "elite.json"), {}) or {}
        trabaja(["elite_espia", "elite_estratega", "elite_arquitecto"], e.get("ultimo"), "Repasó el parte general")
        s = leer(os.path.join("estado", "cine", "sesiones.json"), {}) or {}
        trabaja(["publico_cine", "acomodador"], s.get("actualizado"), "Llenó una sesión del Cine")
        trabaja(["contador_redes"], self.cifras.get("actualizado"), "Contó las visitas y las cifras de las redes")

    def canales(self):
        base = _base("canales")
        man = {c.get("clave"): c for c in self.man.get("canales") or [] if c.get("clave")}
        permisos = (leer(os.path.join("estado", "permisos.json"), {}) or {}).get("permisos") or {}
        esperan = self._esperan()
        reformas = (leer(os.path.join("estado", "elite", "elite.json"), {}) or {}).get("reformas") or {}
        informe = (leer(os.path.join("estado", "analisis", "informe.json"), {}) or {}).get("youtube") or {}
        cif = self.cifras.get("canales") or {}
        docs = {}
        for clave, c in self.n.canales.items():
            m = man.get(clave, {})
            rev = leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
            turnos = self._turnos(clave)
            d = {"nombre": c.get("nombre") or m.get("nombre") or clave, "red": "youtube", "horas": c.get("horas") or [],
                 "permiso": permisos.get(clave) or rev.get("permiso") or m.get("permiso") or "sin_conectar"}
            for k in ("apodo", "tema", "tipo"):
                if c.get(k):
                    d[k] = c[k]
            if m.get("id"):
                d["plataformas"] = {"youtube": {"id": m["id"], "url": f"https://www.youtube.com/channel/{m['id']}"}}
            d["estado"], d["detalle"] = self._estado_canal(clave, c, d["permiso"], turnos, rev, esperan, reformas)
            programados = rev.get("programados") or []
            d.update(programados24h=rev.get("programados24h") or 0, videosProgramados=len(programados),
                     hasta=rev.get("hasta"), suscriptores=rev.get("suscriptores"))
            x = cif.get(clave) or {}
            uv = x.get("ultimoVideo") or rev.get("ultimo_publicado")
            if isinstance(uv, dict):
                d["ultimoVideo"] = {k: uv.get(k) for k in ("titulo", "url", "publicado", "visitas")}
            if x.get("visitas"):
                d["visitas"] = x["visitas"]
            elif (informe.get(clave) or {}).get("visitas_24h") is not None:
                d["visitas"] = {"hoy": informe[clave]["visitas_24h"]}
            for k in ("suscriptoresNuevos", "visitasTotales"):
                if x.get(k) is not None:
                    d[k] = x[k]
            if turnos:
                t = turnos[-1]
                d["ultimoTurno"] = {"fecha": t.get("empezado"), "resultado": t.get("resultado"),
                                    "destino": t.get("destino_resultado"), "titulo": t.get("titulo"), "nota": t.get("nota")}
            docs[clave] = dict(base.get(clave, {}), **d)
        return docs

    def _esperan(self):
        esperan = {}
        for f in ficheros(os.path.join("estado", "fabrica*.json")):
            esperan.update(leer(os.path.relpath(f, privado.carpeta()), {}).get("esperan") or {})
        return {self.n.clave(k): v for k, v in esperan.items()}

    def _turnos(self, clave):
        c = leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}
        turnos = [t for t in c.get("turnos") or [] if isinstance(t, dict) and not t.get("prueba")]
        return sorted(turnos, key=lambda t: str(t.get("empezado") or ""))

    def _estado_canal(self, clave, c, permiso, turnos, rev, esperan, reformas):
        if c.get("pausado") or c.get("estado") == "en_pausa":
            return "en_pausa", c.get("motivo") or "En pausa."
        if permiso == "caducado":
            return "atasco", "El permiso de YouTube ha caducado: hay que volver a darlo."
        if clave in reformas:
            return "espera", "En reforma: " + str((reformas[clave] or {}).get("motivo") or "la Élite lo está mejorando.")
        if turnos and turnos[-1].get("resultado") == "error" and re.match(r"\s*(SinIA|EsperaIA)", str(turnos[-1].get("error"))):
            return "espera", "Espera a la IA: " + _corto(str(turnos[-1].get("error")).split(":", 1)[-1], 140)
        if turnos and turnos[-1].get("resultado") == "error":
            return "atasco", "Su último turno falló: " + _corto(turnos[-1].get("error"), 140)
        recientes = [t for t in turnos if (horas_desde(t.get("terminado") or t.get("empezado")) or 99) <= 6
                     and t.get("resultado") == "hecho" and t.get("destino_resultado") in ("subido", "en_cola", "para_subir")]
        if recientes:
            t = recientes[-1]
            return "trabaja", f"Ha hecho «{_corto(t.get('titulo'), 80)}»" + (f" ({t['nota']}/100)" if t.get("nota") else "") + "."
        if not turnos and not rev.get("recientes"):
            return "parado", esperan.get(clave) or "Todavía no ha empezado."
        if esperan.get(clave):
            return "espera", str(esperan[clave])
        if rev.get("hasta"):
            return "espera", f"Tiene vídeos programados hasta el {str(rev['hasta'])[:10]}."
        return "espera", "Espera su turno."

    def parasubir(self):
        docs = {}
        for f in ficheros(os.path.join("parasubir", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), None)
            if not isinstance(d, dict):
                continue
            doc = quitar(d, "_id")
            if doc.get("video"):
                doc["videoGithub"] = doc["video"]
                doc["videoNombre"] = str(doc["video"]).rstrip("/").rsplit("/", 1)[-1]
            docs[sin_ext(f)] = doc
        for id_, d in self.est.de("parasubir").items():       # lo del dueño manda
            if id_ in docs:
                docs[id_].update(d.get("dueno") or {})
        return docs

    def barrios(self):
        base = _base("barrios")
        man = {b.get("cuenta"): b for b in self.man.get("barrios") or [] if b.get("cuenta")}
        esperan = self._esperan()
        auto = self.cifras.get("barrios") or {}
        dueno_cif = leer(CIFRAS_DUENO, {}) or {}
        pend = collections.Counter()
        subidos = collections.Counter()
        recientes = collections.Counter()
        for f in ficheros(os.path.join("parasubir", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            dueno = (self.est.de("parasubir").get(sin_ext(f)) or {}).get("dueno") or {}
            estado = dueno.get("estado") or d.get("estado")
            b = self.n.clave(d.get("barrio"))
            if estado == "subido":
                subidos[b] += 1
            elif estado != "descartado":
                pend[b] += 1
                if (horas_desde(d.get("creado")) or 99) <= 6:
                    recientes[b] += 1
        docs = {}
        for clave, b in self.n.barrios.items():
            m = man.get(clave, {})
            redes = b.get("redes") or m.get("redes") or []
            d = {"nombre": b.get("nombre") or m.get("nombre") or b.get("cuenta") or clave, "cuenta": b.get("cuenta") or clave,
                 "red": (redes or [m.get("red") or "instagram"])[0], "redes": redes}
            for k in ("apodo", "tema", "idioma"):
                if b.get(k):
                    d[k] = b[k]
            turnos = self._turnos(clave)
            if b.get("estado", "activo") != "activo" or b.get("pausado"):
                d["estado"], d["detalle"] = "en_pausa", b.get("motivo") or esperan.get(clave) or "En pausa."
            else:
                hecho = recientes[clave] or any((horas_desde(t.get("empezado")) or 99) <= 6 and t.get("resultado") == "hecho"
                                                for t in turnos)
                d["estado"] = "trabaja" if hecho else "espera"
                d["detalle"] = (f"{pend[clave]} vídeo(s) esperando en «Para subir» y {subidos[clave]} ya subido(s)."
                                + (f" Ahora: {esperan[clave]}" if not hecho and esperan.get(clave) else ""))
            d["pendientes"], d["subidos"] = pend[clave], subidos[clave]
            a = auto.get(clave) or {}
            por_red = {red: dict(v) for red, v in (a.get("cifrasPorRed") or {}).items() if isinstance(v, dict)}
            mio = dueno_cif.get(clave) or {}
            dueno = (self.est.de("barrios").get(clave) or {}).get("dueno") or {}
            for red, v in dict(mio.get("cifrasPorRed") or {}, **(dueno.get("cifrasPorRed") or {})).items():
                if not isinstance(v, dict):
                    continue
                suyo = por_red.get(red) or {}
                if str(v.get("fecha") or "")[:10] >= str(suyo.get("fecha") or "")[:10]:   # lo de hoy del dueño manda
                    por_red[red] = dict(v, auto=False)
            if por_red:
                d["cifrasPorRed"] = por_red
            for k in ("cifras", "historialCifras"):
                if (dueno.get(k) or mio.get(k)) is not None:
                    d[k] = dueno.get(k) or mio.get(k)
            if a.get("videos"):
                d["videos"] = (a.get("videos") or [])[:12]
            seg = [v.get("seguidores") for v in por_red.values() if isinstance(v.get("seguidores"), (int, float))]
            if seg:
                d["seguidores"] = max(seg)
            docs[clave] = dict(base.get(clave, {}), **d)
        return docs

    def diario(self):
        docs = {k: v for k, v in (self.antes.get("diario") or {}).items() if isinstance(v, dict)}
        for clave in list(self.n.canales) + list(self.n.barrios):
            nombre = self.n.nombre(clave)
            for t in self._turnos(clave):
                if not t.get("empezado"):
                    continue
                texto, quien = _frase_turno(t, nombre, clave in self.n.barrios)
                if texto:
                    id_ = id_doc(f"{t['empezado'].replace(':', '').replace('-', '')}-{clave}")
                    docs[id_] = {"fecha": t.get("terminado") or t["empezado"], "ciudad": "central", "quien": quien,
                                 "texto": texto, "canal": clave}
        for f in ficheros(os.path.join("estado", "coliseo", "torneos", "*.json"))[-TOPE["coliseo"]:]:
            t = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            camp = t.get("campeon") or {}
            if t.get("prueba") or not camp:
                continue
            titulo = (camp.get("salida") or {}).get("titulo") or ""
            docs[f"coliseo-{sin_ext(f)}"] = {"fecha": t.get("fecha"), "ciudad": "coliseo", "quien": "organizador_juegos",
                                             "canal": self.n.clave(t.get("canal")),
                                             "texto": f"El Coliseo: ganó {camp.get('nombre')} (carta {camp.get('carta')}) "
                                                      f"con el título «{titulo}»."}
        fuentes = (leer(os.path.join("estado", "influencers", "ojeador", "tendencias.json"), {}) or {}).get("fuentes") or {}
        for red, f in fuentes.items():
            desde = (f or {}).get("bloqueada_desde")
            if (f or {}).get("estado") == "bloqueada" and (horas_desde(desde) or 0) > 48:
                nombre = "TikTok" if "tiktok" in red else "Instagram" if "instagram" in red else red
                docs[id_doc(f"ojeador-bloqueada-{red}-{str(desde)[:10]}")] = {
                    "fecha": desde, "ciudad": "influencers", "quien": "ojeador_redes",
                    "texto": f"{nombre} no deja mirar al Ojeador desde el {str(desde)[:10]}. No es un fallo: lo vuelve a probar solo."}
        docs.update(self.diario_nuevo)
        orden = sorted(docs, key=lambda i: str(docs[i].get("fecha") or ""))[-TOPE["diario"]:]
        return {i: docs[i] for i in orden}

    def analisis(self):
        inf = leer(os.path.join("estado", "analisis", "informe.json"), {}) or {}
        i = inf.get("informe") or {}
        if not i:
            return {}
        return {"hoy": {"titular": i.get("titular"), "puntos": i.get("puntos") or [], "consejos": i.get("consejos") or [],
                        "fecha": inf.get("fecha") or inf.get("actualizado")}}

    def liga(self):
        jueces = (leer(os.path.join("estado", "juzgado", "liga.json"), {}) or {}).get("jueces") or {}
        candidatos = [(v.get("aciertos") or 0, k) for k, v in jueces.items()
                      if k != "jurado" and (v.get("comparaciones") or 0) >= 10 and v.get("aciertos") is not None]
        mayor = max(candidatos)[1] if candidatos else "reloj"
        return {k: {"nombre": v.get("nombre") or k, "sala": "juzgado", "puesto": "mayor" if k == mayor else "sala",
                    "aciertos": v.get("aciertos"), "comparaciones": v.get("comparaciones") or 0}
                for k, v in jueces.items() if isinstance(v, dict)}

    def recetas(self):
        canales = (leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales") or {}
        docs = {}
        for clave, r in canales.items():
            if not isinstance(r, dict) or not (r.get("titulo") or r.get("gancho")):
                continue                            # solo con radar u ojeador: ya está en radar/
            clave = self.n.clave(clave)
            virales = (leer(os.path.join("estado", "influencers", "virales", f"{clave}.json"), {}) or {}).get("lista") or []
            partes = [f"Título: {r['titulo']}" if r.get("titulo") else "", f"gancho: {r['gancho']}" if r.get("gancho") else "",
                      f"duración: {r['duracion']}" if r.get("duracion") else "", f"final: {r['final']}" if r.get("final") else ""]
            docs[clave] = {"fecha": r.get("fecha"), "tema": self.n.nombre(clave),
                           "receta": "; ".join(p for p in partes if p) + ".",
                           "ejemplos": [f"https://youtu.be/{v['id']}" for v in virales[:3] if isinstance(v, dict) and v.get("id")]}
        return docs

    def casos(self):
        docs = {}
        for c in (leer(os.path.join("estado", "casos.json"), {}) or {}).get("casos") or []:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            docs[id_doc(c["id"])] = {"fecha": c.get("fecha"), "robot": c.get("robot"), "problema": c.get("problema"),
                                      "estado": c.get("estado"), "arreglo": c.get("arreglo") or c.get("se_arregla"),
                                      "veces": c.get("veces"), "ultima": c.get("ultima")}
            if c.get("estado") == "necesita_al_dueno":
                self.avisos_nuevos[f"caso-{id_doc(c['id'])}"] = {
                    "tipo": "mision", "ciudad": "policia", "fecha": c.get("fecha"), "titulo": "Un robot te necesita",
                    "texto": str(c.get("problema") or ""), "hecho": False}
        return docs

    def clips(self):
        docs = {}
        for m in (leer(PARA_GRABAR, {}) or {}).get("momentos") or []:
            if not isinstance(m, dict) or not m.get("codigo"):
                continue
            if m.get("estado") == "descartado" and (horas_desde(m.get("descartado") or m.get("actualizado")) or 0) > 24 * 7:
                continue
            d = quitar(m, "video", "elegido", "rama", "codigo")
            if m.get("rama") and m.get("estado") == "grabado":
                d["enBuzon"] = True
            suyo = self.est.de("clips").get(m["codigo"]) or {}
            d.update({k: v for k, v in (suyo.get("dueno") or {}).items() if k != "estado"})
            d.update(suyo.get("nuestro") or {})
            if m.get("estado") != "por_grabar":
                d.pop("problema", None)
            docs[id_doc(m["codigo"])] = d
        return docs

    def videoteca(self):
        v = leer(os.path.join("estado", "clips", "videoteca.json"), {}) or {}
        tomas = [t for t in v.get("tomas") or [] if isinstance(t, dict)]
        por_juego = collections.Counter(t.get("juego") for t in tomas if t.get("juego"))
        por_etiqueta = {}
        for t in tomas:
            for e in t.get("etiquetas") or []:
                por_etiqueta.setdefault(e, {"gta5": 0, "gta6": 0})
                if t.get("juego") in ("gta5", "gta6"):
                    por_etiqueta[e][t["juego"]] += 1
        resumen = {"total": len(tomas), "porJuego": {"gta5": por_juego.get("gta5", 0), "gta6": por_juego.get("gta6", 0)},
                   "porEtiqueta": por_etiqueta, "parejas": sorted(e for e, x in por_etiqueta.items() if x["gta5"] and x["gta6"]),
                   "tomas": [{"id": t.get("id"), "juego": t.get("juego"), "etiquetas": t.get("etiquetas") or [],
                              "queSeVe": t.get("que_se_ve"), "segundos": t.get("segundos"), "usos": t.get("usos") or 0,
                              "ultimoUso": t.get("ultimo_uso"), "creador": t.get("creador"), "enlace": t.get("enlace")}
                             for t in tomas],
                   "minimos": _minimos_videoteca(), "actualizado": v.get("actualizado")}
        r = leer(os.path.join("estado", "clips", "recolector.json"), {}) or {}
        if r:
            resumen["recolector"] = {"ultimo": r.get("ultimo"), "vistos": len(r.get("vistos") or {}),
                                     "pendientes": r.get("pendientes") or 0}
        return {"resumen": resumen}

    def propios(self):
        docs = {}
        resultados = {sin_ext(f): f for f in ficheros(os.path.join("estado", "propios", "*.json"))}
        for codigo in set(self.est.de("propios")) | set(resultados):
            suyo = self.est.de("propios").get(codigo) or {}
            d = {"estado": "subido"}
            d.update(suyo.get("dueno") or {})
            d.update(suyo.get("nuestro") or {})
            r = leer(os.path.relpath(resultados[codigo], privado.carpeta()), {}) if codigo in resultados else {}
            if r:
                d.update(_resultado_propio(r, self.n))
                if r.get("estado") in ("aprobado", "suspendido", "rechazado"):
                    d.pop("problema", None) if not r.get("problema") else None
            if suyo.get("dueno", {}).get("archivo"):
                d["archivo"] = suyo["dueno"]["archivo"]            # nunca se toca lo que subió el dueño
            docs[id_doc(codigo)] = d
        return dict(sorted(docs.items(), key=lambda kv: str(kv[1].get("subido") or ""))[-TOPE["propios"]:])

    def directos(self):
        docs = {}
        for f in ficheros(os.path.join("estado", "directos", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            clave = self.n.clave(d.get("cuenta") or sin_ext(f))
            cuando = d.get("cuando") or {}
            docs[id_doc(clave)] = {
                "nombre": self.n.nombre(clave), "semana": d.get("semana"), "titulo": d.get("titulo"),
                "cuando": {"dia": cuando.get("dia"), "hora": cuando.get("hora"), "porQue": cuando.get("por_que")},
                "duracionMinutos": d.get("duracion_minutos"), "gancho": d.get("gancho"),
                "bloques": [{"minuto": b.get("minuto"), "tema": b.get("tema"), "queDecir": b.get("que_decir"),
                             "preguntaChat": b.get("pregunta_chat")} for b in d.get("bloques") or [] if isinstance(b, dict)],
                "encuesta": d.get("encuesta"), "reto": d.get("reto"), "saludo": d.get("saludo"), "seguir": d.get("seguir"),
                "preguntasPrevistas": d.get("preguntas_previstas") or [], "cierre": d.get("cierre"),
                "consejos": d.get("consejos") or [], "noHacer": d.get("no_hacer") or [],
                "actualizado": d.get("actualizado")}
        return docs

    def constructor(self):
        docs = {}
        for f in ficheros(os.path.join("estado", "constructor", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            alias = sin_ext(f)
            ficha = d.get("ficha") or {}
            guardadas = d.get("imagenes") or d.get("guardadas") or {}
            imagenes = {}
            for que in ("foto", "banner"):
                nombre = guardadas.get(que) if isinstance(guardadas.get(que), str) else f"{alias}-{que}.png"
                imagenes[que] = {"nombre": nombre, "url": f"/api/video/{nombre}"}
            docs[id_doc(alias)] = {"nombre": d.get("nombre"), "red": d.get("red"), "estado": d.get("estado"),
                                   "pasosDueno": d.get("pasos_dueno") or [],
                                   "ficha": {k: ficha.get(k) for k in ("tema", "descripcion", "etiquetas", "ideas", "lema")},
                                   "imagenes": imagenes, "actualizado": d.get("actualizado")}
            if d.get("pasos_claude"):
                self.para_claude.append({"de": "constructor", "id": alias, "texto": "; ".join(map(str, d["pasos_claude"])),
                                         "fecha": d.get("actualizado")})
        return docs

    def obras(self):
        o = leer(os.path.join("estado", "obras.json"), {}) or {}
        docs = {}
        for id_, x in (o.get("obras") or {}).items():
            if not isinstance(x, dict):
                continue
            d = {k: x.get(k) for k in ("canal", "titulo", "paso", "robot", "detalle", "estado", "empezado", "actualizado")}
            d["canal"] = self.n.clave(d["canal"])
            if x.get("en_sala"):
                d["enSala"] = True
            docs[id_doc(id_)] = d
        meta = {"actualizado": o.get("actualizado")}
        p = o.get("pausa")
        if isinstance(p, dict) and p.get("activa"):
            meta["pausa"] = {k: p[k] for k in ("motivo", "desde", "hasta") if p.get(k)}
        docs["_meta"] = meta
        return docs

    def taller(self):
        t = leer(os.path.join("estado", "mecanicos", "taller.json"), {}) or {}
        if not t:
            return {}
        for p in t.get("partes") or []:
            if isinstance(p, dict) and p.get("estado") == "para_claude":
                self.para_claude.append({"de": "taller", "id": hash8(f"{p.get('fecha')}{p.get('canal')}"),
                                         "texto": self.n.texto(str(p.get("para_claude") or p.get("causa") or "")),
                                         "fecha": p.get("fecha")})
        return {"resumen": {
            "ultimo": t.get("ultimo"),
            "arreglos": [{k: a.get(k) for k in ("fecha", "robot", "que", "detalle")} for a in ultimos(t.get("arreglos"), 20)],
            "cuarentena": {self.n.clave(k): {"hasta": (v or {}).get("hasta"), "motivo": (v or {}).get("motivo")}
                           for k, v in (t.get("cuarentena") or {}).items()},
            "dibujosCaidos": (t.get("dibujos_caidos") or {}).get("hasta"),
            "partes": [{"fecha": p.get("fecha"), "canal": self.n.clave(p.get("canal")), "causa": p.get("causa"),
                        "estado": p.get("estado"), "paraElDueno": p.get("para_el_dueno")}
                       for p in t.get("partes") or [] if isinstance(p, dict)],
            "actualizado": t.get("actualizado")}}

    def cine(self):
        s = leer(os.path.join("estado", "cine", "sesiones.json"), {}) or {}
        docs = {}
        for x in ultimos(s.get("sesiones"), TOPE["cine"]):
            if x.get("prueba"):
                continue
            id_ = id_doc(x.get("id") or f"{x.get('fecha')}-{x.get('canal')}")
            docs[id_] = {"canal": self.n.clave(x.get("canal")), "titulo": x.get("titulo"), "fecha": x.get("fecha"),
                         "version": x.get("version"), "personas": x.get("personas"), "paran": x.get("paran"),
                         "pasan3s": x.get("pasan_3s"), "mitad": x.get("mitad"), "final": x.get("final"),
                         "comparten": x.get("comparten"), "seVanEn": x.get("se_van_en"),
                         "motivosIrse": x.get("motivos_irse") or [], "motivosQuedarse": x.get("motivos_quedarse") or [],
                         "frase": x.get("frase")}
        return docs

    def elite(self):
        e = leer(os.path.join("estado", "elite", "elite.json"), {}) or {}
        if not e:
            return {}
        for o in e.get("obras") or []:
            if isinstance(o, dict) and o.get("estado") == "para_claude":
                self.para_claude.append({"de": "elite", "id": o.get("id") or hash8(o.get("que")),
                                         "texto": self.n.texto(str(o.get("que") or "")), "fecha": o.get("fecha")})
        return {"resumen": {
            "ultimo": e.get("ultimo"), "mirado": e.get("mirado"), "parte": e.get("parte"),
            "problemas": [{k: p.get(k) for k in ("id", "tipo", "canal")} for p in e.get("problemas") or [] if isinstance(p, dict)],
            "decisiones": [{k: d.get(k) for k in ("fecha", "tipo", "canal", "salida", "causa", "texto", "porque",
                                                    "como_se_sabra", "robot", "campo", "antes", "despues", "rechazada",
                                                    "deshacer", "cerebro")} | {
                               "tipo": d.get("tipo") or (d.get("problema") or {}).get("tipo"),
                               "canal": d.get("canal") or (d.get("problema") or {}).get("canal")}
                           for d in ultimos(e.get("decisiones"), 20)],
            "cambios": [{k: c.get(k) for k in ("fecha", "ambito", "clave", "campo", "antes", "despues", "causa", "base",
                                                 "estado", "resultado")} for c in ultimos(e.get("cambios"), 15)],
            "reformas": e.get("reformas") or {},
            "obras": [{k: o.get(k) for k in ("fecha", "canal", "que", "porque", "estado")} for o in e.get("obras") or []
                      if isinstance(o, dict)]}}

    def decisiones(self):
        e = leer(os.path.join("estado", "elite", "elite.json"), {}) or {}
        docs = {}
        for d in ultimos(e.get("decisiones"), TOPE["decisiones"]):
            id_ = id_doc(f"{d.get('id') or hash8(d.get('texto'))}-{str(d.get('fecha') or '')[:10]}")
            docs[id_] = {"fecha": d.get("fecha"), "robot": d.get("robot"), "texto": d.get("texto") or "",
                         "porque": d.get("porque"), "salida": d.get("salida"),
                         "canal": self.n.clave(d.get("canal") or (d.get("problema") or {}).get("canal")), "quien": "elite"}
        return docs

    def ia(self):
        c = leer(os.path.join("estado", "cadena.json"), {}) or {}
        if not c:
            return {}
        hoy = iso()[:10]
        en_espera = collections.Counter()
        for f in ficheros(os.path.join("estado", "espera", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            for v in d.get("videos") or []:
                if isinstance(v, dict) and (horas_desde(v.get("fecha") or v.get("entrada") or v.get("desde")) or 0) <= 36:
                    en_espera[self.n.nombre(d.get("clave") or sin_ext(f))] += 1
        for servicio, x in (c.get("llaves_malas") or {}).items():
            self.avisos_nuevos[id_doc(f"llave-{servicio}")] = {
                "tipo": "mision", "ciudad": "central", "fecha": (x or {}).get("desde"), "hecho": False,
                "titulo": f"La llave de {servicio} no vale",
                "texto": f"La fábrica no puede usar la IA de reserva «{servicio}»: su llave no vale. "
                         "Hay que poner una nueva en los secretos de GitHub (pídeselo a Claude)."}
        return {"cadena": {"encendidos": c.get("encendidos") or [], "uso": {hoy: (c.get("uso") or {}).get(hoy) or {}},
                           "agotados": c.get("agotados") or {}, "llaves_malas": c.get("llaves_malas") or {},
                           "enEspera": dict(en_espera), "actualizado": c.get("actualizado")}}

    def cerebro(self):
        d = leer(os.path.join("estado", "cerebro", "directo.json"), {}) or {}
        r = leer(os.path.join("estado", "cerebro", "recetas.json"), {}) or {}
        docs = {}
        if d:
            docs["directo"] = {"actualizado": d.get("actualizado"), "meta": d.get("meta"), "pasos": ultimos(d.get("pasos"), 60),
                               "cuentas": d.get("cuentas") or {}, "saber": d.get("saber"), "averias_hoy": d.get("averias_hoy"),
                               "nivel": d.get("nivel"), "progreso": ultimos(d.get("progreso"), 48), "todos": d.get("todos"),
                               "para_claude": ultimos(d.get("para_claude"), 20)}
            for p in d.get("para_claude") or []:
                if isinstance(p, dict) and p.get("estado", "para_claude") == "para_claude":
                    self.para_claude.append({"de": "cerebro", "id": hash8(f"{p.get('fecha')}{p.get('texto')}"),
                                             "texto": self.n.texto(str(p.get("texto") or "")), "fecha": p.get("fecha")})
        if r.get("cuentas"):
            docs["planes"] = {k: {c: v.get(c) for c in ("fecha", "diagnostico", "reglas", "no_hagas", "repite", "prueba",
                                                       "media_antes", "mejor_antes")}
                              for k, v in r["cuentas"].items() if isinstance(v, dict)}
        return docs

    def charla(self):
        """Lo que el dueño le ha escrito al Cerebro, con su respuesta cuando llega (estado/cerebro/chat.json)."""
        chat = [m for m in (leer(CHAT, {}) or {}).get("conversacion") or [] if isinstance(m, dict)]
        respuestas = {}
        for m in chat:
            if m.get("de") == "cerebro" and m.get("responde_a"):
                respuestas.setdefault(m["responde_a"], []).append(m)
        docs = {}
        for m in chat:                                  # lo que ya está en la conversación
            if m.get("de") in ("dueño", "dueno") and m.get("id") and not str(m["id"]).startswith("orden-"):
                docs[m["id"]] = {"de": "dueno", "texto": m.get("texto"), "fecha": m.get("fecha"), "estado": "leido"}
        for m in (leer(BUZON, {}) or {}).get("mensajes") or []:
            if isinstance(m, dict) and m.get("id") and not str(m["id"]).startswith("orden-"):
                docs.setdefault(m["id"], {"de": "dueno", "texto": m.get("texto"), "fecha": m.get("fecha"), "estado": "leido"})
        for id_, suyo in self.est.de("charla").items():
            docs[id_] = dict(docs.get(id_, {}), **(suyo.get("nuestro") or {}), **(suyo.get("dueno") or {}))
            docs[id_].setdefault("estado", "leido")
        for id_, d in docs.items():
            if id_ in respuestas:
                d.update(_respuesta(respuestas[id_]), estado="contestado")
        orden = sorted(docs, key=lambda i: str(docs[i].get("fecha") or ""))[-TOPE["charla"]:]
        return {id_doc(i): docs[i] for i in orden}

    def ordenes(self):
        chat = [m for m in (leer(CHAT, {}) or {}).get("conversacion") or [] if isinstance(m, dict)]
        respuestas = {}
        for m in chat:
            if m.get("de") == "cerebro" and str(m.get("responde_a") or "").startswith("orden-"):
                respuestas.setdefault(m["responde_a"][6:], []).append(m)
        docs = {}
        for f in ficheros(os.path.join("ordenes", "*.json")):
            o = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            id_ = sin_ext(f)
            suyo = self.est.de("ordenes").get(id_) or {}
            d = {k: o.get(k) for k in ("texto", "fecha", "estado", "quien", "respuesta") if o.get(k) is not None}
            d.update(suyo.get("dueno") or {})
            if d.get("estado") != "cancelada" and id_ in respuestas:
                r = _respuesta(respuestas[id_])
                claude = any("Claude" in str(a) for m in respuestas[id_] for a in m.get("acciones") or [])
                d.update(r, estado="en_marcha" if claude else "hecha")
                if o.get("estado") != d["estado"] or o.get("respuesta") != r["respuesta"]:
                    privado.escribir(os.path.relpath(f, privado.carpeta()), dict(o, estado=d["estado"],
                                                                                respuesta=r["respuesta"]))
                if claude:
                    self.para_claude.append({"de": "ordenes", "id": id_, "texto": str(o.get("texto") or ""),
                                             "fecha": o.get("fecha")})
            docs[id_doc(id_)] = d
        return dict(sorted(docs.items(), key=lambda kv: str(kv[1].get("fecha") or ""))[-TOPE["ordenes"]:])

    def cerebro_chat(self):
        return _base("cerebro_chat")         # ya no se usa (la conversación va en «charla»)

    def coliseo(self):
        r = leer(os.path.join("estado", "coliseo", "resumen.json"), {}) or {}
        docs = {}
        if r:
            docs["resumen"] = {"hoy": r.get("hoy"), "cartas": r.get("cartas") or {}, "porCuenta": r.get("por_cuenta") or {},
                               "ultimos": [{k: u.get(k) for k in ("id", "canal", "fecha", "video", "campeon", "carta",
                                                                    "titulo", "prueba")} for u in r.get("ultimos") or []
                                           if isinstance(u, dict)], "actualizado": r.get("actualizado")}
        for f in ficheros(os.path.join("estado", "coliseo", "torneos", "*.json"))[-TOPE["coliseo"]:]:
            t = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            docs[id_doc(sin_ext(f))] = _torneo(t, self.n)
        return docs

    def ojeador(self):
        docs = {}
        t = leer(os.path.join("estado", "influencers", "ojeador", "tendencias.json"), {}) or {}
        if t:
            docs["tendencias"] = {"ultimo": t.get("ultimo"), "fuentes": t.get("fuentes") or {},
                                  "canciones": (t.get("canciones") or [])[:10], "hashtags": (t.get("hashtags") or [])[:10],
                                  "top": [_top(x) for x in (t.get("top") or [])[:10]], "categorias": t.get("categorias") or {}}
        for f in ficheros(os.path.join("estado", "influencers", "ojeador", "*.json")):
            nombre = sin_ext(f)
            if nombre in ("tendencias", "_cifras"):
                continue
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            clave = self.n.clave(d.get("clave") or nombre)
            doc = {"nombre": d.get("nombre") or self.n.nombre(clave), "enPausa": bool(d.get("en_pausa")),
                   "ultimo": d.get("ultimo"), "temas": d.get("temas") or [], "categorias": d.get("categorias") or [],
                   "topAhora": [_top(x) for x in (d.get("top_ahora") or [])[:8]],
                   "videos": [_video_analizado(v, ("red", "url", "titulo", "visitas", "visitas_dia", "cancion"))
                              for v in [v for v in d.get("videos") or [] if isinstance(v, dict) and v.get("analisis")][-5:]]}
            if d.get("resumen"):
                doc["resumen"] = _resumen(d["resumen"], extra=("sonidos",))
            docs[id_doc(clave)] = doc
        return docs

    def radar(self):
        docs = {}
        for f in ficheros(os.path.join("estado", "influencers", "radar", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            clave = self.n.clave(d.get("clave") or sin_ext(f))
            doc = {"nombre": d.get("nombre") or self.n.nombre(clave), "red": d.get("red"), "enPausa": bool(d.get("en_pausa")),
                   "ultimo": d.get("ultimo"), "topAhora": [_top(x) for x in d.get("top_ahora") or []]}
            if d.get("resumen"):
                doc.update(_resumen(d["resumen"]))
                doc["videos"] = [_video_analizado(v, ("titulo", "canal", "url", "visitas", "visitas_dia", "dias"))
                                 for v in [v for v in d.get("videos") or [] if isinstance(v, dict) and v.get("analisis")][-5:]]
            docs[id_doc(clave)] = doc
        return docs

    def derechos(self):
        docs = {}
        base = os.path.join("estado", "derechos")
        s = leer(os.path.join(base, "salud.json"), {}) or {}
        if s:
            docs["salud"] = {"resumen": s.get("resumen") or {}, "robots": {
                k: {"salud": v.get("salud"), "carga": v.get("carga"), "trabajo7d": v.get("trabajo_7d"),
                    "fallos7d": v.get("fallos_7d"), "esperas7d": v.get("esperas_7d"), "casosAbiertos": v.get("casos_abiertos"),
                    "ultima": v.get("ultima"), "nota": v.get("nota")}
                for k, v in (s.get("robots") or {}).items() if isinstance(v, dict)}, "actualizado": s.get("actualizado")}
        m = leer(os.path.join(base, "mejoras.json"), {}) or {}
        if m:
            docs["mejoras"] = {"propuestas": [{k: p.get(k) for k in ("robot", "problema", "arreglo", "para", "veces")}
                                              for p in m.get("propuestas") or [] if isinstance(p, dict)],
                               "actualizado": m.get("actualizado")}
            for p in m.get("propuestas") or []:
                if isinstance(p, dict) and p.get("para") == "claude":
                    self.para_claude.append({"de": "derechos", "id": hash8(f"{p.get('robot')}{p.get('problema')}"),
                                             "texto": f"{p.get('nombre') or p.get('robot')}: {p.get('problema')} {p.get('arreglo') or ''}".strip(),
                                             "fecha": m.get("actualizado")})
        for fichero, doc, campo in (("peticiones", "peticiones", None), ("bienvenidas", "bienvenidas", None),
                                    ("psicologa", "notas", "notas"), ("jefe", "jefe", None)):
            d = leer(os.path.join(base, f"{fichero}.json"), {}) or {}
            if d:
                docs[doc] = {"notas": d.get("notas") or [], "actualizado": d.get("actualizado")} if campo else d
        return docs

    def entrenador(self):
        e = leer(os.path.join("estado", "influencers", "entrenador.json"), {}) or {}
        return {id_doc(self.n.clave(k)): {"vaBien": v.get("va_bien"), "mejorar": v.get("mejorar"), "porQue": v.get("por_que"),
                                          "ideas": v.get("ideas") or [], "pruebaSemana": v.get("prueba_semana"),
                                          "fecha": v.get("fecha"), "cerebro": v.get("cerebro"),
                                          "nombre": self.n.nombre(k)}
                for k, v in (e.get("cuentas") or {}).items() if isinstance(v, dict)}

    def mejoras(self):
        e = leer(os.path.join("estado", "influencers", "entrenador.json"), {}) or {}
        lista = []
        for k, v in (e.get("cuentas") or {}).items():
            if not isinstance(v, dict) or not v.get("mejorar"):
                continue
            ideas = v.get("ideas") or []
            idea = ideas[0] if ideas else None
            idea = (idea.get("titulo") or idea.get("idea")) if isinstance(idea, dict) else idea
            lista.append({"para": "guionista", "que": f"{self.n.nombre(k)}: {v['mejorar']}", "porque": v.get("por_que"),
                          "idea": idea})
        if not lista:
            return {}
        return {"hoy": {"titular": "Lo que el Entrenador pide mejorar en cada cuenta", "mejoras": lista,
                        "fecha": e.get("fecha") or e.get("actualizado")}}

    def memoria(self):
        docs = {}
        for f in ficheros(os.path.join("memoria", "*.json")):
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            les = [l for l in d.get("lecciones") or [] if isinstance(l, dict) and l.get("texto")]
            les = [l for l in les if l.get("del_dueno")] + [l for l in les if not l.get("del_dueno")]
            if not les:
                continue
            docs[id_doc(sin_ext(f))] = {"lecciones": [{"texto": l["texto"], "confianza": l.get("confianza"),
                                                       "del_dueno": bool(l.get("del_dueno"))} for l in les[:5]],
                                        "actualizado": d.get("actualizado")}
        return docs

    def cuaderno(self):
        """Una página por robot y día (los 2 últimos): qué hizo, qué fue bien y qué mal, sacado de su cuaderno."""
        mod = _robots_privado()
        frase = getattr(mod, "frase", None) or (lambda e: str(e.get("accion") or ""))
        dias = {iso()[:10], iso(ahora() - dt.timedelta(days=1))[:10]}
        docs = {}
        for f in ficheros(os.path.join("memoria", "*.json")):
            robot = sin_ext(f)
            d = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            por_dia = {}
            for e in d.get("diario") or []:
                if isinstance(e, dict) and str(e.get("fecha") or "")[:10] in dias:
                    por_dia.setdefault(e["fecha"][:10], []).append(e)
            for dia, es in por_dia.items():
                bien = list(dict.fromkeys(_frase(frase, e) for e in es if e.get("accion") not in ("error", "espera_ia")))
                mal = list(dict.fromkeys(_frase(frase, e) for e in es if e.get("accion") == "error"))
                fallos = len([e for e in es if e.get("accion") == "error"])
                docs[id_doc(f"{dia}-{robot}")] = {
                    "robot": robot, "dia": dia, "fecha": es[-1]["fecha"], "hice": f"Hoy he apuntado {len(es)} cosa(s) en mi cuaderno.",
                    "bien": bien[-4:], "mal": mal[-3:],
                    "animo": "atascado" if fallos and not bien else "preocupado" if fallos > 2 else "contento" if len(bien) > 5
                    else "bien"}
        orden = sorted(docs, key=lambda i: docs[i]["fecha"])[-TOPE["cuaderno"]:]
        return {i: docs[i] for i in orden}

    def calendario(self):
        items = []
        for clave in self.n.canales:
            rev = leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
            for p in rev.get("programados") or []:
                t = fecha(p.get("sale")) if isinstance(p, dict) else None
                if t and t > ahora():
                    items.append({"titulo": p.get("titulo"), "fecha": p.get("sale"), "canal": clave,
                                  "url": f"https://youtu.be/{p['id']}" if p.get("id") else None})
        items.sort(key=lambda i: i["fecha"])
        return {"proximos": {"items": items[:30], "actualizado": iso()[:13]}} if items else {}

    def historial(self):
        h = self.cifras.get("historial") or {}
        dias = sorted(k for k in h if re.fullmatch(r"\d{4}-\d{2}-\d{2}", k))[-TOPE["historial"]:]
        return {d: dict(h[d], fecha=d) for d in dias if isinstance(h[d], dict)}

    def sos(self):
        """La línea directa: una por robot que no puede trabajar (caso abierto de más de 24 h o la Psicóloga avisa al
        Jefe), una sola vez; se resuelve sola cuando el caso se cierra. Lo que decide el dueño se guarda."""
        s = leer(SOS, {}) or {}
        mensajes = {m["id"]: m for m in s.get("mensajes") or [] if isinstance(m, dict) and m.get("id")}
        antes = json.dumps(mensajes, sort_keys=True, ensure_ascii=False)
        abiertos = {}
        for c in (leer(os.path.join("estado", "casos.json"), {}) or {}).get("casos") or []:
            if isinstance(c, dict) and c.get("robot") and c.get("estado") in ("abierto", "necesita_al_dueno") \
                    and (horas_desde(c.get("fecha")) or 0) > 24:
                abiertos[f"sos-{id_doc(c.get('id') or c['robot'])}"] = (c["robot"], str(c.get("problema") or ""))
        for n in (leer(os.path.join("estado", "derechos", "psicologa.json"), {}) or {}).get("notas") or []:
            if isinstance(n, dict) and str(n.get("avisar_jefe")).lower() == "true" and n.get("robot"):
                abiertos[f"sos-racha-{id_doc(n['robot'])}"] = (n["robot"], f"{n.get('nombre') or n['robot']} lleva una mala "
                                                               f"racha: {n.get('paso') or 'necesita ayuda'}")
        for id_, (robot, texto) in abiertos.items():
            if id_ not in mensajes:
                mensajes[id_] = {"id": id_, "robot": robot, "fecha": iso(), "tipo": "no_puedo", "texto": texto,
                                 "estado": "abierta", "quien": "jefe_derechos"}
        for id_, m in mensajes.items():
            if m.get("estado") not in ("resuelta",) and str(id_).startswith("sos-") and id_ not in abiertos and m.get("robot"):
                m.update(estado="resuelta", respuesta="Ya puede trabajar otra vez: se ha arreglado solo.", resueltaEl=iso())
        for id_, suyo in self.est.de("sos").items():
            if id_ in mensajes:
                mensajes[id_].update(suyo.get("dueno") or {})
        vivos = {k: m for k, m in mensajes.items() if m.get("estado") != "resuelta"
                 or (horas_desde(m.get("resueltaEl") or m.get("fecha")) or 0) <= 72}
        if json.dumps(vivos, sort_keys=True, ensure_ascii=False) != antes:
            privado.escribir(SOS, {"mensajes": list(vivos.values()), "actualizado": iso()})
        return dict(sorted(((id_doc(k), quitar(v)) for k, v in vivos.items()),
                           key=lambda kv: str(kv[1].get("fecha") or ""))[-TOPE["sos"]:])

    def ayuda(self):
        docs = _base("ayuda")
        c = leer(os.path.join("estado", "claude.json"), {}) or {}
        tope = (self.cfg_fabrica.get("claude") or {}) if isinstance(self.cfg_fabrica.get("claude"), dict) else {}
        if c or tope:
            r = c.get("resumen") or {}
            estado = "sin_saldo" if c.get("sin_saldo") else "apagado" if tope.get("encendido") is False or \
                "llave" in str(c.get("aviso") or "").lower() else "encendido"
            docs["claude"] = dict(docs.get("claude", {}), estado=estado, gastado=r.get("mes_usd"),
                                  presupuesto=tope.get("mes_usd"), hoy=r.get("hoy_usd"), topeDia=tope.get("dia_max_usd"),
                                  topeHoy=r.get("tope_hoy_usd"), renueva=_renueva(tope.get("renueva_dia")),
                                  actualizado=c.get("actualizado"))
            aviso = str(c.get("aviso") or "")
            if aviso and ("llave" in aviso.lower() or (c.get("sin_saldo") and (r.get("dias_para_creditos_nuevos") or 0) > 3)):
                self.avisos_nuevos["claude-llave"] = {"tipo": "mision", "ciudad": "central", "fecha": c.get("actualizado"),
                                                      "hecho": False, "titulo": "Claude no puede escribir", "texto": aviso}
        return docs

    def avisos(self):
        docs = _base("avisos")
        viejos = self.antes.get("avisos") or {}
        for a in (leer(os.path.join("estado", "analisis", "virales.json"), {}) or {}).get("alertas") or []:
            if not isinstance(a, dict) or not a.get("url"):
                continue
            id_ = f"viral-{hash8(a['url'])}"
            docs[id_] = {"tipo": "viral", "ciudad": "influencers", "enlace": a["url"],
                         "fecha": (viejos.get(id_) or {}).get("fecha") or iso(),
                         "titulo": f"Está despegando: {self.n.nombre(a.get('canal'))}",
                         "texto": f"🔥 Está despegando: {a.get('titulo')} — {a.get('visitas')} visitas, "
                                  f"{round(a.get('veces_lo_normal') or 0)} veces lo normal."}
        for clave, p in ((leer(os.path.join("estado", "permisos.json"), {}) or {}).get("permisos") or {}).items():
            if p == "caducado":
                docs[f"permiso-{id_doc(clave)}"] = {
                    "tipo": "mision", "ciudad": "central", "fecha": (viejos.get(f"permiso-{id_doc(clave)}") or {}).get("fecha") or iso(),
                    "hecho": False, "titulo": f"Vuelve a dar permiso a {self.n.nombre(clave)}",
                    "texto": "El permiso de YouTube de este canal ha caducado y la fábrica no puede subir. Pídele a Claude "
                             "el código para volver a darlo (google.com/device → «Permitir»)."}
        for id_, a in self.avisos_nuevos.items():
            docs[id_] = dict(a, fecha=(viejos.get(id_) or {}).get("fecha") or a.get("fecha") or iso())
        if self.para_claude:
            docs["para-claude"] = {"tipo": "mision", "ciudad": "policia", "grupo": "Para Claude", "hecho": False,
                                   "fecha": (viejos.get("para-claude") or {}).get("fecha") or iso(),
                                   "titulo": f"Hay {len(self.para_claude)} cosa(s) que solo puede arreglar Claude",
                                   "texto": "Los robots no saben arreglarlo solos (es código o algo fuera de sus límites). "
                                            "Cuando puedas, abre el chat «fabrica 2.0» y dile: «mira lo que está para Claude».",
                                   "pasos": [str(p.get("texto") or "")[:200] for p in self.para_claude[:8]]}
        for id_, suyo in self.est.de("avisos").items():          # lo que el dueño ha marcado manda
            if id_ in docs:
                docs[id_].update(suyo.get("dueno") or {})
        orden = sorted(docs, key=lambda i: str(docs[i].get("fecha") or ""))[-TOPE["avisos"]:]
        return {i: docs[i] for i in orden}

    # --- todo junto ----------------------------------------------------------------------
    ORDEN = ["ciudades", "skills", "plugins", "fichas", "robots", "canales", "barrios", "parasubir", "analisis", "liga",
             "recetas", "casos", "clips", "videoteca", "propios", "directos", "constructor", "obras", "taller", "cine",
             "elite", "decisiones", "ia", "cerebro", "charla", "ordenes", "cerebro_chat", "coliseo", "ojeador", "radar",
             "derechos", "entrenador", "mejoras", "memoria", "cuaderno", "calendario", "historial", "sos", "ayuda",
             "diario", "avisos"]        # avisos y diario al final: recogen lo que dejan las demás

    def todo(self):
        cols = {}
        for col in self.ORDEN:
            try:
                cols[col] = getattr(self, col)()
            except Exception as e:      # un fichero roto no deja la app en blanco: se queda lo de la foto anterior
                self.errores.append(col)
                print(f"comisario: {col}: fallo {_cifra(e)}; se queda lo de antes", flush=True)
                cols[col] = self.antes.get(col) or {}
        for col in COLECCIONES:
            if col != "juicios":
                cols.setdefault(col, {})
        # los textos en sencillo (alias → nombre de la cuenta), sin tocar los ids de los documentos
        return {col: {id_: self.n.sencillo(doc) for id_, doc in docs.items()} for col, docs in cols.items()}

    def juicios(self, dias=30):
        desde = iso(ahora() - dt.timedelta(days=dias))
        docs = {}
        for f in ficheros(os.path.join("estado", "juzgado", "juicios", "*.json")):
            j = leer(os.path.relpath(f, privado.carpeta()), {}) or {}
            if not isinstance(j, dict) or str(j.get("fecha") or "") < desde:
                continue
            doc = quitar(j, "actualizado", "clave")
            doc["canal"] = self.n.clave(doc.get("canal"))
            docs[id_doc(sin_ext(f))] = self.n.sencillo(doc)
        orden = sorted(docs, key=lambda i: str(docs[i].get("fecha") or ""))
        tam = lambda ids: len(json.dumps({i: docs[i] for i in ids}, ensure_ascii=False, separators=(",", ":")).encode())  # noqa: E731
        if tam(orden) > JUICIOS_MAX:                # el portero lo devuelve entero: que no pase de ~2 MB
            orden = orden[-300:]
            while len(orden) > 50 and tam(orden) > JUICIOS_MAX:
                orden = orden[50:]
        return {i: docs[i] for i in orden}


# ------------------------------------------------------------------ ayudantes de la foto
def _frase(frase, e):
    try:
        return str(frase(e) or e.get("accion") or "")
    except Exception:
        return str(e.get("accion") or "")


def _corto(texto, n):
    t = re.sub(r"\s+", " ", str(texto or "")).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


def _frase_turno(t, nombre, es_barrio):
    titulo = _corto(t.get("titulo"), 90)
    destino, nota = t.get("destino_resultado"), t.get("nota")
    if t.get("resultado") == "error":
        return f"Falló el turno de {nombre}: {_corto(t.get('error'), 100)}", "mecanico_rondas"
    if destino == "subido":
        cuando = f" para el {str(t.get('sale'))[:10]} a las {str(t.get('sale'))[11:16]}" if t.get("sale") else ""
        return f"La fábrica hizo un vídeo para {nombre} («{titulo}») y lo programó{cuando}.", "subidor"
    if destino == "para_subir":
        return f"{nombre} tiene un vídeo nuevo en Para subir («{titulo}»" + (f", nota {nota}" if nota else "") + ").", "publicador"
    if destino == "en_cola":
        return f"El vídeo «{titulo}» de {nombre} está en la cola para subirlo.", "subidor"
    if destino == "suspendido":
        return f"El Juzgado suspendió «{titulo}» de {nombre}" + (f" ({nota}/100)" if nota else "") + ".", "juez_guardia"
    if destino == "espera_juez":
        return f"«{titulo}» de {nombre} espera a un juez de primera en la Sala de espera.", "juez_suplente"
    return None, None


def _respuesta(mensajes):
    textos, acciones, cuando = [], [], None
    for m in mensajes:
        if m.get("texto"):
            textos.append(str(m["texto"]))
        acciones += [str(a) for a in m.get("acciones") or [] if a]
        cuando = m.get("fecha") or cuando
    texto = "\n\n".join(textos)
    if acciones:
        texto += "\nHecho: " + "; ".join(acciones)
    return {"respuesta": texto, "respondido": cuando}


def _resultado_propio(r, n):
    d = {"estado": r.get("estado")}
    for a, b in (("nota", "nota"), ("minimo", "minimo"), ("juzgado", "juzgado"), ("problema", "problema"),
                 ("consejo", "consejo"), ("arreglos", "arreglos"), ("lo_bueno", "loBueno"), ("defensa", "defensa"),
                 ("fiscalia", "fiscalia"), ("fallos_graves", "fallosGraves"), ("salida_antes", "salidaAntes")):
        if r.get(a) is not None:
            d[b] = r[a]
    if r.get("votos"):
        d["votos"] = [{k: v.get(k) for k in ("juez", "voto", "nota", "razon")} for v in r["votos"] if isinstance(v, dict)]
    j = r.get("jurado")
    if isinstance(j, dict):
        d["jurado"] = {k: j.get(k) for k in ("inocente", "culpable", "veredicto", "nota_media") if k in j}
        for a, b in (("en_contra", "enContra"), ("a_favor", "aFavor"), ("enContra", "enContra"), ("aFavor", "aFavor")):
            if j.get(a) is not None:
                d["jurado"][b] = j[a]
        if j.get("votos"):
            d["jurado"]["votos"] = [{k: v.get(k) for k in ("jurado", "voto", "porque", "piel")} for v in j["votos"]
                                    if isinstance(v, dict)]
    v = r.get("visto")
    if isinstance(v, dict):
        d["visto"] = {"narracion": v.get("narracion"), "textoPantalla": v.get("texto_pantalla") or v.get("textoPantalla"),
                      "deQueVa": v.get("de_que_va") or v.get("deQueVa")}
    c = r.get("coliseo")
    if isinstance(c, dict) and r.get("estado") == "aprobado":
        d["coliseo"] = {k: c.get(k) for k in ("torneo", "campeon", "carta", "titulo", "texto", "hashtags")}
    return d


def _torneo(t, n):
    return {"canal": n.clave(t.get("canal")), "fecha": t.get("fecha"), "prueba": bool(t.get("prueba")), "video": t.get("video"),
            "notaJuzgado": t.get("nota_juzgado"), "antes": t.get("antes"),
            "gladiadores": [{"nombre": g.get("nombre"), "carta": g.get("carta"), "salida": g.get("salida"),
                             "fuera": g.get("fuera")} for g in t.get("gladiadores") or [] if isinstance(g, dict)],
            "combates": [{"ronda": c.get("ronda"), "a": c.get("a"), "b": c.get("b"), "criticaAB": c.get("critica_a_b"),
                          "criticaBA": c.get("critica_b_a"), "ganador": c.get("ganador"), "razon": c.get("razon")}
                         for c in t.get("combates") or [] if isinstance(c, dict)],
            "campeon": {k: (t.get("campeon") or {}).get(k) for k in ("nombre", "carta", "salida")}}


def _top(x):
    if not isinstance(x, dict):
        return x
    d = {k: x.get(k) for k in ("red", "url", "creador", "canal", "titulo", "visitas", "likes", "dias", "segundos", "cancion")
         if x.get(k) is not None}
    if x.get("visitas_dia") is not None:
        d["visitasDia"] = x["visitas_dia"]
    return d


def _video_analizado(v, campos):
    a = v.get("analisis") or {}
    d = {("visitasDia" if k == "visitas_dia" else k): v.get(k) for k in campos}
    d.update(gancho=(a.get("gancho") or {}).get("texto") if isinstance(a.get("gancho"), dict) else a.get("gancho"),
             porQue=a.get("por_que_funciona"),
             idea=(a.get("idea_para_nosotros") or {}).get("titulo") if isinstance(a.get("idea_para_nosotros"), dict) else None)
    return d


def _resumen(r, extra=()):
    d = {"titular": r.get("titular"), "loQueFunciona": r.get("lo_que_funciona"), "ganchos": r.get("ganchos"),
         "temas": r.get("temas"), "formato": r.get("formato"), "duracion": r.get("duracion"), "evitar": r.get("evitar"),
         "ideas": [{k: i.get(k) for k in ("titulo", "gancho", "resumen")} if isinstance(i, dict) else i
                   for i in r.get("ideas") or []]}
    for k in extra:
        d[k] = r.get(k)
    return d


def _minimos_videoteca():
    try:
        texto = open(os.path.join(RAIZ, "bots", "central", "videoteca.py"), encoding="utf-8").read()
        m = {k: int(re.search(rf"^{k}\s*=\s*(\d+)", texto, re.M).group(1)) for k in ("MIN_TOMAS", "MIN_FUENTES", "MIN_PAREJAS")}
        return {"gta6": m["MIN_TOMAS"], "fuentes": m["MIN_FUENTES"], "parejas": m["MIN_PAREJAS"]}
    except (OSError, AttributeError):
        return {"gta6": 6, "fuentes": 2, "parejas": 2}


def _renueva(dia):
    try:
        dia = int(dia)
    except (TypeError, ValueError):
        return None
    hoy = ahora().date()
    for meses in (0, 1, 2):
        y, m = hoy.year + (hoy.month - 1 + meses) // 12, (hoy.month - 1 + meses) % 12 + 1
        try:
            d = dt.date(y, m, dia)
        except ValueError:
            continue
        if d > hoy:
            return d.isoformat()
    return None


# ------------------------------------------------------------------ guardar y apuntar
def _sin_actualizado(x):
    if isinstance(x, dict):
        return {k: _sin_actualizado(v) for k, v in x.items() if k not in ("actualizado",)}
    if isinstance(x, list):
        return [_sin_actualizado(v) for v in x]
    return x


def escribir_si_cambia(rel, datos, clave):
    antes = leer(rel, {}) or {}
    if json.dumps(_sin_actualizado(antes.get(clave)), sort_keys=True, ensure_ascii=False) == \
            json.dumps(_sin_actualizado(datos[clave]), sort_keys=True, ensure_ascii=False):
        return False
    r = ruta(rel)
    os.makedirs(os.path.dirname(r), exist_ok=True)
    with open(r + ".tmp", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(r + ".tmp", r)
    return True


def guardar_para_claude(lista):
    d = leer(PARA_CLAUDE, {}) or {}
    vistos = {f"{p.get('de')}:{p.get('id')}": p for p in d.get("pendientes") or [] if isinstance(p, dict)}
    ahora_ids = set()
    for p in lista:
        k = f"{p.get('de')}:{p.get('id')}"
        ahora_ids.add(k)
        vistos.setdefault(k, dict(p, visto=iso()))
    pendientes = [p for k, p in vistos.items() if k in ahora_ids]
    nuevo = {"pendientes": sorted(pendientes, key=lambda p: str(p.get("fecha") or "")),
             "nota": "Lo que los robots no pueden hacer sin Claude (código, Policía, cosas fuera de sus límites). "
                     "Lo apunta el Comisario automático; cuando un chat de Claude lo arregle, desaparece solo."}
    if json.dumps(nuevo["pendientes"], sort_keys=True, ensure_ascii=False) != \
            json.dumps(d.get("pendientes"), sort_keys=True, ensure_ascii=False):
        privado.escribir(PARA_CLAUDE, dict(nuevo, actualizado=iso()))


def apuntar(accion, detalle, cada_horas=0):
    c = privado.cuaderno(ROBOT)
    if cada_horas:
        ult = [e for e in c.datos.get("diario") or [] if e.get("accion") == accion]
        if ult and (horas_desde(ult[-1].get("fecha")) or 99) < cada_horas:
            return
    c.apuntar(accion, detalle)
    c.guardar()


def lanzar_turnos(lanzar):
    """Le dice a app.yml qué turnos arrancar (con gh workflow run): el Cerebro tras un mensaje del dueño y «Juzga mi
    vídeo» tras completar su petición."""
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"lanzar={' '.join(sorted(lanzar))}\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-entradas", action="store_true", help="solo la foto")
    a = p.parse_args(argv)
    nombres = Nombres()
    est = EstadoApp()
    lanzar = set()
    cuenta = collections.Counter()
    if not a.sin_entradas:
        for (para, res), n in sorted(recoger_buzon(est, lanzar).items()):
            print(f"comisario: vídeos de la app ({para}): {n} {res}", flush=True)
        cuenta = aplicar_entradas(est, nombres, lanzar)
        est.guardar()
        for (col, res), n in sorted(cuenta.items()):
            print(f"comisario: entradas de {col}: {n} {res}", flush=True)
    antes = leer(TODO, {}) or {}
    foto = Foto(nombres, est, antes)
    colecciones = foto.todo()
    juicios = foto.juicios()
    est.guardar()
    guardar_para_claude(foto.para_claude)
    todo = {"actualizado": iso(), "colecciones": colecciones}
    cambio = escribir_si_cambia(TODO, todo, "colecciones")
    cambio_j = escribir_si_cambia(JUICIOS, {"actualizado": iso(), "juicios": juicios}, "juicios")
    kb = len(json.dumps(todo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) // 1024
    print(f"comisario: foto con {sum(len(v) for v in colecciones.values())} documentos en {len(colecciones)} colecciones "
          f"({kb} KB){', cambiada' if cambio else ', igual que antes'}; {len(juicios)} juicios"
          f"{' (cambiados)' if cambio_j else ''}; {len(foto.para_claude)} cosas para Claude", flush=True)
    for col in sorted(colecciones):
        print(f"  {col}: {len(colecciones[col])}", flush=True)
    if foto.errores:
        print(f"comisario: colecciones con fallo: {', '.join(foto.errores)}", flush=True)
    hechas = sum(n for (c, r), n in cuenta.items() if r == "hecha")
    if any(r in ("hecha", "rechazada") for (c, r) in cuenta):      # las que solo esperan no se apuntan cada vez
        apuntar("entradas", {"hechas": hechas, "rechazadas": sum(n for (c, r), n in cuenta.items() if r == "rechazada"),
                             "pendientes": sum(n for (c, r), n in cuenta.items() if r in ("pendiente", "fallo"))})
    if foto.errores:
        apuntar("error", {"colecciones": foto.errores})
    else:
        apuntar("foto", {"documentos": sum(len(v) for v in colecciones.values()), "kb": kb, "juicios": len(juicios)},
                cada_horas=1)
        try:
            c = privado.cuaderno("director_general")
            ult = [e for e in c.datos.get("diario") or [] if e.get("accion") == "parte"]
            if not ult or (horas_desde(ult[-1].get("fecha")) or 99) >= 3:
                c.apuntar("parte", {"copiado": sum(len(v) for v in colecciones.values()),
                                    "casos_abiertos": sum(1 for x in colecciones.get("casos", {}).values()
                                                          if x.get("estado") != "arreglado")})
                c.guardar()
        except Exception:
            pass
    lanzar_turnos(lanzar)
    if lanzar:
        print(f"comisario: arrancar ahora: {', '.join(sorted(lanzar))}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
