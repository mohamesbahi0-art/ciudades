"""Simulacro del Investigador de webs (bots/cerebro/capturas.py), SIN RED: robots.txt, páginas y DNS de mentira.
Comprueba el portero (todas las direcciones prohibidas, privacidad, topes, huella repetida y lo que pide el Cerebro
solo), `elegir` (robots.txt, bloqueos, topes y colgados), `guardar` (éxito limpio, captcha, coste, sin modelo gratis,
reintentos), la fusión de la cola, lo que va a la app y que NADA de lo que imprime el turno lleve la web, su dominio
ni el nombre de una cuenta. (El vigilante del programa de la IA se prueba en pruebas/simulacro_caja.py.)

    python pruebas/simulacro_capturas.py
"""
import contextlib
import datetime as dt
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
TMP = tempfile.mkdtemp(prefix="capturas-")
PRIVADO = os.path.join(TMP, "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
os.environ.pop("GITHUB_ACTIONS", None)
SALIDA_GH = os.path.join(TMP, "github_output")
os.environ["GITHUB_OUTPUT"] = SALIDA_GH
from bots.comun import privado  # noqa: E402
from bots.cerebro import capturas  # noqa: E402

_getaddrinfo = socket.getaddrinfo


def sin_red(host, *a, **k):                  # en este simulacro nada sale de la máquina
    if str(host) not in ("localhost", "127.0.0.1", "::1"):
        raise OSError("simulacro sin red")
    return _getaddrinfo(host, *a, **k)


socket.getaddrinfo = sin_red

WEB, HOST, DOMINIO = "https://datos.ejemplo.org/ranking", "datos.ejemplo.org", "ejemplo.org"
CUENTA = "barrio.prueba"                        # el nombre de verdad de la cuenta de prueba (nunca debe salir)
NOMBRES = (CUENTA, "Barrio de prueba", "Canal de historias de prueba")
QUE = "título, puesto y fecha de los 50 primeros del ranking semanal"
FALLOS = 0
SALIDAS = []


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    FALLOS += 0 if vale else 1


def hace(**cuanto):
    return capturas._iso(capturas._ahora() - dt.timedelta(**cuanto))


def config(**cfg):
    base = privado.leer(os.path.join("config", "fabrica.json"), {}) or {}
    base["capturas"] = dict({"encendido": True, "vetados_extra": ["secreta.ejemplo.net"],
                             "permitidos": ["permitida.ejemplo.net", "lista.ejemplo.com"]}, **cfg)
    privado.escribir(os.path.join("config", "fabrica.json"), base)


def vaciar():
    shutil.rmtree(os.path.join(PRIVADO, "estado", "capturas"), ignore_errors=True)


def cola():
    return capturas.leer_cola()


def poner_cola(pedidos, **mas):
    privado.escribir(capturas.COLA, dict({"pedidos": pedidos, "dominios": {}, "uso": {}}, **mas))


def pedido(id_, web=WEB, estado="pendiente", fecha=None, pedido_por="dueño", **mas):
    url, host, dominio = capturas.normalizar(web)
    return dict({"id": id_, "huella": capturas.huella(url, dominio), "estado": estado, "fecha": fecha or hace(minutes=5),
                 "pedido_por": pedido_por, "mensaje": "m1", "cuenta": CUENTA, "web": url, "dominio": dominio,
                 "que": QUE, "para": "elegir temas", "intentos": 0, "empezada": None, "resultado": None}, **mas)


def del_dueno(web, que=QUE, **k):
    """Un pedido del dueño con la dirección en su mensaje (así se prueban las demás reglas)."""
    return capturas.pedir(web, que, pedido_por="dueño", mensaje={"id": "m1", "texto": f"Mira {web} porfa"}, **k)


def orden(*args, entorno=None):
    """Una orden del turno, recogiendo TODO lo que imprime (para mirar luego que no lleva nada privado)."""
    buf = io.StringIO()
    antes = dict(os.environ)
    os.environ.update(entorno or {})
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            codigo = capturas.main(list(args))
    finally:
        os.environ.clear()
        os.environ.update(antes)
    SALIDAS.append(buf.getvalue())
    return codigo, buf.getvalue()


def salida_github():
    try:
        with open(SALIDA_GH, encoding="utf-8") as f:
            texto = f.read()
    except FileNotFoundError:
        return {}
    os.remove(SALIDA_GH)
    return dict(linea.split("=", 1) for linea in texto.splitlines() if "=" in linea)


# ---------------- la red de mentira ----------------
ROBOTS, PAGINAS, IPS = {}, {}, {}
HTML = {"codigo": 200, "cabeceras": {"content-type": "text/html; charset=utf-8"},
        "cuerpo": "<html><head><title>Ranking semanal</title></head><body>" + "dato " * 2000 + "</body></html>"}


def robots_falso(url, dominio, extra=()):
    r = ROBOTS.get(urllib.parse.urlsplit(url).hostname, (404, ""))
    if isinstance(r, BaseException):
        raise r
    return r


def pagina_falsa(url, dominio, extra=()):
    r = PAGINAS.get(url, HTML)
    if isinstance(r, BaseException):
        raise r
    return dict({"final": url}, **r)


def resolver_falso(host):
    r = IPS.get(host, ["93.184.215.14"])
    if isinstance(r, BaseException):
        raise r
    return r


capturas.LEER_ROBOTS, capturas.LEER_PAGINA, capturas.RESOLVER = robots_falso, pagina_falsa, resolver_falso

# ======================= 0. Las normas fijas =======================
comprobar("los topes son los del dueño (2 al día, 5 a la semana, 3 esperando, 1 al mes por web, 1 del Cerebro por "
          "cuenta y semana)", capturas.TOPES == {"dia": 2, "semana": 5, "pendientes": 3, "por_dominio_dias": 30,
                                                 "cerebro_por_cuenta_semana": 1})
comprobar("la lista de vetados lleva TikTok, Instagram, YouTube y las demás redes",
          all(d in capturas.VETADOS for d in ("tiktok.com", "instagram.com", "youtube.com", "youtu.be", "facebook.com",
                                              "threads.net", "x.com", "twitter.com", "snapchat.com", "pinterest.com",
                                              "linkedin.com", "reddit.com", "twitch.tv", "discord.com", "t.me",
                                              "whatsapp.com", "accounts.google.com", "appleid.apple.com")))

comprobar("las tiendas de Amazon están vetadas, pero no los datos públicos en sus servidores (S3, API Gateway) ni "
          "webs como amazonas o redditch",
          capturas.es_vetado("www.amazon.es") == "red" and capturas.es_vetado("amazon-adsystem.com") == "red"
          and not capturas.es_vetado("mybucket.s3.amazonaws.com")
          and not capturas.es_vetado("x.execute-api.eu-west-1.amazonaws.com")
          and not capturas.es_vetado("amazonas.gob.pe") and not capturas.es_vetado("redditch.gov.uk")
          and capturas.es_vetado("tiktokcdn-eu.com") == "red" and capturas.es_vetado("googlevideo.com") == "red")
comprobar("el dueño solo puede apretar los topes: menos capturas o más días entre visitas a la misma web, nunca al revés",
          capturas._tope({"topes": {"por_dominio_dias": 0}}, "por_dominio_dias") == 30
          and capturas._tope({"topes": {"por_dominio_dias": 90}}, "por_dominio_dias") == 90
          and capturas._tope({"topes": {"dia": 9}}, "dia") == 2 and capturas._tope({"topes": {"dia": 1}}, "dia") == 1)

# ======================= 1. El portero =======================
config()
PROHIBIDAS = [
    "https://www.tiktok.com/@x", "https://m.youtube.com/watch?v=1", "https://youtu.be/x", "https://help.instagram.com",
    "http://datos.ejemplo.org", "https://127.0.0.1/", "https://login.ejemplo.org/", "https://usuario:clave@ejemplo.org/",
    "https://tiktok.com./", "https://TikTok.COM/foryou", "https://www.tiktok.com.@ejemplo.org/",
    "https://ejemplo.org\\@tiktok.com/", "https://ejemplo.org@tiktok.com/", "https://xn--tktok-xxa.com/",
    "https://tіktok.com/", "https://localhost/", "https://intranet.local/", "https://servidor.internal/",
    "https://ejemplo.org:8443/", "https://ejemplo.org/?token=abc", "https://ejemplo.org/datos?api_key=1",
    "https://ejemplo.org/datos?sessionid=1", "https://ejemplo.org/datos?auth=1", "https://ejemplo.org/datos?sig=1",
    "https://ejemplo.org/datos#access_token=1", "https://[::1]/", "https://2130706433/", "https://0x7f.0.0.1/",
    "https://169.254.169.254/latest/meta-data", "https://accounts.google.com/", "https://www.google.es/search?q=x",
    "https://appleid.apple.com/", "https://www.facebook.com/pagina", "https://www.threads.net/@x", "https://x.com/u",
    "https://twitter.com/u", "https://www.reddit.com/r/x", "https://www.linkedin.com/in/x", "https://www.pinterest.es/x",
    "https://www.twitch.tv/x", "https://discord.gg/x", "https://t.me/x", "https://wa.me/1", "https://sso.ejemplo.org/",
    "https://auth.ejemplo.org/", "https://ejemplo.org/login", "https://ejemplo.org/wp-admin/",
    "https://ejemplo.org/AbCdEf0123456789AbCdEf0123456789xyz", "https://ejemplo.org/" + "a" * 300, "ftp://ejemplo.org/",
    "javascript:alert(1)", "https://ejemplo .org/", "https://secreta.ejemplo.net/x", "https://www.amazon.es/x",
    "https://archive.org/details/x", "https://github.com/x", "https://ejemplo.org/perfil/@usuario", ""]
dejadas = [w for w in PROHIBIDAS if del_dueno(w)[0] or del_dueno(w)[2]]
comprobar(f"rechaza las {len(PROHIBIDAS)} direcciones prohibidas (redes, IP, logins, trampas con punto final, "
          "mayúsculas, @, \\, letras raras, puertos, llaves y las vetadas del dueño)", not dejadas)
if dejadas:
    print("   se cuelan:", dejadas)
comprobar("y no apunta nada en la cola", not cola()["pedidos"])
texto_red = del_dueno("https://www.tiktok.com/@x")[1]
comprobar("explica en sencillo por qué (una red social nunca)", "red social" in texto_red and "TikTok" in texto_red)
ok, texto, id1 = del_dueno(WEB)
c = cola()
comprobar("una web pública normal entra en la cola como «pendiente», con su huella, quién la pidió y su mensaje",
          ok and id1 == "cap-1" and c["pedidos"][0]["estado"] == "pendiente" and c["pedidos"][0]["pedido_por"] == "dueño"
          and c["pedidos"][0]["mensaje"] == "m1" and len(c["pedidos"][0]["huella"]) == 16
          and c["pedidos"][0]["web"] == WEB and c["pedidos"][0]["dominio"] == DOMINIO)
comprobar("lo que contesta al dueño no lleva la dirección ni el dominio", DOMINIO not in texto and "cap-1" in texto)
VALEN = ["https://ejemplo.org/blog?author=pepe&page=2", "https://ejemplo.org/horoscopo?signo=aries",
         "https://www.bbc.co.uk/sport/football/tables", "https://ejemplo.org/temas/2026-11-26-lo-mas-visto"]
comprobar("y deja pasar direcciones normales (?author=, ?signo=, ?page=, dominios .co.uk, rutas con fecha)",
          all(capturas.normalizar(w) for w in VALEN))
comprobar("normaliza: «tiktok.com.» y «TikTok.COM» son TikTok; quita el punto final y pasa a minúsculas",
          capturas.normalizar("https://Datos.Ejemplo.ORG./ranking")[0] == WEB
          and capturas.es_vetado(capturas.dominio_de("tiktok.com")) == "red")

vaciar()
CASOS_QUE = {"corto": "top", "con @": "los vídeos de @pepe", "con correo": "lo que escribe pepe@correo.es",
             "con id de canal": "los datos del canal UC" + "x" * 22, "con el nombre de la cuenta": "lo que dice Barrio de prueba",
             "de personas": "los teléfonos de contacto de los vecinos", "datos personales": "los datos personales de socios"}
malos = [k for k, q in CASOS_QUE.items() if del_dueno(WEB, q)[0]]
comprobar("rechaza lo que pide si es corto, lleva @, correos, ids de canal, el nombre de una cuenta o datos de personas",
          not malos and not cola()["pedidos"])
comprobar("rechaza la web si lleva el nombre de una cuenta", not del_dueno("https://ejemplo.org/barrio.prueba/top")[0])
ESCRITOS = [del_dueno("https://stats.ejemplo.org/canal/canal-de-noticias-de-prueba"),
            del_dueno("https://stats.ejemplo.org/canal/barrioprueba"), del_dueno(WEB, "ranking del canal de noticias de prueba")]
comprobar("…aunque venga escrito de otra manera (con guiones, sin puntos o en minúsculas), y lo explica",
          not any(x[0] for x in ESCRITOS) and all("cuentas" in x[1] for x in ESCRITOS) and not cola()["pedidos"])
comprobar("y en lo que llega de una web también se quita (o se tira el texto)",
          capturas.sanear("lo comparte canal-de-noticias-de-prueba hoy") == "lo comparte hoy"
          and capturas.sanear("Barrioprueba lo dice") == "lo dice"
          and "noticias" not in capturas.sanear("el CANAL DE NOTÍCIAS DE PRUEBA lo dice"))
DISFRACES = ["ejemplo(.)com", "ejemplo [dot] com", "ejemplo . com", "ejemplo．com", "＠pepe", "ejemplo dot com"]
comprobar("los dominios disfrazados («(.)», « . », «dot», el punto de ancho completo) y la arroba de ancho completo "
          "también se quitan", [capturas.sanear(f"mira {d} hoy") for d in DISFRACES] == ["mira hoy"] * len(DISFRACES)
          and capturas.sanear("desde mi punto de vista. Siguiente frase, 1.200 visitas")
          == "desde mi punto de vista. Siguiente frase, 1.200 visitas")
ok, _, _ = del_dueno(WEB, "títulos del top 50 (como en https://otra.ejemplo.net/x y www.otra.com)\ncon\tfecha")
p = cola()["pedidos"][0] if cola()["pedidos"] else {}
comprobar("a lo que pide le quita enlaces y saltos de línea", ok and "http" not in p.get("que", "x") and "\n" not in p.get("que", "")
          and "otra.com" not in p.get("que", "x"))

vaciar()
ok1 = capturas.pedir(WEB, QUE, pedido_por="dueño", mensaje={"id": "m2", "texto": "Mira la web de recetas que te dije"})[0]
privado.escribir(os.path.join("estado", "cerebro", "buzon.json"),
                 {"mensajes": [{"id": "m3", "texto": "Mira datos.ejemplo.org porfa"},
                               {"id": "m4", "texto": f"Saca el top de {WEB}."}]})
ok2 = capturas.pedir(WEB, QUE, pedido_por="dueño", mensaje="m3")[0]
ok3 = capturas.pedir("https://datos.ejemplo.org/", QUE, pedido_por="dueño", mensaje="m3")[0]
vaciar()
ok4 = capturas.pedir(WEB, QUE, pedido_por="dueño", mensaje="m4")[0]
comprobar("lo del dueño solo vale si la dirección está en su mensaje (la IA no se inventa direcciones; vale el id "
          "del buzón o el mensaje entero, y su dominio solo para la portada)", not ok1 and not ok2 and ok3 and ok4)

vaciar()
config(encendido=False)
comprobar("con el interruptor del dueño apagado no apunta nada", not del_dueno(WEB)[0] and not cola()["pedidos"])
base = privado.leer(os.path.join("config", "fabrica.json"), {})
base.pop("capturas", None)
privado.escribir(os.path.join("config", "fabrica.json"), base)
comprobar("sin el apartado «capturas» en la configuración, también apagado", not del_dueno(WEB)[0])
config()
privado.escribir(os.path.join("estado", "elite", "ajustes.json"), {"fabrica": {"capturas.encendido": True}})
config(encendido=False)
comprobar("ni la Élite puede encenderlo (se lee config/fabrica.json tal cual)", not del_dueno(WEB)[0])
privado.escribir(os.path.join("estado", "elite", "ajustes.json"), {})
config()

# ---- topes y huella ----
vaciar()
ok, _, a = del_dueno(WEB)
dos = del_dueno(WEB)
comprobar("la misma web dos veces solo entra una (y dice cuál es la que ya está)", ok and dos[0] is False and dos[2] == a
          and len(cola()["pedidos"]) == 1)
comprobar("otra página del mismo dominio ese mes, tampoco (una vez al mes por web)",
          not del_dueno("https://ejemplo.org/otra-lista")[0])
ok_b = del_dueno("https://precios.ejemplo.com/lista")[0]
ok_c = del_dueno("https://temas.ejemplo.net/top")[0]
comprobar("el tercero del día se rechaza aunque lo pida el dueño", ok_b and not ok_c and len(cola()["pedidos"]) == 2)
vaciar()
poner_cola([pedido(f"cap-{i}", f"https://web{i}.ejemplo.com/top", fecha=hace(days=2)) for i in (1, 2, 3)])
comprobar("con 3 esperando, el cuarto se rechaza", not del_dueno(WEB)[0] and len(cola()["pedidos"]) == 3)
vaciar()
uso = {(capturas._ahora() - dt.timedelta(days=d)).date().isoformat(): {"capturas": 1} for d in range(1, 6)}
poner_cola([], uso=uso)
comprobar("con 5 capturas esta semana, no apunta más", not del_dueno(WEB)[0])
vaciar()
poner_cola([], dominios={DOMINIO: {"ultima": hace(days=40), "fallos": 1, "vetado_hasta": capturas._iso(
    capturas._ahora() + dt.timedelta(days=3)), "motivo": "captcha"}})
comprobar("una web castigada por captcha no se pide hasta que pase el castigo", not del_dueno(WEB)[0])
vaciar()
ok_p, _, _ = del_dueno(WEB, prueba=True)
comprobar("con prueba=True lo comprueba todo pero no escribe la cola", ok_p and not cola()["pedidos"])

# ---- lo que pide el Cerebro él solo ----
vaciar()
r1 = capturas.pedir(WEB, QUE, cuenta=CUENTA)
r2 = capturas.pedir("https://permitida.ejemplo.net/top", QUE, cuenta=CUENTA)
r3 = capturas.pedir("https://lista.ejemplo.com/top", QUE, cuenta="terror")
comprobar("el Cerebro solo pide webs que el dueño ya pidió o que están permitidas, y una a la semana en total",
          not r1[0] and "permitidas" in r1[1] and r2[0] and not r3[0] and "semana" in r3[1]
          and cola()["pedidos"][0]["pedido_por"] == "cerebro" and cola()["pedidos"][0]["cuenta"] == CUENTA)
vaciar()
poner_cola([pedido("cap-1", WEB, estado="hecha", fecha=hace(days=40))])
r4 = capturas.pedir("https://datos.ejemplo.org/semana", QUE, cuenta=CUENTA)
comprobar("…y una web que el dueño pidió hace más de un mes sí puede volver a pedirla", r4[0])

# ======================= 2. Elegir (antes de la caja) =======================
DIR = os.path.join(TMP, "caja")


def elegir(**entorno):
    salida_github()
    codigo, texto = orden("elegir", "--salida", DIR, entorno=entorno)
    return codigo, texto, salida_github()


def leer(nombre):
    try:
        with open(os.path.join(DIR, nombre), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


vaciar()
ROBOTS[HOST] = (200, "User-agent: *\nDisallow: /privado\nCrawl-delay: 3\n")
poner_cola([pedido("cap-1")], modelos_vetados={"opencode/de-pago": "cobró 0.02 $"})
codigo, texto, gh = elegir()
c = cola()
comprobar("con robots.txt que deja, la elige: pedido.json solo con id, web y qué; hay=1 e id para el turno",
          codigo == 0 and gh == {"hay": "1", "id": "cap-1"} and leer("pedido.json") == {"id": "cap-1", "web": WEB, "que": QUE})
v = leer("vigilante.json") or {}
comprobar("deja las reglas del vigilante: su host, su robots.txt, la pausa del Crawl-delay (3 s) y los topes",
          v.get("hosts") == [HOST] and "Disallow: /privado" in v.get("robots", {}).get(HOST, "") and v.get("pausa") == 3
          and v.get("max_peticiones") == 30 and v.get("max_bytes") == 5_000_000 and v.get("dominio") == DOMINIO)
comprobar("y los modelos que cobraron alguna vez, para que la caja no los vuelva a usar",
          v.get("modelos_vetados") == ["opencode/de-pago"])
comprobar("y la marca «en_curso» con un intento más y una captura más hoy, antes de capturar",
          c["pedidos"][0]["estado"] == "en_curso" and c["pedidos"][0]["intentos"] == 1 and capturas._uso(c) == 1)
codigo, texto, gh = elegir()
comprobar("con una en curso no elige otra (una a la vez)", gh.get("hay") == "0" and leer("pedido.json") is None)

vaciar()
poner_cola([pedido("cap-1", "https://datos.ejemplo.org/privado/top"), pedido("cap-2", "https://otra.ejemplo.com/top")])
codigo, texto, gh = elegir()
c = {p["id"]: p for p in cola()["pedidos"]}
comprobar("una ruta que robots.txt prohíbe queda «vetada» y elige la siguiente en la misma pasada",
          c["cap-1"]["estado"] == "vetada" and c["cap-1"]["motivo"] == "robots" and gh.get("id") == "cap-2"
          and not capturas._castigada(cola(), DOMINIO))

vaciar()
ROBOTS[HOST] = (403, "")
poner_cola([pedido("cap-1")])
elegir()
c, d = cola(), cola()["dominios"].get(DOMINIO, {})
comprobar("robots.txt con 403 lo prohíbe todo: vetada y la web castigada 30 días",
          c["pedidos"][0]["estado"] == "vetada" and c["pedidos"][0]["motivo"] == "robots_prohibe"
          and hace(days=-29) < str(d.get("vetado_hasta")) < hace(days=-31))
vaciar()
ROBOTS[HOST] = (503, "")
poner_cola([pedido("cap-1")])
_, _, gh = elegir()
p = cola()["pedidos"][0]
comprobar("robots.txt con 5xx: se deja para otro día (sigue pendiente, sin gastar intento)",
          gh.get("hay") == "0" and p["estado"] == "pendiente" and p["intentos"] == 0 and p["no_antes_de"] > capturas._iso())
_, _, gh = elegir()
comprobar("y ese mismo día no se vuelve a probar", gh.get("hay") == "0" and cola()["pedidos"][0]["estado"] == "pendiente")
vaciar()
ROBOTS[HOST] = TimeoutError("tarda")
poner_cola([pedido("cap-1")])
elegir()
comprobar("robots.txt que no contesta (tiempo agotado): otro día", cola()["pedidos"][0].get("no_antes_de"))
vaciar()
ROBOTS[HOST] = (404, "")
poner_cola([pedido("cap-1")])
_, _, gh = elegir()
comprobar("sin robots.txt (404) deja pasar", gh.get("hay") == "1")

CASOS_PAGINA = {
    "captcha (cf-mitigated)": (dict(HTML, cabeceras={"content-type": "text/html", "cf-mitigated": "challenge"}),
                               "vetada", "captcha"),
    "«eres un robot»": (dict(HTML, cuerpo="<title>Un momento</title>Are you a robot? Verify you are human"),
                        "vetada", "captcha"),
    "página de entrar": (dict(HTML, cuerpo="<title>Iniciar sesión</title><input type='password' name='p'>"),
                         "vetada", "login"),
    "403": (dict(HTML, codigo=403), "vetada", "bloqueo"),
    "429": (dict(HTML, codigo=429), "vetada", "429"),
    "manda a otro dominio": (dict(HTML, final="https://otra-web.ejemplo.com/"), "vetada", "redirige"),
    "manda a un login del dominio": (capturas._Redireccion("redirige"), "vetada", "redirige"),
    "no existe (404)": (dict(HTML, codigo=404), "fallida", "no_existe"),
    "no es una página": (dict(HTML, cabeceras={"content-type": "application/pdf"}), "fallida", "no_es_pagina"),
}
for nombre, (respuesta, estado, motivo) in CASOS_PAGINA.items():
    vaciar()
    PAGINAS[WEB] = respuesta
    poner_cola([pedido("cap-1")])
    _, _, gh = elegir()
    p = cola()["pedidos"][0]
    castigo = bool(capturas._castigada(cola(), DOMINIO))
    comprobar(f"la página {nombre}: {estado} ({motivo})" + (", con castigo a la web" if motivo in capturas.BLOQUEOS
                                                            else ""),
              gh.get("hay") == "0" and p["estado"] == estado and p["motivo"] == motivo
              and castigo == (motivo in capturas.BLOQUEOS)
              and (privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}).get("estado") == estado)
PAGINAS.clear()
vaciar()
PAGINAS[WEB] = dict(HTML, codigo=404)
poner_cola([pedido("cap-1")])
elegir()
PAGINAS.clear()
ok_buena = del_dueno("https://datos.ejemplo.org/ranking-bueno")[0]
comprobar("si la dirección estaba mal (404), la buena del mismo sitio se puede pedir enseguida (no gasta el «una vez "
          "al mes por web»)", ok_buena and not (cola()["dominios"].get(DOMINIO) or {}).get("ultima"))
vaciar()
IPS[HOST] = ["10.0.0.5"]
poner_cola([pedido("cap-1")])
elegir()
comprobar("una web que apunta a una IP de dentro: vetada", cola()["pedidos"][0]["motivo"] == "ip_no_publica")
IPS.clear()

manejador = capturas._MismoDominio(DOMINIO)
import urllib.request  # noqa: E402
req = urllib.request.Request(WEB)


def sigue(nueva):
    try:
        return manejador.redirect_request(req, None, 302, "Found", {}, nueva) is not None
    except capturas._Redireccion:
        return False


comprobar("las redirecciones solo se siguen dentro del mismo dominio y si pasan el portero",
          sigue("https://www.ejemplo.org/ranking") and not sigue("https://www.youtube.com/x")
          and not sigue("https://login.ejemplo.org/") and not sigue("https://otra.com/") and not sigue("http://ejemplo.org/"))

vaciar()
poner_cola([pedido("cap-1", pedido_por="cerebro", fecha=hace(hours=5)),
            pedido("cap-2", "https://precios.ejemplo.com/lista", fecha=hace(hours=1))])
_, _, gh = elegir()
comprobar("lo que pide el dueño va delante", gh.get("id") == "cap-2")
vaciar()
poner_cola([pedido("cap-1")], uso={capturas._iso()[:10]: {"capturas": 2}})
_, texto, gh = elegir()
comprobar("con 2 capturas hoy, no elige ninguna", gh.get("hay") == "0" and cola()["pedidos"][0]["estado"] == "pendiente")
vaciar()
poner_cola([pedido("cap-1")], uso=uso)
_, _, gh = elegir()
comprobar("con 5 esta semana, tampoco", gh.get("hay") == "0")
vaciar()
poner_cola([])
_, texto, gh = elegir()
comprobar("sin nada pendiente acaba enseguida (hay=0) y sin error", gh == {"hay": "0", "id": ""} and "nada pendiente" in texto)
config(encendido=False)
poner_cola([pedido("cap-1")])
codigo, texto, gh = elegir()
comprobar("con el interruptor apagado no elige nada", codigo == 0 and gh.get("hay") == "0" and "apagado" in texto)
config()

# ---- colgados y caducados ----
c = {"pedidos": [pedido("cap-1", estado="en_curso", empezada=hace(hours=3), intentos=1),
                 pedido("cap-2", "https://b.ejemplo.com/x", estado="en_curso", empezada=hace(hours=3), intentos=2),
                 pedido("cap-3", "https://c.ejemplo.com/x", fecha=hace(days=8)),
                 pedido("cap-4", "https://d.ejemplo.com/x", estado="en_curso", empezada=hace(minutes=30), intentos=1)],
     "dominios": {}, "uso": {}, "modelos_vetados": {}, "ultimo": 4}
vaciar()
capturas._mantener(c)
e = {p["id"]: p for p in c["pedidos"]}
comprobar("una «en_curso» de hace 3 h (la caja se murió) vuelve a «pendiente» para otro día sin gastar otro intento "
          "(elegir ya lo contó); si iba por el segundo, «fallida»",
          e["cap-1"]["estado"] == "pendiente" and e["cap-1"]["intentos"] == 1
          and e["cap-1"]["no_antes_de"] > capturas._iso() and e["cap-2"]["estado"] == "fallida"
          and e["cap-2"]["intentos"] == 2 and e["cap-2"]["motivo"] == "colgada")
comprobar("una que lleva una semana pendiente caduca, y la que va bien (hace 30 min) sigue en curso",
          e["cap-3"]["estado"] == "caducada" and e["cap-4"]["estado"] == "en_curso")
muchas = {"pedidos": [pedido(f"cap-{i}", f"https://w{i}.ejemplo.com/x", estado="hecha") for i in range(1, 251)]
          + [pedido("cap-251", "https://z.ejemplo.com/x")], "dominios": {}, "uso": {"2020-01-01": {"capturas": 9}},
          "modelos_vetados": {}, "ultimo": 251}
capturas._mantener(muchas)
comprobar("la cola no crece sin fin: 200 pedidos como mucho (sin perder los vivos) y sin días viejos",
          len(muchas["pedidos"]) == 200 and muchas["pedidos"][-1]["id"] == "cap-251" and not muchas["uso"])

# ======================= 3. Guardar (después de la caja) =======================
RES = os.path.join(TMP, "resultado")


def guardar(id_, resultado=None, datos=None, enlace=False):
    shutil.rmtree(RES, ignore_errors=True)
    os.makedirs(RES)
    if enlace:
        os.symlink(os.path.join(PRIVADO, "config", "canales.json"), os.path.join(RES, "resultado.json"))
    elif resultado is not None:
        with open(os.path.join(RES, "resultado.json"), "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False)
    if datos is not None:
        with open(os.path.join(RES, "datos.json"), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
    for basura in ("recording.har", "rae-run.ndjson", "rae-run.log"):        # lo que nunca se guarda
        with open(os.path.join(RES, basura), "w") as f:
            f.write("cookie: secreta")
    return orden("guardar", "--id", id_, "--resultado", RES)


def en_curso(id_="cap-1", web=WEB, intentos=1, **mas):
    poner_cola([pedido(id_, web, estado="en_curso", empezada=hace(minutes=20), intentos=intentos)],
               uso={capturas._iso()[:10]: {"capturas": 1}}, **mas)


SUCIA = ("<b>Puesto</b> <script>alert(1)</script> mira https://malo.ejemplo.com/x y www.spam.com, escribe a "
         "pepe@correo.es o a @pepe, en ejemplo.org; llama al 612 345 678; lo dice Barrio de prueba; canal UC"
         + "x" * 22 + "; " + "muy largo " * 60)
FILAS = [{"titulo": f"Tema {i} {SUCIA}", "puesto": i, "visitas": 1000 * i, "enlace": "https://datos.ejemplo.org/t/1"}
         for i in range(1, 251)]
vaciar()
en_curso()
codigo, texto = guardar("cap-1", {"status": "ok", "usage": {"total_cost_usd": 0}, "datos": FILAS, "segundos": 420,
                                  "peticiones": 3, "modelo": "opencode/big-pickle", "hosts": [HOST, "cdn.ejemplo.org"],
                                  "resumen": "Los temas que más suben " + SUCIA})
f = privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}
valores = [str(v) for fila in f.get("datos") or [] for v in fila.values()]
todo = json.dumps(f, ensure_ascii=False)
comprobar("una captura buena y gratis queda «hecha», con 200 filas como mucho y el coste 0",
          codigo == 0 and f.get("estado") == "hecha" and f.get("filas") == 200 and len(f["datos"]) == 200
          and f.get("coste_usd") == 0 and cola()["pedidos"][0]["estado"] == "hecha"
          and cola()["pedidos"][0]["resultado"] == capturas.ruta_ficha("cap-1"))
comprobar("los datos quedan en texto plano: 200 letras por valor, sin <>, enlaces, @, correos, dominios, teléfonos ni "
          "ids de canal", all(len(x) <= 200 for x in valores) and not any(m in todo for m in (
              "<", ">", "http", "www.", "@", "ejemplo.org", "ejemplo.com", "correo.es", "612 345", "UC" + "x" * 22)))
comprobar("ni el nombre de una cuenta (sale su alias) y el resumen, 1.500 letras como mucho",
          not any(n in todo for n in NOMBRES) and "barrio-1" in todo and len(f.get("resumen", "")) <= 1500
          and f.get("resumen", "").startswith("Los temas que más suben"))
comprobar("la ficha lleva sus cifras y cabe (200 KB como mucho)", f.get("segundos") == 420 and f.get("peticiones") == 3
          and f.get("modelo") == "opencode/big-pickle" and len(todo.encode("utf-8")) <= capturas.FICHA_BYTES)
comprobar("los números siguen siendo números", f["datos"][0]["puesto"] == 1 and f["datos"][0]["visitas"] == 1000)
dentro = [n for _, _, fs in os.walk(PRIVADO) for n in fs]
comprobar("ni el HAR, ni el registro de rae, ni nada con cookies llega al repositorio privado",
          not any(n.endswith((".har", ".ndjson", ".log")) or n.startswith("rae-run") for n in dentro))
comprobar("lo que imprime es solo el id y cifras", texto.strip() == "cap-1: hecha · 200 filas · 0 $ · 3 peticiones · 7 min")
comprobar("y lo apunta en su cuaderno (investigador_webs), no en el del Investigador de Influencers",
          any(e["accion"] == "captura" for e in privado.cuaderno("investigador_webs").datos["diario"])
          and not any(e["accion"] == "captura" for e in privado.cuaderno("investigador").datos.get("diario") or []))

vaciar()
en_curso()
guardar("cap-1", {"status": "ok", "usage": {"total_cost_usd": 0}}, datos={"items": [["Tema A", 1], ["Tema B", 2]]})
f = privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}
comprobar("también entiende los datos aparte (datos.json) y filas en forma de lista", f.get("estado") == "hecha"
          and f.get("filas") == 2 and f["datos"][0] == {"campo1": "Tema A", "campo2": 1})

vaciar()
en_curso()
guardar("cap-1", {"status": "error", "error": "the page shows a captcha", "usage": {"total_cost_usd": 0}})
d = cola()["dominios"].get(DOMINIO, {})
comprobar("con captcha: «vetada» y la web castigada 30 días", cola()["pedidos"][0]["estado"] == "vetada"
          and cola()["pedidos"][0]["motivo"] == "captcha" and d.get("fallos") == 1
          and hace(days=-29) < str(d.get("vetado_hasta")) < hace(days=-31))
otra = cola()
otra["pedidos"].append(pedido("cap-2", "https://datos.ejemplo.org/otra", estado="en_curso", empezada=hace(minutes=5),
                              intentos=1))
privado.escribir(capturas.COLA, otra)
guardar("cap-2", {"estado": "bloqueada", "motivo": "login"})
comprobar("a la segunda vez que bloquea, la web queda vetada para siempre",
          cola()["dominios"][DOMINIO]["vetado_hasta"] == capturas.PARA_SIEMPRE and cola()["dominios"][DOMINIO]["fallos"] == 2)
vaciar()
en_curso()
guardar("cap-1", {"status": "ok", "datos": FILAS[:3], "hosts": [HOST, "www.youtube.com"], "usage": {"total_cost_usd": 0}})
comprobar("si la caja vio una red social o una web prohibida, se tira todo y la web queda castigada",
          cola()["pedidos"][0]["estado"] == "vetada" and cola()["pedidos"][0]["motivo"] == "red_vetada"
          and not (privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}).get("datos")
          and capturas._castigada(cola(), DOMINIO))

