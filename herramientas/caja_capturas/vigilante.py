"""El vigilante del programa que ha escrito la IA (dentro de la caja, en el Python limpio).

Antes de que el programa haga nada, se mete en requests, en urllib3 (por debajo de requests: así cuenta también cada
intento) y en httpx (que salen por el filtro de la caja) y solo deja: pedir a los hosts del mismo dominio (nunca uno de
entrar, como login. o accounts.), lo que su robots.txt permite, 30 peticiones y 5 MB como mucho y una pausa de al menos
1 s (o el Crawl-delay) entre peticiones, sin reintentos propios y con su nombre de robot honrado (nada de disfrazarse
de navegador). Si la web le cierra la puerta (401, 403, 407, 429, Cloudflare o DataDome), para EN ESA PETICIÓN y ya no
deja hacer ninguna más. Cierra urllib.request y no deja lanzar programas ni cargar librerías de C. Las reglas son las de
`capturas.py elegir` (vigilante.json); sin ellas, las mismas cifras y el robots.txt que lea él. Es una capa más: la
barrera de verdad es la caja y su filtro.
Al acabar deja en un fichero cuántas peticiones hizo (sin ninguna, los datos serían inventados) y, si paró, por qué.
"""
import atexit
import json
import sys
import threading
import time
import urllib.parse
import urllib.robotparser

PROHIBIDO = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
             "pty.spawn", "os.kill", "os.killpg", "ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function")

NAVEGADOR = "investigador-web/1.0 (robot educado: respeta robots.txt)"   # el mismo nombre que usa capturas.py
BLOQUEOS = (401, 403, 407, 429)
ESQUEMAS = ("https",)                        # (las pruebas lo abren a http para hablar con un servidor de la máquina)

_r = {"dominio": "", "hosts": set(), "prohibidos": set(), "pausa": 1.0, "max_peticiones": 30, "max_bytes": 5_000_000}
_cuenta = {"peticiones": 0, "bytes": 0, "parado": None, "bloqueo": None}
_robots = {}
_ultima = [0.0]
_envio = [None]                              # el envío de requests de verdad (para leer robots.txt)
_dentro = threading.local()


class Parado(ConnectionError):
    """El vigilante ha cortado al programa (para las librerías es un error de red)."""


def _parar(motivo):
    _cuenta["parado"] = motivo
    raise Parado(f"vigilante: no permitido ({motivo})")


def cargar(ruta, base):
    try:
        with open(ruta, encoding="utf-8") as f:
            reglas = json.load(f)
    except (OSError, ValueError):
        reglas = {}
    _r["dominio"] = str(reglas.get("dominio") or base).lower().strip(".")
    _r["hosts"] = {str(h).lower().strip(".") for h in reglas.get("hosts") or [] if h}
    _r["prohibidos"] = {str(x).lower() for x in reglas.get("prohibidos") or []}
    _r["pausa"] = max(1.0, float(reglas.get("pausa") or 1.0))
    _r["max_peticiones"] = min(30, int(reglas.get("max_peticiones") or 30))
    _r["max_bytes"] = min(5_000_000, int(reglas.get("max_bytes") or 5_000_000))
    for host, texto in (reglas.get("robots") or {}).items():
        _robots[str(host).lower()] = _parsear(texto)


def _parsear(texto):
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(str(texto or "").splitlines())
    return rp


def host_ok(host):
    host = str(host or "").lower().rstrip(".")
    base = _r["dominio"]
    if host in _r["hosts"]:
        return True
    return bool(base) and (host == base or host.endswith("." + base)) and \
        not (set(host.split(".")[:-1]) & _r["prohibidos"])


def _mirar_respuesta(estado, cabeceras):
    """Si la web le cierra la puerta (401, 403, 407, 429, Cloudflare o DataDome) se apunta y se para ya: nada de
    insistir ni de buscar otro camino."""
    nombres = {str(k).lower() for k in (cabeceras or {}).keys()}
    if "cf-mitigated" in nombres:
        motivo = "cloudflare"
    elif any(n.startswith("x-datadome") for n in nombres):
        motivo = "datadome"
    elif estado in BLOQUEOS:
        motivo = f"bloqueo_{estado}"
    else:
        return
    _cuenta["bloqueo"] = _cuenta["bloqueo"] or motivo
    _parar(motivo)


def _robots_de(host):
    """El robots.txt de un host del dominio que no venía en las reglas (por el filtro, como todo). Si no contesta bien,
    ese host no se toca; si no tiene (404), se puede; si dice 401, 403 o 429, es que no quiere robots: bloqueo."""
    if host not in _robots:
        import requests
        _dentro.robots = True
        try:
            pedido = requests.Request("GET", f"https://{host}/robots.txt", headers={"User-Agent": NAVEGADOR}).prepare()
            r = _envio[0](requests.Session(), pedido, timeout=15, allow_redirects=False)
            _cuenta["peticiones"] += 1
            if r.status_code in BLOQUEOS:
                _cuenta["bloqueo"] = _cuenta["bloqueo"] or f"bloqueo_{r.status_code}"
            _robots[host] = _parsear(r.text[:512_000]) if r.status_code == 200 else \
                _parsear("") if r.status_code == 404 else None
        except Exception:
            _robots[host] = None
        finally:
            _dentro.robots = False
    return _robots[host]


