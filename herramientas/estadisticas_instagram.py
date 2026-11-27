"""La Contable de Instagram: lee por la vía OFICIAL de Meta las cifras de los reels de las cuentas del dueño.

Solo LEE. Nunca publica, ni comenta, ni lee mensajes: el permiso que se pide es solo instagram_business_basic +
instagram_business_manage_insights. Va en «Revisar canales» (cada 3 horas), en su propio trabajo. No comparte cola con
«Conectar redes» (GitHub cancela la petición que espera en una cola si llega otra): deja en paz la cuenta que se esté
conectando en ese momento (estado/conexion_redes.json «esperando») y, si los dos turnos tocan a la vez
estado/redes/conexiones.json, privado.fusionar se queda con lo más nuevo de cada cuenta («cambiado»).

En cada pasada (estado/redes/conexiones.json del repositorio privado):
  0. Una conexión de una cuenta que ya no está en config/canales.json → barrios no se lee ni se renueva: queda sin
     permiso («fuera de la lista») y se olvida a los 30 días. En el registro sale como «una cuenta retirada», nunca
     con su clave (es el nombre de la cuenta y privado.limpiar ya no la conoce).
  1. Recoge del Buzón de vuelta los avisos de Meta (baja o borrado; /recoger?marcas=1 con VUELTA_LLAVE) y los
     comprueba con la API: solo valen si el permiso de esa cuenta ya no funciona (error 190). Entonces la cuenta queda
     sin permiso desde ese momento y, si pidió el borrado, sus copias se borran ya.
  2. Una vez por semana renueva el permiso de 60 días de cada cuenta conectada y guarda el nuevo en el mismo secreto
     IG_TOKEN_<hueco>. Si Meta dice que ya no vale (error 190), la cuenta queda «caducado» para que la app pida volver
     a conectarla.
  3. Mira que el permiso sigue siendo de esa cuenta (huella de su número, como con YouTube).
  4. Lista sus reels de los últimos 90 días y lee las cifras de cada uno: visitas, alcance, «me gusta», comentarios,
     compartidos, guardados, interacciones, tiempo medio de visionado, tiempo total y cuántos se saltan el vídeo en
     los 3 primeros segundos; y en otra llamada aparte, para que su error 100 no rompa la principal, las veces que lo
     vuelven a compartir (reposts) y las visitas en Facebook. Cada reel se relee cada 6 h sus 3 primeros días, cada
     día hasta los 30 y cada semana hasta los 90. Si una métrica da el error 100 (no vale para ese reel), se piden las
     demás sin ella. Un reel que no da NINGUNA (por ejemplo, uno de antes de pasar la cuenta a profesional) queda «sin
     estadísticas» y no cuenta contra las métricas. La métrica que falla en 3 reels que sí dan las demás se deja de
     pedir 30 días, solo a ESA cuenta (estado/redes/metricas.json); nunca se pide una lista vacía.
  5. Guarda en el privado estado/redes/instagram/<alias>.json (últimos 60 reels, sin enlaces ni usuarios; el texto
     del reel recortado a 150 caracteres y pasado por privado.limpiar, para unirlo con los vídeos de la fábrica; el
     fichero lleva la «huella» de la cuenta, que no cambia aunque cambie el alias, y nunca se mezcla con el de otra
     cuenta) y pasa un resumen al Contador de redes (estado/redes/contador.json → estado/app/cifras.json:
     cifrasPorRed.instagram con auto «api», reelsInstagram y los seguidores de cada día, marcados con fuente «api»).
  6. Una cuenta sin permiso 30 días (en cualquier estado que no sea «conectado») se olvida: se borran su fichero, su
     resumen, sus reels y sus seguidores de cada día en el Contador (lo piden las normas de Meta).

Pendiente (plan, punto 5): las cifras de la cuenta de cada día (/me/insights con period=day: alcance, visitas,
cuentas que interactúan, seguidores ganados y perdidos…) y, una vez por semana, las del público
(follower_demographics). Hoy de la cuenta solo se guardan seguidores y publicaciones.

Los registros de GitHub son PÚBLICOS: aquí solo salen alias (barrio-1…), números de error y cuántas cosas se leen.
Todo token se tapa (::add-mask::) nada más llegar, y nunca se imprimen direcciones, respuestas ni textos de los reels.

Secretos: IG_TOKEN_1 … IG_TOKEN_10 (los escribe «Conectar redes»), GH_SECRETOS (para guardar los renovados) y
VUELTA_LLAVE (para recoger los avisos de Meta). No necesita IG_APP_ID ni IG_APP_SECRET.
Uso:  python herramientas/estadisticas_instagram.py [--sin-renovar]
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.comun import privado  # noqa: E402
import secretos  # noqa: E402  (herramientas/secretos.py: github, guardar_secreto, puede_guardar)

GRAPH = "https://graph.instagram.com"
CANJE = "https://api.instagram.com/oauth/access_token"
VERSION = "v26.0"                       # la que se confirmó; config/redes.json → version_meta manda
CONEXIONES = os.path.join("estado", "redes", "conexiones.json")
CARPETA = os.path.join("estado", "redes", "instagram")
METRICAS = os.path.join("estado", "redes", "metricas.json")
CONTADOR = os.path.join("estado", "redes", "contador.json")
AVISOS = os.path.join("estado", "redes", "avisos_meta.json")
CONECTANDO = os.path.join("estado", "conexion_redes.json")     # lo que está haciendo «Conectar redes» ahora
HUECOS = 10                             # IG_TOKEN_1 … IG_TOKEN_10
PERMISOS = ("instagram_business_basic", "instagram_business_manage_insights")
METRICAS_REEL = ("views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                 "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate")
METRICAS_EXTRA = ("reposts", "facebook_views")   # en otra llamada: si dan el error 100, no rompen la principal
CAMPOS_MEDIA = "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count"
REELS = 60                              # reels que se guardan por cuenta
DIAS_LISTA = 90                         # los reels más viejos ya no se releen
DIAS_CUENTA = 400                       # Meta solo guarda 90 días de la cuenta: la fábrica guarda más
RENOVAR_DIAS = 7
TOPE_USO = 75                           # si Meta dice que llevamos más del 75 % del cupo, se para esa cuenta
PUNTOS_CURVA = (6, 24, 48, 168, 720)    # horas de vida del reel en las que se guarda una foto de sus cifras
OLVIDAR_DIAS = 30                       # sin permiso 30 días: se borran las copias (normas de Meta)
VETO_DIAS = 30                          # una métrica que no vale para una cuenta se vuelve a probar al mes
VETO_REELS = 3                          # reels (que sí dan las demás) en los que tiene que fallar para no pedirla
ERR_RED = -2                            # sin respuesta (la red falla)
ERR_RARO = -1                           # error sin número
SIN_DATOS = "sin_datos"                 # el reel no da ninguna métrica: no es culpa de ninguna en concreto
RETIRADA = "una cuenta retirada"        # cómo sale en el registro una cuenta que ya no está en la lista
FUERA = "fuera de la lista"


# --- Registros públicos y secretos de GitHub ---

def ocultar(*valores):
    """Tapa cada valor en los registros de GitHub Actions (::add-mask::). Se llama nada más recibir un token, un
    código o un usuario. Fuera de Actions no imprime nada (el valor saldría en la pantalla)."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for v in valores:
        v = str(v or "").strip()
        if len(v) >= 4 and "\n" not in v:
            print(f"::add-mask::{v}", flush=True)