vaciar()
en_curso()
_, texto = guardar("cap-1", {"status": "ok", "datos": FILAS[:3], "modelo": "opencode/de-pago",
                             "usage": {"total_cost_usd": 0.02}})
f = privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}
comprobar("si el modelo cobra (0,02 $), se tira el resultado y el modelo queda vetado",
          f.get("estado") == "fallida" and f.get("motivo") == "coste" and not f.get("datos")
          and "opencode/de-pago" in cola()["modelos_vetados"] and f.get("aviso"))
vaciar()
en_curso()
guardar("cap-1", {"status": "ok", "datos": FILAS[:3]})
comprobar("si no dice cuánto costó, NO se da por gratis: fallida", cola()["pedidos"][0]["estado"] == "fallida"
          and cola()["pedidos"][0]["motivo"] == "sin_coste")
vaciar()
en_curso()
guardar("cap-1", {"status": "ok", "datos": [], "usage": {"total_cost_usd": 0}})
comprobar("sin datos de verdad, fallida", cola()["pedidos"][0]["motivo"] == "sin_datos")

vaciar()
en_curso()
guardar("cap-1", {"status": "error", "error_kind": "engine_failure",
                  "error": "Invalid OpenCode model pairing: opencode/big-pickle is not available."})
c = cola()
comprobar("sin modelo gratis: «sin_modelo_gratis», no gasta del tope del día y se puede volver a pedir",
          c["pedidos"][0]["estado"] == "sin_modelo_gratis" and capturas._uso(c) == 0 and del_dueno(WEB)[0])

