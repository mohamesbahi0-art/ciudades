"""Conecta las cuentas de Instagram del dueño por la vía OFICIAL de Meta, solo para LEER sus cifras.

Nunca pide permiso para publicar, comentar ni leer mensajes: solo instagram_business_basic +
instagram_business_manage_insights. TikTok no se hace.

Lo lanza GitHub Actions («Conectar redes») cuando aparece peticiones/conectar_redes.json (solo alias, nunca nombres):
  {"red": "instagram", "barrios": ["barrio-2", "barrio-3"]}
Por cada cuenta:
  1. prepara un enlace de permiso de Instagram con una marca al azar (state) y lo deja SOLO en el repositorio privado
     (estado/conexion_redes.json); la ronda de Claude lo pasa a la app y el dueño lo abre en una pestaña de incógnito,
     entra con ESA cuenta y pulsa «Permitir»;
  2. Instagram le lleva al Buzón de vuelta (Cloudflare), que guarda el código unos minutos; aquí se pregunta al Buzón
     cada 5 segundos (/recoger, con la llave VUELTA_LLAVE) durante 45 minutos como mucho;
  3. cambia el código por el permiso de 1 hora y ese por el de 60 días, y mira que es de la cuenta de ese barrio
     (si no, «otra_cuenta» y no se guarda nada);
  4. guarda el permiso en el secreto de GitHub IG_TOKEN_<hueco> (con GH_SECRETOS) y apunta el estado, sin tokens,
     en estado/redes/conexiones.json del privado.
El hueco de cada cuenta es fijo: config/canales.json → barrios.<clave>.estadisticas.instagram; si no lo tiene, se le
da el primero libre (1 a 10) y queda en estado/redes/conexiones.json. Un hueco que ya usa otra cuenta de la lista
(conectada o con su hueco apuntado, o fijo en su configuración) no se da nunca: se para con «hueco repetido» antes de
guardar nada, porque el permiso nuevo pisaría el de la otra. La renovación semanal la hace la Contable de Instagram
(estadisticas_instagram.py) en «Revisar canales», que deja en paz la cuenta que se esté conectando.

Pon todas las cuentas en UNA petición: si se deja otra mientras una está en marcha, espera en la cola, y una tercera
haría que GitHub cancelase la que esperaba sin decir nada.

Los registros de GitHub son PÚBLICOS: solo salen alias y estados. El enlace, el código, los tokens y los usuarios
nunca se imprimen, y cada uno se tapa (::add-mask::) nada más existir.

Secretos: IG_APP_ID e IG_APP_SECRET (los pone el dueño), VUELTA_LLAVE (la deja el despliegue del Buzón) y GH_SECRETOS.
Privado: config/redes.json → {"vuelta_web", "vuelta_instagram", "version_meta"} (lo escribe el despliegue del Buzón).
"""
import datetime as dt
import json
import os
import re
import secrets
import sys
import time
import urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.comun import privado  # noqa: E402
import estadisticas_instagram as ig  # noqa: E402

PETICION = os.path.join(RAIZ, "peticiones", "conectar_redes.json")
ESTADO = os.path.join("estado", "conexion_redes.json")
AUTORIZAR = "https://www.instagram.com/oauth/authorize"
ESPERA_MINUTOS = 45           # lo que se espera a que el dueño pulse «Permitir» en cada cuenta
TOPE_MINUTOS = 110            # el turno tiene 120: se deja margen para guardar
CADA_SEGUNDOS = 5


def decir(texto):
    print(privado.limpiar(texto), flush=True)


def publicar(estado, mensaje):
    """Deja el estado de la conexión en el privado (la ronda de Claude lo pasa a la app) y lo sube."""
    privado.escribir(ESTADO, dict(estado, actualizado=privado.ahora()))
    decir(mensaje)
    privado.git_guardar(mensaje)


def _usuario(texto):
    return str(texto or "").strip().lstrip("@").lower()