def puede_guardar(llave):
    """True si GH_SECRETOS deja escribir secretos ahora mismo (sin lanzar nunca)."""
    try:
        return secretos.puede_guardar(llave)
    except Exception:                                   # noqa: BLE001 (sin detalles: es un registro público)
        return False


def guardar_con_reintentos(nombre, valor, llave, intentos=3):
    """Guarda el secreto de GitHub; lo intenta varias veces. True si queda guardado."""
    for i in range(intentos):
        try:
            secretos.guardar_secreto(nombre, valor, llave)
            return True
        except Exception:                               # noqa: BLE001 (sin detalles: es un registro público)
            time.sleep(3 * (i + 1))
    return False


# --- La red: una sola puerta, que nunca lanza ni imprime ---

def _json(cuerpo):
    try:
        datos = json.loads(cuerpo or b"{}")
        return datos if isinstance(datos, dict) else {"data": datos}
    except ValueError:
        return {}


def _http(metodo, url, datos=None, cabeceras=None):
    """Hace la petición y devuelve (código HTTP, cuerpo JSON, cabeceras). 0 si no hay respuesta. Nunca lanza: así un
    fallo nunca saca la dirección (que puede llevar el token) en un mensaje de error."""
    cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
    req = urllib.request.Request(url, data=cuerpo, method=metodo,
                                 headers=dict({"User-Agent": "panel-de-cifras/1.0"}, **(cabeceras or {})))
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, _json(r.read()), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        try:
            leido = e.read()
        except OSError:
            leido = b""
        return e.code, _json(leido), {k.lower(): v for k, v in (e.headers or {}).items()}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, {}, {}


def codigo_error(estado_http, datos):
    """El número de error de Meta (190: permiso caducado o quitado; 100: algo de lo pedido no vale) o None si va bien."""
    if estado_http == 0:
        return ERR_RED
    if not isinstance(datos, dict):
        return ERR_RARO
    e = datos.get("error")
    if isinstance(e, dict):
        return _entero(e.get("code")) or ERR_RARO
    if e or "error_type" in datos or "error_message" in datos:
        return _entero(datos.get("code")) or ERR_RARO
    if estado_http >= 400:
        return estado_http
    return None


def _entero(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _uso(cabeceras):
    """El mayor porcentaje de cupo gastado que cuenta Meta en sus cabeceras (X-App-Usage, X-Business-Use-Case-Usage)."""
    mayor = 0
    for nombre in ("x-app-usage", "x-business-use-case-usage"):
        try:
            pila = [json.loads(cabeceras.get(nombre) or "{}")]
        except ValueError:
            continue
        while pila:
            x = pila.pop()
            if isinstance(x, list):
                pila.extend(x)
            elif isinstance(x, dict):
                for k, v in x.items():
                    if k in ("call_count", "total_cputime", "total_time") and isinstance(v, (int, float)):
                        mayor = max(mayor, v)
                    elif isinstance(v, (dict, list)):
                        pila.append(v)
    return mayor


def fijar_version(version):
    """La versión de la API de Meta que manda config/redes.json (solo si tiene la forma vNN.N)."""
    global VERSION
    if isinstance(version, str) and re.fullmatch(r"v\d{2,3}\.\d", version):
        VERSION = version


class Cuenta:
    """Las llamadas de una cuenta con su token. Primero prueba con el token en la cabecera (así no va en la dirección);
    si Meta no lo ve ahí, lo pone en la dirección (siempre tapado en los registros)."""

    def __init__(self, token):
        self.token = token
        self.cabecera = True
        self.uso = 0

    def get(self, ruta, params=None):
        """Devuelve (datos, error). `ruta` va sin la versión: «me», «me/media», «<id>/insights»."""
        url = f"{GRAPH}/{VERSION}/{ruta}"
        params = dict(params or {})
        while True:
            if self.cabecera:
                st, datos, cab = _http("GET", f"{url}?{urllib.parse.urlencode(params)}",
                                       cabeceras={"Authorization": f"Bearer {self.token}"})
            else:
                st, datos, cab = _http("GET", f"{url}?{urllib.parse.urlencode(dict(params, access_token=self.token))}")
            self.uso = max(self.uso, _uso(cab))
            err = codigo_error(st, datos)
            if self.cabecera and err in (104, 190, 2500):     # no ha visto el token en la cabecera: a la dirección
                self.cabecera = False
                continue
            return datos, err


# --- Permisos (los usa también «Conectar redes») ---

def _token_de(datos):
    """El token de una respuesta de Meta, plana o dentro de data[]. Se tapa en los registros nada más verlo."""
    if isinstance(datos.get("data"), list) and datos["data"] and isinstance(datos["data"][0], dict):
        datos = datos["data"][0]
    token = str(datos.get("access_token") or "")
    ocultar(token, datos.get("user_id"))
    return token, datos


def canjear_codigo(app_id, app_secreto, redirect_uri, codigo):
    """Del código de la vuelta al permiso corto (1 hora). Devuelve (token, permisos, error)."""
    codigo = str(codigo or "").strip()
    if codigo.endswith("#_"):
        codigo = codigo[:-2]
    st, datos, _ = _http("POST", CANJE, {"client_id": app_id, "client_secret": app_secreto,
                                         "grant_type": "authorization_code", "redirect_uri": redirect_uri,
                                         "code": codigo})
    token, datos = _token_de(datos)
    if not token:
        return None, [], codigo_error(st, datos) or ERR_RARO
    permisos = datos.get("permissions") or []
    if isinstance(permisos, str):
        permisos = [p.strip() for p in permisos.split(",") if p.strip()]
    return token, list(permisos), None


def token_largo(app_secreto, corto):
    """Del permiso corto al de 60 días. Devuelve (token, segundos que dura, error)."""
    st, datos, _ = _http("GET", f"{GRAPH}/access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_exchange_token", "client_secret": app_secreto, "access_token": corto}))
    token, datos = _token_de(datos)
    if not token:
        return None, 0, codigo_error(st, datos) or ERR_RARO
    return token, _entero(datos.get("expires_in")) or 60 * 86400, None


