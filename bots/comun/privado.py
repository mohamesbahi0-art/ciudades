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


def _por_id(*listas, clave="id"):
    vistos, salida = {}, []
    for lista in listas:
        for x in lista or []:
            k = x.get(clave) if isinstance(x, dict) else json.dumps(x, sort_keys=True, ensure_ascii=False)
            if k is None:
                k = json.dumps(x, sort_keys=True, ensure_ascii=False)
            if k in vistos:
                salida[vistos[k]] = x          # gana la versión más nueva (la nuestra va después)
            else:
                vistos[k] = len(salida)
                salida.append(x)
    return salida


def fusionar(ruta, suyo, nuestro):
    """Junta dos versiones del mismo JSON cuando dos robots lo han tocado a la vez, sin perder lo de ninguno."""
    if suyo is None:
        return nuestro
    if nuestro is None:
        return suyo
    if ruta.startswith("memoria/") and isinstance(suyo, dict) and isinstance(nuestro, dict):
        junto = dict(suyo, **nuestro)
        for k in ("diario", "lecciones", "experimentos"):
            junto[k] = _por_id(suyo.get(k, []), nuestro.get(k, []))
        junto["diario"] = sorted(junto["diario"], key=lambda e: e.get("fecha", ""))
        return junto
    if ruta.startswith("parasubir/") and isinstance(suyo, dict):
        return suyo if suyo.get("estado") in ("subido", "descartado") else nuestro   # lo que marca el dueño manda
    if isinstance(suyo, list) and isinstance(nuestro, list):
        if ruta.startswith("registro/"):
            return _por_id(suyo, nuestro, clave="id")
        if ruta.startswith("estado/historial/"):
            return sorted(_por_id(suyo, nuestro, clave="fecha"), key=lambda x: x.get("fecha", ""))
        return _por_id(suyo, nuestro)
    if isinstance(suyo, dict) and isinstance(nuestro, dict) and ruta.startswith("estado/central/"):
        junto = dict(suyo, **nuestro)
        junto["turnos"] = sorted(_por_id(suyo.get("turnos", []), nuestro.get("turnos", []), clave="empezado"),
                                 key=lambda t: t.get("empezado", ""))[-20:]
        return junto
    return nuestro


def git_guardar(mensaje, intentos=5):
    """Guarda en el repositorio privado lo que han cambiado los robots (commit + push, con reintentos). Si otro turno
    ha tocado los mismos ficheros a la vez, junta las dos versiones (fusionar) en vez de perder nada."""
    import subprocess
    import time
    c = carpeta()

    def git(*args):
        return subprocess.run(["git", "-C", c, *args], capture_output=True, text=True)

    git("add", "-A", "--", ".", ":(exclude)*.mp4", ":(exclude)*.mp3", ":(exclude)*.webp")
    if git("diff", "--cached", "--quiet").returncode != 0:
        git("commit", "-q", "-m", mensaje)
    for i in range(intentos):
        if git("rev-list", "--count", "@{u}..HEAD").stdout.strip() in ("0", ""):
            if git("fetch", "-q").returncode == 0 and git("rev-list", "--count", "@{u}..HEAD").stdout.strip() == "0":
                return True
        if git("pull", "-q", "--rebase").returncode == 0 and git("push", "-q").returncode == 0:
            return True
        git("rebase", "--abort")
        if git("fetch", "-q").returncode != 0:
            time.sleep(5 * (i + 1))
            continue
        cambiados = [f for f in git("diff", "--name-only", "@{u}...HEAD").stdout.split() if f]
        nuestros = {}
        for f in cambiados:
            r = git("show", f"HEAD:{f}")
            nuestros[f] = r.stdout if r.returncode == 0 else None
        git("reset", "-q", "--hard", "@{u}")
        for f, texto in nuestros.items():
            ruta = os.path.join(c, f)
            if texto is None:                    # lo habíamos borrado nosotros (por ejemplo, un vídeo de la cola ya subido)
                if os.path.exists(ruta):
                    os.remove(ruta)
                continue
            if f.endswith(".json"):
                try:
                    suyo = json.load(open(ruta, encoding="utf-8")) if os.path.exists(ruta) else None
                    texto = json.dumps(fusionar(f, suyo, json.loads(texto)), ensure_ascii=False, indent=1)
                except ValueError:
                    pass
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(texto)
        git("add", "-A", "--", ".", ":(exclude)*.mp4", ":(exclude)*.mp3", ":(exclude)*.webp")
        git("commit", "-q", "-m", f"{mensaje} (juntado con otro turno)")
        if git("push", "-q").returncode == 0:
            return True
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