def cuenta_instagram(barrio):
    """El usuario de Instagram de un barrio: «cuentas.instagram» si la tiene aparte; si no, «cuenta»."""
    return _usuario((barrio.get("cuentas") or {}).get("instagram") or barrio.get("cuenta"))


def _hueco_valido(n):
    return n if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= ig.HUECOS else None


def _fijo(barrios, clave):
    return _hueco_valido(((barrios.get(clave) or {}).get("estadisticas") or {}).get("instagram"))


def huecos_usados(clave, barrios, conexiones):
    """Los huecos que ya son de OTRA cuenta de la lista: el fijo de su configuración o el apuntado en su conexión
    (salvo si ya se olvidó). Las conexiones de cuentas retiradas de la lista no cuentan: ya no se leen."""
    usados = {_fijo(barrios, c) for c in barrios if c != clave}
    usados |= {_hueco_valido(x.get("hueco")) for c, x in ig.entradas(conexiones)
               if c != clave and c in barrios and not x.get("borrado")}
    return usados - {None}


def elegir_hueco(clave, cfg, conexiones):
    """El hueco de la cuenta (IG_TOKEN_<n>): el fijo de la configuración, el que ya tenía o el primero libre.
    Devuelve (hueco, None) o (None, motivo): nunca uno que ya use otra cuenta."""
    barrios = cfg.get("barrios") or {}
    usados = huecos_usados(clave, barrios, conexiones)
    fijo = _fijo(barrios, clave)
    if fijo:
        return (None, f"hueco repetido: IG_TOKEN_{fijo} ya es de otra cuenta") if fijo in usados else (fijo, None)
    propio = _hueco_valido(((conexiones.get(clave) or {}).get("instagram") or {}).get("hueco"))
    if propio and propio not in usados:
        return propio, None
    libre = next((n for n in range(1, ig.HUECOS + 1) if n not in usados), None)
    return (libre, None) if libre else (None, "no quedan huecos")


def enlace(app_id, vuelta, marca):
    return AUTORIZAR + "?" + urllib.parse.urlencode(
        {"client_id": app_id, "redirect_uri": vuelta, "response_type": "code", "scope": ",".join(ig.PERMISOS),
         "state": marca}, safe=",")


def recoger(buzon, llave, marca, segundos):
    """Pregunta al Buzón de vuelta si ya ha llegado el código (404 = aún no). Devuelve su JSON, «llave_mala»,
    «marca_mala» o None si no llega a tiempo."""
    base = buzon.get("recoger") or f"{buzon['vuelta_web'].rstrip('/')}/recoger"
    url = f"{base}?" + urllib.parse.urlencode({"state": marca})
    fin, fallos = time.time() + segundos, 0
    while time.time() < fin:
        st, datos, _ = ig._http("GET", url, cabeceras={"Authorization": f"Bearer {llave}"})
        if st == 200 and (datos.get("code") or datos.get("error")) and (datos.get("red") or "instagram") == "instagram":
            ig.ocultar(datos.get("code"))
            return datos
        if st in (401, 403):
            return "llave_mala"
        if st == 400:
            return "marca_mala"
        if st not in (200, 204, 404):
            fallos += 1
            if fallos in (1, 20, 100):
                decir(f"conexión instagram: el buzón contesta {st or 'nada'}; sigo esperando")
        time.sleep(CADA_SEGUNDOS)
    return None


def fallo(clave, hueco, estado, motivo, quedan, alias=None):
    """Un intento que no sale: se dice en la app y, si la cuenta ya estaba conectada, su permiso de antes sigue. Si no
    lo estaba, se parte de lo que había (así no se pierden «caducado_desde», «borrado» ni «huella», que hacen falta
    para borrar sus copias a los 30 días) y, si es la primera vez, «caducado_desde» empieza ahora."""
    alias = privado.alias(clave) if clave else alias
    if clave:
        antes = ((privado.leer(ig.CONEXIONES, {}) or {}).get(clave) or {}).get("instagram") or {}
        ahora = privado.ahora()
        intento = {"estado": estado, "motivo": motivo, "fecha": ahora}
        if antes.get("estado") == "conectado":
            ig.apuntar_conexion(clave, dict(antes, ultimo_intento=intento))
        else:
            nuevo = dict(antes, estado=estado, motivo=motivo, ultimo_intento=intento,
                         hueco=hueco or antes.get("hueco"))
            nuevo.setdefault("desde", ahora)
            nuevo.setdefault("caducado_desde", ahora)
            ig.apuntar_conexion(clave, nuevo)
    publicar({"estado": estado, "barrio": alias, "red": "instagram", "motivo": motivo, "quedan": quedan},
             f"conexión instagram {alias}: {estado} ({motivo})")
    return estado