def renovar(token):
    """Renueva el permiso de 60 días (tiene que tener al menos 24 h y no haber caducado). (token, segundos, error)."""
    st, datos, _ = _http("GET", f"{GRAPH}/refresh_access_token?" + urllib.parse.urlencode(
        {"grant_type": "ig_refresh_token", "access_token": token}))
    nuevo, datos = _token_de(datos)
    if not nuevo:
        return None, 0, codigo_error(st, datos) or ERR_RARO
    return nuevo, _entero(datos.get("expires_in")) or 60 * 86400, None


def huella(texto):
    """Huella corta de un número de cuenta: sirve para reconocerla sin escribir el número en ningún sitio."""
    return hashlib.sha256(str(texto).encode()).hexdigest()[:16]


_DE_PASO = ("leido", "aviso", "cambiado")      # lo que cambia en cada lectura: no cuenta como cambio de la conexión


def apuntar_conexion(clave, datos):
    """Deja el estado de la conexión de Instagram de una cuenta en estado/redes/conexiones.json (sin tokens). Lleva
    «cambiado», la hora del último cambio de verdad (no cuentan las lecturas), para que privado.fusionar sepa qué
    versión gana si «Conectar redes» y la lectura tocan la misma cuenta a la vez."""
    conexiones = privado.leer(CONEXIONES, {}) or {}
    antes = (conexiones.get(clave) or {}).get("instagram") or {}
    nuevo = {k: v for k, v in datos.items() if v is not None}

    def esencia(x):
        return {k: v for k, v in x.items() if k not in _DE_PASO}
    igual = antes.get("cambiado") and esencia(antes) == esencia(nuevo)
    nuevo["cambiado"] = antes["cambiado"] if igual else _iso(_ahora())
    conexiones.setdefault(clave, {})["instagram"] = nuevo
    privado.escribir(CONEXIONES, conexiones)


def entradas(conexiones):
    """(clave, conexión de Instagram) de cada cuenta de estado/redes/conexiones.json que la tiene."""
    for clave, redes in (conexiones or {}).items():
        con = redes.get("instagram") if isinstance(redes, dict) else None
        if isinstance(con, dict):
            yield clave, con


def nombre_publico(clave, barrios):
    """Cómo sale una cuenta en el registro público: su alias (barrio-N) o, si ya no está en la lista, un texto fijo.
    Nunca la clave: es el nombre de la cuenta, y privado.limpiar solo tapa las que siguen en la configuración."""
    return privado.alias(clave) if clave in barrios else RETIRADA


# --- Fechas ---

def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _iso(momento):
    return momento.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fecha(texto):
    try:
        momento = dt.datetime.fromisoformat(str(texto).replace("Z", "+00:00").replace("+0000", "+00:00"))
        return momento if momento.tzinfo else momento.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


# --- Leer ---

def _valores(datos):
    """{métrica: número} de una respuesta de estadísticas. Sin dato (lista vacía) no se apunta: no es un 0."""
    salida = {}
    for x in datos.get("data") or []:
        if not isinstance(x, dict):
            continue
        valor = None
        if isinstance(x.get("total_value"), dict):
            valor = x["total_value"].get("value")
        elif x.get("values"):
            valor = (x["values"][-1] or {}).get("value")
        if x.get("name") and isinstance(valor, (int, float)) and not isinstance(valor, bool):
            salida[x["name"]] = valor
    return salida


def _insights(cuenta, media_id, metricas):
    """({métrica: número}, error) de una sola llamada de estadísticas de un reel."""
    datos, err = cuenta.get(f"{media_id}/insights", {"metric": ",".join(metricas)})
    return ({}, err) if err else (_valores(datos), None)


def cifras_reel(cuenta, media_id, metricas, sospechosas=(), sin_antes=False):
    """Las métricas de un reel: (cifras, las que no valen para él, error). Con el error 100 se prueba sin las que ya
    fallaron en otros reels y, si tampoco, una a una. Si no sale NINGUNA, el error es SIN_DATOS: el reel no tiene
    estadísticas y no es culpa de las métricas. `sin_antes`: ya salió así la otra vez, así que no se prueban una a
    una. Con la lista vacía no se llama a Meta."""
    if not metricas:
        return {}, [], None
    cifras, err = _insights(cuenta, media_id, metricas)
    if err != 100:
        return cifras, [], err
    if sin_antes:
        return {}, [], SIN_DATOS
    sin = [m for m in metricas if m not in sospechosas]
    if sospechosas and sin and len(sin) < len(metricas):
        cifras, err = _insights(cuenta, media_id, sin)
        if not err:
            return cifras, [m for m in metricas if m not in sin], None
    cifras, faltan = {}, []
    for m in metricas:
        valores, err = _insights(cuenta, media_id, [m])
        if err == 100:
            faltan.append(m)
        elif err:
            return cifras, faltan, err
        else:
            cifras.update(valores)
    if len(faltan) == len(metricas):
        return {}, [], SIN_DATOS
    return cifras, faltan, None


