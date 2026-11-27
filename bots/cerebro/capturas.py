"""El Investigador de webs: los datos públicos de una web sin API que el Cerebro necesita para decidir, sacados por
reverse-api-engineer (rae) en una CAJA CERRADA: gratis (el modelo gratis de OpenCode, sin ninguna llave), con un
navegador nuevo sin sesiones, solo webs públicas y con topes bajos. El dueño autorizó el 26-nov-2026 que el Cerebro lo
pida él solo, sin preguntar, con estas normas (nunca TikTok, Instagram, YouTube ni redes; nunca páginas de entrar con
cuenta; nunca saltarse un captcha ni un bloqueo; 2 capturas al día y 5 a la semana como mucho).

Este programa NO navega con la IA ni ejecuta lo que ella escribe (eso va dentro de la caja, sin secretos). Es:
- el PORTERO, `pedir()`: lo usa el Cerebro, sin red. Comprueba el interruptor del dueño, la dirección, los vetos, los
  topes y la privacidad, y apunta el pedido en la cola;
- la COLA, estado/capturas/cola.json del repositorio privado (la dirección completa solo vive allí);
- lo que va ANTES de la caja, `elegir`: recupera lo colgado, vuelve a mirar topes y vetos, lee robots.txt y la página
  (sin cookies y con un nombre de robot honrado) y deja el pedido listo para la caja;
- y lo que va DESPUÉS, `guardar`: lee lo que dejó la caja, lo limpia (texto plano, sin enlaces, sin @, sin dominios,
  sin nombres de las cuentas) y escribe la ficha de la captura.

Órdenes (las usa .github/workflows/capturas.yml):
    python bots/cerebro/capturas.py elegir --salida DIR
        DIR/pedido.json   {"id", "web", "que"} (solo eso: la caja no sabe de qué cuenta es)
        DIR/vigilante.json las reglas de red para el vigilante de la caja (herramientas/caja_capturas/vigilante.py:
                           dominio, hosts, robots.txt, pausa y topes) y los modelos que cobraron (modelos_vetados)
        $GITHUB_OUTPUT     hay=1|0 e id=cap-N. El pedido queda «en_curso» (intentos+1) en la cola: el turno la
                           guarda y la sube ANTES de capturar.
    python bots/cerebro/capturas.py guardar --id cap-N --resultado DIR
        Lee DIR/resultado.json (solo si es un fichero normal y del mismo pedido) y DIR/datos.json si los datos van
        aparte. Es lo que deja la caja (herramientas/caja_capturas/caja.py): {"id", "estado": "hecha|fallida|vetada|
        sin_modelo_gratis", "motivo": una palabra fija (bloqueo_403, cloudflare, web_prohibida, pide_sesion,
        error_caja, de_pago...), "coste_usd", "modelo", "segundos", "peticiones", "datos", "campos", "resumen"}.
        También entiende lo de rae --json ("status", "error_kind", "error", "usage": {"total_cost_usd"}) y, si
        vienen, "bloqueo", "marcas" (retos vistos en el HAR) y "hosts" (los que contestaron).
        Sin coste apuntado cuenta como fallo (nunca como 0); con coste > 0 se tira y el modelo queda vetado. Los
        fallos de la caja (error_caja, caja_sin_resultado...) se repiten otro día una vez; con 2 intentos, «fallida».
Las dos imprimen solo «cap-N: <estado> · cifras» y salen con 0 en todo lo previsto (nada pendiente, vetada, sin modelo
gratis...). Distinto de 0 solo si el programa falla. Nunca sale la web, su dominio ni nada de las cuentas: los
registros de GitHub de este repositorio son públicos.

Normas fijas: TOPES y VETADOS de aquí; el dueño puede apagarlo todo o añadir vetos y bajar topes en config/fabrica.json
→ "capturas": {"encendido": true, "vetados_extra": [...], "permitidos": [...], "topes": {...}} (repositorio privado;
se lee tal cual: ni el Cerebro ni la Élite lo cambian). "permitidos" son los dominios que el Cerebro puede pedir sin que
el dueño los haya pedido antes.
"""
import argparse
import datetime as dt
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import stat
import sys
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import warnings

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import privado  # noqa: E402

CARPETA = os.path.join("estado", "capturas")
COLA = os.path.join(CARPETA, "cola.json")
AVERIAS = os.path.join(CARPETA, "averias.json")
BUZON = os.path.join("estado", "cerebro", "buzon.json")     # los mensajes del dueño (para ver que la web es suya)

TOPES = {"dia": 2, "semana": 5, "pendientes": 3, "por_dominio_dias": 30, "cerebro_por_cuenta_semana": 1}
CEREBRO_SEMANA = 1            # y el Cerebro solo, en total (todas las cuentas), una a la semana
HUELLA_DIAS = 30              # la misma web no se vuelve a pedir en un mes
COLGADA_HORAS = 2             # «en_curso» más de esto: la caja se murió
INTENTOS = 2                  # con 2 intentos, «fallida»
CADUCA_DIAS = 7               # pendiente una semana sin hacerse: «caducada»
CASTIGO_DIAS = 30             # web que bloquea (captcha, cuenta, 401/403/429): un mes fuera; a la segunda, siempre
PARA_SIEMPRE = "9999-12-31T00:00:00Z"
URL_MAXIMO, QUE_MINIMO, QUE_MAXIMO, PARA_MAXIMO = 300, 10, 300, 200
FILAS, VALOR, CAMPOS, CAMPO, RESUMEN = 200, 200, 20, 40, 1500
FICHA_BYTES, RESULTADO_BYTES = 200_000, 5_000_000
GUARDA_PEDIDOS, GUARDA_DOMINIOS, GUARDA_USO_DIAS = 200, 500, 30
RED = {"max_peticiones": 30, "max_bytes": 5_000_000, "pausa": 1.0}     # para el programa de la IA (vigilante.py)
NAVEGADOR = "investigador-web/1.0 (robot educado: respeta robots.txt)"  # nombre honrado, sin disfraces
ESPERA = 15                   # segundos para robots.txt y la página
FINALES = ("hecha", "fallida", "vetada", "caducada", "sin_modelo_gratis")
NO_CUENTAN = ("caducada", "sin_modelo_gratis")     # pedidos que no llegaron a mirar la web: se pueden volver a pedir
# y los que no llegaron a la web buena (la dirección estaba mal): no cuentan para «una vez al mes por web»
NO_TOCAN = ("no_existe", "no_es_pagina", "portero", "ip_no_publica", "redirige")

# Dominios prohibidos (se comprueban por sufijo y en minúsculas). Los del dueño (su app, su servidor) NO van aquí,
# que este repositorio es público: van en config/fabrica.json → capturas.vetados_extra del privado.
VETADOS = (
    # TikTok
    "tiktok.com", "tiktokv.com", "tiktokcdn.com", "tiktokcdn-us.com", "byteoversea.com", "ibytedtos.com",
    "musical.ly", "douyin.com",
    # Instagram, Facebook, Meta y Threads
    "instagram.com", "cdninstagram.com", "ig.me", "facebook.com", "facebook.net", "fb.com", "fb.me", "fb.watch",
    "fbcdn.net", "meta.com", "meta.ai", "messenger.com", "threads.net", "threads.com",
    # YouTube y lo que va con él
    "youtube.com", "youtu.be", "youtube-nocookie.com", "youtubekids.com", "ytimg.com", "googlevideo.com", "ggpht.com",
    "googleapis.com", "googleusercontent.com",
    # X (Twitter)
    "x.com", "twitter.com", "t.co", "twimg.com",
    # las demás redes y mensajerías
    "snapchat.com", "snap.com", "pinterest.com", "pin.it", "pinimg.com", "linkedin.com", "lnkd.in", "licdn.com",
    "reddit.com", "redd.it", "redditmedia.com", "redditstatic.com", "twitch.tv", "ttvnw.net", "kick.com",
    "discord.com", "discord.gg", "discordapp.com", "telegram.org", "telegram.me", "t.me", "whatsapp.com",
    "whatsapp.net", "wa.me", "vk.com", "weibo.com", "bsky.app", "bsky.social", "mastodon.social", "tumblr.com",
    "quora.com", "onlyfans.com", "patreon.com", "vimeo.com", "dailymotion.com", "spotify.com", "soundcloud.com",
    "likee.video", "kwai.com", "bereal.com",
    # entrar con cuenta (Google, Apple, Microsoft y compañía)
    "accounts.google.com", "appleid.apple.com", "idmsa.apple.com", "icloud.com", "live.com", "microsoftonline.com",
    "okta.com", "auth0.com", "onelogin.com",
    # buscadores y tiendas que no lo dejan
    "bing.com", "duckduckgo.com", "yahoo.com", "baidu.com", "aliexpress.com", "temu.com",
    # servicios propios o de pago, y webs que ya tienen API oficial
    "github.com", "githubusercontent.com", "githubassets.com", "anthropic.com", "claude.ai", "claude.com",
    "openai.com", "chatgpt.com", "opencode.ai", "elevenlabs.io", "paypal.com", "stripe.com", "archive.org",
    "wikipedia.org", "wikimedia.org", "wikidata.org",
    # buscadores de personas
    "whitepages.com", "spokeo.com", "pipl.com", "beenverified.com", "truepeoplesearch.com", "paginasblancas.es",
)
# Marcas prohibidas en cualquier país: las de MARCAS, también con lo que lleven pegado detrás (tiktokcdn, googlevideo…);
# las de MARCAS_ENTERAS, solo la palabra entera o con un guion (amazon.es, amazon-adsystem.com), porque amazonaws (los
# datos públicos en S3), amazonas o redditch son otras webs
MARCAS = ("tiktok", "instagram", "youtu", "facebook", "fbcdn", "whatsapp", "snapchat", "pinterest", "linkedin",
          "twitter", "google", "yandex")