def conectar_barrio(alias, claves, buzon, espera, quedan):
    """Conecta una cuenta. Devuelve su estado final: conectado, otra_cuenta, faltan_permisos, caducado o error.
    `claves` = (IG_APP_ID, IG_APP_SECRET, GH_SECRETOS, VUELTA_LLAVE); `buzon` = config/redes.json."""
    app_id, _, _, llave_buzon = claves
    clave = privado.resolver(alias)
    cfg = privado.config()
    barrio = (cfg.get("barrios") or {}).get(clave)
    if not barrio or "instagram" not in (barrio.get("redes") or [barrio.get("red")]):
        return fallo(None, None, "error", "no es una cuenta de Instagram de la lista", quedan, alias=alias)
    esperada = cuenta_instagram(barrio)
    ig.ocultar(esperada)
    hueco, por_que = elegir_hueco(clave, cfg, privado.leer(ig.CONEXIONES, {}) or {})
    if not esperada or not hueco:
        return fallo(clave, hueco, "error", "sin usuario en la configuración" if not esperada else por_que, quedan)
    marca = secrets.token_urlsafe(24)
    ig.ocultar(marca)
    caduca = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=espera)
    publicar({"estado": "esperando", "barrio": alias, "red": "instagram", "quedan": quedan,
              "enlace": enlace(app_id, buzon["vuelta_instagram"], marca),
              "caduca": caduca.strftime("%Y-%m-%dT%H:%M:%SZ")}, f"conexión instagram {alias}: esperando")
    vuelta = recoger(buzon, llave_buzon, marca, espera)
    if vuelta is None:
        return fallo(clave, hueco, "caducado", "el enlace caducó sin respuesta", quedan)
    if vuelta in ("llave_mala", "marca_mala"):
        motivo = "la llave VUELTA_LLAVE" if vuelta == "llave_mala" else "la marca del enlace"
        return fallo(clave, hueco, "error", f"el buzón de vuelta no acepta {motivo}", quedan)
    if vuelta.get("error") or not vuelta.get("code"):
        rechazo = str(vuelta.get("error") or "") in ("access_denied", "user_denied")
        return fallo(clave, hueco, "error", "el dueño no dio permiso" if rechazo else "Instagram no dio el código", quedan)
    return terminar(clave, hueco, vuelta["code"], esperada, claves, buzon, quedan)


def terminar(clave, hueco, codigo, esperada, claves, buzon, quedan):
    """Del código al permiso de 60 días, comprobado y guardado."""
    app_id, app_secreto, llave, _ = claves                 # llave = GH_SECRETOS
    ig.ocultar(codigo, str(codigo)[:-2])
    corto, permisos, err = ig.canjear_codigo(app_id, app_secreto, buzon["vuelta_instagram"], codigo)
    if not corto:
        return fallo(clave, hueco, "error", f"Instagram no cambió el código (error {err})", quedan)
    if permisos and any(p not in permisos for p in ig.PERMISOS):
        return fallo(clave, hueco, "faltan_permisos", "falta el permiso de estadísticas", quedan)
    largo, segundos, err = ig.token_largo(app_secreto, corto)
    if not largo:
        return fallo(clave, hueco, "error", f"Instagram no dio el permiso de 60 días (error {err})", quedan)
    yo, err = ig.Cuenta(largo).get("me", {"fields": "user_id,username"})
    ig.ocultar(yo.get("username"), yo.get("user_id"))
    if err or not yo.get("user_id"):
        return fallo(clave, hueco, "error", f"Instagram no dice de quién es el permiso (error {err})", quedan)
    if _usuario(yo.get("username")) != esperada:
        return fallo(clave, hueco, "otra_cuenta", "se entró con otra cuenta de Instagram", quedan)
    if not ig.guardar_con_reintentos(f"IG_TOKEN_{hueco}", largo, llave):
        return fallo(clave, hueco, "error", "no pude guardar el permiso en GitHub", quedan)
    ahora = dt.datetime.now(dt.timezone.utc)
    ig.apuntar_conexion(clave, {"estado": "conectado", "desde": ig._iso(ahora), "renovado": ig._iso(ahora),
                                "caduca": ig._iso(ahora + dt.timedelta(seconds=segundos)),
                                "permisos": permisos or list(ig.PERMISOS), "hueco": hueco,
                                "huella": ig.huella(yo["user_id"])})
    alias = privado.alias(clave)
    publicar({"estado": "conectado", "barrio": alias, "red": "instagram", "quedan": quedan - 1},
             f"conexión instagram {alias}: conectado")
    return "conectado"


