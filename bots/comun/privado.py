"""Acceso a lo privado (repositorio ciudades-memoria, que los turnos sacan en la carpeta de la variable PRIVADO):
configuración de canales, estado para la app y memoria de los robots."""
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import memoria  # noqa: E402  (herramientas/memoria.py)


def carpeta():
    return os.environ.get("PRIVADO") or os.path.join(RAIZ, "..", "ciudades-memoria")


def ahora():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def leer(ruta_relativa, defecto=None):
    """Lee un JSON del repositorio privado; si no está o está roto, devuelve el valor por defecto."""
    try:
        with open(os.path.join(carpeta(), ruta_relativa), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return defecto


def escribir(ruta_relativa, datos):
    ruta = os.path.join(carpeta(), ruta_relativa)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)


def config():
    return leer(os.path.join("config", "canales.json"), {"canales": {}, "barrios": {}})


def ajustes():
    """Ajustes de la fábrica (config/fabrica.json), con valores prudentes si falta alguno."""
    base = {"subidas_por_dia": 8, "videos_por_ronda": 3, "dias_maximos": 30, "cola_maxima": 4,
            "pendientes_por_barrio": 3, "minutos_por_ronda": 150, "prioridad": []}
    base.update(leer(os.path.join("config", "fabrica.json"), {}) or {})
    return base


def canal(clave):
    """Un canal de YouTube o un barrio (cuenta de TikTok/Instagram), con su clave y su destino."""
    cfg = config()
    if clave in cfg.get("canales", {}):
        datos = dict(cfg["canales"][clave], destino="youtube")
    elif clave in cfg.get("barrios", {}):
        datos = dict(cfg["barrios"][clave], destino="parasubir")
        datos.setdefault("nombre", clave)
    else:
        raise SystemExit(f"No conozco «{clave}». Canales: {', '.join(cfg.get('canales', {}))}; "
                         f"barrios: {', '.join(cfg.get('barrios', {}))}")
    datos["clave"] = clave
    return datos


def cuaderno(robot):
    os.environ.setdefault("MEMORIA_DIR", os.path.join(carpeta(), "memoria"))
    return memoria.Cuaderno(robot)


def guardar_estado(ruta_relativa, datos):
    """Deja el estado de un robot o de un canal en estado/ del repositorio privado (lo copia a la app una ronda de Claude)."""
    ruta = os.path.join(carpeta(), "estado", ruta_relativa)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    datos = dict(datos, actualizado=ahora())
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def titulos_recientes(clave, cuantos=40):
    """Títulos ya hechos en ese canal (los nuestros y los que dejó programados la fábrica antigua), para no repetir."""
    propios = leer(os.path.join("estado", "titulos", f"{clave}.json"), []) or []
    if cuantos >= 10_000:
        return propios
    revision = leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
    antiguos = [p["titulo"] for p in revision.get("programados", [])]
    if revision.get("ultimo_publicado"):
        antiguos.append(revision["ultimo_publicado"]["titulo"])
    vistos, lista = set(), []
    for t in antiguos + propios:
        if t not in vistos:
            vistos.add(t)
            lista.append(t)
    return lista[-cuantos:]


def apuntar_titulo(clave, titulo):
    ruta = os.path.join(carpeta(), "estado", "titulos", f"{clave}.json")
    lista = titulos_recientes(clave, 10_000)
    lista.append(titulo)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(lista[-500:], f, ensure_ascii=False, indent=1)


def git_guardar(mensaje, intentos=5):
    """Guarda en el repositorio privado lo que han cambiado los robots (commit + push, con reintentos)."""
    import subprocess
    import time
    c = carpeta()

    def git(*args):
        return subprocess.run(["git", "-C", c, *args], capture_output=True, text=True)

    git("add", "-A", "--", ".", ":(exclude)*.mp4", ":(exclude)*.mp3", ":(exclude)*.webp")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return True
    git("commit", "-q", "-m", mensaje)
    for i in range(intentos):
        if git("pull", "-q", "--rebase").returncode == 0 and git("push", "-q").returncode == 0:
            return True
        git("rebase", "--abort")
        time.sleep(5 * (i + 1))
    print("No he podido guardar en el repositorio privado: lo intentará la siguiente ronda.", flush=True)
    return False


# --- Lo que sale en los registros de GitHub es PÚBLICO: los barrios (cuentas de TikTok/Instagram) salen con un alias
# («barrio-2») y los nombres de los canales, con su clave. ---
def _barrios():
    return sorted(config().get("barrios", {}))


def alias(clave):
    b = _barrios()
    return f"barrio-{b.index(clave) + 1}" if clave in b else clave


def resolver(nombre):
    """Del alias a la clave de verdad («barrio-2» → la cuenta), para las peticiones que llegan por el repo público."""
    import re
    m = re.fullmatch(r"barrio-(\d+)", nombre.strip())
    b = _barrios()
    if m and 0 < int(m.group(1)) <= len(b):
        return b[int(m.group(1)) - 1]
    return nombre.strip()


def limpiar(texto):
    import re
    cfg = config()
    for clave, b in cfg.get("barrios", {}).items():
        palabras = {clave, b.get("cuenta", ""), b.get("nombre", ""), re.sub(r"[^a-z0-9]+", "-", clave.lower()).strip("-")}
        for p in sorted((x for x in palabras if x), key=len, reverse=True):
            texto = re.sub(re.escape(p), alias(clave), texto, flags=re.IGNORECASE)
    for clave, c in cfg.get("canales", {}).items():
        if c.get("nombre"):
            texto = texto.replace(c["nombre"], clave)
    return texto