def _antes(url):
    if _cuenta["bloqueo"]:                       # la web ya dijo que no: ni una petición más
        _parar(_cuenta["bloqueo"])
    partes = urllib.parse.urlsplit(str(url))
    host = (partes.hostname or "").lower().rstrip(".")
    if partes.scheme not in ESQUEMAS or not host_ok(host):
        _parar("otro_dominio")
    if partes.path != "/robots.txt":
        rp = _robots_de(host)
        if rp is None or not rp.can_fetch("*", str(url)):
            _parar("robots")
        espera = max(_r["pausa"], float(rp.crawl_delay("*") or 0))
    else:
        espera = _r["pausa"]
    if _cuenta["peticiones"] >= _r["max_peticiones"]:
        _parar("demasiadas_peticiones")
    falta = _ultima[0] + espera - time.monotonic()
    if falta > 0:
        time.sleep(min(falta, 30))
    _ultima[0] = time.monotonic()
    _cuenta["peticiones"] += 1


def _despues(cuantos):
    _cuenta["bytes"] += cuantos
    if _cuenta["bytes"] > _r["max_bytes"]:
        _parar("demasiados_datos")


def _honrado(cabeceras):
    """Las cabeceras con el nombre de robot de verdad (fuera el User-Agent que traiga, sea el que sea)."""
    limpias = {k: v for k, v in dict(cabeceras or {}).items() if str(k).lower() != "user-agent"}
    return {**limpias, "User-Agent": NAVEGADOR}


def _con_requests():
    import requests
    from requests.structures import CaseInsensitiveDict
    original = requests.Session.send

    def send(self, request, **kwargs):
        if getattr(_dentro, "robots", False):
            return original(self, request, **kwargs)
        request.headers = CaseInsensitiveDict(_honrado(request.headers))
        _antes(request.url)
        _dentro.contado = True                   # urllib3, por debajo, no la vuelve a contar
        try:
            respuesta = original(self, request, **kwargs)
        finally:
            _dentro.contado = False
        _mirar_respuesta(respuesta.status_code, respuesta.headers)
        _despues(len(respuesta.content or b""))
        return respuesta
    requests.Session.send = send
    _envio[0] = original


# Los argumentos de urlopen de urllib3, en su orden (para quitarle los reintentos aunque vengan sin nombre)
_URLOPEN = ("body", "headers", "retries", "redirect", "assert_same_host", "timeout", "pool_timeout", "release_conn",
            "chunked", "body_pos")


def _con_urllib3():
    """Por debajo de requests, cada intento de urllib3 pasa por aquí: sin reintentos propios (así una petición es una
    y cuenta, con su pausa, y el primer 403 o 429 llega hasta el vigilante) y con el nombre honrado. Lo que no venga
    de requests también se cuenta y se mira aquí."""
    try:
        from urllib3 import connectionpool
    except ImportError:
        return
    original = connectionpool.HTTPConnectionPool.urlopen

    def urlopen(self, method, url, *args, **kwargs):
        kwargs.update(zip(_URLOPEN, args))
        if getattr(_dentro, "robots", False):
            return original(self, method, url, **kwargs)
        kwargs["retries"] = False
        kwargs["headers"] = _honrado(kwargs.get("headers") or self.headers)
        suelta = not getattr(_dentro, "contado", False)
        if suelta:
            _antes(url if "://" in str(url) else f"{self.scheme}://{self.host}{url}")
        respuesta = original(self, method, url, **kwargs)
        if suelta:
            _mirar_respuesta(getattr(respuesta, "status", 0), getattr(respuesta, "headers", {}))
        return respuesta
    connectionpool.HTTPConnectionPool.urlopen = urlopen


def _con_httpx():
    try:
        import httpx
    except ImportError:
        return
    normal, asincrono = httpx.Client.send, httpx.AsyncClient.send

    def send(self, request, **kwargs):
        request.headers["User-Agent"] = NAVEGADOR
        _antes(request.url)
        respuesta = normal(self, request, **kwargs)
        _mirar_respuesta(respuesta.status_code, respuesta.headers)
        _despues(len(respuesta.read() or b""))
        return respuesta

    async def asend(self, request, **kwargs):
        request.headers["User-Agent"] = NAVEGADOR
        _antes(request.url)
        respuesta = await asincrono(self, request, **kwargs)
        _mirar_respuesta(respuesta.status_code, respuesta.headers)
        _despues(len(await respuesta.aread() or b""))
        return respuesta
    httpx.Client.send, httpx.AsyncClient.send = send, asend


def _cerrar_urllib():
    import urllib.request

    def prohibido(*_args, **_kwargs):
        _parar("urllib_cerrado")
    urllib.request.urlopen = prohibido


def _auditar(evento, _args):
    if evento in PROHIBIDO or evento.startswith(("os.exec", "os.spawn", "os.posix_spawn")):
        raise PermissionError("vigilante: no permitido (programa)")


def poner(reglas, base, fichero_cuenta):
    cargar(reglas, base)
    _con_requests()
    _con_urllib3()
    _con_httpx()
    _cerrar_urllib()

    def apuntar():
        with open(fichero_cuenta, "w", encoding="utf-8") as f:
            json.dump(_cuenta, f)
    atexit.register(apuntar)                     # antes del gancho: escribir su fichero tiene que poder hacerse
    sys.addaudithook(_auditar)