def preparar():
    """Comprueba secretos, buzón y llave de GitHub. Devuelve (claves, buzón) o None si falta algo (ya avisado)."""
    claves = tuple(os.environ.get(n, "").strip() for n in ("IG_APP_ID", "IG_APP_SECRET", "GH_SECRETOS", "VUELTA_LLAVE"))
    faltan = [n for n, v in zip(("IG_APP_ID", "IG_APP_SECRET", "GH_SECRETOS", "VUELTA_LLAVE"), claves) if not v]
    if faltan:
        fallo(None, None, "error", "faltan los secretos " + ", ".join(faltan), 0)
        return None
    redes = privado.leer(os.path.join("config", "redes.json"), {}) or {}
    if not all(re.match(r"https://", str(redes.get(k) or "")) for k in ("vuelta_web", "vuelta_instagram")):
        fallo(None, None, "error", "falta el buzón de vuelta (config/redes.json)", 0)
        return None
    ig.fijar_version(redes.get("version_meta"))
    if not ig.puede_guardar(claves[2]):
        fallo(None, None, "error", "la llave GH_SECRETOS no deja guardar secretos", 0)
        return None
    return claves, redes


def main():
    try:
        with open(PETICION, encoding="utf-8") as f:
            peticion = json.load(f)
    except (OSError, ValueError):
        decir("conexión: no hay petición (peticiones/conectar_redes.json)")
        return 1
    if str(peticion.get("red") or "instagram") != "instagram":
        decir("conexión: solo se conecta Instagram (TikTok no se hace)")
        return 0
    barrios = [str(b) for b in peticion.get("barrios") or [] if re.fullmatch(r"barrio-\d+", str(b))]
    if not barrios:
        decir("conexión: la petición no trae barrios (barrio-N)")
        return 1
    try:
        listo = preparar()
        if not listo:
            return 1
        claves, buzon = listo
        inicio, resumen = time.time(), {}
        for n, alias in enumerate(barrios):
            queda = TOPE_MINUTOS * 60 - (time.time() - inicio)
            if queda < 5 * 60:
                resumen[alias] = "sin_tiempo"
                continue
            resumen[alias] = conectar_barrio(alias, claves, buzon, min(ESPERA_MINUTOS * 60, queda - 120),
                                             len(barrios) - n)
            if resumen[alias] == "caducado":        # el dueño no está: no se espera por las demás
                break
    except Exception as e:                           # sin detalles: podrían llevar una dirección con token
        fallo(None, None, "error", f"fallo inesperado ({type(e).__name__})", 0)
        return 1
    ultimo = privado.leer(ESTADO, {}) or {}
    ultimo.pop("enlace", None)                       # el enlace ya no sirve
    publicar(dict(ultimo, terminado=True, resumen=resumen),
             "conexión instagram: terminado (" + ", ".join(f"{a} {e}" for a, e in resumen.items()) + ")")
    return 0 if all(e == "conectado" for e in resumen.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
