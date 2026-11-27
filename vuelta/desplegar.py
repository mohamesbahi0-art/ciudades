"""Despliega el Buzón de vuelta del «Panel de cifras» en Cloudflare Pages (gratis) y apunta sus direcciones.

Lo lanza GitHub Actions (.github/workflows/vuelta.yml):
  python vuelta/desplegar.py desplegar
      Elige la llave de Cloudflare que vale (CLOUDFLARE_AI_TOKEN y, si no tiene permiso de Pages y KV,
      CLOUDFLARE_PAGES_TOKEN), crea el proyecto de Pages y el KV si no existen, crea VUELTA_LLAVE la primera vez (y la
      guarda en GitHub con GH_SECRETOS), la pone como secreto del proyecto, despliega y hace una prueba de ida y vuelta
      con el buzón ya publicado. Deja la dirección del buzón en VUELTA_WEB (GITHUB_ENV) para los pasos siguientes.
      Si está IG_APP_SECRET, también lo pone como secreto del proyecto, solo para comprobar la firma de los avisos de
      Meta (/meta/baja y /meta/borrado); sin él, los avisos se apuntan sin comprobar (una marca por cuenta).
  python vuelta/desplegar.py apuntar
      Escribe las direcciones en el privado (config/redes.json) y lo guarda (privado.git_guardar).

El registro de Actions es PÚBLICO: solo se imprimen pasos, códigos de estado y la dirección del buzón (neutra y pública
a propósito). Nunca llaves, ids, cuerpos de respuestas ni códigos de permiso.
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
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

with open(os.path.join(AQUI, "wrangler.toml"), "rb") as _f:
    PROYECTO = tomllib.load(_f)["name"]          # el nombre vive solo en wrangler.toml
KV_TITULO = f"{PROYECTO}-buzon"
ID_FALSO = "ID_DEL_KV"                           # lo que pone wrangler.toml en lugar del id de verdad
VERSION_META = "v26.0"
API = "https://api.cloudflare.com/client/v4"
COPIAR = ["public", "functions", "lib", "wrangler.toml", "package.json"]
RUTAS = {"vuelta_web": "", "vuelta_instagram": "/vuelta/instagram", "recoger": "/recoger",
         "privacidad": "/privacidad", "condiciones": "/condiciones", "borrado": "/borrado",
         "meta_baja": "/meta/baja", "meta_borrado": "/meta/borrado", "icono": "/icono.png"}
FALTA_PERMISO = "falta permiso de Cloudflare Pages"
COMO_ARREGLARLO = ("Hay que crear en Cloudflare (Mi perfil > Tokens de API) una llave con «Cloudflare Pages: Editar» y "
                   "«Workers KV Storage: Editar» y guardarla en GitHub como CLOUDFLARE_PAGES_TOKEN.")
OCULTOS = []                                     # valores que nunca deben salir en el registro


class Parada(Exception):
    """Algo impide seguir: el mensaje se puede enseñar en el registro público."""


def ocultar(valor):
    """Pide a GitHub que tape el valor en el registro, nada más tenerlo."""
    if valor and valor not in OCULTOS:
        OCULTOS.append(valor)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{valor}", flush=True)


def limpio(texto, lineas=15):
    """Las últimas líneas de una salida, con llaves, ids y cosas que parezcan ids tapadas."""
    for valor in OCULTOS:
        texto = texto.replace(valor, "***")
    texto = re.sub(r"\b[0-9a-f]{32}\b", "***", texto)
    return "\n".join(texto.strip().splitlines()[-lineas:])


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
    for nombre in ("CLOUDFLARE_AI_TOKEN", "CLOUDFLARE_PAGES_TOKEN"):
        token = os.environ.get(nombre, "").strip()
        if not token:
            print(f"{nombre}: no está.")
            continue
        ocultar(token)
        falta = falta_permiso(token, cuenta)
        if not falta:
            print(f"Uso {nombre}.")
            return token
        print(f"{nombre} no tiene permiso de Cloudflare {falta[0]} (código {falta[1]}).")
    raise Parada(f"{FALTA_PERMISO}. {COMO_ARREGLARLO}")


def comprobar(codigo, que):
    if codigo in (401, 403):
        raise Parada(f"{FALTA_PERMISO} ({que}: código {codigo}). {COMO_ARREGLARLO}")
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
    """Devuelve el id del KV del buzón, creándolo si no existe. El id se tapa en el registro."""
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


def carpeta_de_despliegue(id_kv):
    """Copia de vuelta/ con el id de verdad del KV en wrangler.toml (el del repositorio nunca lo lleva)."""
    destino = tempfile.mkdtemp(prefix="vuelta-")
    for parte in COPIAR:
        origen = os.path.join(AQUI, parte)
        if os.path.isdir(origen):
            shutil.copytree(origen, os.path.join(destino, parte))
        else:
            shutil.copy2(origen, destino)
    ruta = os.path.join(destino, "wrangler.toml")
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    if f'"{ID_FALSO}"' not in texto:
        raise Parada("wrangler.toml no tiene el hueco del id del KV.")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto.replace(f'"{ID_FALSO}"', f'"{id_kv}"'))
    return destino


# --- La llave del buzón ---
def llave_del_buzon():
    """VUELTA_LLAVE: la de GitHub si ya existe; si no, una nueva que se guarda en GitHub antes de tocar Cloudflare
    (así nunca quedan distintas)."""
    llave = os.environ.get("VUELTA_LLAVE", "").strip()
    if llave:
        ocultar(llave)
        return llave
    llave = secrets.token_urlsafe(32)
    ocultar(llave)
    gh = os.environ.get("GH_SECRETOS", "").strip()
    if not gh:
        raise Parada("Falta el secreto GH_SECRETOS para guardar VUELTA_LLAVE en GitHub.")
    import secretos                              # herramientas/secretos.py (necesita pynacl)
    try:
        secretos.guardar_secreto("VUELTA_LLAVE", llave, gh)
    except urllib.error.HTTPError as e:
        raise Parada(f"No pude guardar VUELTA_LLAVE en GitHub (código {e.code}).") from None
    print("VUELTA_LLAVE nueva guardada en GitHub.")
    return llave


# --- wrangler ---
def wrangler(argumentos, token, cuenta, carpeta, entrada=None):
    """Lanza wrangler con lo justo en el entorno (sin GH_SECRETOS ni las otras llaves). Devuelve (bien, salida limpia)."""
    entorno = {k: v for k, v in os.environ.items()
               if k not in ("GH_SECRETOS", "VUELTA_LLAVE", "CLOUDFLARE_AI_TOKEN", "CLOUDFLARE_PAGES_TOKEN",
                            "IG_APP_SECRET", "IG_APP_ID")}
    entorno.update(CLOUDFLARE_API_TOKEN=token, CLOUDFLARE_ACCOUNT_ID=cuenta, WRANGLER_SEND_METRICS="false", CI="true")
    r = subprocess.run(["wrangler", *argumentos], cwd=carpeta, env=entorno, input=entrada, text=True,
                       capture_output=True, timeout=600)
    salida = (r.stdout or "") + "\n" + (r.stderr or "")
    if r.returncode != 0 and re.search(r"Authentication error|code: 10000|\b403\b", salida):
        raise Parada(f"{FALTA_PERMISO} (wrangler {argumentos[1]}). {COMO_ARREGLARLO}")
    return r.returncode == 0, limpio(salida)


def poner_llave(token, cuenta, carpeta, llave):
    bien, salida = wrangler(["pages", "secret", "put", "VUELTA_LLAVE", "--project-name", PROYECTO],
                            token, cuenta, carpeta, entrada=llave)
    if not bien:
        print(salida)
        raise Parada("No pude poner VUELTA_LLAVE en Cloudflare.")
    print("VUELTA_LLAVE puesta en Cloudflare.")


def poner_secreto_app(token, cuenta, carpeta):
    """IG_APP_SECRET como secreto del proyecto, solo para comprobar la firma de los avisos de Meta. Si aún no está
    en GitHub, el buzón funciona igual y los avisos se apuntan sin comprobar (el turno de Instagram los confirma con la
    API antes de borrar nada)."""
    secreto = os.environ.get("IG_APP_SECRET", "").strip()
    if not secreto:
        print("Sin IG_APP_SECRET: los avisos de Meta se apuntan sin comprobar su firma. Cuando esté, lanza otra vez "
              "este turno a mano.")
        return
    ocultar(secreto)
    bien, salida = wrangler(["pages", "secret", "put", "IG_APP_SECRET", "--project-name", PROYECTO],
                            token, cuenta, carpeta, entrada=secreto)
    if not bien:
        print(salida)
        raise Parada("No pude poner IG_APP_SECRET en Cloudflare.")
    print("IG_APP_SECRET puesto en Cloudflare: el buzón comprueba la firma de los avisos de Meta.")


def publicar(token, cuenta, carpeta):
    bien, salida = wrangler(["pages", "deploy", "public", "--project-name", PROYECTO, "--branch", "main",
                             "--commit-dirty=true"], token, cuenta, carpeta)
    print(salida)
    if not bien:
        raise Parada("El despliegue ha fallado.")
    print("Buzón desplegado.")


# --- Prueba de ida y vuelta ---
class _SinSaltos(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None                                # una redirección cuenta como fallo: no se sigue


def pedir(url, cabeceras=None):
    """GET sin seguir redirecciones. Devuelve (código, texto); 0 si no hay conexión."""
    abrir = urllib.request.build_opener(_SinSaltos)
    try:
        with abrir.open(urllib.request.Request(url, headers=cabeceras or {}), timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return 0, ""


def esperar_web(web, intentos=40, pausa=15):
    """La primera vez, la dirección pages.dev tarda unos minutos en funcionar."""
    codigo = 0
    for _ in range(intentos):
        codigo, _texto = pedir(f"{web}/vuelta/instagram")
        if codigo == 200:
            return
        time.sleep(pausa)
    raise Parada(f"El buzón no contesta (código {codigo}).")


def probar(web, llave, pausa=5):
    """Deja en el buzón una respuesta de prueba (un «error» inventado, nunca un código de verdad) y la recoge con la
    llave, como hará el turno de conectar. Así se sabe que el KV, la llave y las rutas funcionan."""
    esperar_web(web)
    estado = "prueba" + secrets.token_urlsafe(18)
    codigo, texto = pedir(f"{web}/vuelta/instagram?" + urllib.parse.urlencode({"state": estado,
                                                                              "error": "prueba_del_turno"}))
    if codigo != 200 or "Listo" not in texto:
        raise Parada(f"La vuelta de prueba no ha ido bien (código {codigo}).")
    codigo, _texto = pedir(f"{web}/recoger?state={estado}")
    if codigo != 401:
        raise Parada(f"/recoger sin llave debería decir que no (código {codigo}).")
    for _ in range(24):                            # el KV puede tardar hasta un minuto en verlo
        codigo, texto = pedir(f"{web}/recoger?state={estado}", {"Authorization": f"Bearer {llave}"})
        if codigo != 404:
            break
        time.sleep(pausa)
    try:
        datos = json.loads(texto) if codigo == 200 else {}
    except ValueError:
        datos = {}
    if datos.get("red") != "instagram" or datos.get("error") != "prueba_del_turno" or datos.get("code"):
        raise Parada(f"La recogida de prueba no ha ido bien (código {codigo}).")
    print("Prueba de ida y vuelta: bien.")


def dejar_para_los_pasos_siguientes(web):
    ruta = os.environ.get("GITHUB_ENV")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"VUELTA_WEB={web}\n")


def desplegar():
    cuenta = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not cuenta:
        raise Parada("Falta el secreto CLOUDFLARE_ACCOUNT_ID.")
    ocultar(cuenta)
    token = elegir_token(cuenta)
    web = proyecto(token, cuenta)
    carpeta = carpeta_de_despliegue(kv(token, cuenta))
    try:
        llave = llave_del_buzon()
        poner_llave(token, cuenta, carpeta, llave)
        poner_secreto_app(token, cuenta, carpeta)
        publicar(token, cuenta, carpeta)
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)
    dejar_para_los_pasos_siguientes(web)
    probar(web, llave)
    print(f"Buzón de vuelta: {web}")


# --- Apuntar en el privado ---
def direcciones(web):
    web = web.rstrip("/")
    return {k: web + ruta for k, ruta in RUTAS.items()}


def apuntar():
    from bots.comun import privado
    web = os.environ.get("VUELTA_WEB", "").strip()
    if not re.fullmatch(r"https://[a-z0-9.-]+\.pages\.dev", web):
        raise Parada("No sé la dirección del buzón (VUELTA_WEB).")
    ruta = os.path.join("config", "redes.json")
    antes = privado.leer(ruta, {}) or {}
    nuevo = dict(antes, **direcciones(web), proyecto=PROYECTO)
    nuevo.setdefault("version_meta", VERSION_META)
    if {k: v for k, v in nuevo.items() if k != "actualizado"} == {k: v for k, v in antes.items() if k != "actualizado"}:
        print("Las direcciones ya estaban apuntadas.")
        return
    nuevo["actualizado"] = privado.ahora()
    privado.escribir(ruta, nuevo)
    if not privado.git_guardar("buzón de vuelta: direcciones"):
        raise Parada("No pude guardar las direcciones en el privado.")
    print("Direcciones apuntadas en el privado (config/redes.json).")


def main():
    orden = sys.argv[1] if len(sys.argv) > 1 else ""
    acciones = {"desplegar": desplegar, "apuntar": apuntar}
    if orden not in acciones:
        print("Uso: python vuelta/desplegar.py desplegar|apuntar")
        return 2
    try:
        acciones[orden]()
    except Parada as e:
        print(f"::error::{e}" if os.environ.get("GITHUB_ACTIONS") == "true" else str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