def _codigo_reel(permalink):
    """Solo el código corto del reel (lo que va tras /reel/), nunca el enlace entero (puede llevar el usuario)."""
    m = re.search(r"/(?:reels?|p|tv)/([A-Za-z0-9_-]{5,40})", str(permalink or ""))
    return m.group(1) if m else None


def lista_reels(cuenta, ahora):
    """Los reels de los últimos 90 días (60 como mucho), del más nuevo al más viejo: (lista, error)."""
    reels, despues = [], None
    limite = ahora - dt.timedelta(days=DIAS_LISTA)
    for _ in range(6):                                     # 6 páginas de 50 como mucho
        params = {"fields": CAMPOS_MEDIA, "limit": 50}
        if despues:
            params["after"] = despues
        datos, err = cuenta.get("me/media", params)
        if err:
            return reels, err
        viejo = False
        for m in datos.get("data") or []:
            subido = _fecha(m.get("timestamp"))
            if not subido or not m.get("id"):
                continue
            if subido < limite:
                viejo = True
                continue
            if m.get("media_product_type") == "REELS":
                reels.append({"id": str(m["id"]), "codigo": _codigo_reel(m.get("permalink")), "subido": _iso(subido),
                              "texto": privado.limpiar(" ".join(str(m.get("caption") or "").split()))[:150],
                              "meGusta": _entero(m.get("like_count")), "comentarios": _entero(m.get("comments_count"))})
        paging = datos.get("paging") or {}
        despues = (paging.get("cursors") or {}).get("after")
        if viejo or len(reels) >= REELS or not paging.get("next") or not despues:
            break
    return reels[:REELS], None


def toca_releer(guardado, subido, ahora):
    """Cada 6 h los 3 primeros días (los datos llegan con retraso), cada día hasta los 30 y cada semana hasta los 90."""
    leido = _fecha((guardado or {}).get("leido"))
    if not leido:
        return True
    edad = ahora - subido
    if edad < dt.timedelta(days=3):
        cada = dt.timedelta(hours=6)
    elif edad < dt.timedelta(days=30):
        cada = dt.timedelta(days=1)
    elif edad < dt.timedelta(days=DIAS_LISTA):
        cada = dt.timedelta(days=7)
    else:
        return False
    return ahora - leido >= cada - dt.timedelta(minutes=20)     # margen: los turnos no caen al minuto


def _curva(reel, ahora):
    """Una foto de las cifras al pasar las 6, 24, 48, 168 y 720 horas de vida (solo si se lee cerca de ese momento)."""
    horas = (ahora - _fecha(reel["subido"])).total_seconds() / 3600
    pasados = [p for p in PUNTOS_CURVA if horas >= p]
    if not pasados:
        return
    p = pasados[-1]
    curva = reel.setdefault("curva", {})
    if str(p) not in curva and horas <= p * 1.5 + 6:
        m = reel.get("metricas") or {}
        curva[str(p)] = {"horas": round(horas, 1), **{k: m[k] for k in ("views", "reach", "likes", "shares", "saved")
                                                     if k in m}}


# --- Lo guardado de cada cuenta (estado/redes/instagram/<alias>.json, con su huella para reconocerlo) ---

def _ruta(alias):
    return os.path.join(CARPETA, f"{alias}.json")


def _es_suya(datos, huella_cuenta, hueco, alias=None):
    """¿Es de esta cuenta lo guardado? Por su huella, que no cambia nunca; si el fichero no la lleva (es de antes),
    por hueco y alias a la vez. Así nunca se mezclan las cifras de dos cuentas que han tenido el mismo hueco o alias."""
    if datos.get("huella"):
        return bool(huella_cuenta) and datos["huella"] == huella_cuenta
    return bool(alias) and datos.get("hueco") == hueco and datos.get("alias") == alias


def _ficheros():
    for ruta in sorted(glob.glob(os.path.join(privado.carpeta(), CARPETA, "*.json"))):
        yield ruta, privado.leer(os.path.relpath(ruta, privado.carpeta()), {}) or {}


def buscar(huella_cuenta, hueco, alias=None):
    """(ruta, datos) de lo último guardado de la cuenta, o (None, {}). El alias puede cambiar si entra un barrio nuevo."""
    for ruta, datos in _ficheros():
        if _es_suya(datos, huella_cuenta, hueco, alias):
            return ruta, datos
    return None, {}


def cargar(huella_cuenta, hueco, alias=None):
    return buscar(huella_cuenta, hueco, alias)[1]


def guardar(alias, hueco, huella_cuenta, datos):
    """Guarda estado/redes/instagram/<alias>.json. Quita las copias de esta cuenta con otro alias; y si <alias>.json
    era de OTRA cuenta (los alias se corren al entrar un barrio nuevo), lo aparta en vez de pisarlo: esa cuenta lo
    vuelve a encontrar por su huella en su lectura."""
    for ruta, otro in _ficheros():
        suyo = _es_suya(otro, huella_cuenta, hueco, alias)
        if os.path.basename(ruta) == f"{alias}.json":
            if otro and not suyo:
                marca = otro.get("huella") or f"hueco-{otro.get('hueco')}"
                os.replace(ruta, os.path.join(os.path.dirname(ruta), f"apartado-{marca}.json"))
        elif suyo:
            os.remove(ruta)
    privado.escribir(_ruta(alias), dict(datos, alias=alias, hueco=hueco, huella=huella_cuenta, red="instagram",
                                        actualizado=_iso(_ahora())))


