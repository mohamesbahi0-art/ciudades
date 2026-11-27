"""Simulacro de la caja del Investigador de webs (herramientas/caja_capturas y .github/workflows/capturas.yml), SIN RED,
sin Docker y sin IA: un repositorio privado de mentira (git local), un capturas.py de mentira y un transporte de
mentira para requests. Comprueba:
- la caja: el texto limpio, la revisión del programa de la IA (lo que no puede llevar, también reintentos y
  transportes propios), las filas, el coste (sin cifra no vale), lo que se ve en la grabación (403, Cloudflare,
  DataDome, captcha; solo si es un fichero normal de la carpeta de rae), el dominio igual que en capturas.py, los
  modelos que cobraron, que el juez y rae van separados y que su entorno no lleva llaves;
- el vigilante: solo su dominio, robots.txt, tope de peticiones, pausa, nada de lanzar programas y, contra un servidor
  de la máquina que contesta 429, una sola petición (sin reintentos), parada en seco y su nombre de robot honrado;
- el turno: las máscaras de la web, las listas del filtro (con las normas de capturas.py y los servicios que meten la IP
  en el nombre, DNS por https y captchas), que la llave no toca el disco, que «en_curso» se guarda antes de capturar,
  que la caja no ve los vetados del dueño, que solo vale el resultado de una caja que acabó sola, lo que se ve en el
  registro del filtro (nombre cambiado dentro del túnel, webs vetadas, captchas), que en el registro solo salen «cap-N»
  y cifras, que se guarda la ficha y que la prueba gasta de los topes del dueño (y sin topes no se hace);
- el workflow: YAML válido, solo en main, llaves solo en «Elegir» y «Guardar», sin credenciales guardadas, sin
  artefactos ni caché, y los topes de los pasos caben en el del trabajo; el filtro mira el SNI (squid-openssl).

    python pruebas/simulacro_caja.py
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="caja-")
os.environ["RUNNER_TEMP"] = TMP
sys.path.insert(0, os.path.join(RAIZ, "herramientas", "caja_capturas"))
import caja  # noqa: E402
import turno  # noqa: E402

FALLOS = [0]
WEB = "https://datos.ejemplo-web.org/ranking/semanal"
LLAVE = "llave-de-prueba-1234567890"


def comprobar(que, vale):
    print(("bien " if vale else "MAL  ") + que, flush=True)
    FALLOS[0] += 0 if vale else 1


def capturado(funcion, *args):
    """Lo que imprime una función (lo que saldría en el registro público) y lo que devuelve."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = funcion(*args)
    return r, buf.getvalue()


# ======================= 1. La caja por dentro =======================
t = caja.limpiar("<b>Hola</b> mira https://x.ejemplo.com/a y www.algo.es, escribe a pepe@correo.com o @alguien; "
                 "ejemplo.org fin")
comprobar("el texto de la web queda plano: sin HTML, enlaces, correos, @ ni dominios",
          not any(x in t for x in ("http", "@", "<", ".org", "correo", "www")))
comprobar("cada valor, 200 caracteres como mucho", len(caja.limpiar("a" * 500)) == 200)
comprobar("el dominio que se registra", caja.dominio_base("a.b.ejemplo.co.uk") == "ejemplo.co.uk"
          and caja.dominio_base("books.toscrape.com") == "toscrape.com")
sys.path.insert(0, RAIZ)
from bots.cerebro import capturas  # noqa: E402
HOSTS = ("data.gov.au", "datos.gob.mx", "www.u-tokyo.ac.jp", "stats.edu.au", "www.bbc.co.uk", "datos.ejemplo.org")
comprobar("y se calcula igual que en capturas.py (data.gov.au no es «gov.au»: otra web del gobierno es otra web)",
          all(caja.dominio_base(h) == capturas.dominio_de(h) for h in HOSTS) and caja.dominio_base("data.gov.au") == "data.gov.au")
BASE = "toscrape.com"
BUENO = textwrap.dedent('''\
    """Cliente de libros (sin cookies ni nada de sesión)."""
    import json, re
    import requests
    BASE = "https://books.toscrape.com/"
    def libros():
        r = requests.get(BASE, timeout=20)
        return [{"titulo": t} for t in re.findall(r'title="([^"]+)"', r.text)]
    if __name__ == "__main__":
        print(json.dumps(libros()))
    ''')
comprobar("un programa limpio pasa la revisión", caja.revisar_cliente(BUENO, BASE) is None)
for codigo, esperado in {
        "import subprocess\n": "import_prohibido", "import os\n": "import_prohibido", "from . import x\n": "import_prohibido",
        "import requests\nrequests.get('https://otra.com/x')\n": "otro_dominio",
        "import requests\nh = {'Authorization': 'Bearer x'}\n": "pide_sesion",
        "import requests\ns = requests.Session()\ns.cookies.set('a', 'b')\n": "pide_sesion",
        "import requests\nrequests.get('https://books.toscrape.com', cookies={})\n": "pide_sesion",
        "import requests\nrequests.get('https://books.toscrape.com', verify=False)\n": "pide_sesion",
        "import httpcloak\n": "disfraz", "import cloudscraper\n": "disfraz",
        "k = 'sk9Fh2kLmQ8zR4tYvB7nX1cW5eJ3pA6dG0uI'\n": "clave_dentro",
        "eval('1')\n": "llamada_prohibida", "open('/etc/passwd')\n": "llamada_prohibida",
        "x = ().__class__.__bases__\n": "llamada_prohibida", "def (:\n": "programa_roto",
        # reintentos y transportes propios: se saltarían la cuenta, las pausas y el «para al primer 429» del vigilante
        "from requests.adapters import HTTPAdapter, Retry\n": "import_prohibido",
        "from urllib3.util import Retry\n": "import_prohibido", "import urllib3\n": "import_prohibido",
        "import requests\ns = requests.Session()\ns.mount('https://', None)\n": "llamada_prohibida",
        "import requests\na = requests.adapters\n": "llamada_prohibida",
        "import requests\nmax_retries = 500\n": "llamada_prohibida",
        "import httpx\nc = httpx.Client(transport=httpx.HTTPTransport(retries=9))\n": "llamada_prohibida"}.items():
    comprobar(f"se descarta un programa con {codigo.strip().splitlines()[-1][:45]!r} ({esperado})",
              caja.revisar_cliente(codigo, BASE) == esperado)
