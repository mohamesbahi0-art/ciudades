"""Despliega el portero de la app (panel/) en Cloudflare Pages (gratis), con la app del repositorio privado dentro.

Lo lanza GitHub Actions (.github/workflows/panel.yml):
  python panel/desplegar.py desplegar
      Mira que estén las llaves (CLOUDFLARE_PAGES_TOKEN o una CLOUDFLARE_AI_TOKEN que valga para Pages y KV,
      CLOUDFLARE_ACCOUNT_ID, PANEL_GH_TOKEN y PANEL_CLAVE). Si falta alguna, avisa y termina BIEN (sin romper nada):
      el siguiente paso apunta en el privado {estado: "faltan_llaves", faltan: [...]}.
      Si están: crea el proyecto de Pages y su KV si no existen, crea PANEL_FIRMA la primera vez (y la guarda en GitHub
      con GH_SECRETOS), pone PANEL_GH_TOKEN, PANEL_CLAVE y PANEL_FIRMA como secretos del proyecto, monta en una carpeta
      aparte lo que se despliega (el portero + la app de privado/app/panel, que llega en PANEL_APP; sin app, la página
      «la app nueva todavía no está»), despliega con wrangler y comprueba que /entrar da 200 y /api/yo da 401.
  python panel/desplegar.py apuntar
      Escribe estado/app/panel.json en el privado (estado, dirección, proyecto, qué app lleva) y lo guarda.

El registro de Actions es PÚBLICO: solo se imprimen pasos y códigos de estado. Nunca llaves, ids, el dueño, cuerpos de
respuestas ni la dirección (esa queda en el privado).
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

with open(os.path.join(AQUI, "wrangler.toml"), "rb") as _f:
    PROYECTO = tomllib.load(_f)["name"]          # el nombre vive solo en wrangler.toml
KV_TITULO = f"{PROYECTO}-kv"
ID_FALSO = "ID_DEL_KV"                           # lo que pone wrangler.toml en lugar del id de verdad
API = "https://api.cloudflare.com/client/v4"
COPIAR = ["functions", "lib", "wrangler.toml", "package.json"]
# lo de la app que nunca se despliega: podría saltarse el portero o no pinta nada en la web
NO_COPIAR = shutil.ignore_patterns("_worker.js", "_routes.json", "functions", ".git", "*.md", "__pycache__")
FALTA_PERMISO = "falta permiso de Cloudflare Pages"
PARA_CASA = "está en Para casa, «La app sin Claude»"
SECRETOS_PAGES = ("PANEL_GH_TOKEN", "PANEL_CLAVE", "PANEL_FIRMA")
NOMBRE_VALIDO = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
OCULTOS = []                                     # valores que nunca deben salir en el registro
EN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


class Parada(Exception):
    """Algo impide seguir: el mensaje se puede enseñar en el registro público."""


class Faltan(Exception):
    """Faltan llaves: no es un fallo, se avisa y se termina bien."""

    def __init__(self, faltan):
        super().__init__(", ".join(faltan))
        self.faltan = faltan


def ocultar(valor):
    """Pide a GitHub que tape el valor en el registro, nada más tenerlo."""
    if valor and valor not in OCULTOS:
        OCULTOS.append(valor)
        if EN_ACTIONS:
            print(f"::add-mask::{valor}", flush=True)


def limpio(texto, lineas=15):
    """Las últimas líneas de una salida, con llaves, ids, direcciones y cosas que parezcan ids tapadas."""
    for valor in OCULTOS:
        texto = texto.replace(valor, "***")
    texto = re.sub(r"\b[0-9a-f]{32}\b", "***", texto)
    texto = re.sub(r"https://[A-Za-z0-9.-]+\.pages\.dev\S*", "https://***.pages.dev", texto)
    return "\n".join(texto.strip().splitlines()[-lineas:])


def aviso(texto):
    print(f"::warning::{texto}" if EN_ACTIONS else texto, flush=True)


def para_los_pasos_siguientes(**valores):
    ruta = os.environ.get("GITHUB_ENV")
    if not ruta:
        return
    with open(ruta, "a", encoding="utf-8") as f:
        for k, v in valores.items():
            f.write(f"{k}={v}\n")


# --- Las llaves ---
def faltan_llaves():
    """Las llaves que faltan en GitHub (solo mira si están; si valen se ve después)."""
    faltan = []
    if not any(os.environ.get(n, "").strip() for n in ("CLOUDFLARE_PAGES_TOKEN", "CLOUDFLARE_AI_TOKEN")):
        faltan.append("CLOUDFLARE_PAGES_TOKEN")
    for nombre in ("CLOUDFLARE_ACCOUNT_ID", "PANEL_GH_TOKEN", "PANEL_CLAVE"):
        if not os.environ.get(nombre, "").strip():
            faltan.append(nombre)
    return faltan


# --- Cloudflare ---
def cf(metodo, ruta, token, datos=None):
    """Llama a la API de Cloudflare. Devuelve (código HTTP, respuesta). No imprime nada."""
    req = urllib.request.Request(f"{API}{ruta}", method=metodo,
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {}
    except urllib.error.URLError:
        return 0, {}


def falta_permiso(token, cuenta):
    """None si la llave puede con Pages y con KV; si no, (qué le falta, código)."""
    for que, ruta in (("Pages", "pages/projects"), ("Workers KV", "storage/kv/namespaces")):
        codigo, _ = cf("GET", f"/accounts/{cuenta}/{ruta}", token)
        if codigo != 200:
            return que, codigo
    return None


def elegir_token(cuenta):
    """La primera llave de Cloudflare que puede con Pages y KV. Si ninguna puede, faltan llaves (no es un fallo)."""
    for nombre in ("CLOUDFLARE_PAGES_TOKEN", "CLOUDFLARE_AI_TOKEN"):
        token = os.environ.get(nombre, "").strip()
        if not token:
            continue
        ocultar(token)
        falta = falta_permiso(token, cuenta)
        if not falta:
            print(f"Uso {nombre}.")
            return token
        print(f"{nombre} no tiene permiso de Cloudflare {falta[0]} (código {falta[1]}).")
    raise Faltan(["CLOUDFLARE_PAGES_TOKEN"])


def comprobar(codigo, que):
    if codigo in (401, 403):
        raise Parada(f"{FALTA_PERMISO} ({que}: código {codigo}).")
    if codigo != 200:
        raise Parada(f"Cloudflare no deja {que} (código {codigo}).")


def proyecto(token, cuenta):
    """Crea el proyecto de Pages si no existe y devuelve su dirección (pages.dev puede añadirle letras si el nombre
    ya lo tiene otra persona: por eso se lee de Cloudflare)."""
    codigo, r = cf("GET", f"/accounts/{cuenta}/pages/projects/{PROYECTO}", token)
    if codigo == 404:
        codigo, r = cf("POST", f"/accounts/{cuenta}/pages/projects", token,
                       {"name": PROYECTO, "production_branch": "main"})
        comprobar(codigo, "crear el proyecto de Pages")
        print("Proyecto de Pages creado.")
    else:
        comprobar(codigo, "leer el proyecto de Pages")
        print("El proyecto de Pages ya existía.")
    sub = (r.get("result") or {}).get("subdomain") or f"{PROYECTO}.pages.dev"
    return f"https://{sub}"


def kv(token, cuenta):
    """Devuelve el id del KV del portero, creándolo si no existe. El id se tapa en el registro."""
    for pagina in range(1, 11):
        codigo, r = cf("GET", f"/accounts/{cuenta}/storage/kv/namespaces?per_page=100&page={pagina}", token)
        comprobar(codigo, "leer los KV")
        lote = r.get("result") or []
        for ns in lote:
            if ns.get("title") == KV_TITULO:
                ocultar(ns["id"])
                print("El KV ya existía.")
                return ns["id"]
        if len(lote) < 100:
            break
    codigo, r = cf("POST", f"/accounts/{cuenta}/storage/kv/namespaces", token, {"title": KV_TITULO})
    comprobar(codigo, "crear el KV")
    ocultar(r["result"]["id"])
    print("KV creado.")
    return r["result"]["id"]


# --- Lo que se despliega ---
def variables():
    """Quién es el dueño y cómo se llaman los repositorios: del entorno de GitHub Actions, nunca escritos a mano."""
    dueno = os.environ.get("PANEL_DUENO") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    publico = os.environ.get("PANEL_PUBLICO") or os.environ.get("GITHUB_REPOSITORY", "").partition("/")[2]
    privado = os.environ.get("PANEL_PRIVADO") or "ciudades-memoria"
    for que, valor in (("el dueño", dueno), ("el repositorio público", publico), ("el privado", privado)):
        if not NOMBRE_VALIDO.match(valor or ""):
            raise Parada(f"No sé {que} (GITHUB_REPOSITORY_OWNER / GITHUB_REPOSITORY / PANEL_PRIVADO).")
    return {"PANEL_DUENO": dueno, "PANEL_PRIVADO": privado, "PANEL_PUBLICO": publico}


def copiar_app(app, public):
    """La app del privado (app/panel/) en public/. Devuelve "propia" o "espera" (sin app: la página de espera)."""
    tipo = "espera"
    if app and os.path.isdir(app) and os.listdir(app):
        shutil.copytree(app, public, ignore=NO_COPIAR, dirs_exist_ok=True)
        if not os.path.exists(os.path.join(public, "index.html")) and os.path.exists(os.path.join(public, "torre.html")):
            shutil.copy2(os.path.join(public, "torre.html"), os.path.join(public, "index.html"))
        if os.path.exists(os.path.join(public, "index.html")):
            tipo = "propia"
    # lo del portero va encima: la página de entrar es siempre la suya
    shutil.copytree(os.path.join(AQUI, "public"), public, dirs_exist_ok=True)
    if tipo == "espera":
        shutil.copy2(os.path.join(AQUI, "public", "espera.html"), os.path.join(public, "index.html"))
    return tipo


def carpeta_de_despliegue(id_kv, app):
    """Una carpeta aparte (fuera del repositorio) con el portero, la app y el wrangler.toml con el id de verdad del
    KV y las variables. El wrangler.toml del repositorio nunca lleva nada de eso."""
    destino = tempfile.mkdtemp(prefix="panel-")
    for parte in COPIAR:
        origen = os.path.join(AQUI, parte)
        if os.path.isdir(origen):
            shutil.copytree(origen, os.path.join(destino, parte))
        else:
            shutil.copy2(origen, destino)
    tipo = copiar_app(app, os.path.join(destino, "public"))
    ruta = os.path.join(destino, "wrangler.toml")
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    if f'"{ID_FALSO}"' not in texto or "[vars]" in texto:
        raise Parada("wrangler.toml no tiene el hueco del id del KV (o ya trae [vars]).")
    texto = texto.replace(f'"{ID_FALSO}"', f'"{id_kv}"')
    texto += "\n[vars]\n" + "".join(f'{k} = "{v}"\n' for k, v in variables().items())
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return destino, tipo


# --- PANEL_FIRMA ---
def llave_de_firma():
    """PANEL_FIRMA: la de GitHub si ya existe; si no, una nueva que se guarda en GitHub antes de tocar Cloudflare
    (así nunca quedan distintas)."""
    firma = os.environ.get("PANEL_FIRMA", "").strip()
    if firma:
        ocultar(firma)
        return firma
    firma = secrets.token_urlsafe(48)
    ocultar(firma)
    gh = os.environ.get("GH_SECRETOS", "").strip()
    if not gh:
        raise Parada("Falta el secreto GH_SECRETOS para guardar PANEL_FIRMA en GitHub.")
    import secretos                              # herramientas/secretos.py (necesita pynacl)
    try:
        secretos.guardar_secreto("PANEL_FIRMA", firma, gh)
    except urllib.error.HTTPError as e:
        raise Parada(f"No pude guardar PANEL_FIRMA en GitHub (código {e.code}).") from None
    except urllib.error.URLError:
        raise Parada("No pude guardar PANEL_FIRMA en GitHub (sin conexión).") from None
    print("PANEL_FIRMA nueva guardada en GitHub.")
    return firma


# --- wrangler ---
QUITAR_DEL_ENTORNO = ("GH_SECRETOS", "CLOUDFLARE_AI_TOKEN", "CLOUDFLARE_PAGES_TOKEN", *SECRETOS_PAGES)


def wrangler(argumentos, token, cuenta, carpeta, entrada=None):
    """Lanza wrangler con lo justo en el entorno (sin GH_SECRETOS ni las llaves). Devuelve (bien, salida limpia)."""
    entorno = {k: v for k, v in os.environ.items() if k not in QUITAR_DEL_ENTORNO}
    entorno.update(CLOUDFLARE_API_TOKEN=token, CLOUDFLARE_ACCOUNT_ID=cuenta, WRANGLER_SEND_METRICS="false", CI="true")
    r = subprocess.run(["wrangler", *argumentos], cwd=carpeta, env=entorno, input=entrada, text=True,
                       capture_output=True, timeout=600)
    salida = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 and re.search(r"Authentication error|code: 10000|\b403\b", salida):
        raise Parada(f"{FALTA_PERMISO} (wrangler {argumentos[1]}).")
    return r.returncode == 0, limpio(salida)


def poner_secretos(token, cuenta, carpeta, valores):
    for nombre in SECRETOS_PAGES:
        bien, salida = wrangler(["pages", "secret", "put", nombre, "--project-name", PROYECTO],
                                token, cuenta, carpeta, entrada=valores[nombre])
        if not bien:
            print(salida)
            raise Parada(f"No pude poner {nombre} en Cloudflare.")
        print(f"{nombre} puesto en Cloudflare.")


def publicar(token, cuenta, carpeta):
    bien, salida = wrangler(["pages", "deploy", "public", "--project-name", PROYECTO, "--branch", "main",
                             "--commit-dirty=true"], token, cuenta, carpeta)
    print(salida)
    if not bien:
        raise Parada("El despliegue ha fallado.")
    print("Portero desplegado.")


# --- Comprobar ---
class _SinSaltos(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None                                # las redirecciones no se siguen: se miran


def pedir(url):
    """GET sin seguir redirecciones. Devuelve (código, cabeceras); 0 si no hay conexión."""
    abrir = urllib.request.build_opener(_SinSaltos)
    try:
        with abrir.open(urllib.request.Request(url, headers={"User-Agent": "panel-fabrica"}), timeout=30) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {})
    except (urllib.error.URLError, TimeoutError):
        return 0, {}


def probar(web, intentos=40, pausa=15):
    """La primera vez, la dirección pages.dev tarda unos minutos en funcionar."""
    codigo = 0
    for _ in range(intentos):
        codigo, _cab = pedir(f"{web}/entrar")
        if codigo == 200:
            break
        time.sleep(pausa)
    print(f"/entrar: {codigo}")
    if codigo != 200:
        raise Parada(f"La página de entrar no contesta (código {codigo}).")
    codigo, _cab = pedir(f"{web}/api/yo")
    print(f"/api/yo sin sesión: {codigo}")
    if codigo != 401:
        raise Parada(f"/api/yo sin sesión debería decir que no (código {codigo}).")
    codigo, cab = pedir(f"{web}/")
    destino = {k.lower(): v for k, v in cab.items()}.get("location", "")
    print(f"/ sin sesión: {codigo} → {'/entrar' if destino.endswith('/entrar') else 'otro sitio'}")
    if codigo != 302 or not destino.endswith("/entrar"):
        raise Parada(f"La app sin sesión debería mandar a /entrar (código {codigo}).")
    print("Prueba sin sesión: bien.")


def desplegar():
    faltan = faltan_llaves()
    if faltan:
        raise Faltan(faltan)
    cuenta = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
    ocultar(cuenta)
    for nombre in ("PANEL_GH_TOKEN", "PANEL_CLAVE"):
        ocultar(os.environ[nombre].strip())
    token = elegir_token(cuenta)
    web = proyecto(token, cuenta)
    ocultar(web.removeprefix("https://"))
    carpeta, tipo = carpeta_de_despliegue(kv(token, cuenta), os.environ.get("PANEL_APP", ""))
    print("Con la app del privado." if tipo == "propia" else "Sin app en el privado: va la página de espera.")
    try:
        valores = {"PANEL_GH_TOKEN": os.environ["PANEL_GH_TOKEN"].strip(),
                   "PANEL_CLAVE": os.environ["PANEL_CLAVE"].strip(), "PANEL_FIRMA": llave_de_firma()}
        poner_secretos(token, cuenta, carpeta, valores)
        publicar(token, cuenta, carpeta)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    probar(web)
    para_los_pasos_siguientes(PANEL_ESTADO="listo", PANEL_WEB=web, PANEL_TIPO=tipo)


# --- Apuntar en el privado ---
def apuntar():
    from bots.comun import privado
    estado = os.environ.get("PANEL_ESTADO", "").strip()
    ruta = os.path.join("estado", "app", "panel.json")
    antes = privado.leer(ruta, {}) or {}
    if estado == "faltan_llaves":
        faltan = [x for x in os.environ.get("PANEL_FALTAN", "").split(",") if x]
        nuevo = {k: v for k, v in antes.items() if k in ("web", "proyecto")}
        nuevo.update(estado="faltan_llaves", faltan=faltan,
                     aviso="Faltan llaves de la app sin Claude: están en Para casa («La app sin Claude»).")
    elif estado == "listo":
        web = os.environ.get("PANEL_WEB", "").strip()
        if not re.fullmatch(r"https://[a-z0-9.-]+\.pages\.dev", web):
            raise Parada("No sé la dirección del portero (PANEL_WEB).")
        nuevo = {"estado": "listo", "web": web, "entrar": web + "/entrar", "proyecto": PROYECTO,
                 "app": os.environ.get("PANEL_TIPO", "espera")}
    else:
        print("No hay nada que apuntar (el despliegue no terminó).")
        return
    if {k: v for k, v in nuevo.items() if k != "actualizado"} == {k: v for k, v in antes.items() if k != "actualizado"}:
        print("Ya estaba apuntado.")
        return
    nuevo["actualizado"] = privado.ahora()
    privado.escribir(ruta, nuevo)
    if not privado.git_guardar("portero de la app: estado"):
        raise Parada("No pude guardar el estado en el privado.")
    print("Apuntado en el privado (estado/app/panel.json).")


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    acciones = {"desplegar": desplegar, "apuntar": apuntar}
    if orden not in acciones:
        print("Uso: python panel/desplegar.py desplegar|apuntar")
        return 2
    try:
        acciones[orden]()
    except Faltan as e:
        for nombre in e.faltan:
            donde = PARA_CASA if nombre != "CLOUDFLARE_ACCOUNT_ID" else "es el número de la cuenta de Cloudflare"
            aviso(f"Falta la llave {nombre} ({donde}). Cuando esté, la app nueva se enciende sola en la siguiente "
                  "vuelta de este turno (una al día).")
        para_los_pasos_siguientes(PANEL_ESTADO="faltan_llaves", PANEL_FALTAN=",".join(e.faltan))
        return 0
    except Parada as e:
        print(f"::error::{e}" if EN_ACTIONS else str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