vaciar()
en_curso()
guardar("cap-1", {"status": "error", "error": "OpenCode provider requires login (403)"})
comprobar("un aviso de OpenCode (pide entrar, 403) es «sin modelo gratis» y NO castiga a la web",
          cola()["pedidos"][0]["estado"] == "sin_modelo_gratis" and not capturas._castigada(cola(), DOMINIO))
vaciar()
en_curso()
guardar("cap-1", {"status": "ok", "datos": FILAS[:3], "marcas": ["x-datadome"], "usage": {"total_cost_usd": 0}})
comprobar("si la caja vio marcas de reto en el HAR, se tira aunque la IA diga que salió bien",
          cola()["pedidos"][0]["estado"] == "vetada" and cola()["pedidos"][0]["motivo"] == "captcha")
vaciar()
en_curso(intentos=1)
_, texto = guardar("cap-1", {"status": "error", "error_kind": "engine_failure", "error": "Agent analysis produced no result."})
p = cola()["pedidos"][0]
comprobar("un fallo del programa al primer intento: vuelve a «pendiente» para otro día", p["estado"] == "pendiente"
          and p["no_antes_de"] > capturas._iso() and "pendiente" in texto)
en_curso(intentos=2)
guardar("cap-1", {"status": "error", "error_kind": "network"})
comprobar("…y al segundo intento, «fallida»", cola()["pedidos"][0]["estado"] == "fallida"
          and cola()["pedidos"][0]["motivo"] == "programa")