comprobar("las filas salen del JSON que imprime el programa, aunque traiga texto alrededor",
          caja.a_filas('Resultado:\n[{"t": "A"}, {"t": "B"}]\nfin') == [{"t": "A"}, {"t": "B"}])
comprobar("200 filas como mucho", len(caja.a_filas(json.dumps({"items": [{"a": 1}] * 300}))) == 200)
fila = caja.a_filas(json.dumps([{"t": "<script>x</script> https://malo.com/x @alguien"}]))[0]["t"]
comprobar("las filas también quedan planas", not any(x in fila for x in ("<", "malo", "@")))
comprobar("sin «usage» o sin cifra de coste no hay coste conocido (nunca es un 0)",
          caja.coste_de({"usage": {}}) is None and caja.coste_de({}) is None
          and caja.coste_de({"usage": {"total_cost_usd": 0}}) == 0.0)
comprobar("rae gratis y bien: sigue; con coste: de_pago; sin coste: sin_coste; colgado: colgada",
          caja._juzgar_rae(0, {"status": "ok", "usage": {"total_cost_usd": 0.0}}, None) is None
          and caja._juzgar_rae(0, {"status": "ok", "usage": {"total_cost_usd": 0.02}}, None) == ("fallida", "de_pago")
          and caja._juzgar_rae(0, {"status": "ok", "usage": {}}, None) == ("fallida", "sin_coste")
          and caja._juzgar_rae(124, None, None) == ("fallida", "colgada"))
comprobar("«no serving provider» es que no hay modelo gratis, no un fallo de la web",
          caja._causa("OpenCode has no serving provider available for this model") == "sin_modelo_gratis")

caja.TRABAJO = os.path.join(TMP, "trabajo")       # la carpeta de rae: solo de ahí lee el juez lo que deja
os.makedirs(caja.TRABAJO)
HAR = os.path.join(caja.TRABAJO, "recording.har")


def grabacion(*entradas):
    with open(HAR, "w", encoding="utf-8") as f:
        json.dump({"log": {"entries": list(entradas)}}, f)
    return caja.leer_har(HAR, BASE)


def peticion(url, estado=200, dest="document", mime="text/html", cabeceras=(), cuerpo=None):
    contenido = {"mimeType": mime, **({"text": cuerpo} if cuerpo else {})}
    return {"request": {"method": "GET", "url": url, "headers": [{"name": "Sec-Fetch-Dest", "value": dest}]},
            "response": {"status": estado, "headers": [{"name": k, "value": v} for k, v in cabeceras],
                         "content": contenido}}


h = grabacion(peticion("https://books.toscrape.com/"),
              peticion("https://books.toscrape.com/api/x?page=2&q=a", dest="empty", mime="application/json"),
              peticion("https://www.youtube.com/embed/1", estado=0, dest="iframe"))
comprobar("la grabación da peticiones, llamadas a la API (sin valores) y webs abiertas",
          h["bloqueo"] is None and h["peticiones"] == 3 and h["endpoints"] == ["GET /api/x?page=&q="]
          and h["navegados"] == ["books.toscrape.com"] and h["hosts"] == ["books.toscrape.com"])
for nombre, entradas, esperado in (
        ("un 403 de la web", [peticion("https://books.toscrape.com/", 403)], "bloqueo_403"),
        ("un 429 de la web", [peticion("https://books.toscrape.com/", 429)], "bloqueo_429"),
        ("Cloudflare", [peticion("https://books.toscrape.com/", cabeceras=[("cf-mitigated", "challenge")])],
         "cloudflare"),
        ("DataDome", [peticion("https://books.toscrape.com/", cabeceras=[("x-datadome", "protected")])], "datadome"),
        ("un captcha en la página", [peticion("https://books.toscrape.com/", cuerpo="<div class='g-recaptcha'>")],
         "captcha"),
        ("un servicio de retos", [peticion("https://challenges.cloudflare.com/x", dest="script")], "captcha"),
        ("el 403 del propio filtro (no cuenta)",
         [peticion("https://books.toscrape.com/", 403, cabeceras=[("X-Squid-Error", "ERR_ACCESS_DENIED 0")])], None),
        ("un 429 de otra web (no cuenta)", [peticion("https://otra.com/", 429)], None)):
    comprobar(f"la grabación ve {nombre}", grabacion(*entradas)["bloqueo"] == esperado)
fuera = os.path.join(TMP, "fuera.har")
with open(fuera, "w", encoding="utf-8") as f:
    f.write("{}")
os.symlink(fuera, os.path.join(caja.TRABAJO, "enlace.har"))
comprobar("lo que deja rae solo se lee si es un fichero normal de su carpeta (ni de fuera ni un enlace)",
          caja.leer_de_rae(HAR, 10_000_000) and caja.leer_de_rae(fuera, 1000) is None
          and caja.leer_de_rae(os.path.join(caja.TRABAJO, "enlace.har"), 1000) is None)
casa, caja_casa = os.path.join(TMP, "casa-rae"), caja.CASA
os.makedirs(casa)
caja.CASA = casa
separados = caja.juez_separado() is False         # una casa que no es de rae (o sin ser root): la caja no trabaja
if os.geteuid() == 0:                             # como root también se ven el caso bueno y la casa cerrada (0750)
    os.chown(casa, caja.UID_RAE, caja.GID_RAE)
    os.chmod(casa, 0o755)
    separados = separados and caja.juez_separado()
    os.chmod(casa, 0o750)
    separados = separados and not caja.juez_separado()
caja.CASA = caja_casa
comprobar("el juez tiene que ser root y rae otro usuario, con su casa abierta para que el juez pueda entrar (si no, la "
          "caja no trabaja)", separados)