MARCAS_ENTERAS = ("telegram", "discord", "twitch", "reddit", "amazon", "ebay")
ENTRADAS = ("login", "logon", "signin", "signup", "auth", "account", "accounts", "sso", "oauth", "id", "idp", "secure",
            "passport", "cuenta", "cuentas", "acceso")                                       # login.*, accounts.*...
RUTAS_ENTRADA = ("login", "log-in", "logon", "signin", "sign-in", "signup", "sign-up", "register", "registro", "auth",
                 "oauth", "sso", "account", "accounts", "cuenta", "mi-cuenta", "micuenta", "iniciar-sesion", "acceder",
                 "password", "wp-login.php", "wp-admin", "admin", "checkout", "carrito", "cart", "cesta")
LOCALES = ("localhost", "local", "internal", "intranet", "lan", "home", "corp", "localdomain", "private", "test",
           "invalid", "example", "onion", "arpa")
PARAMETROS = ("token", "session", "signature", "passw", "secret", "apikey", "csrf", "xsrf", "nonce", "credential")
PARAMETROS_EXACTOS = {"key", "sig", "sid", "jwt", "pwd", "pass", "otp", "code", "ticket", "auth", "authorization",
                      "authkey", "accesskey", "signed"}
SEGUNDO_NIVEL = {"co", "com", "org", "net", "gov", "gob", "edu", "ac", "nom", "mil", "or", "ne", "go", "info", "biz",
                 "ltd", "plc", "sch", "nhs"}

UCID = re.compile(r"UC[A-Za-z0-9_-]{22}")
CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ENLACE = re.compile(r"(?:https?|ftp)://\S*|www\.\S+", re.IGNORECASE)
DOMINIO_TXT = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}\b", re.IGNORECASE)
MENCION = re.compile(r"@[\w.]+")
# Puntos disfrazados para colar un dominio: «ejemplo(.)com», «ejemplo [dot] com», «ejemplo . com», «ejemplo dot com»
PUNTO_DISFRAZADO = re.compile(
    r"\s*[(\[{]\s*(?:\.|dot|punto)\s*[)\]}]\s*"
    r"|(?<=[a-z0-9])\s+\.\s*(?=[a-z]{2,24}\b)"
    r"|\s+(?:dot|punto)\s+(?=(?:com|org|net|io|info|biz|xyz|app|dev|ai|gg|ly|online|site|shop|store|link)\b)",
    re.IGNORECASE)
TELEFONO = re.compile(r"(?<![\w.,])\+?\d[\d \-()]{7,}\d(?![\w.,])")
DNI = re.compile(r"\b\d{8}[A-Za-z]\b")
LLAVE = re.compile(r"[A-Za-z0-9_]{32,}")
PERSONAS = re.compile(
    r"n[uú]meros? de (tel[eé]fono|m[oó]vil|whatsapp)|tel[eé]fonos? (de contacto|personal|particular)|"
    r"correos? electr[oó]nicos?|\be-?mails?\b|direcci[oó]n(es)? (de correo|postal|de casa|particular)|domicilio|"
    r"\b(dni|nif|nie|iban|pasaportes?)\b|datos (personales|privados)|contraseñas?|passwords?|cuentas? bancarias?|"
    r"seguridad social", re.IGNORECASE)
MARCAS_BLOQUEO = ("cf-chl", "challenge-platform", "just a moment...", "attention required! | cloudflare",
                  "px-captcha", "captcha-delivery", "datadome", "perimeterx", "are you a robot", "eres un robot",
                  "verify you are human", "comprueba que eres humano", "unusual traffic", "tráfico inusual")
TITULOS_ENTRADA = ("log in", "login", "sign in", "signin", "iniciar sesión", "inicia sesión", "acceder", "inloggen",
                   "anmelden", "connexion")

EXPLICA = {
    "hecha": "Ya tengo los datos de esa web.",
    "robots": "Su robots.txt no deja a los robots mirar esa página: la dejo en paz.",
    "robots_prohibe": "Esa web no deja entrar a ningún robot: la dejo en paz.",
    "captcha": "Esa web me ha puesto un captcha o un aviso de robot: no me lo salto.",
    "login": "Esa web pide entrar con cuenta: no la toco.",
    "bloqueo": "Esa web me ha cerrado la puerta: no insisto.",
    "429": "Esa web me ha dicho que voy demasiado deprisa: no insisto.",
    "red_vetada": "Esa web me llevaba a una red social o a una página prohibida: he tirado lo que saqué.",
    "redirige": "Esa dirección me mandaba a otra web: no la sigo.",
    "ip_no_publica": "Esa dirección no lleva a una web pública: no la toco.",
    "no_existe": "Esa página no existe (o ya no está).",
    "no_es_pagina": "Esa dirección no es una página web normal.",
    "portero": "Esa dirección ya no cumple las normas del dueño.",
    "castigada": "Esa web me bloqueó hace poco: espero.",
    "sin_datos": "He entrado, pero no he sacado ningún dato útil.",
    "coste": "El modelo que tenía que ser gratis ha cobrado algo: he tirado el resultado y no lo vuelvo a usar.",
    "sin_coste": "No he podido comprobar que fuera gratis: he tirado el resultado por si acaso.",
    "programa": "El programa de capturas ha fallado dos veces con esta web.",
    "colgada": "Se quedó colgada y la doy por perdida.",
    "caducada": "Llevaba una semana esperando sin poder hacerse: la quito de la cola.",
    "sin_modelo_gratis": "Hoy no había ningún modelo gratis para hacerla: no gasto dinero; pídemela otro día.",
    "har_enorme": "Esa web es enorme y pesada: no la miro.",
    "sin_har": "No he podido grabar lo que hacía la web: no me fío del resultado.",
    "sin_cliente": "La IA no ha sabido sacar los datos de esa web.",
    "programa_roto": "La IA no ha sabido sacar los datos de esa web.",
    "cliente_enlace": "Lo que dejó la IA era raro: lo he tirado.",
    "disfraz": "La IA quería disfrazarse para entrar: eso no se hace, lo he tirado.",
    "import_prohibido": "Lo que escribió la IA usaba cosas prohibidas: lo he tirado.",
    "llamada_prohibida": "Lo que escribió la IA hacía cosas prohibidas: lo he tirado.",
    "pide_sesion": "Esos datos solo salen con cuenta o con cookies: ya no son públicos, lo dejo.",
    "proveedor_extra": "El servicio gratis quería usar otra cosa que no es gratis: no lo uso.",
    "llave_en_la_caja": "He parado por seguridad: Claude tiene que mirarlo.",
    "error_caja": "Se ha roto la caja donde trabajo: lo repito otro día.",
    "caja_sin_resultado": "La caja no me ha devuelto nada: lo repito otro día.",
    "caja_abierta": "La caja donde trabajo no estaba bien cerrada: no he hecho nada.",
    "otro_dominio": "Lo que escribió la IA quería sacar los datos de otra web: lo he tirado.",
    "clave_dentro": "Lo que escribió la IA llevaba algo que parece una llave: lo he tirado.",
    "cliente_grande": "Lo que escribió la IA era demasiado grande para fiarme: lo he tirado.",
}
BLOQUEOS = ("captcha", "login", "bloqueo", "429", "robots_prohibe", "red_vetada")    # castigan al dominio
AVISOS = {"coste": "El modelo gratis ha cobrado: queda vetado. Claude tiene que mirarlo.",
          "llave_en_la_caja": "Había una llave dentro de la caja: no se ha usado nada. Claude tiene que mirarlo ya."}
VETOS = {"red": "Eso es una red social o va con ella: nunca la investigo (ni TikTok, ni Instagram, ni YouTube, ni "
                "ninguna red).",
         "entrar": "Esa web es de entrar con cuenta: no la toco.",
         "prohibida": "Esa web está en la lista de prohibidas del dueño."}


class Rechazo(Exception):
    """Una petición que el portero no deja pasar. El texto es para el dueño, en sencillo."""


class _Redireccion(Exception):
    """La web manda a otro dominio (o a uno prohibido): no se sigue."""