en_curso(intentos=2)
_, texto = guardar("cap-1", {"id": "cap-1", "estado": "fallida", "motivo": "error_caja"})
f = privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}
comprobar("un fallo de la caja por segunda vez es un fallo del programa (el Cerebro se lo pasa a Claude): guarda la "
          "palabra de la caja aparte y al dueño le dice «ha fallado dos veces»",
          cola()["pedidos"][0]["motivo"] == "programa" and f.get("causa") == "error_caja"
          and "dos veces" in capturas.explicar("fallida", "programa") and texto.strip().endswith("· programa"))
en_curso(intentos=1)
_, texto = guardar("cap-1", {"id": "cap-1", "estado": "fallida", "motivo": "palabrarara"})
comprobar("en el registro solo salen palabras nuestras: otra cualquiera sale como «otro»",
          texto.strip().endswith("· otro") and "palabrarara" not in texto)
en_curso(intentos=1)
guardar("cap-1", enlace=True)
comprobar("un resultado.json que es un enlace a otro fichero no se lee (cuenta como fallo, no como datos)",
          cola()["pedidos"][0]["estado"] == "pendiente" and not (privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}).get("datos"))
en_curso(intentos=1)
guardar("cap-1")
comprobar("sin resultado.json (la caja murió): un intento menos, a otro día", cola()["pedidos"][0]["estado"] == "pendiente")
# lo que deja de verdad la caja (herramientas/caja_capturas): «estado» y una palabra fija en «motivo»
DE_LA_CAJA = {
    "hecha": ({"id": "cap-1", "estado": "hecha", "motivo": None, "coste_usd": 0.0, "modelo": "big-pickle",
               "filas": 2, "campos": ["titulo", "puesto"], "datos": [{"titulo": "A", "puesto": 1},
                                                                    {"titulo": "B", "puesto": 2}],
               "resumen": "2 temas", "peticiones": 12, "segundos": 300, "denegadas": 0}, "hecha", "hecha", False),
    "bloqueo_403": ({"id": "cap-1", "estado": "vetada", "motivo": "bloqueo_403"}, "vetada", "bloqueo", True),
    "cloudflare": ({"id": "cap-1", "estado": "vetada", "motivo": "cloudflare"}, "vetada", "captcha", True),
    "bloqueo_429": ({"id": "cap-1", "estado": "vetada", "motivo": "bloqueo_429"}, "vetada", "429", True),
    "web_prohibida": ({"id": "cap-1", "estado": "vetada", "motivo": "web_prohibida"}, "vetada", "red_vetada", True),
    "har_enorme": ({"id": "cap-1", "estado": "vetada", "motivo": "har_enorme"}, "vetada", "har_enorme", False),
    "pide_sesion": ({"id": "cap-1", "estado": "fallida", "motivo": "pide_sesion"}, "fallida", "pide_sesion", False),
    "sin_datos": ({"id": "cap-1", "estado": "fallida", "motivo": "sin_datos"}, "fallida", "sin_datos", False),
    "de_pago": ({"id": "cap-1", "estado": "fallida", "motivo": "de_pago", "coste_usd": 0.01, "modelo": "caro"},
                "fallida", "coste", False),
    "llave_en_la_caja": ({"id": "cap-1", "estado": "fallida", "motivo": "llave_en_la_caja"}, "fallida",
                         "llave_en_la_caja", False),
    "sin_modelo_gratis": ({"id": "cap-1", "estado": "sin_modelo_gratis", "motivo": "sin_modelo_gratis"},
                          "sin_modelo_gratis", "sin_modelo_gratis", False),
    "error_caja (1.er intento)": ({"id": "cap-1", "estado": "fallida", "motivo": "error_caja"}, "pendiente",
                                  "error_caja", False),
    "de otro pedido": ({"id": "cap-7", "estado": "hecha", "coste_usd": 0, "datos": [{"a": "b"}]}, "pendiente",
                       "caja_sin_resultado", False),
}
for nombre, (resultado, estado, motivo, castigo) in DE_LA_CAJA.items():
    vaciar()
    en_curso()
    guardar("cap-1", resultado)
    p = cola()["pedidos"][0]
    comprobar(f"lo que dice la caja ({nombre}) → {estado} ({motivo})" + (" y castigo a la web" if castigo else ""),
              p["estado"] == estado and p.get("motivo") == motivo and bool(capturas._castigada(cola(), DOMINIO)) == castigo)