dockerfile = open(os.path.join(RAIZ, "herramientas", "caja_capturas", "Dockerfile"), encoding="utf-8").read()
comprobar("la imagen deja la casa de rae en 0755 (Ubuntu la hace en 0750 y el juez, sin poderes, no podría entrar) y el "
          "filtro va con squid-openssl para mirar el nombre de dentro del túnel",
          "chmod 0755 /home/rae" in dockerfile and "squid-openssl" in dockerfile)
filtro = open(os.path.join(RAIZ, "herramientas", "caja_capturas", "filtro.conf"), encoding="utf-8").read()
comprobar("el filtro mira el SNI sin descifrar (peek) y corta los vetados también ahí (terminate)",
          all(x in filtro for x in ("ssl-bump", "ssl_bump peek paso1", "ssl_bump terminate sni_vetado",
                                    "ssl_bump terminate sni_vetado_re", "ssl_bump splice all", "%ssl::>sni")))
sys.modules.setdefault("httpx2", type(sys)("httpx2"))       # modelo.py sin rae ni OpenCode: solo su elección
falso_rt = type(sys)("reverse_api.opencode_runtime")
falso_rt.OpenCodeSetupError = RuntimeError
falso_rt.opencode_model_is_selectable = lambda datos: bool(datos.get("tool_call"))
falso_rt.ensure_opencode_server = falso_rt.get_opencode_model_catalog = falso_rt.stop_managed_opencode_server = None
sys.modules.setdefault("reverse_api", type(sys)("reverse_api"))
sys.modules["reverse_api.opencode_runtime"] = falso_rt
import modelo  # noqa: E402
CERO = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
CATALOGO = {"providers": [{"id": "opencode", "models": {
    "big-pickle": {"tool_call": True, "cost": dict(CERO)}, "otro-gratis": {"tool_call": True, "cost": dict(CERO)},
    "de-pago": {"tool_call": True, "cost": dict(CERO, output=2)}, "sin-herramientas": {"cost": dict(CERO)}}}]}
comprobar("el modelo: el gratis de verdad (big-pickle primero); el que cobró una vez, nunca más; si no queda ninguno, "
          "«sin modelo gratis»; con otro proveedor conectado, nada",
          modelo.elegir(CATALOGO) == ("big-pickle", None)
          and modelo.elegir(CATALOGO, ["opencode/big-pickle"]) == ("otro-gratis", None)
          and modelo.elegir(CATALOGO, ["big-pickle", "otro-gratis"]) == (None, "sin_modelo_gratis")
          and modelo.elegir({"providers": CATALOGO["providers"] + [{"id": "openai", "models": {}}]})
          == (None, "proveedor_extra"))
comprobar("la caja se para si ve una llave (…_KEY, …_TOKEN, GH_…, OPENCODE_…)",
          set(caja.llaves_a_la_vista({"GH_SECRETOS": "x", "GROQ_API_KEY": "y", "MI_TOKEN": "z",
                                      "OPENCODE_AUTH_CONTENT": "w", "PATH": "/bin"}))
          == {"GH_SECRETOS", "GROQ_API_KEY", "MI_TOKEN", "OPENCODE_AUTH_CONTENT"})
env = caja.entorno("clave", 4096, "big-pickle", True)
cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
comprobar("OpenCode solo con su proveedor gratis, ese modelo, sin compartir ni actualizarse y sin webfetch",
          cfg["enabled_providers"] == ["opencode"] and cfg["provider"]["opencode"]["whitelist"] == ["big-pickle"]
          and cfg["model"] == cfg["small_model"] == "opencode/big-pickle" and cfg["share"] == "disabled"
          and cfg["autoupdate"] is False and cfg["permission"] == {"webfetch": "deny", "websearch": "deny"})
comprobar("navegador nuevo y sin sesiones, sin WebMCP, versiones fijas y todo por el filtro",
          env["PLAYWRIGHT_MCP_ISOLATED"] == "true" and env["PLAYWRIGHT_MCP_WEBMCP"] == "false"
          and env["RAE_OPENCODE_PACKAGE"] == "opencode-ai@1.18.31" and env["npm_config_offline"] == "true"
          and env["HTTPS_PROXY"] == env["PLAYWRIGHT_MCP_PROXY_SERVER"] == caja.FILTRO_URL)
comprobar("el entorno de rae no lleva ninguna llave (solo la contraseña propia de su OpenCode)",
          [k for k in caja.llaves_a_la_vista(env) if k != "OPENCODE_SERVER_PASSWORD"
           and not k.startswith("OPENCODE_")] == [] and "GITHUB_TOKEN" not in env and "GH_SECRETOS" not in env)