# ---------------- horas ----------------
def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _iso(t=None):
    return (t or _ahora()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fecha(texto):
    try:
        return dt.datetime.strptime(str(texto), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _hace(texto, **cuanto):
    """¿La fecha es más nueva que hace `cuanto` (días=, horas=)?"""
    f = _fecha(texto)
    return bool(f and f > _ahora() - dt.timedelta(**cuanto))


def _manana():
    """El día siguiente a las 00:00 (UTC): lo que falla por la red o por la web se deja para otro día."""
    return _iso((_ahora() + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0))


# ---------------- lo que decide el dueño ----------------
def _config():
    """config/fabrica.json → capturas, tal cual (sin los ajustes de la Élite: ese interruptor solo lo toca el dueño)."""
    cfg = (privado.leer(os.path.join("config", "fabrica.json"), {}) or {}).get("capturas") or {}
    return cfg if isinstance(cfg, dict) else {}


def _lista(cfg, nombre):
    return [str(x).strip().lower().strip(".") for x in cfg.get(nombre) or [] if str(x).strip()]


def _tope(cfg, nombre):
    """Los topes de aquí; el dueño solo puede apretarlos (config → capturas.topes): menos capturas o, en los que se
    miden en días (…_dias), más días de espera. Nunca aflojarlos."""
    try:
        valor = int((cfg.get("topes") or {}).get(nombre, TOPES[nombre]))
    except (TypeError, ValueError):
        return TOPES[nombre]
    if nombre.endswith("_dias"):
        return min(3650, max(TOPES[nombre], valor))
    return min(TOPES[nombre], valor)


# ---------------- la dirección ----------------
def dominio_de(host):
    """El dominio que se registra (ejemplo.org de datos.ejemplo.org; bbc.co.uk de www.bbc.co.uk)."""
    partes = host.split(".")
    if len(partes) >= 3 and len(partes[-1]) == 2 and partes[-2] in SEGUNDO_NIVEL:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def es_vetado(host, extra=()):
    """Por qué está prohibido este host («red», «entrar», «prohibida») o None si se puede mirar."""
    host = str(host or "").lower().rstrip(".")
    for s in tuple(VETADOS) + tuple(extra):
        if s and (host == s or host.endswith("." + s)):
            return "entrar" if s in ("accounts.google.com", "appleid.apple.com", "idmsa.apple.com") else \
                "prohibida" if s in extra else "red"
    etiquetas = host.split(".")[:-1]
    if any(e.startswith(MARCAS) or e.split("-")[0] in MARCAS_ENTERAS for e in etiquetas):
        return "red"
    if any(e in ENTRADAS for e in etiquetas):
        return "entrar"
    return None


def _parametro_malo(nombre):
    trozos = [t for t in re.split(r"[^a-z0-9]+", nombre.lower()) if t]
    return any(t in PARAMETROS_EXACTOS or t.startswith(PARAMETROS) for t in trozos)


def _parece_llave(texto):
    return any(re.search(r"[A-Za-z]", m) and re.search(r"\d", m) for m in LLAVE.findall(texto))


def normalizar(web):
    """La dirección limpia y comprobada: (url, host, dominio). Si no vale, Rechazo con el porqué en sencillo.
    Solo https, sin usuario:clave@, sin IP ni nombres de dentro, puerto normal, 300 letras como mucho, sin
    parámetros de sesión ni llaves, dominio normal (con idna y sin punto final) y nada de páginas de entrar."""
    if not isinstance(web, str) or not web.strip():
        raise Rechazo("No me has dado ninguna dirección.")
    web = web.strip()
    if "://" not in web and re.match(r"[a-z0-9.-]+\.[a-z]{2,24}(/|$)", web, re.IGNORECASE):
        web = "https://" + web
    if len(web) > URL_MAXIMO:
        raise Rechazo("La dirección es demasiado larga (más de 300 letras).")
    if re.search(r"[\s\x00-\x1f\x7f\\]", web):
        raise Rechazo("La dirección lleva espacios o signos raros: no la acepto.")
    partes = urllib.parse.urlsplit(web)
    if partes.scheme.lower() != "https":
        raise Rechazo("Solo miro webs seguras (las que empiezan por https://).")
    if "@" in partes.netloc:
        raise Rechazo("La dirección lleva un usuario o una contraseña dentro: no la acepto.")
    if any(c in partes.netloc for c in "%[]") or not partes.hostname:
        raise Rechazo("Esa dirección no es una web normal.")
    try:
        puerto = partes.port
    except ValueError:
        raise Rechazo("Esa dirección lleva un puerto raro.")
    if puerto not in (None, 443):
        raise Rechazo("Solo miro webs normales (sin puertos raros).")
    host = partes.hostname.rstrip(".")
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise Rechazo("Esa dirección no es una web normal.")
    if "xn--" in host:
        raise Rechazo("El dominio lleva letras especiales (puede ser una trampa): no lo acepto.")
    try:
        ipaddress.ip_address(host)
        raise Rechazo("Solo miro webs con nombre, nunca una IP.")
    except ValueError:
        pass
    etiquetas = host.split(".")
    if len(etiquetas) < 2 or not re.fullmatch(r"[a-z]{2,24}", etiquetas[-1]) or \
            not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", e) for e in etiquetas):
        raise Rechazo("Esa dirección no es una web normal.")
    if etiquetas[-1] in LOCALES or host == "localhost":
        raise Rechazo("Esa dirección es de una red de dentro, no de Internet.")
    if es_vetado(host):
        raise Rechazo(VETOS[es_vetado(host)])
    ruta = partes.path or "/"
    if "@" in ruta:
        raise Rechazo("Eso es el perfil de alguien: no miro perfiles de personas.")
    if any(t.lower() in RUTAS_ENTRADA for t in ruta.split("/") if t):
        raise Rechazo("Esa página es de entrar con cuenta (o de pagar): no la toco.")
    pares = urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
    if any(_parametro_malo(k) for k, _ in pares):
        raise Rechazo("La dirección lleva un código de sesión o una llave: no la acepto.")
    if partes.fragment and re.search(r"token|key|auth|session|sig", partes.fragment, re.IGNORECASE):
        raise Rechazo("La dirección lleva un código de sesión o una llave: no la acepto.")
    if _parece_llave(ruta + "?" + partes.query):
        raise Rechazo("La dirección lleva algo que parece una llave o un código de sesión: no la acepto.")
    url = urllib.parse.urlunsplit(("https", host, ruta, partes.query, ""))
    if len(url) > URL_MAXIMO:
        raise Rechazo("La dirección es demasiado larga (más de 300 letras).")
    return url, host, dominio_de(host)


def huella(url, dominio=None):
    """sha256(dominio + ruta normalizada)[:16]: la misma web no se repite en un mes."""
    partes = urllib.parse.urlsplit(url)
    dominio = dominio or dominio_de(partes.hostname or "")
    consulta = "&".join(sorted(f"{k}={v}" for k, v in urllib.parse.parse_qsl(partes.query, keep_blank_values=True)))
    base = dominio + (partes.path.rstrip("/") or "/") + ("?" + consulta if consulta else "")
    return hashlib.sha256(base.lower().encode("utf-8")).hexdigest()[:16]


# ---------------- limpiar lo que entra y lo que sale ----------------
def _junto(texto):
    """Solo letras y cifras, sin acentos y en minúsculas: «Canal-De_Prueba», «canal de prueba» y «canaldeprueba» son
    lo mismo (así se ve un nombre de cuenta aunque venga escrito de otra manera)."""
    plano = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", plano.lower())


_NOMBRES = {}


def _nombres_privados():
    """Los nombres de las cuentas, como en _junto y de 4 letras o más: de cada barrio, su clave, su cuenta y su nombre;
    de cada canal, su nombre y su id o handle (config/canales.json del privado). Se leen una vez por versión del
    fichero. Devuelve [(junto, patrón)]: el patrón casa el nombre con cualquier separador entre letras."""
    ruta = os.path.join(privado.carpeta(), "config", "canales.json")
    try:
        marca = (ruta, os.stat(ruta).st_mtime_ns)
    except OSError:
        marca = (ruta, None)
    if marca not in _NOMBRES:
        cfg = privado.config() or {}
        nombres = set()
        for clave, b in (cfg.get("barrios") or {}).items():
            b = b if isinstance(b, dict) else {}
            nombres |= {clave, b.get("cuenta"), b.get("nombre"), b.get("handle"), b.get("usuario")}
        for c in (cfg.get("canales") or {}).values():
            c = c if isinstance(c, dict) else {}
            nombres |= {c.get("nombre"), c.get("id"), c.get("handle"), c.get("usuario")}
        juntos = sorted({_junto(n) for n in nombres if isinstance(n, str) and len(_junto(n)) >= 4},
                        key=len, reverse=True)
        _NOMBRES.clear()
        _NOMBRES[marca] = [(n, re.compile(r"[\W_]*".join(map(re.escape, n)), re.IGNORECASE)) for n in juntos]
    return _NOMBRES[marca]


def _sin_nombres(texto):
    """Quita los nombres de las cuentas aunque vengan en minúsculas, con guiones, puntos o sin espacios. Si aun así
    se adivina uno (con acentos o letras raras en medio), el texto entero se tira: mejor sin dato que con un nombre."""
    for _, patron in _nombres_privados():
        texto = patron.sub(" ", texto)
    junto = _junto(texto)
    return "" if any(n in junto for n, _ in _nombres_privados()) else texto


def destapar(texto):
    """Las letras raras pasan a normales (＠ → @, ． → .) y los puntos disfrazados vuelven a ser puntos
    («ejemplo(.)com», «ejemplo . com», «ejemplo dot com» → «ejemplo.com»): así los dominios y los @ escondidos se ven
    y se quitan."""
    return PUNTO_DISFRAZADO.sub(".", unicodedata.normalize("NFKC", str(texto)))


def sanear(valor, tope=VALOR):
    """Texto plano y sin nada privado: fuera etiquetas, <>, enlaces, correos, @usuarios, dominios (también los
    disfrazados), teléfonos e ids de canal; los nombres de las cuentas, cambiados por su alias (privado.limpiar) y,
    escritos de cualquier otra manera, quitados. Cortado al tope."""
    if valor is None:
        return ""
    t = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False) if isinstance(valor, (dict, list)) \
        else str(valor)
    t = html.unescape(unicodedata.normalize("NFKC", t[:20_000]))
    t = re.sub(r"<[^>]*>", " ", t).replace("<", " ").replace(">", " ")
    t = CORREO.sub("[correo]", destapar(t))
    t = ENLACE.sub(" ", t)
    t = MENCION.sub(" ", t).replace("@", " ")
    t = DOMINIO_TXT.sub(" ", t)
    t = UCID.sub(" ", t)
    t = TELEFONO.sub(lambda m: "[teléfono]" if sum(c.isdigit() for c in m.group(0)) >= 9 else m.group(0), t)
    t = DNI.sub("[dni]", t)
    t = re.sub(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]", " ", t)
    t = _sin_nombres(privado.limpiar(re.sub(r"\s+", " ", t).strip()))
    return re.sub(r"\s+", " ", t)[:tope].strip()


def _limpiar_que(que):
    """Qué datos quiere: una línea de 10 a 300 letras, sin enlaces ni signos que puedan liar a la caja."""
    t = re.sub(r"\s+", " ", destapar(que or "")).strip()
    if "@" in t or CORREO.search(t) or UCID.search(t):
        raise Rechazo("Lo que quieres saber lleva un correo, un @ o un id de canal: eso no sale fuera.")
    t = ENLACE.sub(" ", t)
    t = DOMINIO_TXT.sub(" ", t)
    t = re.sub(r"[<>{}$`|\\\"\x00-\x1f\x7f]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < QUE_MINIMO:
        raise Rechazo("Dime qué datos quieres de esa web (por ejemplo: «título, puesto y fecha del top 50»).")
    if PERSONAS.search(t):
        raise Rechazo("Solo saco datos públicos y de conjunto (listas, rankings, precios, temas), nunca datos de "
                      "personas concretas.")
    return t[:QUE_MAXIMO].rsplit(" ", 1)[0] if len(t) > QUE_MAXIMO else t


def _privado_dentro(texto):
    """¿Lleva el nombre de una cuenta (escrito como sea: con guiones, sin espacios, en minúsculas…), un correo o un id
    de canal? (eso nunca sale a la web ni a la caja)"""
    junto = _junto(texto)
    return privado.limpiar(texto) != texto or bool(CORREO.search(texto)) or bool(UCID.search(texto)) or \
        any(n in junto for n, _ in _nombres_privados())


# ---------------- la cola ----------------
def leer_cola():
    c = privado.leer(COLA, {}) or {}
    if not isinstance(c, dict):
        c = {}
    for k, defecto in (("pedidos", []), ("dominios", {}), ("uso", {}), ("modelos_vetados", {})):
        if not isinstance(c.get(k), type(defecto)):
            c[k] = defecto
    c["pedidos"] = [p for p in c["pedidos"] if isinstance(p, dict) and p.get("id")]
    try:
        c["ultimo"] = int(c.get("ultimo") or 0)
    except (TypeError, ValueError):
        c["ultimo"] = 0
    return c


def guardar_cola(cola):
    cola["actualizado"] = _iso()
    privado.escribir(COLA, cola)


def _numero(id_):
    m = re.fullmatch(r"cap-(\d{1,6})", str(id_ or ""))
    return int(m.group(1)) if m else 0


def _nuevo_id(cola):
    n = max([cola.get("ultimo") or 0] + [_numero(p.get("id")) for p in cola["pedidos"]]) + 1
    cola["ultimo"] = n
    return f"cap-{n}"


def _uso(cola, dias=1):
    """Capturas empezadas hoy (dias=1) o en los últimos 7 días (dias=7), sin las devueltas (las que no llegaron a mirar
    la web porque no había modelo gratis)."""
    hoy = _ahora().date()
    total = 0
    for d in range(dias):
        uno = cola["uso"].get((hoy - dt.timedelta(days=d)).isoformat()) or {}
        total += max(0, int(uno.get("capturas") or 0) - int(uno.get("devueltas") or 0))
    return total


def _sumar_uso(cola, campo="capturas", dia=None):
    """Una captura más ese día («capturas») o una devuelta («devueltas»). Nunca se resta: al juntar dos copias de la
    cola gana el máximo de cada cifra, y una resta se perdería."""
    uno = cola["uso"].setdefault(str(dia or _iso())[:10], {"capturas": 0})
    uno[campo] = int(uno.get(campo) or 0) + 1


def _dominio(cola, dominio):
    return cola["dominios"].setdefault(dominio, {"ultima": None, "fallos": 0, "vetado_hasta": None, "motivo": None})


def _castigar(cola, dominio, motivo):
    """Una web que bloquea descansa 30 días; a la segunda vez, para siempre."""
    d = _dominio(cola, dominio)
    d["fallos"] = int(d.get("fallos") or 0) + 1
    d["vetado_hasta"] = PARA_SIEMPRE if d["fallos"] >= 2 else _iso(_ahora() + dt.timedelta(days=CASTIGO_DIAS))
    d["motivo"] = motivo
    d["ultima"] = _iso()


def _castigada(cola, dominio):
    hasta = (cola["dominios"].get(dominio) or {}).get("vetado_hasta")
    return hasta if hasta and str(hasta) > _iso() else None


def ruta_ficha(id_):
    return os.path.join(CARPETA, f"{id_}.json")


def _terminar(cola, p, estado, motivo, extra=None):
    """Cierra un pedido y deja su ficha (estado/capturas/<id>.json), también cuando no salió."""
    ahora = _iso()
    p.update(estado=estado, motivo=motivo, cambiado=ahora, terminada=ahora, resultado=ruta_ficha(p["id"]))
    p.pop("no_antes_de", None)
    ficha = {"id": p["id"], "estado": estado, "fecha": ahora, "filas": 0, "campos": [], "datos": [], "resumen": "",
             "motivo": motivo, "coste_usd": 0.0}
    ficha.update(extra or {})
    privado.escribir(ruta_ficha(p["id"]), ficha)
    return ficha


def _mantener(cola):
    """Lo colgado vuelve a la cola (para otro día) o, si ya iba por su último intento, se da por fallido; lo que lleva
    una semana esperando caduca;
    y las listas no crecen sin fin."""
    for p in cola["pedidos"]:
        if p.get("estado") == "en_curso" and not _hace(p.get("empezada"), hours=COLGADA_HORAS):
            if int(p.get("intentos") or 0) >= INTENTOS:     # `elegir` ya contó el intento al ponerla «en_curso»
                _terminar(cola, p, "fallida", "colgada")
            else:                                           # como un fallo de la caja: otro día, una vez más
                p.update(estado="pendiente", empezada=None, no_antes_de=_manana(), cambiado=_iso())
        elif p.get("estado") == "pendiente" and not _hace(p.get("fecha"), days=CADUCA_DIAS):
            _terminar(cola, p, "caducada", "caducada")
    vivos = [p for p in cola["pedidos"] if p.get("estado") not in FINALES]
    hechos = sorted((p for p in cola["pedidos"] if p.get("estado") in FINALES), key=lambda p: _numero(p.get("id")))
    sitio = max(0, GUARDA_PEDIDOS - len(vivos))
    guarda = vivos + (hechos[len(hechos) - sitio:] if sitio else [])
    cola["pedidos"] = sorted(guarda, key=lambda p: _numero(p.get("id")))
    viejo = (_ahora() - dt.timedelta(days=GUARDA_USO_DIAS)).date().isoformat()
    cola["uso"] = {d: v for d, v in cola["uso"].items() if d >= viejo}
    vivos_dom = {d: v for d, v in cola["dominios"].items() if isinstance(v, dict) and (
        v.get("del_dueno") or _castigada(cola, d) or _hace(v.get("ultima"), days=60))}
    cola["dominios"] = dict(sorted(vivos_dom.items(), key=lambda x: str(x[1].get("ultima") or ""))[-GUARDA_DOMINIOS:])


# ---------------- 1. pedir (lo usa el Cerebro, sin red) ----------------
def _texto_del_mensaje(mensaje):
    if isinstance(mensaje, dict):
        return str(mensaje.get("texto") or "")
    for m in (privado.leer(BUZON, {}) or {}).get("mensajes") or []:
        if isinstance(m, dict) and mensaje and m.get("id") == mensaje:
            return str(m.get("texto") or "")
    return ""


def _id_mensaje(mensaje):
    return str(mensaje.get("id") or "") if isinstance(mensaje, dict) else (str(mensaje) if mensaje else None)


def _en_su_mensaje(url, host, mensaje):
    """La web que pide el dueño tiene que estar tal cual en lo que escribió (así la IA no se inventa direcciones)."""
    texto = _texto_del_mensaje(mensaje)
    for trozo in re.findall(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:[/?][^\s<>\"'«»]*)?", texto, re.IGNORECASE):
        trozo = re.sub(r"^http://", "https://", trozo.rstrip(".,;:!?)]}»"), flags=re.IGNORECASE)
        try:
            suya, su_host, _ = normalizar(trozo)
        except Rechazo:
            continue
        if suya.rstrip("/") == url.rstrip("/"):
            return True
        partes = urllib.parse.urlsplit(url)
        if su_host.removeprefix("www.") == host.removeprefix("www.") and partes.path in ("", "/") and not partes.query:
            return True
    return False


def pedir(web, que, para="", pedido_por="cerebro", cuenta="todas", mensaje=None, prueba=False):
    """El portero. Devuelve (ok, texto_para_el_dueño, id). ok=True: pedido nuevo apuntado en la cola («pendiente»).
    ok=False: no se apunta nada y el texto dice por qué; si es porque ya estaba (la misma web este mes), el id es el de
    ese pedido. Sin red: lo de robots.txt y la página se mira en `elegir`. Con prueba=True lo comprueba todo y no
    escribe la cola. Nunca lanza errores: si algo suyo falla, lo apunta y dice que no."""
    try:
        return _pedir(web, que, para, pedido_por, cuenta, mensaje, prueba)
    except Rechazo as e:
        return False, str(e), None
    except Exception as e:
        _apuntar_averia("pedir", e)
        return False, "Ahora no he podido apuntarlo (un fallo mío): lo intento en la siguiente pasada.", None


def _pedir(web, que, para, pedido_por, cuenta, mensaje, prueba):
    cfg = _config()
    if not cfg.get("encendido"):
        raise Rechazo("El dueño tiene apagado el investigador de webs: no apunto nada.")
    pedido_por = "dueño" if str(pedido_por).lower() in ("dueño", "dueno") else "cerebro"
    url, host, dominio = normalizar(web)
    extra = _lista(cfg, "vetados_extra")
    if es_vetado(host, extra):
        raise Rechazo(VETOS[es_vetado(host, extra)])
    que = _limpiar_que(que)
    para = sanear(para, PARA_MAXIMO)
    if _privado_dentro(url + " " + que):
        raise Rechazo("Eso lleva el nombre de una de tus cuentas, un correo o un id de canal: no lo saco fuera.")
    cuenta = str(cuenta or "todas")[:80]
    if pedido_por == "dueño" and not _en_su_mensaje(url, host, mensaje):
        raise Rechazo("Solo investigo la dirección exacta que tú me escribas en el mensaje: pégamela y la miro.")
    cola = leer_cola()
    hasta = _castigada(cola, dominio)
    if hasta:
        raise Rechazo("Esa web me bloqueó (captcha, cuenta o «eres un robot»): " +
                      ("no vuelvo nunca." if hasta >= PARA_SIEMPRE else f"no vuelvo hasta el {hasta[:10]}."))
    repetido = _repetido(cola, huella(url, dominio), dominio, _tope(cfg, "por_dominio_dias"))
    if repetido:
        return repetido
    _topes(cola, cfg, pedido_por, cuenta, host, dominio)
    p = {"id": _nuevo_id(cola), "huella": huella(url, dominio), "estado": "pendiente", "fecha": _iso(),
         "pedido_por": pedido_por, "mensaje": _id_mensaje(mensaje) if pedido_por == "dueño" else None,
         "cuenta": cuenta, "web": url, "dominio": dominio, "que": que, "para": para, "intentos": 0,
         "empezada": None, "resultado": None, "cambiado": _iso()}
    cola["pedidos"].append(p)
    if pedido_por == "dueño":
        _dominio(cola, dominio)["del_dueno"] = True
    if not prueba:
        guardar_cola(cola)
    hoy = sum(1 for x in cola["pedidos"] if str(x.get("fecha"))[:10] == _iso()[:10])
    return True, (f"Apuntado ({p['id']}): investigo esa web yo solo en unas horas, gratis, sin cuenta y con un "
                  f"navegador nuevo. Hoy van {hoy} de {_tope(cfg, 'dia')}."), p["id"]


def _repetido(cola, firma, dominio, dias_dominio):
    """La misma web (o el mismo dominio) en el último mes: no se vuelve a pedir."""
    for p in reversed(cola["pedidos"]):
        if p.get("estado") in NO_CUENTAN or p.get("motivo") in NO_TOCAN or \
                not _hace(p.get("fecha"), days=max(HUELLA_DIAS, dias_dominio)):
            continue
        if p.get("huella") == firma and _hace(p.get("fecha"), days=HUELLA_DIAS):
            dias = max(0, (_ahora() - (_fecha(p.get("fecha")) or _ahora())).days)
            if p.get("estado") in ("pendiente", "en_curso"):
                return False, f"Esa web ya la tengo apuntada ({p['id']}): los datos llegan en unas horas.", p["id"]
            if p.get("estado") == "hecha":
                return False, f"Esa web ya la investigué hace {dias} día(s) ({p['id']}): uso esos datos.", p["id"]
            return False, (f"Esa web ya la intenté hace {dias} día(s) ({p['id']}) y no salió: no la repito hasta "
                           "pasado un mes."), p["id"]
        if p.get("dominio") == dominio and _hace(p.get("fecha"), days=dias_dominio):
            raise Rechazo(f"Esa web ya la investigué este mes ({p['id']}): como mucho una vez al mes por web.")
    return None


def _topes(cola, cfg, pedido_por, cuenta, host, dominio):
    hoy = _iso()[:10]
    vivos = [p for p in cola["pedidos"] if p.get("estado") in ("pendiente", "en_curso")]
    if len(vivos) >= _tope(cfg, "pendientes"):
        raise Rechazo(f"Ya tengo {len(vivos)} investigaciones esperando: cuando salgan, pido más.")
    de_hoy = sum(1 for p in cola["pedidos"] if str(p.get("fecha"))[:10] == hoy)
    if max(de_hoy, _uso(cola)) >= _tope(cfg, "dia"):
        raise Rechazo(f"Hoy ya van {_tope(cfg, 'dia')} investigaciones (el tope del dueño): mañana sigo.")
    semana = [p for p in cola["pedidos"] if _hace(p.get("fecha"), days=7)]
    if max(len(semana), _uso(cola, 7)) >= _tope(cfg, "semana"):
        raise Rechazo(f"Esta semana ya van {_tope(cfg, 'semana')} investigaciones (el tope del dueño): la semana "
                      "que viene sigo.")
    ultima = (cola["dominios"].get(dominio) or {}).get("ultima")
    if _hace(ultima, days=_tope(cfg, "por_dominio_dias")):
        raise Rechazo("Esa web ya la miré este mes: como mucho una vez al mes por web.")
    if pedido_por != "cerebro":
        return
    mias = [p for p in semana if p.get("pedido_por") == "cerebro"]
    if sum(1 for p in mias if p.get("cuenta") == cuenta) >= _tope(cfg, "cerebro_por_cuenta_semana") or \
            len(mias) >= CEREBRO_SEMANA:
        raise Rechazo("Esta semana ya he pedido mi investigación: la siguiente, la semana que viene.")
    del_dueno = (cola["dominios"].get(dominio) or {}).get("del_dueno") or \
        any(p.get("dominio") == dominio and p.get("pedido_por") == "dueño" for p in cola["pedidos"])
    if not del_dueno and not any(host == x or host.endswith("." + x) for x in _lista(cfg, "permitidos")):
        raise Rechazo("Yo solo puedo investigar webs que el dueño ya me pidió alguna vez o que estén en su lista de "
                      "permitidas.")


# ---------------- 2. elegir (antes de la caja) ----------------
class _MismoDominio(urllib.request.HTTPRedirectHandler):
    """Sigue redirecciones solo dentro del mismo dominio y si la nueva dirección también pasa el portero."""
    max_redirections = 5

    def __init__(self, dominio, extra=()):
        super().__init__()
        self.dominio, self.extra = dominio, extra

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            url, host, dominio = normalizar(newurl)
        except Rechazo:
            raise _Redireccion("redirige")
        if dominio != self.dominio or es_vetado(host, self.extra):
            raise _Redireccion("redirige")
        return super().redirect_request(req, fp, code, msg, headers, url)


def _abrir(url, dominio, limite, extra=()):
    """GET sin cookies y con un nombre de robot honrado. Devuelve (código, cabeceras, dirección final, cuerpo)."""
    abridor = urllib.request.build_opener(_MismoDominio(dominio, extra))
    peticion = urllib.request.Request(url, headers={"User-Agent": NAVEGADOR, "Accept": "text/html,text/plain,*/*"})

    def cabeceras(h):
        salida = {k.lower(): v for k, v in (h.items() if h else [])}
        if h and h.get_all("set-cookie"):
            salida["set-cookie"] = "; ".join(h.get_all("set-cookie"))
        return salida
    try:
        with abridor.open(peticion, timeout=ESPERA) as r:
            return r.status, cabeceras(r.headers), r.geturl(), r.read(limite)
    except urllib.error.HTTPError as e:
        cuerpo = e.read(limite) if e.fp else b""
        return e.code, cabeceras(e.headers), e.geturl() or url, cuerpo


def _leer_robots(url, dominio, extra=()):
    codigo, _, _, cuerpo = _abrir(url, dominio, 512 * 1024, extra)
    return codigo, cuerpo.decode("utf-8", "replace")


def _leer_pagina(url, dominio, extra=()):
    codigo, cabeceras, final, cuerpo = _abrir(url, dominio, 256 * 1024, extra)
    return {"codigo": codigo, "cabeceras": cabeceras, "final": final, "cuerpo": cuerpo.decode("utf-8", "replace")}


def _resolver(host):
    return sorted({r[4][0] for r in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})


# Se pueden cambiar en las pruebas (sin red): (url, dominio, extra) → ...; host → [ips]
LEER_ROBOTS, LEER_PAGINA, RESOLVER = _leer_robots, _leer_pagina, _resolver
FALLOS_DE_RED = (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError, ValueError, UnicodeError)


def _bloqueo_en_pagina(pagina):
    """¿La página es un captcha, un «eres un robot» o una de entrar con cuenta? → motivo o None."""
    cab = {str(k).lower(): str(v).lower() for k, v in (pagina.get("cabeceras") or {}).items()}
    cuerpo = str(pagina.get("cuerpo") or "").lower()
    if "cf-mitigated" in cab or any(k.startswith("x-datadome") for k in cab) or \
            re.search(r"(^|[;,\s])(_px\w*|datadome)=", cab.get("set-cookie", "")):
        return "captcha"
    if any(m in cuerpo for m in MARCAS_BLOQUEO):
        return "captcha"
    visible = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", cuerpo, flags=re.S))
    if "captcha" in cuerpo and len(visible) < 5000:
        return "captcha"
    titulo = re.search(r"<title[^>]*>(.*?)</title>", cuerpo, re.S)
    if titulo and any(t in titulo.group(1) for t in TITULOS_ENTRADA) and \
            re.search(r"type\s*=\s*[\"']?password", cuerpo):
        return "login"
    return None


def _revisar(p, cola, cfg):
    """Lo último antes de la caja. Devuelve ("ok", info), ("vetada"|"fallida", motivo) u ("otro_dia", motivo)."""
    extra = _lista(cfg, "vetados_extra")
    try:
        url, host, dominio = normalizar(p.get("web"))
    except Rechazo:
        return "vetada", "portero"
    if es_vetado(host, extra):
        return "vetada", "portero"
    if _castigada(cola, dominio):
        return "vetada", "castigada"
    try:
        ips = RESOLVER(host)
    except FALLOS_DE_RED:
        return "otro_dia", "dns"
    if not ips:
        return "otro_dia", "dns"
    try:
        publicas = all(ipaddress.ip_address(str(ip).split("%")[0]).is_global for ip in ips)
    except ValueError:
        publicas = False
    if not publicas:
        return "vetada", "ip_no_publica"
    try:
        codigo, texto = LEER_ROBOTS(f"https://{host}/robots.txt", dominio, extra)
    except _Redireccion:
        codigo, texto = 404, ""                      # robots.txt que manda fuera: como si no hubiera
    except FALLOS_DE_RED:
        return "otro_dia", "robots_no_contesta"
    robots = urllib.robotparser.RobotFileParser()
    if codigo in (401, 403):
        return "vetada", "robots_prohibe"
    if codigo == 429:
        return "vetada", "429"
    if codigo >= 500:
        return "otro_dia", "robots_no_contesta"
    texto = texto if codigo == 200 else ""
    robots.parse(texto.splitlines())
    if not robots.can_fetch("*", url):
        return "vetada", "robots"
    try:
        pagina = LEER_PAGINA(url, dominio, extra)
    except _Redireccion:
        return "vetada", "redirige"
    except FALLOS_DE_RED:
        return "otro_dia", "pagina_no_contesta"
    try:
        _, host_final, dominio_final = normalizar(pagina.get("final") or url)
    except Rechazo:
        return "vetada", "redirige"
    if dominio_final != dominio or es_vetado(host_final, extra):
        return "vetada", "redirige"
    codigo = int(pagina.get("codigo") or 0)
    bloqueo = _bloqueo_en_pagina(pagina)
    if codigo in (401, 403, 407) or bloqueo:
        return "vetada", bloqueo or "bloqueo"
    if codigo == 429:
        return "vetada", "429"
    if codigo >= 500 or codigo == 0:
        return "otro_dia", "pagina_no_contesta"
    if codigo != 200:
        return "fallida", "no_existe"
    if "html" not in str((pagina.get("cabeceras") or {}).get("content-type", "")).lower():
        return "fallida", "no_es_pagina"
    pausa = max(RED["pausa"], float(robots.crawl_delay("*") or 0))
    return "ok", {"url": url, "host": host, "dominio": dominio, "robots": texto[:65536], "pausa": pausa,
                  "extra": [e for e in extra if e == dominio or e.endswith("." + dominio)]}


def _candidatos(cola):
    """Lo pendiente que ya toca: lo del dueño primero y, dentro, por orden de llegada."""
    ahora = _iso()
    listos = [p for p in cola["pedidos"] if p.get("estado") == "pendiente" and str(p.get("no_antes_de") or "") <= ahora]
    return sorted(listos, key=lambda p: (p.get("pedido_por") != "dueño", str(p.get("fecha") or ""), _numero(p["id"])))


def _tapar(*valores):
    """En GitHub, que la web, su host, su dominio y su ruta salgan como *** si algo los imprime por error."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    formas = set()
    for v in valores:
        if not v:
            continue
        v = str(v)
        formas.update({v, urllib.parse.quote(v, safe=""), urllib.parse.quote(v, safe=":/"), v.removeprefix("www.")})
        partes = urllib.parse.urlsplit(v if "://" in v else "https://" + v)
        if partes.hostname:
            formas.update({partes.hostname, dominio_de(partes.hostname)})
            etiqueta = dominio_de(partes.hostname).split(".")[0]
            if len(etiqueta) >= 5:
                formas.add(etiqueta)
        if len(partes.path) >= 6:
            formas.update({partes.path, urllib.parse.quote(partes.path, safe="")})
    for f in sorted(formas, key=len, reverse=True):
        if len(f) >= 4:
            print(f"::add-mask::{f}", flush=True)


def _salida_github(**valores):
    ruta = os.environ.get("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            for k, v in valores.items():
                f.write(f"{k}={v}\n")


def _limpiar_salida(salida):
    for nombre in ("pedido.json", "vigilante.json"):
        try:
            os.remove(os.path.join(salida, nombre))
        except FileNotFoundError:
            pass


def _escribir_json(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def elegir(salida):
    """Elige UN pedido para la caja (o ninguno) y lo deja listo en `salida`. Imprime solo id, estado y cifras."""
    os.makedirs(salida, exist_ok=True)
    _limpiar_salida(salida)
    cola, cfg = leer_cola(), _config()
    _tapar(*(p.get("web") for p in cola["pedidos"] if p.get("estado") in ("pendiente", "en_curso")))
    _mantener(cola)
    elegido, info, linea = None, None, None
    hoy, semana = _uso(cola), _uso(cola, 7)
    cifras = f"hoy {hoy}/{_tope(cfg, 'dia')} · semana {semana}/{_tope(cfg, 'semana')}"
    if not cfg.get("encendido"):
        linea = "capturas: apagado por el dueño"
    elif any(p.get("estado") == "en_curso" for p in cola["pedidos"]):
        linea = "capturas: ya hay una en curso"
    elif hoy >= _tope(cfg, "dia") or semana >= _tope(cfg, "semana"):
        linea = f"capturas: tope alcanzado · {cifras}"
    else:
        for p in _candidatos(cola)[:TOPES["pendientes"]]:
            veredicto, detalle = _revisar(p, cola, cfg)
            if veredicto == "ok":
                elegido, info = p, detalle
                break
            if veredicto == "otro_dia":
                p.update(no_antes_de=_manana(), cambiado=_iso())
                print(f"{p['id']}: pendiente · otro día ({detalle})", flush=True)
                continue
            _terminar(cola, p, veredicto, detalle)
            if detalle in BLOQUEOS:
                _castigar(cola, p.get("dominio") or "", detalle)
            elif p.get("dominio") and detalle not in NO_TOCAN:     # una dirección mal puesta no gasta la web
                _dominio(cola, p["dominio"]).update(ultima=_iso(), motivo=detalle)
            print(f"{p['id']}: {veredicto} · {detalle}", flush=True)
    if elegido:
        _tapar(elegido.get("web"), info["host"], info["dominio"])
        _escribir_json(os.path.join(salida, "pedido.json"), {"id": elegido["id"], "web": info["url"],
                                                              "que": elegido.get("que") or ""})
        _escribir_json(os.path.join(salida, "vigilante.json"), dict(
            RED, dominio=info["dominio"], hosts=[info["host"]], robots={info["host"]: info["robots"]},
            pausa=info["pausa"], prohibidos=list(ENTRADAS), vetados=info["extra"],
            modelos_vetados=sorted(cola["modelos_vetados"])))
        elegido["intentos"] = int(elegido.get("intentos") or 0) + 1
        elegido.update(estado="en_curso", empezada=_iso(), cambiado=_iso())
        elegido.pop("no_antes_de", None)
        _sumar_uso(cola)
        linea = (f"{elegido['id']}: en_curso · intento {elegido['intentos']} · "
                 f"hoy {_uso(cola)}/{_tope(cfg, 'dia')} · semana {_uso(cola, 7)}/{_tope(cfg, 'semana')}")
    elif linea is None:
        linea = f"capturas: nada pendiente · {cifras}"
    guardar_cola(cola)
    _salida_github(hay=1 if elegido else 0, id=elegido["id"] if elegido else "")
    print(linea, flush=True)
    return 0


# ---------------- 3. guardar (después de la caja) ----------------
def _leer_fichero(ruta, tope):
    """Solo ficheros normales (nada de enlaces a otros sitios) y no muy grandes; si no, None."""
    try:
        info = os.lstat(ruta)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > tope:
        return None
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _filas(crudo, campos_dados):
    """Las filas tal cual vengan (lista de dicts, de listas o de valores) → lista de dicts con campos limpios."""
    if isinstance(crudo, dict):
        crudo = next((v for v in crudo.values() if isinstance(v, list)), [crudo])
    if not isinstance(crudo, list):
        return [], []
    campos = [sanear(c, CAMPO) for c in campos_dados or [] if sanear(c, CAMPO)][:CAMPOS]
    filas = []
    for fila in crudo[:FILAS * 2]:
        if isinstance(fila, dict):
            pares = list(fila.items())
        elif isinstance(fila, (list, tuple)):
            pares = [(campos[i] if i < len(campos) else f"campo{i + 1}", v) for i, v in enumerate(fila)]
        else:
            pares = [(campos[0] if campos else "valor", fila)]
        limpia = {}
        for k, v in pares[:CAMPOS]:
            k = sanear(k, CAMPO) or f"campo{len(limpia) + 1}"
            if isinstance(v, bool) or (isinstance(v, (int, float)) and v == v and abs(v) < 1e15):
                limpia[k] = v
            else:
                v = sanear(v)
                if v:
                    limpia[k] = v
        if limpia:
            filas.append(limpia)
        if len(filas) >= FILAS:
            break
    if not campos:
        for fila in filas:
            campos += [k for k in fila if k not in campos]
    return filas, campos[:CAMPOS]


def _resumen(r, filas, campos):
    dado = sanear(r.get("resumen"), RESUMEN)
    if dado:
        return dado
    texto = f"{len(filas)} filas con: {', '.join(campos[:10])}."
    for i, fila in enumerate(filas[:12], 1):
        linea = f" {i}) " + " · ".join(f"{k}: {v}" for k, v in list(fila.items())[:6])
        if len(texto) + len(linea) > RESUMEN:
            break
        texto += linea
    return texto[:RESUMEN]


def _coste(r):
    valor = r.get("coste_usd")
    if valor is None:
        valor = (r.get("usage") or {}).get("total_cost_usd") if isinstance(r.get("usage"), dict) else None
    try:
        return None if valor is None else float(valor)
    except (TypeError, ValueError):
        return None


SIN_MODELO = re.compile(r"modelo gratis|free model|no serving provider|model pairing|provider|opencode|credit|"
                        r"billing|insufficient|quota|payment required")
# Lo que dice la caja (herramientas/caja_capturas) en «motivo» → lo nuestro
CAJA_BLOQUEO = {"captcha": "captcha", "cloudflare": "captcha", "datadome": "captcha", "perimeterx": "captcha",
                "bloqueo_401": "login", "login": "login", "bloqueo_403": "bloqueo", "bloqueo_407": "bloqueo",
                "bloqueo": "bloqueo",
                "bloqueo_429": "429", "web_prohibida": "red_vetada", "red_vetada": "red_vetada", "robots": "robots",
                "har_enorme": "har_enorme"}
RAE_ERRORES = ("engine_failure", "config_invalid", "network", "interrupted", "permission_denied", "misuse", "unknown")
CAJA_REINTENTO = ("caja_sin_resultado", "error_caja", "filtro_roto", "filtro_caido", "caja_abierta", "opencode_no_para",
                  "opencode_no_arranca", "rae_sin_respuesta", "rae_error", *(f"rae_{x}" for x in RAE_ERRORES),
                  "programa")     # fallos nuestros: otro día, una vez más; a la segunda, «programa»
# Las únicas palabras que pueden salir en el registro público (lo demás sale como «otro»)
MOTIVOS_PUBLICOS = frozenset(EXPLICA) | frozenset(CAJA_BLOQUEO) | frozenset(CAJA_BLOQUEO.values()) | \
    frozenset(CAJA_REINTENTO)


def _palabra(texto):
    t = str(texto or "").strip().lower()
    return t if re.fullmatch(r"[a-z0-9_]{1,30}", t) else None


def _veredicto(r, extra=()):
    """Qué ha pasado en la caja → (estado, motivo); estado «reintento» si es un fallo nuestro que se puede repetir.
    Lo dudoso cuenta como fallo, nunca como éxito. Va en este orden: una red o web prohibida vista en la caja, un
    modelo que cobra, que no hubo modelo gratis (los avisos de OpenCode nunca castigan a la web), un bloqueo de la
    web, lo que la caja ya da por fallido y, por fin, el éxito (con su coste apuntado)."""
    estado = str(r.get("estado") or "").lower()
    rae = r.get("rae") if isinstance(r.get("rae"), dict) else {}
    status = str(r.get("status") or rae.get("status") or "").lower()
    motivo = _palabra(r.get("motivo"))
    marcas = r.get("marcas") if isinstance(r.get("marcas"), list) else []
    texto = " ".join(str(r.get(k) or "") for k in ("motivo", "error", "error_kind")).lower()
    texto += " " + " ".join(str(m) for m in marcas[:20]).lower()
    if any(es_vetado(h, extra) for h in r.get("hosts") or [] if isinstance(h, str)):
        return "vetada", "red_vetada"
    coste = _coste(r)
    if (coste is not None and coste > 0) or motivo == "de_pago":
        return "fallida", "coste"
    if estado in ("sin_modelo_gratis", "sin_modelo") or (estado != "fallida" and status != "ok"
                                                          and not motivo and SIN_MODELO.search(texto)):
        return "sin_modelo_gratis", "sin_modelo_gratis"
    if estado in ("bloqueada", "vetada", "captcha", "login") or r.get("bloqueo") or marcas or (
            estado not in ("hecha", "fallida") and
            re.search(r"captcha|cloudflare|datadome|perimeterx|robot|login|iniciar sesi|\b(401|403|429)\b", texto)):
        if motivo in CAJA_BLOQUEO:
            return "vetada", CAJA_BLOQUEO[motivo]
        if "robots" in texto and not re.search(r"captcha|login|\b(401|403|429)\b", texto):
            return "vetada", "robots"
        return "vetada", ("captcha" if re.search(r"captcha|cloudflare|datadome|perimeterx|robot|_px|cf-", texto) else
                          "login" if re.search(r"login|iniciar sesi|\b401\b", texto) else
                          "429" if "429" in texto else "bloqueo")
    if estado == "fallida":
        if motivo in CAJA_REINTENTO or (motivo or "").startswith("rae_"):
            return "reintento", motivo
        return "fallida", motivo or "programa"
    if estado in ("hecha", "ok") or (not estado and status == "ok"):
        return ("fallida", "sin_coste") if coste is None else ("hecha", "hecha")
    if estado == "sin_datos":
        return "fallida", "sin_datos"
    return "reintento", "programa"


def _lo_de_la_ficha(r, estado, motivo, filas, campos, coste):
    """Las cifras de la captura y, si salió, sus datos limpios (la ficha entera cabe en 200 KB)."""
    extra = {"coste_usd": coste}
    for k, tope in (("segundos", 10 ** 5), ("peticiones", 10 ** 4)):
        if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool):
            extra[k] = int(max(0, min(tope, r[k])))
    if re.fullmatch(r"[A-Za-z0-9/._-]{1,60}", str(r.get("modelo") or "")):
        extra["modelo"] = r["modelo"]
    if motivo in AVISOS:
        extra["aviso"] = AVISOS[motivo]
    if estado == "hecha":
        extra.update(filas=len(filas), campos=campos, datos=filas, resumen=_resumen(r, filas, campos))
        while filas and len(json.dumps(extra, ensure_ascii=False).encode("utf-8")) > FICHA_BYTES:
            filas.pop()
            extra.update(filas=len(filas), datos=filas)
    return extra


def guardar(id_, carpeta):
    """Apunta lo que salió de la caja: ficha limpia, cola al día y castigos de dominio. Imprime solo cifras."""
    cola = leer_cola()
    p = next((x for x in cola["pedidos"] if x.get("id") == id_), None)
    if p is None:
        print(f"{id_}: no está en la cola", flush=True)
        return 0
    _tapar(p.get("web"), p.get("dominio"))
    if p.get("estado") in FINALES:
        print(f"{id_}: ya estaba {p['estado']}", flush=True)
        return 0
    r = _leer_fichero(os.path.join(carpeta, "resultado.json"), RESULTADO_BYTES)
    if not isinstance(r, dict) or r.get("id") not in (None, id_):            # sin resultado, o es de otro pedido
        r = {"estado": "fallida", "motivo": "caja_sin_resultado"}
    estado, motivo = _veredicto(r, _lista(_config(), "vetados_extra"))
    filas, campos, coste = [], [], _coste(r)
    if estado == "hecha":
        aparte = _leer_fichero(os.path.join(carpeta, "datos.json"), RESULTADO_BYTES)
        filas, campos = _filas(r.get("datos") if r.get("datos") is not None else aparte, r.get("campos"))
        if not filas:
            estado, motivo = "fallida", "sin_datos"
    if (coste is not None and coste > 0) or motivo == "coste":   # ha cobrado: ese modelo no se vuelve a usar nunca
        modelo = str(r.get("modelo") or "")                       # (elegir se lo pasa a la caja en vigilante.json)
        modelo = modelo if re.fullmatch(r"[A-Za-z0-9/._-]{1,60}", modelo) else "desconocido"
        cola["modelos_vetados"][modelo] = f"cobró {coste if coste is not None else '?'} $ el {_iso()[:10]}"
    causa = None
    if estado == "reintento":
        if int(p.get("intentos") or 0) < INTENTOS:
            p.update(estado="pendiente", empezada=None, no_antes_de=_manana(), cambiado=_iso(), motivo=motivo)
            guardar_cola(cola)
            print(f"{id_}: pendiente · lo repito otro día · intento {p.get('intentos')}/{INTENTOS}", flush=True)
            return 0
        # el mismo fallo nuestro dos veces: es cosa del programa (el Cerebro se lo pasa a Claude, una vez)
        estado, causa, motivo = "fallida", motivo, "programa"
    if estado == "sin_modelo_gratis":           # no llegó a mirar la web: no gasta del tope de ese día
        _sumar_uso(cola, "devueltas", p.get("empezada"))
    extra = _lo_de_la_ficha(r, estado, motivo, filas, campos, coste)
    if causa:
        extra["causa"] = causa
    _terminar(cola, p, estado, motivo, extra)
    if motivo in BLOQUEOS:
        _castigar(cola, p.get("dominio") or "", motivo)
    elif p.get("dominio") and estado != "sin_modelo_gratis":          # sin modelo no llegó a mirar la web
        _dominio(cola, p["dominio"]).update(ultima=_iso(), motivo=None if estado == "hecha" else motivo)
    guardar_cola(cola)
    _apuntar_cuaderno(p, estado, motivo, len(filas))
    minutos = f" · {round(extra['segundos'] / 60)} min" if "segundos" in extra else ""
    pet = f" · {extra['peticiones']} peticiones" if "peticiones" in extra else ""
    euros = "?" if coste is None else f"{coste:g}"
    publico = motivo if motivo in MOTIVOS_PUBLICOS else "otro"     # nunca una palabra que no sea nuestra
    print(f"{id_}: {estado} · {len(filas)} filas · {euros} $" + pet + minutos +
          ("" if estado == "hecha" else f" · {publico}"), flush=True)
    return 0


def _apuntar_cuaderno(p, estado, motivo, filas):
    try:
        c = privado.cuaderno("investigador_webs")      # el suyo («investigador» es el de Influencers)
        c.apuntar("captura", {"id": p["id"], "estado": estado, "motivo": motivo, "filas": filas,
                              "pedido_por": p.get("pedido_por")})
        c.guardar()
    except Exception:
        pass


def _apuntar_averia(paso, error):
    """El detalle de un fallo del programa va al repositorio privado (nunca al registro público)."""
    try:
        averias = (privado.leer(AVERIAS, {}) or {}).get("averias") or []
        averias.append({"fecha": _iso(), "paso": paso, "error": f"{type(error).__name__}: {str(error)[:300]}",
                        "traza": traceback.format_exc()[-3000:]})
        privado.escribir(AVERIAS, {"averias": averias[-20:], "actualizado": _iso()})
    except Exception:
        pass


# ---------------- para el Cerebro y la app ----------------
def explicar(estado, motivo):
    """Lo que ha pasado, en sencillo, para contárselo al dueño."""
    texto = EXPLICA.get(motivo) or EXPLICA.get(estado) or "No ha salido."
    if motivo in BLOQUEOS:
        texto += " No vuelvo a esa web en 30 días (si vuelve a pasar, nunca más)."
    return texto


def resumen_para_directo():
    """El apartado «capturas» de directo.json: cuántas van y qué hay en la cola (sin la dirección completa)."""
    cola, cfg = leer_cola(), _config()

    def corta(p):
        return {"id": p.get("id"), "dominio": p.get("dominio"), "que": p.get("que"), "estado": p.get("estado"),
                "cuenta": p.get("cuenta"), "pedido_por": p.get("pedido_por"), "fecha": p.get("fecha")}
    terminados = [p for p in cola["pedidos"] if p.get("estado") in FINALES]
    ultimas = []
    for p in sorted(terminados, key=lambda x: str(x.get("terminada") or x.get("fecha") or ""))[-8:]:
        ficha = privado.leer(ruta_ficha(p["id"]), {}) or {}
        ultimas.append(dict(corta(p), filas=int(ficha.get("filas") or 0), motivo=p.get("motivo"),
                            fecha=p.get("terminada") or p.get("fecha")))
    return {"encendido": bool(cfg.get("encendido")), "hoy": _uso(cola), "semana": _uso(cola, 7),
            "tope_dia": _tope(cfg, "dia"), "tope_semana": _tope(cfg, "semana"),
            "pendientes": [corta(p) for p in cola["pedidos"] if p.get("estado") in ("pendiente", "en_curso")],
            "ultimas": ultimas}


def terminadas(vistas=()):
    """Las capturas ya terminadas que el Cerebro no ha visto: su ficha (datos limpios) y lo del pedido (cuenta,
    dominio, qué, para qué, quién lo pidió y su mensaje), con «explicacion» en sencillo para el dueño."""
    vistas = set(vistas or ())
    salida = []
    for p in leer_cola()["pedidos"]:
        if p.get("estado") not in FINALES or p.get("id") in vistas:
            continue
        ficha = privado.leer(ruta_ficha(p["id"]), None)
        ficha = dict(ficha) if isinstance(ficha, dict) else {
            "id": p["id"], "fecha": p.get("terminada") or p.get("fecha"), "filas": 0, "campos": [], "datos": [],
            "resumen": "", "motivo": p.get("motivo"), "coste_usd": 0.0}
        ficha.update(estado=p["estado"], resumen=sanear(ficha.get("resumen"), RESUMEN),
                     explicacion=explicar(p["estado"], ficha.get("motivo") or p.get("motivo")),
                     **{k: p.get(k) for k in ("cuenta", "dominio", "que", "para", "pedido_por", "mensaje")})
        salida.append(ficha)
    return salida


# ---------------- órdenes ----------------
def main(argv=None):
    warnings.simplefilter("ignore")              # ningún aviso de las librerías (pueden llevar el host) al registro
    p = argparse.ArgumentParser(description="El Investigador de webs (ver el principio del fichero).")
    ordenes = p.add_subparsers(dest="orden", required=True)
    e = ordenes.add_parser("elegir", help="elige el siguiente pedido para la caja")
    e.add_argument("--salida", required=True)
    g = ordenes.add_parser("guardar", help="guarda lo que ha dejado la caja")
    g.add_argument("--id", required=True)
    g.add_argument("--resultado", required=True)
    a = p.parse_args(argv)
    nombre = getattr(a, "id", None) or "capturas"
    if a.orden == "guardar" and not re.fullmatch(r"cap-\d{1,6}", nombre):
        print("capturas: ese id no es de una captura", flush=True)
        return 2
    try:
        return elegir(a.salida) if a.orden == "elegir" else guardar(a.id, a.resultado)
    except Exception as error:                  # nada del fallo (puede llevar la web) sale al registro público
        _apuntar_averia(a.orden, error)
        print(f"{nombre}: error del programa ({type(error).__name__})", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