f = privado.leer(capturas.ruta_ficha("cap-1"), {}) or {}
comprobar("la llave dentro de la caja deja un aviso para Claude en la ficha, y el modelo que cobra queda vetado",
          capturas._veredicto({"estado": "fallida", "motivo": "llave_en_la_caja"}) == ("fallida", "llave_en_la_caja")
          and "llave_en_la_caja" in capturas.AVISOS and capturas.explicar("fallida", "pide_sesion").startswith("Esos datos"))

vaciar()
poner_cola([pedido("cap-1", estado="hecha")])
codigo, texto = guardar("cap-1", {"status": "ok"})
codigo2, texto2 = orden("guardar", "--id", "cap-99", "--resultado", RES)
codigo3, _ = orden("guardar", "--id", "../x", "--resultado", RES)
comprobar("guardar dos veces no estropea nada, un id que no está acaba bien y un id raro se rechaza",
          codigo == 0 and "ya estaba" in texto and codigo2 == 0 and codigo3 == 2)

# ======================= 4. La cola entre dos turnos a la vez (fusionar) =======================
t1, t2 = hace(hours=3), hace(minutes=1)
suyo = {"pedidos": [pedido("cap-1", estado="en_curso", intentos=1, cambiado=t1), pedido("cap-2", intentos=0),
                    pedido("cap-3", estado="en_curso", intentos=1, cambiado=t1), pedido("cap-5", estado="hecha", intentos=1)],
        "dominios": {"a.org": {"fallos": 1, "vetado_hasta": "2026-12-20T00:00:00Z", "motivo": "captcha", "del_dueno": True}},
        "uso": {"2026-11-26": {"capturas": 2}}, "modelos_vetados": {"x/y": "cobró"}, "ultimo": 5}