def _vetos(d, veto):
    return ((d.get("instagram") or {}).get("cuentas") or {}).get(veto) or {}


def metricas_vetadas(veto, grupo, ahora):
    """Las métricas («reel» o «extra») que Meta no da a ESA cuenta; se vuelven a probar al mes."""
    vetadas = _vetos(privado.leer(METRICAS, {}) or {}, veto).get(grupo) or {}
    return {m for m, hasta in vetadas.items() if (_fecha(hasta) or ahora) > ahora}


def apuntar_vetos(veto, grupo, fallos, aciertos, ahora):
    """Deja de pedir 30 días, solo a esa cuenta, la métrica que ha fallado en 3 reels o más que sí daban las demás y
    no ha salido en ninguno; la que sale se vuelve a pedir."""
    if not fallos and not aciertos:
        return
    d = privado.leer(METRICAS, {}) or {}
    parte = d.setdefault("instagram", {})
    parte.pop("reel", None)                     # el veto de antes valía para todas las cuentas a la vez: fuera
    vetadas = parte.setdefault("cuentas", {}).setdefault(veto, {}).setdefault(grupo, {})
    hasta = _iso(ahora + dt.timedelta(days=VETO_DIAS))
    for m, n in fallos.items():
        if n >= VETO_REELS and not aciertos.get(m):
            vetadas[m] = hasta
    for m in aciertos:
        vetadas.pop(m, None)
    d["actualizado"] = _iso(ahora)
    privado.escribir(METRICAS, d)


def _sumar(cuenta, nombres):
    for m in nombres:
        cuenta[m] = cuenta.get(m, 0) + 1


def leer_reel(cuenta, r, metricas, extras, cuentas, ahora):
    """Lee las cifras de un reel y las deja en `r`. Devuelve None o el error que impide leerlo. `cuentas` lleva cuántas
    veces falla y sale cada métrica en esta cuenta y pasada (solo de reels que sí tienen estadísticas)."""
    sospechosas = {m for m, n in cuentas["fallos"].items() if n}
    cifras, faltan, e = cifras_reel(cuenta, r["id"], metricas, sospechosas, bool(r.get("sin_estadisticas")))
    if e == SIN_DATOS:                          # no da ninguna (p. ej., de antes de ser cuenta profesional)
        r.update(sin_estadisticas=True, leido=_iso(ahora))
        return None
    if e:
        return e
    _sumar(cuentas["fallos"], faltan)
    _sumar(cuentas["aciertos"], cifras)
    if extras:                                  # reposts y facebook_views: aparte, y no cuentan para las de arriba
        mas, no, e2 = cifras_reel(cuenta, r["id"], extras)
        if e2 == 190:
            return 190
        if e2 in (None, SIN_DATOS):
            no = list(extras) if e2 == SIN_DATOS else no
            _sumar(cuentas["efallos"], no)
            _sumar(cuentas["eaciertos"], mas)
            cifras, faltan = dict(cifras, **mas), faltan + no
    r.pop("sin_estadisticas", None)
    r.update(metricas=dict(r.get("metricas") or {}, **cifras), leido=_iso(ahora))
    if faltan:
        r["faltan"] = faltan
    else:
        r.pop("faltan", None)
    _curva(r, ahora)
    return None


def leer_cuenta(clave, con, token, ahora, decir):
    """Lee la cuenta y guarda sus cifras. Devuelve «bien», «parado» (cupo de Meta), «caducado», «otra_cuenta» o «error_N»."""
    alias, hueco = privado.alias(clave), con["hueco"]
    cuenta = Cuenta(token)
    yo, err = cuenta.get("me", {"fields": "user_id,username,account_type,followers_count,media_count"})
    if err == 100:                                                   # algún campo no vale: lo justo
        yo, err = cuenta.get("me", {"fields": "user_id,username"})
    if err == 190:
        return "caducado"
    if err:
        return f"error_{err}"
    ocultar(yo.get("username"), yo.get("user_id"))
    if con.get("huella") and huella(yo.get("user_id")) != con["huella"]:
        return "otra_cuenta"
    suya = con.get("huella") or huella(yo.get("user_id"))
    anterior = cargar(suya, hueco, alias)
    viejos = {r["id"]: r for r in anterior.get("reels") or [] if isinstance(r, dict) and r.get("id")}
    lista, err = lista_reels(cuenta, ahora)
    if err == 190:
        return "caducado"
    if err:
        decir(f"instagram {alias}: la lista de reels no llega entera (error {err}); se repite en la próxima pasada")
    malas = metricas_vetadas(suya, "reel", ahora)
    metricas = [m for m in METRICAS_REEL if m not in malas] or list(METRICAS_REEL)     # nunca una lista vacía
    extras = [m for m in METRICAS_EXTRA if m not in metricas_vetadas(suya, "extra", ahora)]
    cuentas = {"fallos": {}, "aciertos": {}, "efallos": {}, "eaciertos": {}}
    leidos, estado = 0, "bien"
    for r in lista:
        guardado = viejos.get(r["id"]) or {}
        r = dict(guardado, **{k: v for k, v in r.items() if v is not None})
        viejos[r["id"]] = r
        if cuenta.uso > TOPE_USO:
            estado = "parado"
            continue
        if not toca_releer(guardado, _fecha(r["subido"]), ahora):
            continue
        e = leer_reel(cuenta, r, metricas, extras, cuentas, ahora)
        if e == 190:
            return "caducado"
        if e:
            decir(f"instagram {alias}: un reel no da sus cifras (error {e}); se repite en la próxima pasada")
            continue
        leidos += 1
    apuntar_vetos(suya, "reel", cuentas["fallos"], cuentas["aciertos"], ahora)
    apuntar_vetos(suya, "extra", cuentas["efallos"], cuentas["eaciertos"], ahora)
    reels = sorted(viejos.values(), key=lambda x: x.get("subido") or "", reverse=True)[:REELS]
    dias = dict(anterior.get("dias") or {})
    cifras_cuenta = {"seguidores": _entero(yo.get("followers_count")), "publicaciones": _entero(yo.get("media_count"))}
    if cifras_cuenta["seguidores"] is not None:
        dias[_iso(ahora)[:10]] = cifras_cuenta
    limite = _iso(ahora - dt.timedelta(days=DIAS_CUENTA))[:10]
    dias = {d: v for d, v in sorted(dias.items()) if d >= limite}
    guardar(alias, hueco, suya, {"tipo_cuenta": yo.get("account_type"), "cuenta": dict(cifras_cuenta, fecha=_iso(ahora)),
                                 "dias": dias, "reels": reels})
    decir(f"instagram {alias}: {len(lista)} reels en la lista, {leidos} releídos"
          + (" (Meta pide parar: el resto en la próxima pasada)" if estado == "parado" else ""))
    return estado