# ======================= 2. El vigilante del programa de la IA (en otro Python: deja puesto su gancho) ==========
VIGILA = textwrap.dedent(r'''
    import json, os, sys, tempfile, time
    sys.path.insert(0, sys.argv[1])
    import requests, requests.adapters
    def falso(self, request, **kw):
        r = requests.Response(); r.status_code = 200; r.url = request.url
        r._content = b"User-agent: *\nDisallow: /privado\n" if request.url.endswith("/robots.txt") else b"[1]"
        return r
    requests.adapters.HTTPAdapter.send = falso
    import vigilante
    d = tempfile.mkdtemp(); reglas = os.path.join(d, "v.json"); cuenta = os.path.join(d, "c.json")
    json.dump({"dominio": "ejemplo.org", "hosts": ["datos.ejemplo.org"], "pausa": 0.01, "max_peticiones": 4,
               "robots": {"datos.ejemplo.org": "User-agent: *\nAllow: /\n"}, "prohibidos": ["login"]}, open(reglas, "w"))
    vigilante.poner(reglas, "ejemplo.org", cuenta)
    def prueba(url):
        try:
            requests.get(url, timeout=5); return "ok"
        except vigilante.Parado as e:
            return str(e).split("(")[-1].rstrip(")")
    t = time.monotonic()
    res = [prueba(u) for u in ("https://datos.ejemplo.org/api", "https://otra.com/x", "http://datos.ejemplo.org/api",
                               "https://login.ejemplo.org/", "https://www.ejemplo.org/privado/x",
                               "https://www.ejemplo.org/a", "https://www.ejemplo.org/b", "https://www.ejemplo.org/c")]
    try:
        import subprocess; subprocess.run(["true"]); res.append("programa")
    except PermissionError:
        res.append("sin_programas")
    res.append(round(time.monotonic() - t, 1))
    print(json.dumps(res))
''')
# un servidor de la máquina que contesta 429 en /x y bien en lo demás (robots.txt: no a /privado)
VIGILA_429 = textwrap.dedent(r'''
    import http.server, json, os, sys, tempfile, threading
    sys.path.insert(0, sys.argv[1])
    recibidas, agentes = [0], []
    class Web(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            recibidas[0] += 1
            agentes.append(self.headers.get("User-Agent"))
            self.send_response(429 if self.path == "/x" else 200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"[]")
        def log_message(self, *a):
            pass
    web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{web.server_address[1]}"
    import requests, urllib3
    from requests.adapters import HTTPAdapter
    from urllib3.util import Retry
    import vigilante
    vigilante.ESQUEMAS = ("https", "http")             # solo en la prueba: el servidor de la máquina va sin https
    d = tempfile.mkdtemp()
    reglas, cuenta = os.path.join(d, "v.json"), os.path.join(d, "c.json")
    json.dump({"dominio": "", "hosts": ["127.0.0.1"], "pausa": 0.01,
               "robots": {"127.0.0.1": "User-agent: *\nDisallow: /privado\n"}}, open(reglas, "w"))
    vigilante.poner(reglas, "", cuenta)
    # primero urllib3 a pelo (sin requests): cuenta y robots.txt
    pm = urllib3.PoolManager()
    def por_urllib3(ruta):
        try:
            pm.request("GET", base + ruta, retries=urllib3.Retry(total=50, status_forcelist=[429]))
            return "ok"
        except vigilante.Parado as e:
            return str(e).split("(")[-1].rstrip(")")
    sale_urllib3 = [por_urllib3("/a"), por_urllib3("/privado/b")]
    cuenta_urllib3, recibidas[0], agentes[:] = vigilante._cuenta["peticiones"], 0, []
    s = requests.Session()
    s.mount("http://", HTTPAdapter(max_retries=Retry(total=500, status_forcelist=[403, 429], backoff_factor=0)))
    def intento(ruta):
        try:
            s.get(base + ruta, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"}, timeout=5)
            return "sin parar"
        except Exception as e:
            return type(e).__name__
    error, segunda = intento("/x"), intento("/y")
    print(json.dumps({"recibidas": recibidas[0], "agentes": agentes, "error": error, "segunda": segunda,
                      "cuenta": vigilante._cuenta, "urllib3": sale_urllib3, "cuenta_urllib3": cuenta_urllib3}))
''')
try:
    import requests  # noqa: F401
    hay_requests = True
except ImportError:
    hay_requests = False
if hay_requests:
    r = subprocess.run([sys.executable, "-c", VIGILA, os.path.join(RAIZ, "herramientas", "caja_capturas")],
                       capture_output=True, text=True, timeout=60)
    res = json.loads((r.stdout.strip().splitlines() or ["[]"])[-1])
    comprobar("el vigilante: su dominio sí; otro dominio, http y las de entrar, no; robots.txt manda; 4 como mucho; "
              "nada de lanzar programas; y al menos 1 s entre peticiones",
              res[:9] == ["ok", "otro_dominio", "otro_dominio", "otro_dominio", "robots", "ok", "ok",
                          "demasiadas_peticiones", "sin_programas"] and res[9] >= 2.0)
    r = subprocess.run([sys.executable, "-c", VIGILA_429, os.path.join(RAIZ, "herramientas", "caja_capturas")],
                       capture_output=True, text=True, timeout=60)
    res = json.loads((r.stdout.strip().splitlines() or ["{}"])[-1])
    comprobar("contra una web que contesta 429 (con 500 reintentos de urllib3 puestos): le llega UNA petición, se para "
              "en seco con «bloqueo_429», ya no deja hacer ninguna más y va con su nombre de robot honrado",
              res.get("recibidas") == 1 and res.get("error") == "Parado" and res.get("segunda") == "Parado"
              and res.get("cuenta", {}).get("bloqueo") == "bloqueo_429"
              and res.get("agentes") == ["investigador-web/1.0 (robot educado: respeta robots.txt)"])
    comprobar("y lo que va por urllib3 sin requests también se cuenta y pasa por robots.txt",
              res.get("urllib3") == ["ok", "robots"] and res.get("cuenta_urllib3") == 1)
else:
    print("(sin requests en esta máquina: el vigilante se prueba dentro de la caja)")

# ======================= 3. El turno en la máquina de GitHub =======================
turno.preparar_carpetas()
_, salida = capturado(turno.tapar, WEB + "?pagina=2", ["miapp.example.net"])
mascaras = [x.split("::add-mask::", 1)[1] for x in salida.splitlines() if x.startswith("::add-mask::")]
comprobar("se tapan la web, su host, su dominio, su nombre, su ruta, su forma %-codificada y los vetados del dueño",
          all(v in mascaras for v in (WEB + "?pagina=2", "datos.ejemplo-web.org", "ejemplo-web.org", "ejemplo-web",
                                      "/ranking/semanal", "miapp.example.net", "example.net",
                                      "https%3A%2F%2Fdatos.ejemplo-web.org%2Franking%2Fsemanal%3Fpagina%3D2")))
sufijos = turno.listas_del_filtro(turno.normas_de_capturas(), ["miapp.example.net"])
with open(os.path.join(turno.LISTAS, "vetados.txt"), encoding="utf-8") as f:
    vet = f.read().split()