nuestro = {"pedidos": [pedido("cap-1", intentos=1, cambiado=t2), pedido("cap-2", estado="hecha", intentos=1, cambiado=t2),
                       pedido("cap-3", intentos=1, cambiado=t2), pedido("cap-4"), pedido("cap-5", intentos=3)],
           "dominios": {"a.org": {"fallos": 0, "vetado_hasta": None, "ultima": t2}, "b.org": {"fallos": 0}},
           "uso": {"2026-11-26": {"capturas": 1}, "2026-11-27": {"capturas": 1}}, "modelos_vetados": {}, "ultimo": 4}
junto = privado.fusionar("estado/capturas/cola.json", suyo, nuestro)
e = {p["id"]: p for p in junto["pedidos"]}
comprobar("fusionar: lo colgado que volvió a «pendiente» (tocado después, con los mismos intentos) gana a la copia "
          "vieja «en_curso»", e["cap-1"]["estado"] == "pendiente" and e["cap-1"]["intentos"] == 1)
comprobar("fusionar: un estado final nunca vuelve atrás y un reintento tocado después gana a la copia vieja",
          e["cap-2"]["estado"] == "hecha" and e["cap-5"]["estado"] == "hecha" and e["cap-3"]["estado"] == "pendiente")
comprobar("fusionar: no se pierde ningún pedido y van en orden", [p["id"] for p in junto["pedidos"]] ==
          ["cap-1", "cap-2", "cap-3", "cap-4", "cap-5"] and junto["ultimo"] == 5)