# --- Renovar ---

def renovar_si_toca(clave, con, token, llave, ahora, decir):
    """Una vez por semana: permiso nuevo de 60 días en el mismo secreto. Devuelve el token que vale ahora (o None si
    ha caducado; entonces `con` queda en «caducado»)."""
    alias = privado.alias(clave)
    caduca = _fecha(con.get("caduca"))
    if caduca and caduca <= ahora:
        con.update(estado="caducado", motivo="pasaron los 60 días sin renovar", caducado_desde=_iso(ahora))
        return None
    base = _fecha(con.get("renovado") or con.get("desde"))
    if base and ahora - base < dt.timedelta(days=RENOVAR_DIAS):
        return token
    if not puede_guardar(llave):
        decir(f"instagram {alias}: no puedo guardar secretos (GH_SECRETOS): no renuevo en esta pasada")
        return token
    nuevo, segundos, err = renovar(token)
    if err == 190:
        con.update(estado="caducado", motivo="Meta ya no acepta el permiso", caducado_desde=_iso(ahora))
        return None
    if not nuevo:
        decir(f"instagram {alias}: no se ha podido renovar (error {err}); se intenta en la próxima pasada")
        return token
    if not guardar_con_reintentos(f"IG_TOKEN_{con['hueco']}", nuevo, llave):
        decir(f"instagram {alias}: renovado pero no guardado; se repite en la próxima pasada")
        con["aviso"] = "renovado_sin_guardar"
        return nuevo
    con.update(renovado=_iso(ahora), caduca=_iso(ahora + dt.timedelta(seconds=segundos)), aviso=None)
    decir(f"instagram {alias}: permiso renovado")
    return nuevo


# --- Para los gráficos de la app ---

def al_contador(clave, con, ahora):
    """Pasa el resumen de la cuenta al Contador de redes (mismo formato que sus cifras de TikTok, con auto «api»; los
    seguidores de cada día llevan fuente «api» para poder borrarlos si se pierde el permiso)."""
    datos = cargar(con.get("huella"), con.get("hueco"), privado.alias(clave))
    if not datos:
        return
    reels = datos.get("reels") or []

    def suma(k):
        valores = [(r.get("metricas") or {}).get(k) for r in reels]
        return sum(v for v in valores if isinstance(v, (int, float))) if any(v is not None for v in valores) else None

    cifras = {"seguidores": (datos.get("cuenta") or {}).get("seguidores"),
              "publicaciones": (datos.get("cuenta") or {}).get("publicaciones"),
              "visitas": suma("views"), "meGusta": suma("likes"), "comentarios": suma("comments"),
              "compartidos": suma("shares"), "guardados": suma("saved"), "reels": len(reels)}
    cifras = {k: v for k, v in cifras.items() if v is not None}
    c = privado.leer(CONTADOR, {}) or {}
    c.setdefault("cuentas", {}).setdefault(clave, {})["instagram"] = dict(cifras, fecha=_iso(ahora), auto="api")
    if cifras.get("seguidores") is not None:
        c.setdefault("dias", {}).setdefault(_iso(ahora)[:10], {}).setdefault(clave, {})["instagram"] = dict(
            cifras, fuente="api")
    c.setdefault("videos_instagram", {})[clave] = [_para_app(r) for r in reels[:12]]
    privado.escribir(CONTADOR, c)


def _para_app(r):
    m = r.get("metricas") or {}
    salida = {"titulo": str(r.get("texto") or "")[:100], "visitas": m.get("views"), "alcance": m.get("reach"),
              "meGusta": m.get("likes", r.get("meGusta")), "comentarios": m.get("comments", r.get("comentarios")),
              "compartidos": m.get("shares"), "guardados": m.get("saved"),
              "tiempoMedioMs": m.get("ig_reels_avg_watch_time"), "saltanAlInicio": m.get("reels_skip_rate"),
              "subido": r.get("subido"), "codigo": r.get("codigo")}
    return {k: v for k, v in salida.items() if v is not None}


def _quitar_del_contador(clave):
    """Quita del Contador de redes lo que vino de Meta de una cuenta: su resumen (auto «api»), sus reels y sus
    seguidores de cada día (fuente «api»). Lo que el Contador lee de la página pública se queda."""
    c = privado.leer(CONTADOR, {}) or {}
    suya = (c.get("cuentas") or {}).get(clave) or {}
    if (suya.get("instagram") or {}).get("auto") == "api":
        suya.pop("instagram")
    (c.get("videos_instagram") or {}).pop(clave, None)
    for dia in (c.get("dias") or {}).values():
        redes = dia.get(clave) if isinstance(dia, dict) else None
        if isinstance(redes, dict) and (redes.get("instagram") or {}).get("fuente") == "api":
            redes.pop("instagram")
    privado.escribir(CONTADOR, c)


