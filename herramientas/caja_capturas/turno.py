"""El turno del Investigador de webs (.github/workflows/capturas.yml), en la máquina de GitHub, por pasos:

  elegir     Con la llave GH_SECRETOS: saca del repositorio privado SOLO la cola y lo justo, pide a capturas.py el
             siguiente pedido, tapa la web en el registro, guarda «en_curso» (y el intento) ANTES de capturar y borra
             la copia privada. Con peticiones/capturas.json {"probar": true}, una web de práctica fija, sin pedido en
             la cola pero gastando del tope del día y de la semana como cualquier captura (y apuntado antes).
  preparar   Sin llaves: construye las dos imágenes (Dockerfile), cierra la red (iptables) y arranca el filtro.
  capturar   Sin llaves: lanza la caja desechable (docker run --rm, sin variables ni montajes del checkout; su juez,
             root sin más poderes que cambiar de usuario y parar procesos, es el único que escribe en /salida) y
             revisa lo que deja: que la caja acabara por sí misma, que sea un fichero normal y, con el registro del
             filtro (que la IA no alcanza), que no hablara con webs vetadas, de captchas o con un nombre cambiado.
  desmontar  Quita la caja, el filtro y sus redes, y comprueba que no queda ningún contenedor vivo.
  guardar    Con la llave, y solo si no queda nada vivo de la caja: otra copia del privado, capturas.py guardar y
             git_guardar. La prueba se guarda en estado/capturas/prueba.json, sin tocar la cola.

La llave nunca toca el disco: va en una cabecera de git por variables de entorno de este proceso (como hace
actions/checkout por dentro) y se tapa en el registro. El registro de Actions es PÚBLICO: aquí solo salen «cap-N» y
cifras; lo de capturas.py, git y docker va a ficheros de la máquina (la copia privada se borra; la máquina se tira).
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
import caja  # noqa: E402  (constantes y limpieza compartidas con lo de dentro de la caja)

CAJA = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "caja-capturas")
ENTRADA, SALIDA, LIMPIO = (os.path.join(CAJA, n) for n in ("entrada", "salida", "limpio"))
LISTAS, REGISTROS = os.path.join(CAJA, "listas"), os.path.join(CAJA, "registros")   # LISTAS: lo que lee el filtro
TURNO, EXTRA, VETOS = (os.path.join(CAJA, n) for n in ("turno.json", "extra.json", "vetos.json"))
PROGRAMA = ("caja_sin_resultado", "error_caja", "filtro_roto", "filtro_caido", "caja_abierta", "llave_en_la_caja",
            "proveedor_extra")
# Las palabras que pueden salir en el registro público como motivo (lo demás sale como «otro»)
MOTIVOS = frozenset(caja.MOTIVOS) | frozenset(PROGRAMA) | {"web_prohibida", "red_trampa"}
CODIGOS_CAJA = (0, 3, 4)          # las salidas de caja.py; con otra (124, 137, 143…) no acabó ella sola: no se lee
CAPTURAS = os.path.join(RAIZ, "bots", "cerebro", "capturas.py")
PETICION = os.path.join(RAIZ, "peticiones", "capturas.json")
# La web de práctica de las pruebas: pública, hecha para aprender a sacar datos y que no pasa por la cola
PRUEBA = {"id": "cap-0", "web": "https://books.toscrape.com/",
          "que": "título, precio y si quedan existencias de los libros de la primera página del catálogo"}
PARCIAL = ["/estado/capturas/", "/config/fabrica.json", "/config/canales.json"]
RED_DENTRO, RED_FUERA = "172.30.99.0/24", "172.30.98.0/24"
PRIVADAS = ["10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16",
            "168.63.129.16/32", "0.0.0.0/8"]
# Lo que la caja nunca puede usar mientras captura (además de capturas.VETADOS): paquetes, código y buscadores
INFRA = ("pypi.org", "pythonhosted.org", "npmjs.org", "npmjs.com", "yarnpkg.com", "bun.sh", "jsr.io", "github.com",
         "githubusercontent.com", "githubassets.com", "ghcr.io", "docker.io", "docker.com", "exa.ai", "localhost",
         "local", "internal", "localdomain", "home.arpa", "lan",
         # los que meten en el nombre la IP que se quiera (1-2-3-4.sslip.io): con ellos se llegaría a cualquier sitio
         "sslip.io", "nip.io", "xip.io", "nip.direct", "traefik.me", "localtest.me", "lvh.me", "1u.ms", "rbndr.us",
         # DNS por https (para preguntar nombres sin pasar por el filtro)
         "cloudflare-dns.com", "dns.google", "dns.quad9.net", "doh.opendns.com", "dns.nextdns.io", "doh.dns.sb",
         # los captchas y retos: ni se cargan ni se pueden resolver
         *caja.DOMINIOS_RETO)
MODELO = ("opencode.ai", "models.opencode.ai", "models.dev")      # los que deja pasar el filtro para el modelo gratis
PREFIJOS = ("login", "signin", "signup", "logon", "account", "accounts", "auth", "oauth", "sso", "id", "secure",
            "passport", "myaccount")
JUEZ = "0:0"                      # el juez de la caja (root, pero con --cap-drop ALL y solo SETUID, SETGID y KILL)


# --- Lo que sale en el registro público: solo «cap-N» y cifras ---
def seguro(texto):
    """Quita enlaces, correos, @ y dominios de una línea antes de enseñarla."""
    return caja.limpiar(texto, 200)


def decir(texto):
    print(seguro(texto), flush=True)


def pasar(log):
    """De lo que ha impreso capturas.py: primero sus máscaras (las tapa el propio GitHub, no se ven) y después solo sus
    líneas «cap-N: …» o «capturas: …», limpias. El resto se queda en el fichero de la máquina."""
    with open(log, encoding="utf-8", errors="replace") as f:
        lineas = [x.rstrip("\n") for x in f]
    for x in lineas:
        if x.startswith("::add-mask::") and "\r" not in x:
            print(x, flush=True)
    otras = 0
    for x in lineas:
        if re.match(r"^(cap-\d{1,6}|capturas): ", x):
            decir(x.strip())
        elif x.strip() and not x.startswith("::add-mask::"):
            otras += 1
    if otras:
        print(f"({otras} líneas más solo en la máquina)", flush=True)


def tapar(web, extra=()):
    """Tapa en el registro la web en todas sus formas (entera, host, dominio, ruta y %-codificada) y los vetados
    privados del dueño. Se hace en cuanto se leen, antes de imprimir nada más."""
    partes = urllib.parse.urlsplit(web)
    host = (partes.hostname or "").lower()
    base = caja.dominio_base(host)
    valores = {web, web.rstrip("/"), host, host.removeprefix("www."), base, urllib.parse.quote(web, safe=""),
               urllib.parse.quote(web, safe="/:"), base.split(".")[0] if len(base.split(".")[0]) >= 5 else ""}
    for forma in (lambda h: h.encode("idna").decode(), lambda h: h.encode().decode("idna")):
        try:
            valores.add(forma(host))
        except UnicodeError:
            pass
    if len(partes.path) >= 6:
        valores |= {partes.path, urllib.parse.quote(partes.path)}
    if partes.query:
        valores.add(partes.query)
    for e in extra:
        valores |= {e, caja.dominio_base(e)}
    for v in sorted((v.strip() for v in valores if v), key=len, reverse=True):
        if len(v) >= 4 and "\n" not in v:
            print(f"::add-mask::{v}", flush=True)


# --- Lo que pasa de un paso a otro (en la máquina, nunca en el registro) ---
def salidas(**valores):
    with open(os.environ.get("GITHUB_OUTPUT") or os.devnull, "a", encoding="utf-8") as f:
        for k, v in valores.items():
            f.write(f"{k}={v}\n")


def leer_salidas(ruta):
    datos = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                if "=" in linea and "<<" not in linea:
                    k, v = linea.rstrip("\n").split("=", 1)
                    datos[k.strip()] = v.strip()
    return datos


def guardar_turno(datos):
    with open(TURNO, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def leer_turno():
    with open(TURNO, encoding="utf-8") as f:
        datos = json.load(f)
    if not caja.ID.fullmatch(str(datos.get("id"))):
        raise SystemExit("cap-?: el turno no tiene un pedido válido")
    return datos


def ejecutar(orden, log, **kwargs):
    os.makedirs(REGISTROS, exist_ok=True)
    with open(os.path.join(REGISTROS, log), "a", encoding="utf-8") as f:
        return subprocess.run(orden, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kwargs).returncode


# --- El repositorio privado, con la llave solo en memoria ---
def poner_llave():
    token = os.environ.pop("GH_SECRETOS", "")
    if not token:
        raise SystemExit("cap-?: falta la llave del repositorio privado")
    cabecera = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    print(f"::add-mask::{cabecera}", flush=True)
    os.environ.update({
        "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {cabecera}", "GIT_CONFIG_KEY_1": "credential.helper",
        "GIT_CONFIG_VALUE_1": "", "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "ciudades-bot", "GIT_AUTHOR_EMAIL": "ciudades-bot@users.noreply.github.com",
        "GIT_COMMITTER_NAME": "ciudades-bot", "GIT_COMMITTER_EMAIL": "ciudades-bot@users.noreply.github.com"})


def url_privado():
    return f"https://github.com/{os.environ.get('GITHUB_REPOSITORY_OWNER', '')}/ciudades-memoria.git"


def sacar_privado(destino, rutas=None):
    """Copia del repositorio privado: entera o solo con `rutas` (sparse-checkout). Sin credenciales en .git/config."""
    shutil.rmtree(destino, ignore_errors=True)
    url = url_privado()
    if not rutas:
        return ejecutar(["git", "clone", "-q", "--depth", "1", url, destino], "git.log") == 0
    pasos = [["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--no-checkout", url, destino],
             ["git", "-C", destino, "sparse-checkout", "set", "--no-cone", *rutas],
             ["git", "-C", destino, "checkout", "-q"]]
    return all(ejecutar(p, "git.log") == 0 for p in pasos)


def git_guardar(destino, mensaje):
    os.environ["PRIVADO"] = destino
    from bots.comun import privado
    return privado.git_guardar(mensaje)


def apuntar_fallo(destino, paso, log):
    """Lo que ha fallado, con detalle, va al repositorio PRIVADO (estado/capturas/fallo_turno.json), nunca aquí."""
    try:
        with open(os.path.join(REGISTROS, log), encoding="utf-8", errors="replace") as f:
            detalle = f.read()[-4000:]
    except OSError:
        detalle = ""
    ruta = os.path.join(destino, "estado", "capturas", "fallo_turno.json")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"paso": paso, "fecha": caja.ahora(), "detalle": detalle}, f, ensure_ascii=False, indent=1)


def correr_capturas(destino, *args, log, salidas_en=None):
    env = dict(os.environ, PRIVADO=destino, MEMORIA_DIR=os.path.join(destino, "memoria"), PYTHONWARNINGS="ignore")
    env.pop("GH_SECRETOS", None)
    if salidas_en:                                # lo que capturas.py deja para GitHub, primero en un fichero nuestro
        env["GITHUB_OUTPUT"] = salidas_en
    return ejecutar([sys.executable, CAPTURAS, *args], log, env=env, cwd=RAIZ)


def leer_extra(destino):
    """Lo que manda el dueño en config/fabrica.json → capturas: (encendido, vetados_extra)."""
    try:
        with open(os.path.join(destino, "config", "fabrica.json"), encoding="utf-8") as f:
            ajustes = json.load(f).get("capturas") or {}
    except (OSError, ValueError, AttributeError):
        ajustes = {}
    extra = [str(x).strip().lower().lstrip(".") for x in ajustes.get("vetados_extra") or [] if str(x).strip()]
    return ajustes.get("encendido"), extra


# --- elegir ---
def es_prueba():
    if os.environ.get("GITHUB_EVENT_NAME") != "push":
        return False
    try:
        with open(PETICION, encoding="utf-8") as f:
            return json.load(f).get("probar") is True
    except (OSError, ValueError, AttributeError):
        return False


def preparar_carpetas():
    shutil.rmtree(CAJA, ignore_errors=True)
    for c in (ENTRADA, LISTAS, REGISTROS):
        os.makedirs(c, mode=0o755)
        os.chmod(c, 0o755)


def reglas_para_la_caja():
    """Las reglas de red que deja capturas.py (vigilante.json), sin los vetados propios del dueño: la caja no los
    necesita (el filtro ya los corta) y lo que ve la IA puede acabar fuera."""
    ruta = os.path.join(ENTRADA, "vigilante.json")
    try:
        with open(ruta, encoding="utf-8") as f:
            reglas = json.load(f)
    except (OSError, ValueError):
        reglas = None
    if os.path.lexists(ruta):
        os.remove(ruta)
    if not isinstance(reglas, dict):
        return
    reglas.pop("vetados", None)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(reglas, f, ensure_ascii=False)
    os.chmod(ruta, 0o644)


def dejar_pedido(pedido, extra, probar):
    with open(os.path.join(ENTRADA, "pedido.json"), "w", encoding="utf-8") as f:
        json.dump({k: pedido[k] for k in ("id", "web", "que")}, f, ensure_ascii=False)
    os.chmod(os.path.join(ENTRADA, "pedido.json"), 0o644)
    reglas_para_la_caja()
    for nombre in os.listdir(ENTRADA):            # la caja solo ve el pedido y sus reglas
        if nombre not in ("pedido.json", "vigilante.json"):
            os.remove(os.path.join(ENTRADA, nombre))
    with open(EXTRA, "w", encoding="utf-8") as f:
        json.dump(extra, f)
    guardar_turno({"id": pedido["id"], "probar": probar})


def gastar_prueba(destino):
    """La prueba es una captura de verdad: gasta del tope del día y de la semana (2 y 5) como las demás. Si ya no queda,
    None; si queda, la apunta en el uso de hoy de la cola (en la copia privada) y devuelve las cifras."""
    os.environ["PRIVADO"] = destino
    from bots.cerebro import capturas
    cola, cfg = capturas.leer_cola(), capturas._config()
    dia, semana = capturas._tope(cfg, "dia"), capturas._tope(cfg, "semana")
    if capturas._uso(cola) >= dia or capturas._uso(cola, 7) >= semana:
        return None
    capturas._sumar_uso(cola)
    capturas.guardar_cola(cola)
    return f"hoy {capturas._uso(cola)}/{dia} · semana {capturas._uso(cola, 7)}/{semana}"


def elegir_prueba(destino):
    if not sacar_privado(destino, ["/config/fabrica.json", "/config/canales.json", "/estado/capturas/"]):
        decir("cap-0: no he podido mirar si el dueño lo tiene encendido")
        return 1
    encendido, extra = leer_extra(destino)
    if encendido is not True:                     # el mismo interruptor que todo lo demás: sin él, ni la prueba
        decir("cap-0: el dueño no lo tiene encendido; no hago la prueba")
        salidas(hay=0)
        return 0
    cifras = gastar_prueba(destino)
    if cifras is None:
        decir("cap-0: tope de capturas alcanzado (el del dueño); no hago la prueba")
        salidas(hay=0)
        return 0
    if not git_guardar(destino, "investigador: prueba de la caja"):    # sin apuntarla antes, no se hace
        decir("cap-0: no he podido apuntar la prueba; la dejo para otro turno")
        salidas(hay=0)
        return 0
    tapar(PRUEBA["web"], extra)
    dejar_pedido(PRUEBA, extra, True)
    salidas(hay=1, id="cap-0")
    decir(f"cap-0: prueba con la web de práctica · {cifras}")
    return 0


def elegir_de_la_cola(destino):
    if not sacar_privado(destino, PARCIAL):
        decir("cap-?: no he podido sacar la cola del repositorio privado")
        return 1
    _, extra = leer_extra(destino)
    fichero = os.path.join(CAJA, "elegir.salidas")
    codigo = correr_capturas(destino, "elegir", "--salida", ENTRADA, log="elegir.log", salidas_en=fichero)
    pedido = leer_pedido_elegido(leer_salidas(fichero))
    if pedido:
        tapar(pedido["web"], extra)
    for e in extra:
        print(f"::add-mask::{e}", flush=True)
    pasar(os.path.join(REGISTROS, "elegir.log"))
    if codigo != 0:
        apuntar_fallo(destino, "elegir", "elegir.log")
        git_guardar(destino, "investigador: fallo al elegir")
        salidas(hay=0)
        decir("cap-?: capturas.py elegir ha fallado (el detalle, en estado/capturas/fallo_turno.json)")
        return 1
    guardado = git_guardar(destino, "investigador: empiezo una captura" if pedido else "investigador: cola al día")
    if not pedido:
        salidas(hay=0)
        return 0
    if not guardado:                              # sin «en_curso» guardado no se captura
        salidas(hay=0)
        decir(f"{pedido['id']}: no he podido apuntar que empieza; lo dejo para el siguiente turno")
        return 0
    dejar_pedido(pedido, extra, False)
    salidas(hay=1, id=pedido["id"])
    return 0


def leer_pedido_elegido(valores):
    if valores.get("hay") != "1" or not caja.ID.fullmatch(valores.get("id", "")):
        return None
    try:
        with open(os.path.join(ENTRADA, "pedido.json"), encoding="utf-8") as f:
            pedido = json.load(f)
    except (OSError, ValueError):
        return None
    web = str(pedido.get("web") or "")
    if pedido.get("id") != valores["id"] or not web.startswith("https://"):
        return None
    return {"id": pedido["id"], "web": web, "que": str(pedido.get("que") or "")}


def elegir():
    preparar_carpetas()
    destino = os.path.join(CAJA, "privado-cola")
    poner_llave()
    try:
        return elegir_prueba(destino) if es_prueba() else elegir_de_la_cola(destino)
    finally:
        shutil.rmtree(destino, ignore_errors=True)    # la copia privada no se queda en el disco mientras se captura


# --- preparar: imágenes, cortafuegos, redes y filtro ---
def _dominio(valor):
    valor = str(valor or "").strip().lower().rstrip(".")
    try:
        return valor.encode("idna").decode() if valor else ""
    except UnicodeError:
        return valor


def listas_del_filtro(normas, extra):
    """Escribe para el filtro listas/vetados.txt (dominios con todos sus subdominios) y listas/vetados_re.txt (hosts
    con una parte de entrar, como login. o accounts., y los que empiezan por una marca prohibida en cualquier país).
    `normas` son las de capturas.py: VETADOS (sufijos; «login.» o «login.*» son prefijos), ENTRADAS, MARCAS,
    MARCAS_ENTERAS y LOCALES."""
    sufijos = set()
    entradas = set(PREFIJOS) | set(normas.get("entradas") or ())
    for valor in list(normas.get("vetados") or ()) + list(INFRA) + list(normas.get("locales") or ()) + list(extra):
        v = _dominio(valor)
        if v.endswith((".*", ".")) and re.fullmatch(r"[a-z0-9-]+\.\*?", v):
            entradas.add(v.split(".")[0])
        elif re.fullmatch(r"\*?\.?[a-z0-9.-]+", v) and v.strip("*."):
            sufijos.add(v.strip("*."))
    def palabras(clave):
        return sorted({m for m in (str(x).lower() for x in normas.get(clave) or ()) if re.fullmatch(r"[a-z0-9-]+", m)})
    marcas, enteras = palabras("marcas"), palabras("enteras")
    entradas = sorted(e for e in entradas if re.fullmatch(r"[a-z0-9-]+", e))
    limpios = sorted(s for s in sufijos if not any(s.endswith("." + o) for o in sufijos if o != s))
    with open(os.path.join(LISTAS, "vetados.txt"), "w", encoding="utf-8") as f:
        f.write("".join(f".{s}\n" for s in limpios))
    with open(os.path.join(LISTAS, "vetados_re.txt"), "w", encoding="utf-8") as f:
        f.write(f"(^|\\.)({'|'.join(entradas)})\\.\n")
        if marcas:                                # la marca y lo que lleve pegado (tiktokcdn, googlevideo…)
            f.write(f"(^|\\.)({'|'.join(marcas)})[a-z0-9-]*\\.\n")
        if enteras:                               # solo la palabra entera o con guion (amazon, amazon-…; no amazonaws)
            f.write(f"(^|\\.)({'|'.join(enteras)})(-[a-z0-9-]*)?\\.\n")
    for nombre in os.listdir(LISTAS):
        os.chmod(os.path.join(LISTAS, nombre), 0o644)
    with open(VETOS, "w", encoding="utf-8") as f:
        json.dump({"sufijos": limpios, "entradas": entradas, "marcas": marcas, "enteras": enteras}, f)
    return limpios


def normas_de_capturas():
    from bots.cerebro import capturas
    return {"vetados": capturas.VETADOS, "entradas": getattr(capturas, "ENTRADAS", ()),
            "marcas": getattr(capturas, "MARCAS", ()), "enteras": getattr(capturas, "MARCAS_ENTERAS", ()),
            "locales": getattr(capturas, "LOCALES", ())}


def leer_lista_extra():
    try:
        with open(EXTRA, encoding="utf-8") as f:
            return [str(x) for x in json.load(f) if x]
    except (OSError, ValueError, TypeError):
        return []


def construir(objetivo, etiqueta):
    orden = ["docker", "build", "--target", objetivo, "-t", etiqueta, AQUI]
    if ejecutar(orden, f"construir-{objetivo}.log") == 0:
        return True
    with open(os.path.join(REGISTROS, f"construir-{objetivo}.log"), encoding="utf-8", errors="replace") as f:
        print("".join(f.readlines()[-40:]), flush=True)    # solo hay cosas públicas: el Dockerfile y las versiones
    return False


def sudo():
    return [] if os.geteuid() == 0 else ["sudo", "-n"]


def cortafuegos():
    """Además del filtro: nada de la red de dentro sale a ningún sitio, y el filtro no llega a la red de la máquina
    (ni a la de Azure ni a 169.254.169.254), salvo para preguntar nombres (DNS)."""
    reglas = [["-s", RED_DENTRO, "!", "-d", RED_DENTRO, "-j", "DROP"]]
    reglas += [["-s", RED_FUERA, "-d", red, "-j", "DROP"] for red in PRIVADAS]
    reglas += [["-s", RED_FUERA, "-p", p, "--dport", "53", "-j", "ACCEPT"] for p in ("udp", "tcp")]
    for regla in reglas:                          # cada una se mete la primera: las de DNS quedan delante
        if ejecutar([*sudo(), "iptables", "-I", "DOCKER-USER", "1", *regla], "cortafuegos.log") != 0:
            return False
    for red in (RED_DENTRO, RED_FUERA):
        if ejecutar([*sudo(), "iptables", "-I", "INPUT", "1", "-s", red, "-j", "DROP"], "cortafuegos.log") != 0:
            return False
    return True


def redes():
    for nombre in ("caja-interna", "caja-salida"):
        ejecutar(["docker", "network", "rm", nombre], "docker.log")
    return (ejecutar(["docker", "network", "create", "--internal", "--subnet", RED_DENTRO, "caja-interna"],
                     "docker.log") == 0
            and ejecutar(["docker", "network", "create", "--subnet", RED_FUERA, "caja-salida"], "docker.log") == 0)


# Lo que dice squid cuando ya escucha. Con ssl-bump en el puerto escribe «Accepting SSL bumped HTTP Socket
# connections» (sin ssl-bump, «Accepting HTTP Socket connections»): la prueba de verdad del 27 nov se quedó esperando
# la frase sin «SSL bumped» y dio el filtro por roto estando bien.
FILTRO_LISTO = re.compile(r"Accepting (?:SSL bumped )?HTTP Socket connections")


def arrancar_filtro():
    orden = ["docker", "run", "-d", "--name", "caja-filtro", "--network", "caja-salida", "--cap-drop", "ALL",
             "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "512m", "--read-only",
             "--tmpfs", "/var/log/squid:rw,mode=1777", "--tmpfs", "/var/spool/squid:rw,mode=1777",
             "--tmpfs", "/tmp:rw,mode=1777", "-v", f"{LISTAS}:/etc/squid/listas:ro", "caja-filtro:turno"]
    conectar = ["docker", "network", "connect", "--ip", caja.FILTRO_IP, "caja-interna", "caja-filtro"]
    if ejecutar(orden, "docker.log") != 0 or ejecutar(conectar, "docker.log") != 0:
        return False
    for _ in range(60):
        r = subprocess.run(["docker", "logs", "caja-filtro"], capture_output=True, text=True)
        if FILTRO_LISTO.search(r.stdout + r.stderr):
            return True
        estado = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", "caja-filtro"],
                                capture_output=True, text=True).stdout.strip()
        if estado == "false":                      # squid se paró (configuración mala): no hace falta esperar más
            break
        time.sleep(1)
    return False


def preparar():
    leer_turno()
    sufijos = listas_del_filtro(normas_de_capturas(), leer_lista_extra())
    pasos = [("la imagen del filtro", lambda: construir("filtro", "caja-filtro:turno")),
             ("la imagen de la caja", lambda: construir("caja", "caja-captura:turno")),
             ("el cortafuegos", cortafuegos), ("las redes", redes), ("el filtro", arrancar_filtro)]
    for nombre, paso in pasos:
        if not paso():
            decir(f"cap: no he podido preparar {nombre}")
            return 1
    decir(f"cap: caja preparada · {len(sufijos)} webs vetadas en el filtro")
    return 0


# --- capturar ---
def salida_del_juez(suya):
    """/salida es solo del juez de la caja (root, modo 700): rae y su IA no pueden dejar ahí nada. Al acabar (con la
    caja ya muerta) vuelve a ser de este turno para poder leerla."""
    dueno = "0:0" if suya else f"{os.getuid()}:{os.getgid()}"
    pasos = [[*sudo(), "chown", "-R", "-h", dueno, SALIDA]] + ([[*sudo(), "chmod", "0700", SALIDA]] if suya else [])
    return all(ejecutar(p, "docker.log") == 0 for p in pasos)


def lanzar_caja():
    shutil.rmtree(SALIDA, ignore_errors=True)
    os.makedirs(SALIDA)
    if not salida_del_juez(True):
        return 125
    orden = ["docker", "run", "--rm", "--name", "caja-captura", "--init", "--network", "caja-interna",
             "--dns", "127.0.0.1", "--user", JUEZ, "--cap-drop", "ALL", "--cap-add", "SETUID", "--cap-add", "SETGID",
             "--cap-add", "KILL", "--security-opt", "no-new-privileges",
             "--pids-limit", "512", "--memory", "4g", "--memory-swap", "4g", "--cpus", "3", "--shm-size", "1g",
             "-v", f"{ENTRADA}:/entrada:ro", "-v", f"{SALIDA}:/salida", "caja-captura:turno"]
    try:
        codigo = ejecutar(orden, "caja.log", timeout=26 * 60)
    except subprocess.TimeoutExpired:
        ejecutar(["docker", "kill", "caja-captura"], "docker.log")
        codigo = 124
    salida_del_juez(False)
    return codigo


def leer_resultado(id_):
    """El resultado de la caja, solo si es un fichero normal, pequeño y del pedido de este turno."""
    ruta = os.path.join(SALIDA, "resultado.json")
    try:
        info = os.lstat(ruta)
        if not os.path.isfile(ruta) or os.path.islink(ruta) or info.st_size > 2_000_000:
            return None
        with open(ruta, encoding="utf-8") as f:
            r = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict) or r.get("id") != id_ or r.get("estado") not in caja.ESTADOS:
        return None
    return r


def vetada_por_nombre(host, vetos):
    """Lo mismo que corta el filtro: dominio vetado o subdominio suyo, una parte de entrar o una marca prohibida."""
    host = _dominio(host)
    if any(host == s or host.endswith("." + s) for s in vetos["sufijos"]):
        return True
    partes = host.split(".")[:-1]
    marcas, enteras = tuple(vetos.get("marcas") or ()), set(vetos.get("enteras") or ())
    return any(p in vetos["entradas"] or (marcas and p.startswith(marcas)) or p.split("-")[0] in enteras
               for p in partes)


def leer_vetos():
    with open(VETOS, encoding="utf-8") as f:
        return json.load(f)


def registro_del_filtro():
    """Lo que apuntó el filtro de cada conexión de la caja: [(cortada, host, sni, túnel abierto)]. Está en el otro
    contenedor y la IA no lo alcanza (la grabación del navegador, sí). None si no se puede leer."""
    r = subprocess.run(["docker", "exec", "caja-filtro", "cat", "/var/log/squid/access.log"], capture_output=True,
                       text=True)
    return conexiones(r.stdout) if r.returncode == 0 else None


def conexiones(texto):
    """De cada línea del filtro («hora resultado/código método destino sni»): (cortada, host, sni en minúsculas, si
    es un túnel https que el filtro dejó abierto)."""
    salida = []
    for linea in texto.splitlines():
        trozos = linea.split()
        if len(trozos) < 4:
            continue
        destino = trozos[3]
        host = destino.rsplit(":", 1)[0] if trozos[2] == "CONNECT" else urllib.parse.urlsplit(destino).hostname or ""
        sni = trozos[4] if len(trozos) > 4 and trozos[4] != "-" else ""
        tunel = trozos[2] == "CONNECT" and trozos[1].startswith("TCP_TUNNEL")
        salida.append(("DENIED" in trozos[1], _dominio(host.strip("[]")), _dominio(sni), tunel))
    return salida


def lo_que_vio_el_filtro(lista, vetos):
    """La palabra de lo que se ve en el registro del filtro, o None: un túnel que pide un nombre y habla con otro (SNI
    cambiado) o que va sin nombre dentro (así el filtro no puede mirarlo): trampas para llegar a una web vetada; una web
    vetada que pasó (no debería), o un captcha. El navegador y requests siempre dicen el nombre."""
    reales = [c for c in lista if c[1] not in caja.PRUEBAS_FILTRO]       # sin la comprobación del propio filtro
    if any((sni and sni != host) or (tunel and not sni) for _, host, sni, tunel in reales):
        return "red_trampa"
    if any(not cortada and host not in MODELO and any(h and vetada_por_nombre(h, vetos) for h in (host, sni))
           for cortada, host, sni, _ in reales):
        return "web_prohibida"
    if any(caja.del_sitio(h, d) for _, host, sni, _ in reales for h in (host, sni) if h for d in caja.DOMINIOS_RETO):
        return "captcha"
    return None


def revisar(r):
    """Lo que la caja no puede juzgar sola: lo que vio el filtro (que la IA no alcanza) y si el navegador abrió alguna
    web vetada (aunque el filtro la cortase). Si se ve algo, los datos se tiran y la web queda «vetada»."""
    vetos = leer_vetos()
    navegados = r.pop("navegados", None) or []
    lista = registro_del_filtro()
    if lista is None and r["estado"] == "hecha":   # sin el registro no se puede comprobar nada: no vale
        r.update({"estado": "fallida", "motivo": "filtro_caido", "datos": [], "filas": 0, "resumen": ""})
    motivo = lo_que_vio_el_filtro(lista or [], vetos)
    if not motivo and r["estado"] == "hecha" and any(vetada_por_nombre(h, vetos) for h in navegados
                                                    if isinstance(h, str)):
        motivo = "web_prohibida"
    if motivo and (r["estado"] == "hecha" or (r["estado"] == "fallida" and r.get("motivo") not in PROGRAMA)):
        r.update({"estado": "vetada", "motivo": motivo, "datos": [], "filas": 0, "resumen": ""})
    r["denegadas"] = None if lista is None else sum(1 for c in lista if c[0] and c[1] not in caja.PRUEBAS_FILTRO)
    return r


def linea(r):
    trozos = [f"{r['id']}: {r['estado']}"]
    for clave, texto in (("filas", "filas"), ("peticiones", "peticiones"), ("denegadas", "cortadas por el filtro")):
        if isinstance(r.get(clave), int):
            trozos.append(f"{r[clave]} {texto}")
    if isinstance(r.get("coste_usd"), (int, float)):
        trozos.append(f"{r['coste_usd']:g} $")
    if isinstance(r.get("segundos"), int):
        trozos.append(f"{round(r['segundos'] / 60)} min")
    if r.get("motivo"):                           # solo palabras nuestras: nada que haya podido escribir la IA
        trozos.append(r["motivo"] if r["motivo"] in MOTIVOS else "otro")
    return " · ".join(trozos)


def escribir_limpio(r):
    shutil.rmtree(LIMPIO, ignore_errors=True)
    os.makedirs(LIMPIO)
    with open(os.path.join(LIMPIO, "resultado.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)


def capturar():
    turno = leer_turno()
    codigo = lanzar_caja()
    # solo vale lo que dejó la caja si acabó ella sola (0, 3 o 4): si la mataron o se colgó, no se lee nada
    r = leer_resultado(turno["id"]) if codigo in CODIGOS_CAJA else None
    if r is None:
        r = {"id": turno["id"], "estado": "fallida", "motivo": "caja_sin_resultado", "fecha": caja.ahora()}
    r = revisar(r)
    escribir_limpio(r)
    decir(linea(r))
    # rojo solo si falla el programa (la caja no estaba cerrada o se rompió); lo previsto sale en verde
    return 1 if r.get("motivo") in PROGRAMA else 0


# --- desmontar ---
def cajas_vivas():
    r = subprocess.run(["docker", "ps", "-aq", "--filter", "name=caja-"], capture_output=True, text=True)
    return [x for x in r.stdout.split() if x] if r.returncode == 0 else ["?"]


def desmontar():
    for nombre in ("caja-captura", "caja-filtro"):
        ejecutar(["docker", "rm", "-f", nombre], "docker.log")
    for nombre in ("caja-interna", "caja-salida"):
        ejecutar(["docker", "network", "rm", nombre], "docker.log")
    for carpeta in (SALIDA, ENTRADA, LISTAS):
        shutil.rmtree(carpeta, ignore_errors=True)
        if os.path.exists(carpeta):
            ejecutar([*sudo(), "rm", "-rf", carpeta], "docker.log")
    for fichero in (EXTRA, VETOS):                # los vetados propios del dueño no se quedan en el disco
        if os.path.exists(fichero):
            os.remove(fichero)
    if cajas_vivas():
        decir("cap: queda un contenedor de la caja vivo")
        return 1
    decir("cap: caja desmontada")
    return 0


# --- guardar ---
def ficha_prueba(r):
    datos = [{caja.limpiar(k, 40): caja.limpiar(v) for k, v in f.items()} for f in (r.get("datos") or [])[:20]
             if isinstance(f, dict)]
    ficha = {k: r.get(k) for k in ("id", "estado", "fecha", "segundos", "modelo", "coste_usd", "peticiones",
                                    "denegadas", "filas", "campos", "cliente")}
    rae = r.get("rae") if isinstance(r.get("rae"), dict) else {}
    ficha["rae"] = {k: str(rae[k]) if re.fullmatch(r"[a-z_]{1,30}", str(rae.get(k) or "")) else None
                    for k in ("status", "error_kind")}
    ficha["motivo"] = (r["motivo"] if r["motivo"] in MOTIVOS else "otro") if r.get("motivo") else None
    return {**ficha, "datos": datos, "resumen": caja.limpiar(r.get("resumen"), caja.RESUMEN)}


def leer_limpio(turno):
    try:
        with open(os.path.join(LIMPIO, "resultado.json"), encoding="utf-8") as f:
            r = json.load(f)
        if r.get("id") == turno["id"]:
            return r
    except (OSError, ValueError, AttributeError):
        pass
    r = {"id": turno["id"], "estado": "fallida", "motivo": "caja_sin_resultado", "fecha": caja.ahora()}
    escribir_limpio(r)
    return r


def guardar_prueba(r, destino):
    if not sacar_privado(destino, ["/estado/capturas/"]):
        decir("cap-0: no he podido sacar el repositorio privado para guardar la prueba")
        return 1
    ruta = os.path.join(destino, "estado", "capturas", "prueba.json")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(ficha_prueba(r), f, ensure_ascii=False, indent=1)
    ok = git_guardar(destino, "investigador: prueba de la caja")
    decir(f"cap-0: prueba guardada · {r['estado']}" if ok else "cap-0: no he podido guardar la prueba")
    return 0 if ok else 1


def guardar_de_la_cola(r, destino):
    if not sacar_privado(destino):
        decir(f"{r['id']}: no he podido sacar el repositorio privado")
        return 1
    codigo = correr_capturas(destino, "guardar", "--id", r["id"], "--resultado", LIMPIO, log="guardar.log")
    pasar(os.path.join(REGISTROS, "guardar.log"))
    if codigo != 0:
        apuntar_fallo(destino, "guardar", "guardar.log")
    ok = git_guardar(destino, "investigador: captura")
    if codigo != 0:
        decir(f"{r['id']}: capturas.py guardar ha fallado (el detalle, en estado/capturas/fallo_turno.json)")
    return 0 if codigo == 0 and ok else 1


def guardar():
    turno = leer_turno()
    if cajas_vivas():                             # la llave no se usa mientras quede vivo algo de la caja
        for nombre in ("caja-captura", "caja-filtro"):
            ejecutar(["docker", "rm", "-f", nombre], "docker.log")
        if cajas_vivas():
            decir(f"{turno['id']}: queda algo de la caja vivo; no saco la llave")
            return 1
    r = leer_limpio(turno)
    destino = os.path.join(CAJA, "privado-guardar")
    poner_llave()
    try:
        return guardar_prueba(r, destino) if turno.get("probar") else guardar_de_la_cola(r, destino)
    finally:
        shutil.rmtree(destino, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("paso", choices=["elegir", "preparar", "capturar", "desmontar", "guardar"])
    paso = p.parse_args().paso
    try:
        return {"elegir": elegir, "preparar": preparar, "capturar": capturar, "desmontar": desmontar,
                "guardar": guardar}[paso]()
    except SystemExit:
        raise
    except Exception as e:                        # sin el detalle: podría llevar la web; solo el tipo de error
        print(f"cap: el paso {paso} ha fallado ({type(e).__name__})", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