vetos = turno.leer_vetos()
comprobar("el filtro lleva los vetados de capturas.py, PyPI, npm y los del dueño, sin repetir",
          all(d in vet for d in (".tiktok.com", ".youtube.com", ".instagram.com", ".pypi.org", ".npmjs.org",
                                 ".miapp.example.net", ".localhost")) and len(vet) == len(set(vet)) == len(sufijos))
comprobar("y los que meten la IP en el nombre (1-2-3-4.sslip.io), el DNS por https y los servicios de captcha",
          all(turno.vetada_por_nombre(x, vetos) for x in ("1-2-3-4.sslip.io", "10.0.0.1.nip.io", "cloudflare-dns.com",
                                                          "dns.google", "challenges.cloudflare.com", "www.recaptcha.net",
                                                          "js.hcaptcha.com", "geo.captcha-delivery.com")))
comprobar("las tiendas de Amazon y eBay sí, pero no los datos públicos en sus servidores (S3, API Gateway)",
          all(turno.vetada_por_nombre(x, vetos) for x in ("amazon.es", "www.amazon.co.uk", "amazon-adsystem.com",
                                                          "ebay.de"))
          and not any(turno.vetada_por_nombre(x, vetos) for x in ("mybucket.s3.amazonaws.com",
                                                                   "x.execute-api.eu-west-1.amazonaws.com")))
comprobar("el filtro corta también las de entrar y las marcas en cualquier país",
          all(turno.vetada_por_nombre(x, vetos) for x in ("login.ejemplo.org", "www.accounts.algo.com", "tiktok.es",
                                                          "googletagmanager.com", "youtu.be", "instagram.de"))
          and not any(turno.vetada_por_nombre(x, vetos) for x in ("books.toscrape.com", "loginsoft.es",
                                                                   "fonts.gstatic.com")))
log = os.path.join(turno.REGISTROS, "x.log")
with open(log, "w", encoding="utf-8") as f:
    f.write("::add-mask::secreto.org\ncap-3: en_curso · intento 1 · https://secreto.org/x\nTraceback secreto.org\n"
            "capturas: nada pendiente · hoy 0/2\n")
_, salida = capturado(turno.pasar, log)
visible = "\n".join(x for x in salida.splitlines() if not x.startswith("::add-mask::"))
comprobar("de capturas.py solo se ven sus máscaras y sus líneas «cap-N»/«capturas», limpias",
          "::add-mask::secreto.org" in salida and "secreto" not in visible and "Traceback" not in visible
          and "cap-3: en_curso" in visible)
comprobar("la línea del registro: solo cap-N y cifras",
          turno.linea({"id": "cap-7", "estado": "hecha", "filas": 48, "peticiones": 12, "denegadas": 3,
                       "coste_usd": 0.0, "segundos": 420, "datos": [{"x": "secreto.org"}]})
          == "cap-7: hecha · 48 filas · 12 peticiones · 3 cortadas por el filtro · 0 $ · 7 min"
          and turno.linea({"id": "cap-7", "estado": "vetada", "motivo": "algo https://x"}) == "cap-7: vetada · otro"
          and turno.linea({"id": "cap-7", "estado": "vetada", "motivo": "rae_secreto"}) == "cap-7: vetada · otro"
          and turno.linea({"id": "cap-7", "estado": "vetada", "motivo": "bloqueo_403"}) == "cap-7: vetada · bloqueo_403")
comprobar("y la ficha de la prueba guarda lo de rae solo si es una palabra corta nuestra",
          turno.ficha_prueba({"id": "cap-0", "estado": "fallida", "motivo": "x y z",
                              "rae": {"status": "error", "error_kind": "ejemplo.org/secreto"}})["rae"]
          == {"status": "error", "error_kind": None})

# --- el repositorio privado de mentira (git local) y un capturas.py de mentira ---
ORIGEN = os.path.join(TMP, "origen")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), ORIGEN)
with open(os.path.join(ORIGEN, "config", "fabrica.json"), encoding="utf-8") as f:
    fab = json.load(f)
fab["capturas"] = {"encendido": True, "vetados_extra": ["miapp.example.net"]}
with open(os.path.join(ORIGEN, "config", "fabrica.json"), "w", encoding="utf-8") as f:
    json.dump(fab, f)
os.makedirs(os.path.join(ORIGEN, "estado", "capturas"), exist_ok=True)
with open(os.path.join(ORIGEN, "estado", "capturas", "cola.json"), "w", encoding="utf-8") as f:
    json.dump({"pedidos": [{"id": "cap-5", "estado": "pendiente", "web": WEB}]}, f)
GIT = {**os.environ, "GIT_AUTHOR_NAME": "p", "GIT_AUTHOR_EMAIL": "p@p", "GIT_COMMITTER_NAME": "p",
       "GIT_COMMITTER_EMAIL": "p@p"}
for orden in (["git", "init", "-q", "-b", "main"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "inicio"]):
    subprocess.run(orden, cwd=ORIGEN, env=GIT, check=True, capture_output=True)