def olvidar(clave, con, ahora, decir, ya=False):
    """Borra las copias de las cifras que vinieron de Meta de una cuenta sin permiso (lo piden sus normas): a los 30
    días sin permiso, en cualquier estado que no sea «conectado», o ya (`ya`) si Meta avisó de que se pidió el borrado
    y se ha confirmado. Su fichero se queda solo si lo usa otra conexión viva de la misma cuenta. Apunta «borrado» en
    `con` y devuelve True si ha borrado."""
    if con.get("borrado") or con.get("estado") == "conectado":
        return False
    desde = _fecha(con.get("caducado_desde") or con.get("desde"))
    if not ya and (not desde or ahora - desde < dt.timedelta(days=OLVIDAR_DIAS)):
        return False
    barrios = set(privado.config().get("barrios") or {})
    suya = con.get("huella")
    viva = suya and any(c != clave and x.get("estado") == "conectado" and x.get("huella") == suya
                        for c, x in entradas(privado.leer(CONEXIONES, {}) or {}))
    if not viva:
        ruta, _ = buscar(suya, con.get("hueco"), privado.alias(clave) if clave in barrios else None)
        if ruta and os.path.exists(ruta):
            os.remove(ruta)
        d = privado.leer(METRICAS, {}) or {}
        if suya and ((d.get("instagram") or {}).get("cuentas") or {}).pop(suya, None) is not None:
            privado.escribir(METRICAS, d)
    _quitar_del_contador(clave)
    con["borrado"] = _iso(ahora)
    por_que = "pidió el borrado y su permiso ya no vale" if ya else f"sin permiso desde hace {OLVIDAR_DIAS} días"
    decir(f"instagram {nombre_publico(clave, barrios)}: {por_que}: copias borradas")
    return True


# --- Antes de leer: cuentas retiradas, avisos de Meta y la que se está conectando ---

def retirar(barrios, ahora, decir):
    """Las conexiones de cuentas que ya no están en config/canales.json → barrios no se leen ni se renuevan: su clave
    (el nombre de la cuenta) no tiene alias y saldría tal cual en el registro. Quedan sin permiso desde ahora («fuera
    de la lista») y se olvidan a los 30 días."""
    n = 0
    for clave, con in entradas(privado.leer(CONEXIONES, {}) or {}):
        if clave in barrios or con.get("borrado") or con.get("motivo") == FUERA:
            continue
        desde = con.get("caducado_desde") if con.get("estado") != "conectado" else None
        apuntar_conexion(clave, dict(con, estado="caducado", motivo=FUERA, caducado_desde=desde or _iso(ahora)))
        n += 1
    if n == 1:
        decir(f"instagram: 1 conexión de una cuenta que ya no está en la lista: no se lee y se olvida a los "
              f"{OLVIDAR_DIAS} días")
    elif n:
        decir(f"instagram: {n} conexiones de cuentas que ya no están en la lista: no se leen y se olvidan a los "
              f"{OLVIDAR_DIAS} días")


def recoger_avisos(redes_cfg, ahora, decir):
    """Trae los avisos de Meta (baja o borrado) que esperan en el Buzón de vuelta (que los borra al darlos) y los deja
    en estado/redes/avisos_meta.json hasta comprobarlos. Del número de cuenta que manda Meta solo queda su huella."""
    llave = os.environ.get("VUELTA_LLAVE", "").strip()
    web = str(redes_cfg.get("vuelta_web") or "").rstrip("/")
    base = str(redes_cfg.get("recoger") or (f"{web}/recoger" if web else ""))
    if not llave or not base.startswith("https://"):
        return
    ocultar(llave)
    st, datos, _ = _http("GET", f"{base}?marcas=1", cabeceras={"Authorization": f"Bearer {llave}"})
    if st != 200:
        decir(f"instagram: no he podido mirar los avisos de Meta (código {st or 'sin respuesta'}); otra vez en la "
              "próxima pasada")
        return
    marcas = [m for m in datos.get("marcas") or [] if isinstance(m, dict) and m.get("tipo") in ("baja", "borrado")]
    if not marcas:
        return
    d = privado.leer(AVISOS, {}) or {}
    for m in marcas:
        usuario = re.sub(r"\D", "", str(m.get("usuario") or ""))
        d.setdefault("avisos", []).append({"tipo": m["tipo"], "huella": huella(usuario) if usuario else None,
                                            "llegado": _iso(ahora)})
    d["actualizado"] = _iso(ahora)
    privado.escribir(AVISOS, d)
    decir(f"instagram: {len(marcas)} {'aviso' if len(marcas) == 1 else 'avisos'} de Meta para comprobar")


def sin_permiso(con):
    """True si el permiso guardado ya no vale para esa cuenta (no está, error 190 o es de otra cuenta), False si vale
    y None si no se sabe (la red falla)."""
    if con.get("estado") != "conectado":
        return True
    token = os.environ.get(f"IG_TOKEN_{con.get('hueco')}", "").strip()
    if not token:
        return True
    yo, err = Cuenta(token).get("me", {"fields": "user_id"})
    ocultar(yo.get("user_id"))
    if err == 190:
        return True
    if err:
        return None
    return bool(con.get("huella")) and huella(yo.get("user_id")) != con["huella"]