comprobar("fusionar: de cada web, el mayor castigo y los fallos; el uso, el máximo de cada día (no la suma)",
          junto["dominios"]["a.org"]["vetado_hasta"] == "2026-12-20T00:00:00Z" and junto["dominios"]["a.org"]["fallos"] == 1
          and junto["dominios"]["a.org"]["motivo"] == "captcha" and junto["dominios"]["a.org"]["del_dueno"]
          and "b.org" in junto["dominios"] and junto["uso"] == {"2026-11-26": {"capturas": 2}, "2026-11-27": {"capturas": 1}}
          and junto["modelos_vetados"] == {"x/y": "cobró"})
HOY = capturas._iso()[:10]
devuelta, otra_copia = {"pedidos": [], "uso": {HOY: {"capturas": 1, "devueltas": 1}}}, {"pedidos": [], "uso": {HOY: {"capturas": 1}}}
juntas = [privado.fusionar("estado/capturas/cola.json", a, b) for a, b in ((devuelta, otra_copia), (otra_copia, devuelta))]
comprobar("fusionar: una captura devuelta (sin modelo gratis) no se pierde al juntar dos copias y no gasta del tope",
          all(j["uso"][HOY] == {"capturas": 1, "devueltas": 1} and capturas._uso(dict(j, uso=j["uso"])) == 0
              for j in juntas))