DESNUDO = os.path.join(TMP, "privado.git")
subprocess.run(["git", "clone", "-q", "--bare", ORIGEN, DESNUDO], check=True, capture_output=True)
subprocess.run(["git", "-C", DESNUDO, "config", "uploadpack.allowFilter", "true"], check=True)
turno.url_privado = lambda: "file://" + DESNUDO
CHIVATO = os.path.join(TMP, "chivato.json")
FALSO = os.path.join(TMP, "capturas_falso.py")
with open(FALSO, "w", encoding="utf-8") as f:
    f.write(textwrap.dedent(f'''
        import json, os, subprocess, sys
        orden, priv = sys.argv[1], os.environ["PRIVADO"]
        config = subprocess.run(["git", "-C", priv, "config", "--list", "--local"], capture_output=True, text=True).stdout
        ficheros = sorted(os.path.relpath(os.path.join(d, n), priv) for d, _, ns in os.walk(priv) if ".git" not in d
                          for n in ns)
        json.dump({{"orden": orden, "config_con_llave": "extraheader" in config or {LLAVE!r} in config,
                   "ficheros": ficheros, "llave_en_entorno": "GH_SECRETOS" in os.environ}},
                  open({CHIVATO!r}, "w"))
        ruta_cola = os.path.join(priv, "estado", "capturas", "cola.json")
        cola = json.load(open(ruta_cola))
        if orden == "elegir":
            salida = sys.argv[sys.argv.index("--salida") + 1]
            print("::add-mask::{WEB}")
            json.dump({{"id": "cap-5", "web": "{WEB}", "que": "puesto y título"}}, open(os.path.join(salida, "pedido.json"), "w"))
            json.dump({{"dominio": "ejemplo-web.org", "hosts": ["datos.ejemplo-web.org"], "vetados": ["miapp.example.net"]}},
                      open(os.path.join(salida, "vigilante.json"), "w"))
            cola["pedidos"][0].update(estado="en_curso", intentos=1)
            open(os.environ["GITHUB_OUTPUT"], "a").write("hay=1\\nid=cap-5\\n")
            print("cap-5: en_curso · intento 1 · {WEB}")
            print("Traceback: algo con {WEB}")
        else:
            carpeta = sys.argv[sys.argv.index("--resultado") + 1]
            r = json.load(open(os.path.join(carpeta, "resultado.json")))
            cola["pedidos"][0].update(estado=r["estado"])
            json.dump({{"id": "cap-5", "estado": r["estado"], "filas": r.get("filas")}},
                      open(os.path.join(priv, "estado", "capturas", "cap-5.json"), "w"))
            print(f"cap-5: {{r['estado']}} · {{r.get('filas')}} filas")
        json.dump(cola, open(ruta_cola, "w"))
    '''))
turno.CAPTURAS = FALSO