def atender_avisos(barrios, ahora, decir):
    """Comprueba los avisos de Meta pendientes. Cada uno vale para las cuentas con esa huella o, si Meta manda otro
    número, para las conectadas; y solo si la API confirma que su permiso ya no funciona (un aviso falso no borra
    nada). Entonces la cuenta queda sin permiso desde ahora y, si se pidió el borrado, se olvida ya. Los que no se
    pueden comprobar (la red falla) esperan a la próxima pasada. Devuelve cuántas cuentas se han olvidado."""
    d = privado.leer(AVISOS, {}) or {}
    if not d.get("avisos"):
        return 0
    quedan, olvidadas = [], 0
    for aviso in d["avisos"]:
        if ahora - (_fecha(aviso.get("llegado")) or ahora) > dt.timedelta(days=OLVIDAR_DIAS):
            continue
        vivas = [(c, x) for c, x in entradas(privado.leer(CONEXIONES, {}) or {}) if not x.get("borrado")]
        suyas = [(c, x) for c, x in vivas if aviso.get("huella") and x.get("huella") == aviso["huella"]]
        dudas = False
        for clave, con in suyas or [(c, x) for c, x in vivas if x.get("estado") == "conectado"]:
            sin = sin_permiso(con)
            dudas = dudas or sin is None
            if not sin:
                continue
            con = dict(con)
            if con.get("estado") == "conectado":
                con.update(estado="caducado", motivo="se quitó el permiso (aviso de Meta)", caducado_desde=_iso(ahora))
                decir(f"instagram {nombre_publico(clave, barrios)}: Meta avisa de que se quitó el permiso")
            if aviso.get("tipo") == "borrado":
                con.setdefault("caducado_desde", _iso(ahora))
                olvidadas += olvidar(clave, con, ahora, decir, ya=True)
            apuntar_conexion(clave, con)
        if dudas:
            quedan.append(aviso)
    d.update(avisos=quedan, actualizado=_iso(ahora))
    privado.escribir(AVISOS, d)
    return olvidadas


def conectando(ahora):
    """El alias de la cuenta que «Conectar redes» está conectando ahora mismo (su enlace aún espera), o None. Esa
    cuenta no se renueva ni se lee en esta pasada: así nunca se cruzan dos permisos en el mismo secreto."""
    e = privado.leer(CONECTANDO, {}) or {}
    caduca = _fecha(e.get("caduca"))
    if e.get("estado") == "esperando" and not e.get("terminado") and caduca and ahora < caduca + dt.timedelta(minutes=15):
        return e.get("barrio")
    return None


# --- La pasada ---

def leer_conectada(clave, con, renovar_permisos, llave, ahora, decir):
    """Renueva (si toca) y lee una cuenta conectada; deja su estado en `con`. Devuelve cómo ha ido."""
    hueco = con.get("hueco")
    token = os.environ.get(f"IG_TOKEN_{hueco}", "").strip() if hueco else ""
    if not token:
        con.update(estado="caducado", motivo="no está su permiso en los secretos", caducado_desde=_iso(ahora))
        return "caducado"
    if renovar_permisos:
        token = renovar_si_toca(clave, con, token, llave, ahora, decir)
    estado = leer_cuenta(clave, con, token, ahora, decir) if token else "caducado"
    if estado == "caducado" and con.get("estado") != "caducado":
        con.update(estado="caducado", motivo="Meta ya no acepta el permiso", caducado_desde=_iso(ahora))
    elif estado == "otra_cuenta":
        con.update(estado="otra_cuenta", motivo="el permiso ya no es de esta cuenta", caducado_desde=_iso(ahora))
    elif estado in ("bien", "parado"):
        con.update(leido=_iso(ahora))
        al_contador(clave, con, ahora)
    return estado


def pasada(renovar_permisos=True, decir=None):
    """Una pasada entera. Devuelve ({alias: cómo ha ido} de las cuentas conectadas, cuántas cuentas se han olvidado)."""
    decir = decir or (lambda t: print(privado.limpiar(t), flush=True))
    ahora = _ahora()
    redes_cfg = privado.leer(os.path.join("config", "redes.json"), {}) or {}
    fijar_version(redes_cfg.get("version_meta"))
    ocultar(*(privado.leer(CONEXIONES, {}) or {}))          # las claves son nombres de cuentas: tapadas por si acaso
    for n in range(1, HUECOS + 1):
        ocultar(os.environ.get(f"IG_TOKEN_{n}"))
    barrios = set(privado.config().get("barrios") or {})
    retirar(barrios, ahora, decir)
    if any(True for _ in entradas(privado.leer(CONEXIONES, {}) or {})):     # sin conexiones, no hay a quién avisar
        recoger_avisos(redes_cfg, ahora, decir)
    olvidadas = atender_avisos(barrios, ahora, decir)
    for clave, con in entradas(privado.leer(CONEXIONES, {}) or {}):     # las que perdieron el permiso hace mucho
        con = dict(con)
        if olvidar(clave, con, ahora, decir):
            apuntar_conexion(clave, con)
            olvidadas += 1
    conexiones = privado.leer(CONEXIONES, {}) or {}
    conectadas = [c for c, x in entradas(conexiones) if c in barrios and x.get("estado") == "conectado"]
    if not conectadas:
        decir("instagram: ninguna cuenta conectada; nada que hacer")
        return {}, olvidadas
    ocupada = conectando(ahora)
    llave = os.environ.get("GH_SECRETOS", "")
    resultado = {}
    for clave in conectadas:
        con = dict(conexiones[clave]["instagram"])
        alias = privado.alias(clave)
        if alias == ocupada:
            decir(f"instagram {alias}: se está conectando ahora mismo; no se toca en esta pasada")
            continue
        resultado[alias] = leer_conectada(clave, con, renovar_permisos, llave, ahora, decir)
        if con.get("estado") != "conectado":
            decir(f"instagram {alias}: {con['estado']}: hay que volver a conectarla desde la app")
        apuntar_conexion(clave, con)
    return resultado, olvidadas


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-renovar", action="store_true", help="solo lee; no renueva ningún permiso")
    a = p.parse_args(argv)
    try:
        resultado, olvidadas = pasada(renovar_permisos=not a.sin_renovar)
    except Exception as e:                                   # sin detalles: podrían llevar una dirección con token
        print(f"instagram: algo ha fallado ({type(e).__name__}); se repite en la próxima pasada", flush=True)
        return 1
    if resultado or olvidadas:
        from bots.influencers import contador                # los gráficos de la app, con lo nuevo de Instagram
        contador.para_app()
    if resultado:
        cuaderno = privado.cuaderno("contable_instagram")
        cuaderno.apuntar("lectura", {"cuentas": len(resultado),
                                     "bien": sum(1 for v in resultado.values() if v in ("bien", "parado"))})
        cuaderno.guardar()
        print(f"instagram: {len(resultado)} cuentas repasadas", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