# ======================= 5. Para el Cerebro y la app =======================
vaciar()
poner_cola([pedido("cap-1", estado="hecha", terminada=hace(minutes=3)), pedido("cap-2", "https://b.ejemplo.com/x",
            estado="vetada", motivo="captcha"), pedido("cap-3", "https://c.ejemplo.com/x")],
           uso={capturas._iso()[:10]: {"capturas": 1}})
privado.escribir(capturas.ruta_ficha("cap-1"), {"id": "cap-1", "estado": "hecha", "filas": 3, "datos": [{"a": 1}],
                                                "resumen": "Tres temas que suben: mira https://x.com/y", "coste_usd": 0})
r = capturas.resumen_para_directo()
comprobar("el apartado de la app: hoy, semana, topes, pendientes y últimas, sin la dirección completa",
          r["hoy"] == 1 and r["tope_dia"] == 2 and r["tope_semana"] == 5 and [x["id"] for x in r["pendientes"]] == ["cap-3"]
          and {x["id"] for x in r["ultimas"]} == {"cap-1", "cap-2"} and "https://" not in json.dumps(r)
          and next(x for x in r["ultimas"] if x["id"] == "cap-1")["filas"] == 3)
t = capturas.terminadas({"cap-2"})
comprobar("terminadas() da las fichas que el Cerebro no ha visto, con lo del pedido y la explicación en sencillo",
          [x["id"] for x in t] == ["cap-1"] and t[0]["cuenta"] == CUENTA and t[0]["mensaje"] == "m1"
          and t[0]["dominio"] == DOMINIO and t[0]["explicacion"] and "https" not in t[0]["resumen"])
t = capturas.terminadas(set())
comprobar("y también las que no salieron (aunque no tengan ficha), con su porqué",
          any(x["id"] == "cap-2" and "captcha" in x["explicacion"] and "30 días" in x["explicacion"] for x in t))

# ======================= 6. Nada privado en el registro público =======================
vaciar()
ROBOTS[HOST] = (200, "User-agent: *\nAllow: /\n")
poner_cola([pedido("cap-1")])
_, texto = orden("elegir", "--salida", DIR, entorno={"GITHUB_ACTIONS": "true"})
mascaras = [linea for linea in texto.splitlines() if linea.startswith("::add-mask::")]
resto = [linea for linea in texto.splitlines() if not linea.startswith("::add-mask::")]
comprobar("en GitHub tapa la web, su host, su dominio y su ruta (también %-codificados) antes de nada",
          {f"::add-mask::{x}" for x in (WEB, HOST, DOMINIO, "/ranking", urllib.parse.quote(WEB, safe=""))} <= set(mascaras)
          and not any(DOMINIO in linea for linea in resto))
SALIDAS[-1] = "\n".join(resto)
original = capturas._revisar
capturas._revisar = lambda *a: (_ for _ in ()).throw(ValueError(f"fallo con {WEB} de {CUENTA}"))
vaciar()
poner_cola([pedido("cap-1")])
codigo, texto = orden("elegir", "--salida", DIR)
capturas._revisar = original
averias = (privado.leer(capturas.AVERIAS, {}) or {}).get("averias") or []
comprobar("si el programa falla con la web en el error, solo imprime «error del programa» (el detalle, al privado)",
          codigo == 1 and texto.strip() == "capturas: error del programa (ValueError)" and averias
          and "ValueError" in averias[-1]["error"])
original = capturas._veredicto
capturas._veredicto = lambda *a: 1 / 0
en_curso()
codigo, texto = guardar("cap-1", {"status": "ok"})
capturas._veredicto = original
comprobar("igual en guardar", codigo == 1 and texto.strip() == "cap-1: error del programa (ZeroDivisionError)")
todo = "\n".join(SALIDAS)
comprobar("nada de lo que ha impreso el turno lleva la web, su dominio ni el nombre de una cuenta",
          SALIDAS and not any(x in todo for x in (WEB, HOST, DOMINIO, "ejemplo.com", "ejemplo.net", "https://") + NOMBRES))

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nSimulacro del Investigador de webs: {'TODO BIEN' if not FALLOS else f'{FALLOS} FALLO(S)'}")
sys.exit(1 if FALLOS else 0)