def en_el_origen(ruta):
    r = subprocess.run(["git", "-C", DESNUDO, "show", f"main:{ruta}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


SALIDAS = os.path.join(TMP, "github_output")
os.environ.update({"GITHUB_OUTPUT": SALIDAS, "GITHUB_EVENT_NAME": "schedule", "GITHUB_ACTIONS": "true",
                   "GH_SECRETOS": LLAVE})
codigo, salida = capturado(turno.elegir)
chivato = json.load(open(CHIVATO))
visible = [x for x in salida.splitlines() if not x.startswith("::add-mask::")]
comprobar("elegir: sale bien y deja hay=1 e id=cap-5 para los pasos siguientes",
          codigo == 0 and turno.leer_salidas(SALIDAS) == {"hay": "1", "id": "cap-5"})
comprobar("la copia privada para elegir es parcial (la cola y lo justo) y sin la llave en .git/config ni en capturas.py",
          not chivato["config_con_llave"] and not chivato["llave_en_entorno"]
          and "estado/capturas/cola.json" in chivato["ficheros"] and not any(
              x.startswith(("memoria/organizador", "trabajo/")) for x in chivato["ficheros"]))
comprobar("«en_curso» queda guardado en el privado ANTES de capturar",
          (en_el_origen("estado/capturas/cola.json") or {}).get("pedidos", [{}])[0].get("estado") == "en_curso")
comprobar("y la copia privada se borra del disco", not os.path.exists(os.path.join(turno.CAJA, "privado-cola")))
comprobar("la web, la llave y su cabecera se tapan antes de imprimir nada", salida.splitlines()[0].startswith("::add-mask::")
          and any(x.endswith("datos.ejemplo-web.org") for x in salida.splitlines() if x.startswith("::add-mask::"))
          and any(x.startswith("::add-mask::eC1hY2Nlc3Mt") for x in salida.splitlines()))
comprobar("en el registro solo «cap-N» y cifras: ni la web, ni su dominio, ni la llave, ni el traceback",
          visible and not any(x in "\n".join(visible) for x in ("ejemplo-web", "datos.", LLAVE, "Traceback")))
with open(os.path.join(turno.ENTRADA, "vigilante.json"), encoding="utf-8") as f:
    reglas = json.load(f)
comprobar("la caja solo ve el pedido y las reglas de red, sin los vetados propios del dueño",
          sorted(os.listdir(turno.ENTRADA)) == ["pedido.json", "vigilante.json"] and "vetados" not in reglas)

comprobar("los vetados del dueño pasan al filtro (solo en la máquina, no en la caja)",
          turno.leer_lista_extra() == ["miapp.example.net"])
turno.listas_del_filtro(turno.normas_de_capturas(), turno.leer_lista_extra())     # lo que hace «preparar»

# lo que dejaría la caja: el navegador abrió una web prohibida → la captura se tira
os.makedirs(turno.SALIDA, exist_ok=True)
with open(os.path.join(turno.SALIDA, "resultado.json"), "w", encoding="utf-8") as f:
    json.dump({"id": "cap-5", "estado": "hecha", "filas": 3, "datos": [{"a": 1}], "coste_usd": 0.0,
               "navegados": ["datos.ejemplo-web.org", "accounts.google.com"]}, f)
LIMPIO_FILTRO = ("1795739033 TCP_DENIED/403 CONNECT prueba.tiktok.com:443 -\n"
                 "1795739033 TCP_TUNNEL/200 CONNECT datos.ejemplo-web.org:443 datos.ejemplo-web.org\n"
                 "1795739033 TCP_TUNNEL/200 CONNECT opencode.ai:443 opencode.ai\n"
                 "1795739033 TCP_DENIED/403 CONNECT www.youtube.com:443 -\n"
                 "1795739033 TCP_DENIED/403 GET http://fonts.googleapis.com/css -\n")
FILTRO = [LIMPIO_FILTRO]
turno.registro_del_filtro = lambda: None if FILTRO[0] is None else turno.conexiones(FILTRO[0])
r = turno.revisar(turno.leer_resultado("cap-5"))
comprobar("si el navegador abrió una web vetada (aunque el filtro la cortase), la captura se tira",
          r["estado"] == "vetada" and r["motivo"] == "web_prohibida" and r["datos"] == [] and "navegados" not in r)


def revisada(registro, **resultado):
    FILTRO[0] = registro
    return turno.revisar(dict({"id": "cap-5", "estado": "hecha", "filas": 1, "datos": [{"a": 1}], "coste_usd": 0.0},
                              **resultado))


bueno = revisada(LIMPIO_FILTRO, navegados=["datos.ejemplo-web.org"])
comprobar("con el registro del filtro limpio, sigue «hecha» y cuenta lo que cortó (sin las pruebas del propio filtro)",
          bueno["estado"] == "hecha" and bueno["denegadas"] == 2)
for nombre, linea_filtro, esperado in (
        ("pide un nombre inocente y dentro del túnel habla con TikTok (SNI cambiado)",
         "1795739033 NONE_NONE/200 CONNECT 1-2-3-4.ejemplo-web.org:443 www.tiktok.com\n", "red_trampa"),
        ("abre un túnel sin nombre dentro (así el filtro no puede mirar con quién habla)",
         "1795739033 TCP_TUNNEL/200 CONNECT 1-2-3-4.ejemplo-web.org:443 -\n", "red_trampa"),
        ("habla con una web vetada que el filtro dejó pasar",
         "1795739033 TCP_TUNNEL/200 CONNECT m.youtube.com:443 m.youtube.com\n", "web_prohibida"),
        ("carga un captcha (aunque el filtro lo cortase)",
         "1795739033 TCP_DENIED/403 CONNECT challenges.cloudflare.com:443 -\n", "captcha")):
    malo = revisada(LIMPIO_FILTRO + linea_filtro)
    comprobar(f"el registro del filtro (que la IA no alcanza) ve que {nombre}: «vetada», sin datos",
              malo["estado"] == "vetada" and malo["motivo"] == esperado and malo["datos"] == [])
comprobar("y también tira lo que la caja diera por fallido por la web (la grabación la pudo tocar la IA)",
          revisada(LIMPIO_FILTRO + "1795739033 TCP_TUNNEL/200 CONNECT x.tiktokcdn.com:443 x.tiktokcdn.com\n",
                   estado="fallida", motivo="sin_datos")["estado"] == "vetada")
sin_registro = revisada(None)
comprobar("sin poder leer el registro del filtro, una «hecha» no vale (no se puede comprobar nada)",
          sin_registro["estado"] == "fallida" and sin_registro["motivo"] == "filtro_caido" and sin_registro["datos"] == [])
FILTRO[0] = LIMPIO_FILTRO
os.makedirs(turno.SALIDA, exist_ok=True)
for codigo_caja, esperado in ((137, "caja_sin_resultado"), (124, "caja_sin_resultado"), (143, "caja_sin_resultado"),
                              (0, "hecha")):
    with open(os.path.join(turno.SALIDA, "resultado.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "cap-5", "estado": "hecha", "filas": 1, "datos": [{"a": 1}], "coste_usd": 0.0}, f)
    turno.lanzar_caja = lambda codigo=codigo_caja: codigo
    capturado(turno.capturar)
    with open(os.path.join(turno.LIMPIO, "resultado.json"), encoding="utf-8") as f:
        hecho = json.load(f)
    comprobar(f"la caja acaba con {codigo_caja}: " + ("se lee lo que dejó" if codigo_caja == 0 else
                                                      "no acabó ella sola (la mataron o se colgó): no se lee nada"),
              (hecho.get("motivo") or hecho.get("estado")) == esperado)
os.remove(os.path.join(turno.SALIDA, "resultado.json"))
os.symlink("/etc/hostname", os.path.join(turno.SALIDA, "resultado.json"))
comprobar("un resultado que es un enlace a otro sitio no se lee", turno.leer_resultado("cap-5") is None)
os.remove(os.path.join(turno.SALIDA, "resultado.json"))
turno.escribir_limpio({"id": "cap-5", "estado": "hecha", "filas": 3, "datos": [{"a": 1}], "coste_usd": 0.0})

turno.cajas_vivas = lambda: ["abc"]
os.environ["GH_SECRETOS"] = LLAVE
codigo, salida = capturado(turno.guardar)
comprobar("guardar no saca la llave mientras quede algo vivo de la caja",
          codigo == 1 and en_el_origen("estado/capturas/cap-5.json") is None)
turno.cajas_vivas = lambda: []
os.environ["GH_SECRETOS"] = LLAVE
codigo, salida = capturado(turno.guardar)
comprobar("guardar: capturas.py guardar con el resultado limpio y la ficha subida al privado",
          codigo == 0 and (en_el_origen("estado/capturas/cap-5.json") or {}).get("estado") == "hecha"
          and json.load(open(CHIVATO))["orden"] == "guardar" and not json.load(open(CHIVATO))["config_con_llave"])
comprobar("y en el registro solo «cap-5: hecha · 3 filas»", "cap-5: hecha · 3 filas" in salida and LLAVE not in salida)

# la prueba con la web de práctica: no pasa por la cola, pero gasta de los mismos topes del dueño (2 al día, 5 a la
# semana) y lo apunta ANTES de capturar
def cambiar_en_el_origen(ruta, datos, mensaje):
    """El privado cambia por otro lado (el dueño o el Cerebro): una copia al día, el cambio y push."""
    subprocess.run(["git", "-C", ORIGEN, "pull", "-q", DESNUDO, "main"], env=GIT, check=True, capture_output=True)
    with open(os.path.join(ORIGEN, ruta), "w", encoding="utf-8") as f:
        json.dump(datos, f)
    subprocess.run(["git", "commit", "-q", "-am", mensaje], cwd=ORIGEN, env=GIT, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", DESNUDO, "main"], cwd=ORIGEN, env=GIT, check=True, capture_output=True)


def elegir_prueba():
    if os.path.exists(SALIDAS):
        os.remove(SALIDAS)
    os.environ["GH_SECRETOS"] = LLAVE
    return capturado(turno.elegir)


PETICION = os.path.join(TMP, "capturas.json")
with open(PETICION, "w", encoding="utf-8") as f:
    json.dump({"probar": True}, f)
turno.PETICION = PETICION
os.environ["GITHUB_EVENT_NAME"] = "push"
HOY = capturas._ahora().date()
cola_antes = en_el_origen("estado/capturas/cola.json") or {}
codigo, salida = elegir_prueba()
with open(os.path.join(turno.ENTRADA, "pedido.json"), encoding="utf-8") as f:
    pedido = json.load(f)
cola_prueba = en_el_origen("estado/capturas/cola.json") or {}


def de_hoy(cola):
    return int(((cola.get("uso") or {}).get(HOY.isoformat()) or {}).get("capturas") or 0)


comprobar("la prueba elige la web de práctica fija (cap-0) sin pasar por la cola, pero apunta antes que gasta una de hoy",
          codigo == 0 and turno.leer_salidas(SALIDAS) == {"hay": "1", "id": "cap-0"}
          and pedido["web"] == turno.PRUEBA["web"] and cola_prueba.get("pedidos") == cola_antes.get("pedidos")
          and de_hoy(cola_prueba) == de_hoy(cola_antes) + 1 and "hoy 1/2" in salida)
turno.escribir_limpio({"id": "cap-0", "estado": "hecha", "filas": 2, "datos": [{"t": "<b>A</b>"}], "coste_usd": 0.0})
os.environ["GH_SECRETOS"] = LLAVE
codigo, _ = capturado(turno.guardar)
prueba = en_el_origen("estado/capturas/prueba.json") or {}
comprobar("y se guarda en estado/capturas/prueba.json, limpia, sin tocar más la cola",
          codigo == 0 and prueba.get("estado") == "hecha" and prueba.get("datos") == [{"t": "b A /b"}]
          and en_el_origen("estado/capturas/cola.json") == cola_prueba)
cambiar_en_el_origen("estado/capturas/cola.json", dict(cola_prueba, uso={HOY.isoformat(): {"capturas": 2}}), "tope")
codigo, salida = elegir_prueba()
comprobar("con las 2 de hoy ya hechas, la prueba no se hace", codigo == 0 and turno.leer_salidas(SALIDAS) == {"hay": "0"}
          and "tope" in salida)
semana = {(HOY - capturas.dt.timedelta(days=d)).isoformat(): {"capturas": 1} for d in range(1, 6)}
cambiar_en_el_origen("estado/capturas/cola.json", dict(cola_prueba, uso=semana), "semana")
codigo, salida = elegir_prueba()
comprobar("con las 5 de la semana ya hechas, tampoco", codigo == 0 and turno.leer_salidas(SALIDAS) == {"hay": "0"})
cambiar_en_el_origen("estado/capturas/cola.json", dict(cola_prueba, uso={}), "sin uso")
fab["capturas"]["encendido"] = False                       # el dueño lo apaga
cambiar_en_el_origen(os.path.join("config", "fabrica.json"), fab, "apagado")
codigo, _ = elegir_prueba()
comprobar("con el interruptor del dueño apagado, ni la prueba", codigo == 0 and turno.leer_salidas(SALIDAS) == {"hay": "0"})
del fab["capturas"]                                        # y sin el apartado «capturas», tampoco
cambiar_en_el_origen(os.path.join("config", "fabrica.json"), fab, "sin capturas")
codigo, _ = elegir_prueba()
comprobar("ni sin el apartado «capturas» en la configuración", codigo == 0 and turno.leer_salidas(SALIDAS) == {"hay": "0"})

# ======================= 4. El workflow =======================
try:
    import yaml
except ImportError:
    yaml = None
if yaml:
    with open(os.path.join(RAIZ, ".github", "workflows", "capturas.yml"), encoding="utf-8") as f:
        texto = f.read()
    w = yaml.safe_load(texto)
    on, trabajo = w.get(True) or w.get("on"), w["jobs"]["investigar"]
    fuera = [p.get("name") or p.get("uses") for p in trabajo["steps"]
             if "secrets." in yaml.safe_dump(p) and p.get("name") not in ("Elegir", "Guardar")]
    pasos = sum(int(p.get("timeout-minutes") or 0) for p in trabajo["steps"])
    comprobar("capturas.yml: 7:21 y 19:21, a mano y con peticiones/capturas.json (solo en main); solo lectura; uno detrás "
              "de otro; y los topes de los pasos caben con margen en el del trabajo (así «Guardar» nunca se queda a medias)",
              on["schedule"] == [{"cron": "21 7,19 * * *"}]
              and on["push"] == {"branches": ["main"], "paths": ["peticiones/capturas.json"]}
              and "workflow_dispatch" in on and w["permissions"] == {"contents": "read"}
              and w["concurrency"] == {"group": "capturas", "cancel-in-progress": False}
              and all(p.get("timeout-minutes") for p in trabajo["steps"] if p.get("run"))
              and pasos + 5 <= trabajo["timeout-minutes"])
    simulacro = open(os.path.join(RAIZ, ".github", "workflows", "simulacro.yml"), encoding="utf-8").read()
    comprobar("y GitHub pasa estos simulacros (los del Investigador y de su caja) en cada cambio",
              "python pruebas/simulacro_capturas.py" in simulacro and "python pruebas/simulacro_caja.py" in simulacro)
    comprobar("la llave solo en «Elegir» y «Guardar», sin credenciales guardadas, sin artefactos, caché ni resumen",
              not fuera and all((p.get("with") or {}).get("persist-credentials") is False for p in trabajo["steps"]
                                if str(p.get("uses", "")).startswith("actions/checkout"))
              and not any(x in texto for x in ("upload-artifact", "actions/cache", "GITHUB_STEP_SUMMARY",
                                               "GITHUB_TOKEN", "github.token")))
else:
    print("(sin PyYAML en esta máquina: no se mira capturas.yml)")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nSimulacro de la caja del Investigador: {'TODO BIEN' if not FALLOS[0] else f'{FALLOS[0]} FALLO(S)'}")
sys.exit(1 if FALLOS[0] else 0)
