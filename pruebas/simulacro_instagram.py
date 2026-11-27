"""Simulacro SIN RED de la conexión y la lectura de Instagram (vía oficial de Meta, solo leer). Meta, el Buzón de vuelta
y GitHub son de mentira; el repositorio privado es una carpeta temporal.

Comprueba: conexión buena (permiso guardado en su hueco), otra cuenta (no se guarda nada), cuenta que no es de
Instagram, faltan permisos, enlace que caduca sin respuesta, lectura de los reels con el error 100 en una métrica
(se piden las demás sin ella), dato vacío (no es un 0), renovación semanal (nuevo permiso en el mismo secreto), token
con la cabecera que Meta no acepta (va a la dirección), token caducado (la cuenta queda «caducado»), sin cuentas
conectadas (sale 0 sin hacer nada), el resumen para la app (estado/app/cifras.json) y que el Contador ya no mira la
página pública de una cuenta con cifras oficiales. También: reposts y facebook_views en su llamada aparte (si no
valen, no rompen nada), reels sin estadísticas que no vetan métricas, vetos solo para la cuenta que falla, nunca una
lista de métricas vacía, avisos de Meta (los falsos no borran nada; el de borrado confirmado borra ya), la cuenta que
se está conectando no se toca, hueco repetido, un intento fallido que no pierde la fecha de «sin permiso», «otra
cuenta» que también se olvida a los 30 días (también sus seguidores en el historial), una cuenta retirada de la lista
que no se lee ni sale con su nombre, y cómo se juntan dos versiones de conexiones.json. Y, sobre todo, que NADA de lo
que sale en los registros lleva tokens, códigos, marcas, enlaces, usuarios ni textos de los reels, y que en el privado
no queda ningún token.

    python pruebas/simulacro_instagram.py
"""
import base64
import contextlib
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.parse

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
TMP = tempfile.mkdtemp(prefix="simulacro-instagram-")
PRIV = os.path.join(TMP, "privado")
os.environ.update(PRIVADO=PRIV, MEMORIA_DIR=os.path.join(PRIV, "memoria"), GITHUB_REPOSITORY="dueno/ciudades",
                  GITHUB_ACTIONS="true", IG_APP_ID="1234567890falso", IG_APP_SECRET="secreto-de-app-FALSO-9f8e7d",
                  GH_SECRETOS="llave-github-FALSA-0a1b2c", VUELTA_LLAVE="llave-buzon-FALSA-3d4e5f")
for k in [k for k in os.environ if k.startswith("IG_TOKEN_")]:
    os.environ.pop(k)

from nacl import encoding, public  # noqa: E402

from bots.comun import privado  # noqa: E402
from bots.influencers import contador  # noqa: E402
import conectar_redes  # noqa: E402
import estadisticas_instagram as ig  # noqa: E402
import secretos  # noqa: E402

WEB = "https://buzon-falso.pages.dev"
VUELTA = WEB + "/vuelta/instagram"
USUARIOS = {"uno": "usuario.uno.falso", "dos": "usuario.dos.falso", "otra": "otra.persona.falsa"}
IDS = {"uno": "17840000000000111", "dos": "17840000000000222", "otra": "17840000000000999"}
SALIDA = io.StringIO()                  # todo lo que iría al registro público de GitHub
PROHIBIDO = set(USUARIOS.values()) | set(IDS.values()) | {os.environ[k] for k in (
    "IG_APP_SECRET", "GH_SECRETOS", "VUELTA_LLAVE")}
TAPADO_OBLIGATORIO = set(USUARIOS.values()) | set(IDS.values())


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que, flush=True)
    if not cond:
        print("\n--- registro ---\n" + SALIDA.getvalue()[-4000:])
        sys.exit(1)


def escribir(ruta, datos):
    os.makedirs(os.path.dirname(os.path.join(PRIV, ruta)), exist_ok=True)
    with open(os.path.join(PRIV, ruta), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)


def leer(ruta, defecto=None):
    try:
        with open(os.path.join(PRIV, ruta), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


# --- El repositorio privado de mentira (los barrios van por orden: dos = barrio-1, tres = barrio-2, uno = barrio-3) ---
escribir("config/canales.json", {"canales": {}, "barrios": {
    "cuenta_uno_falsa": {"red": "instagram", "redes": ["instagram", "tiktok"], "cuenta": USUARIOS["uno"],
                         "estado": "activo"},
    "cuenta_dos_falsa": {"red": "instagram", "redes": ["instagram", "tiktok"], "cuenta": USUARIOS["dos"],
                         "estado": "activo", "estadisticas": {"instagram": 4}},
    "cuenta_tres_falsa": {"red": "tiktok", "redes": ["tiktok"], "cuenta": "solo.tiktok.falso", "estado": "activo"}}})
escribir("config/redes.json", {"vuelta_web": WEB, "vuelta_instagram": VUELTA, "version_meta": "v26.0"})
PROHIBIDO.add("solo.tiktok.falso")
GUARDADOS = []
privado.git_guardar = lambda mensaje, intentos=5: GUARDADOS.append(mensaje) or True


class Reloj:
    """El tiempo de mentira: cada espera avanza el reloj sin esperar de verdad."""
    ahora = 1_800_000_000.0

    def time(self):
        return self.ahora

    def sleep(self, s):
        self.ahora += s


conectar_redes.time = Reloj()
ig.time = conectar_redes.time

# --- GitHub de mentira: guarda los secretos abriéndolos con la llave privada ---
LLAVE_PRIVADA = public.PrivateKey.generate()
SECRETOS = {}


def github_falso(metodo, ruta, llave, datos=None):
    assert llave == os.environ["GH_SECRETOS"]
    if metodo == "GET" and ruta == "actions/secrets/public-key":
        return {"key": LLAVE_PRIVADA.public_key.encode(encoding.Base64Encoder()).decode(), "key_id": "k1"}
    if metodo == "PUT" and ruta.startswith("actions/secrets/"):
        abierto = public.SealedBox(LLAVE_PRIVADA).decrypt(base64.b64decode(datos["encrypted_value"])).decode()
        SECRETOS[ruta.rsplit("/", 1)[1]] = abierto
        return {}
    raise AssertionError(ruta)


secretos.github = github_falso

# --- Meta y el Buzón de vuelta de mentira ---
MUNDO = {"cabecera_ok": True, "tokens": {}, "caducados": set(), "codigos": {}, "llamadas": [], "guion": [],
         "estados_vistos": {}, "enlaces": [], "n": 0, "marcas": [], "pedidas": []}
LARGO = "x" * 300


def _reel(uid, n, dias, tipo="REELS"):
    subido = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {"id": f"{uid[-3:]}0{n}", "media_type": "VIDEO" if tipo == "REELS" else "IMAGE", "media_product_type": tipo,
            "timestamp": subido, "permalink": f"https://www.instagram.com/{USUARIOS['uno']}/reel/CodReel{uid[-3:]}{n}/",
            "caption": f"Texto del reel {n} de la cuenta {USUARIOS['uno']} " + LARGO, "like_count": 10 * n,
            "comments_count": n}


MEDIA = {IDS["uno"]: [_reel(IDS["uno"], 1, 0.2), _reel(IDS["uno"], 2, 2), _reel(IDS["uno"], 3, 5, "FEED"),
                      _reel(IDS["uno"], 4, 20), _reel(IDS["uno"], 5, 120)],
         IDS["dos"]: [_reel(IDS["dos"], 1, 1), _reel(IDS["dos"], 2, 10)]}
NO_VALE = {f"{IDS['uno'][-3:]}02": {"reels_skip_rate"},           # Meta no da esta métrica para este reel (error 100)
           f"{IDS['uno'][-3:]}01": {"facebook_views"}}            # ni esta otra, de la llamada aparte
VACIA = {f"{IDS['uno'][-3:]}01": {"ig_reels_video_view_total_time"}}   # aún sin dato: lista vacía
for t in list(MEDIA.values()):
    for m in t:
        PROHIBIDO.update({m["permalink"], m["caption"][:60]})


def _token_nuevo(tipo, quien):
    MUNDO["n"] += 1
    token = f"IG{tipo}-{quien}-{MUNDO['n']}-tokenFALSO"
    MUNDO["tokens"][token] = quien
    PROHIBIDO.add(token)
    TAPADO_OBLIGATORIO.add(token)
    return token


def _error(codigo_meta, http=400):
    return http, {"error": {"message": "mensaje con detalles que no deben salir", "type": "OAuthException",
                            "code": codigo_meta, "fbtrace_id": "AbCdEf"}}, {}


def _buzon(url, cabeceras):
    if cabeceras.get("Authorization") != f"Bearer {os.environ['VUELTA_LLAVE']}":
        return 401, {}, {}
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if q.get("marcas") == ["1"]:                                  # los avisos de Meta: se dan una vez y se borran
        marcas, MUNDO["marcas"] = MUNDO["marcas"], []
        return 200, {"marcas": marcas}, {}
    marca = q["state"][0]
    PROHIBIDO.add(marca)
    TAPADO_OBLIGATORIO.add(marca)
    if marca not in MUNDO["estados_vistos"]:                     # el dueño abre el enlace que le dejó la app
        enlace = leer("estado/conexion_redes.json", {}).get("enlace")
        MUNDO["enlaces"].append(enlace)
        PROHIBIDO.add(enlace)
        MUNDO["estados_vistos"][marca] = {"accion": MUNDO["guion"].pop(0), "vueltas": 0}
    paso = MUNDO["estados_vistos"][marca]
    paso["vueltas"] += 1
    accion = paso["accion"]
    if accion[0] == "nada" or paso["vueltas"] < 3 or paso.get("recogido"):
        return 404, {}, {}
    paso["recogido"] = True
    if accion[0] == "cancelar":
        return 200, {"red": "instagram", "code": None, "error": "access_denied", "hora": "x"}, {}
    MUNDO["n"] += 1
    codigo = f"AQCodigoFALSO{MUNDO['n']}xyz"
    MUNDO["codigos"][codigo] = accion
    PROHIBIDO.update({codigo, codigo + "#_"})
    TAPADO_OBLIGATORIO.add(codigo)
    return 200, {"red": "instagram", "code": codigo + "#_", "error": None, "hora": "x"}, {}


def _canje(datos):
    assert datos["client_id"] == os.environ["IG_APP_ID"] and datos["client_secret"] == os.environ["IG_APP_SECRET"]
    assert datos["redirect_uri"] == VUELTA and datos["grant_type"] == "authorization_code"
    accion = MUNDO["codigos"].pop(datos["code"], None)              # sin «#_» y de un solo uso
    if not accion:
        return 400, {"error_type": "OAuthException", "code": 400, "error_message": "Invalid code"}, {}
    _, quien, permisos, plano = accion
    token = _token_nuevo("corto", quien)
    cuerpo = {"access_token": token, "user_id": "app" + IDS[quien], "permissions": permisos}
    return 200, (cuerpo if plano else {"data": [dict(cuerpo, permissions=",".join(permisos))]}), {}


def _token_de(url, cabeceras):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "access_token" in q:
        return q["access_token"][0], "direccion"
    auth = cabeceras.get("Authorization", "")
    if MUNDO["cabecera_ok"] and auth.startswith("Bearer "):
        return auth[7:], "cabecera"
    return None, None


def _graph(url, cabeceras):
    p = urllib.parse.urlparse(url)
    q = {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}
    if p.path == "/access_token":
        assert q["client_secret"] == os.environ["IG_APP_SECRET"] and q["grant_type"] == "ig_exchange_token"
        quien = MUNDO["tokens"].pop(q["access_token"], None)
        return (200, {"access_token": _token_nuevo("largo", quien), "token_type": "bearer", "expires_in": 5184000}, {}) \
            if quien else _error(190)
    token, via = _token_de(url, cabeceras)
    if p.path == "/refresh_access_token":
        if token in MUNDO["caducados"] or token not in MUNDO["tokens"]:
            return _error(190)
        return 200, {"access_token": _token_nuevo("renovado", MUNDO["tokens"][token]), "token_type": "bearer",
                     "expires_in": 5184000}, {}
    if not token:
        return _error(2500)
    if token in MUNDO["caducados"] or token not in MUNDO["tokens"]:
        return _error(190)
    quien = MUNDO["tokens"][token]
    uid = IDS[quien]
    MUNDO["llamadas"].append((p.path, via, token))
    assert p.path.startswith("/v26.0/"), p.path
    ruta = p.path[len("/v26.0/"):]
    uso = {"x-app-usage": json.dumps({"call_count": 5, "total_cputime": 2, "total_time": 3})}
    if ruta == "me":
        todo = {"user_id": uid, "username": USUARIOS[quien], "account_type": "MEDIA_CREATOR",
                "followers_count": 150 if quien == "uno" else 80, "media_count": len(MEDIA.get(uid, []))}
        return 200, {k: todo[k] for k in q["fields"].split(",")}, uso
    if ruta == "me/media":
        lista, desde = MEDIA.get(uid, []), int(q.get("after") or 0)
        trozo = lista[desde:desde + 2]                               # páginas de 2 para probar el paso de página
        paging = {"cursors": {"before": "a", "after": str(desde + 2)}}
        if desde + 2 < len(lista):
            paging["next"] = f"https://graph.instagram.com/v26.0/me/media?access_token={token}&after={desde + 2}"
        return 200, {"data": trozo, "paging": paging}, uso
    if ruta.endswith("/insights"):
        media = ruta.split("/")[0]
        assert q.get("metric"), "nunca se piden las estadísticas con la lista de métricas vacía"
        MUNDO["pedidas"].append((media, q["metric"]))
        pedidas = q["metric"].split(",")
        if NO_VALE.get(media, set()) & set(pedidas):
            return _error(100)
        datos = [{"name": m, "period": "lifetime", "values": [] if m in VACIA.get(media, set())
                  else [{"value": 100 + i}], "id": f"{media}/insights/{m}/lifetime"} for i, m in enumerate(pedidas)]
        return 200, {"data": datos}, uso
    return _error(100)


def http_falso(metodo, url, datos=None, cabeceras=None):
    cabeceras = cabeceras or {}
    host = urllib.parse.urlparse(url).netloc
    if host == "buzon-falso.pages.dev":
        return _buzon(url, cabeceras)
    if host == "api.instagram.com":
        return _canje(datos)
    if host == "graph.instagram.com":
        return _graph(url, cabeceras)
    raise AssertionError("petición a un sitio que no toca: " + host)


ig._http = http_falso


def conectar(barrios, guion):
    """Una pasada de «Conectar redes» con lo que hará el dueño en cada enlace."""
    escribir_peticion = os.path.join(TMP, "conectar_redes.json")
    with open(escribir_peticion, "w", encoding="utf-8") as f:
        json.dump({"red": "instagram", "barrios": barrios}, f)
    conectar_redes.PETICION = escribir_peticion
    MUNDO["guion"] = list(guion)
    with contextlib.redirect_stdout(SALIDA):
        return conectar_redes.main()


def leer_cifras(argv=None):
    for n in range(1, 11):
        os.environ.pop(f"IG_TOKEN_{n}", None)
    for nombre, valor in SECRETOS.items():                          # lo que GitHub pasaría al turno
        os.environ[nombre] = valor
    with contextlib.redirect_stdout(SALIDA):
        return ig.main(argv or [])


PERMISOS = ["instagram_business_basic", "instagram_business_manage_insights"]
TODAS = set(ig.METRICAS_REEL) | set(ig.METRICAS_EXTRA)


def hace(**cuanto):
    """La hora de hace tanto tiempo (con días negativos, en el futuro), como la escriben los robots."""
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(**cuanto)).strftime("%Y-%m-%dT%H:%M:%SZ")

# 1) Conexión: una buena, una con otra cuenta y una que no es de Instagram
r = conectar(["barrio-3", "barrio-1", "barrio-2"],
             [("permitir", "uno", PERMISOS, False), ("permitir", "otra", PERMISOS, False)])
con = leer("estado/redes/conexiones.json", {})
comprobar(r == 1, "conexión: termina con aviso porque no todas han salido")
comprobar(set(SECRETOS) == {"IG_TOKEN_1"}, "conexión buena: el permiso va al primer hueco libre (IG_TOKEN_1)")
comprobar(MUNDO["tokens"].get(SECRETOS["IG_TOKEN_1"]) == "uno" and "largo" in SECRETOS["IG_TOKEN_1"],
          "conexión buena: se guarda el permiso de 60 días de ESA cuenta")
uno = con["cuenta_uno_falsa"]["instagram"]
comprobar(uno["estado"] == "conectado" and uno["hueco"] == 1 and uno["huella"] == ig.huella(IDS["uno"])
          and set(uno["permisos"]) == set(PERMISOS) and uno.get("caduca"), "conexión buena: estado sin tokens")
comprobar(con["cuenta_dos_falsa"]["instagram"]["estado"] == "otra_cuenta"
          and con["cuenta_dos_falsa"]["instagram"]["hueco"] == 4 and "IG_TOKEN_4" not in SECRETOS,
          "otra cuenta: no se guarda nada (y respeta su hueco fijo, el 4)")
enlace = urllib.parse.urlparse(MUNDO["enlaces"][0])
q = urllib.parse.parse_qs(enlace.query)
comprobar(enlace.netloc == "www.instagram.com" and enlace.path == "/oauth/authorize"
          and q["client_id"] == [os.environ["IG_APP_ID"]] and q["redirect_uri"] == [VUELTA]
          and q["response_type"] == ["code"]
          and q["scope"] == ["instagram_business_basic,instagram_business_manage_insights"]
          and 20 <= len(q["state"][0]) <= 64, "el enlace pide solo leer (sin publicar, comentarios ni mensajes)")
final = leer("estado/conexion_redes.json", {})
comprobar(final.get("terminado") and "enlace" not in final and final["resumen"] == {
    "barrio-3": "conectado", "barrio-1": "otra_cuenta", "barrio-2": "error"},
    "estado/conexion_redes.json: resumen por alias y sin enlace al terminar")
comprobar(len(GUARDADOS) >= 4, "cada paso de la conexión se guarda en el privado para la app")

# 2) Faltan permisos, el dueño cancela, el enlace caduca y, a la cuarta, bien (respuesta plana, sin data[])
r = conectar(["barrio-1"], [("permitir", "dos", PERMISOS[:1], True)])
comprobar(leer("estado/redes/conexiones.json")["cuenta_dos_falsa"]["instagram"]["estado"] == "faltan_permisos"
          and "IG_TOKEN_4" not in SECRETOS, "faltan permisos: no se guarda")
r = conectar(["barrio-1"], [("cancelar",)])
comprobar(leer("estado/conexion_redes.json")["estado"] == "error" and "IG_TOKEN_4" not in SECRETOS,
          "el dueño pulsa «Cancelar»: error y nada guardado")
antes = conectar_redes.time.ahora
r = conectar(["barrio-1", "barrio-3"], [("nada",)])
fin = leer("estado/conexion_redes.json")
comprobar(fin["estado"] == "caducado" and fin["resumen"] == {"barrio-1": "caducado"}
          and 44 * 60 <= conectar_redes.time.ahora - antes <= 46 * 60,
          "sin respuesta: el enlace caduca a los 45 minutos y no se espera por las demás")
r = conectar(["barrio-1"], [("permitir", "dos", PERMISOS, True)])
comprobar(r == 0 and MUNDO["tokens"].get(SECRETOS.get("IG_TOKEN_4")) == "dos"
          and leer("estado/redes/conexiones.json")["cuenta_dos_falsa"]["instagram"]["estado"] == "conectado",
          "a la cuarta, conectada en su hueco fijo (IG_TOKEN_4)")

# 3) Lectura: reels, error 100 en una métrica y dato vacío
r = leer_cifras()
d = leer("estado/redes/instagram/barrio-3.json", {})
reels = {x["id"]: x for x in d.get("reels", [])}
p = IDS["uno"][-3:]
comprobar(r == 0 and d.get("hueco") == 1 and set(reels) == {f"{p}01", f"{p}02", f"{p}04"},
          "lectura: solo los reels de los últimos 90 días (fuera la foto y el de hace 120 días)")
comprobar(set(reels[f"{p}02"]["metricas"]) == TODAS - {"reels_skip_rate"}
          and reels[f"{p}02"].get("faltan") == ["reels_skip_rate"],
          "error 100: se piden las demás métricas sin la que no vale (y reposts y facebook_views, aparte)")
comprobar(set(reels[f"{p}01"]["metricas"]) == TODAS - {"ig_reels_video_view_total_time", "facebook_views"}
          and reels[f"{p}01"].get("faltan") == ["facebook_views"],
          "dato vacío: no se apunta (no es un 0); y la de la llamada aparte que no vale no rompe la principal")
comprobar(all(len(x["texto"]) <= 150 for x in reels.values()) and reels[f"{p}01"]["codigo"] == f"CodReel{p}1",
          "el texto va recortado a 150 caracteres y del enlace solo queda el código del reel")
texto_fichero = json.dumps(d, ensure_ascii=False)
comprobar("permalink" not in texto_fichero and "instagram.com" not in texto_fichero and IDS["uno"] not in texto_fichero
          and not any(u in texto_fichero for u in USUARIOS.values()),
          "en el fichero de cifras no hay enlaces, usuarios (ni dentro del texto) ni el número de la cuenta")
comprobar(d["cuenta"]["seguidores"] == 150 and d["dias"], "cifras de la cuenta (seguidores y publicaciones) por día")
cifras = leer("estado/app/cifras.json", {})
b = cifras["barrios"]["cuenta_uno_falsa"]
comprobar(b["cifrasPorRed"]["instagram"]["auto"] == "api" and b["cifrasPorRed"]["instagram"]["seguidores"] == 150
          and len(b["reelsInstagram"]) == 3 and "visitas" in b["reelsInstagram"][0],
          "cifras.json: Instagram con auto «api» y sus reels para los gráficos")
hoy = sorted(cifras["historial"])[-1]
comprobar(cifras["historial"][hoy]["barrios"]["cuenta_uno_falsa"]["porRed"]["instagram"] == 150,
          "cifras.json: los seguidores de Instagram entran en el historial por día")
llamadas = len(MUNDO["llamadas"])
cambiado = leer("estado/redes/conexiones.json")["cuenta_uno_falsa"]["instagram"]["cambiado"]
leer_cifras()
comprobar(len(MUNDO["llamadas"]) - llamadas <= 6, "una pasada justo después no relee los reels (solo cuenta y lista)")
comprobar(leer("estado/redes/conexiones.json")["cuenta_uno_falsa"]["instagram"]["cambiado"] == cambiado,
          "leer no cuenta como cambio de la conexión («cambiado» sigue igual)")

# 4) Renovación semanal, con una Meta que no acepta el token en la cabecera
c = leer("estado/redes/conexiones.json")
hace8 = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
c["cuenta_uno_falsa"]["instagram"].update(renovado=hace8, desde=hace8)
escribir("estado/redes/conexiones.json", c)
viejo = SECRETOS["IG_TOKEN_1"]
MUNDO["cabecera_ok"] = False
leer_cifras()
nuevo = SECRETOS["IG_TOKEN_1"]
c = leer("estado/redes/conexiones.json")["cuenta_uno_falsa"]["instagram"]
comprobar(nuevo != viejo and "renovado" in nuevo and c["renovado"] > hace8 and c["estado"] == "conectado",
          "renovación: permiso nuevo en el mismo secreto (IG_TOKEN_1)")
ultimas = [x for x in MUNDO["llamadas"][llamadas:] if x[2] == nuevo]
comprobar(ultimas and all(v == "direccion" for _, v, _ in ultimas),
          "sin cabecera: el token va en la dirección y se lee con el renovado")
MUNDO["cabecera_ok"] = True


def mas_reels(quien, numeros, dias, no_valen, sitio):
    uid = IDS[quien]
    for n in numeros:
        reel = _reel(uid, n, dias)
        MEDIA[uid].insert(sitio, reel)
        NO_VALE[reel["id"]] = set(no_valen)
        PROHIBIDO.update({reel["permalink"], reel["caption"][:60]})


# 4b) Reels sin estadísticas (de antes de pasar la cuenta a profesional): en esta pasada solo se releen esos y no
#     vetan nada (antes se vetaban las 10 métricas para todas las cuentas). La que falla en 3 reels de UNA cuenta,
#     que sí dan las demás, se deja de pedir solo a esa cuenta.
mas_reels("uno", (6, 7, 8), 40, TODAS, 4)
mas_reels("dos", (3, 4, 5), 15, {"reels_skip_rate"}, 2)
r = leer_cifras()
reels = {x["id"]: x for x in leer("estado/redes/instagram/barrio-3.json", {}).get("reels", [])}
sin = [reels.get(f"{p}0{n}") or {} for n in (6, 7, 8)]
comprobar(r == 0 and all(x.get("sin_estadisticas") and not x.get("metricas") and x.get("leido") for x in sin),
          "reels sin estadísticas: quedan apuntados así, sin cifras")
AHORA = dt.datetime.now(dt.timezone.utc)
H_UNO, H_DOS = ig.huella(IDS["uno"]), ig.huella(IDS["dos"])
comprobar(ig.metricas_vetadas(H_UNO, "reel", AHORA) == set(), "los reels sin estadísticas no vetan ninguna métrica")
comprobar(ig.metricas_vetadas(H_DOS, "reel", AHORA) == {"reels_skip_rate"},
          "la métrica que falla en 3 reels de una cuenta se deja de pedir solo a ESA cuenta")
dos_reels = {x["id"]: x for x in leer("estado/redes/instagram/barrio-1.json", {}).get("reels", [])}
comprobar(all(set(dos_reels[f"{IDS['dos'][-3:]}0{n}"]["metricas"]) == TODAS - {"reels_skip_rate"} for n in (3, 4, 5)),
          "y sus reels traen todas las demás")

# 4c) Todas vetadas: se vuelven a pedir las 10 (nunca una lista vacía). Un reel que ya salió sin estadísticas se
#     vuelve a probar con una sola llamada.
m = leer("estado/redes/metricas.json")
m["instagram"]["cuentas"].setdefault(H_UNO, {})["reel"] = {x: hace(days=-20) for x in ig.METRICAS_REEL}
escribir("estado/redes/metricas.json", m)
d = leer("estado/redes/instagram/barrio-3.json")
for x in d["reels"]:
    if x["id"] in (f"{p}01", f"{p}06"):
        x["leido"] = hace(days=8)
escribir("estado/redes/instagram/barrio-3.json", d)
MUNDO["pedidas"] = []
r = leer_cifras()
del_01 = [q for media, q in MUNDO["pedidas"] if media == f"{p}01"]
comprobar(r == 0 and del_01 and set(del_01[0].split(",")) == set(ig.METRICAS_REEL),
          "con todas las métricas vetadas se vuelven a pedir las 10 (nunca una lista vacía)")
comprobar(len([1 for media, _ in MUNDO["pedidas"] if media == f"{p}06"]) == 1,
          "un reel que ya salió sin estadísticas se vuelve a probar con una sola llamada")

# 4d) Avisos de Meta falsos o de otra persona (el permiso sigue funcionando): no se borra nada
MUNDO["marcas"] = [{"tipo": "borrado", "usuario": IDS["dos"], "hora": "x", "sin_comprobar": True, "codigo": "C0D1G0"},
                   {"tipo": "baja", "usuario": "17849999999999999", "hora": "x", "sin_comprobar": True}]
PROHIBIDO.add("17849999999999999")
r = leer_cifras()
c = leer("estado/redes/conexiones.json")
comprobar(r == 0 and c["cuenta_dos_falsa"]["instagram"]["estado"] == "conectado"
          and c["cuenta_uno_falsa"]["instagram"]["estado"] == "conectado"
          and os.path.exists(os.path.join(PRIV, "estado/redes/instagram/barrio-1.json"))
          and leer("estado/redes/avisos_meta.json")["avisos"] == [],
          "avisos de Meta que la API no confirma (el permiso sigue valiendo): no se borra nada")

# 4e) La cuenta que «Conectar redes» está conectando ahora no se renueva ni se lee (ya no comparten cola)
guardado = leer("estado/conexion_redes.json")
escribir("estado/conexion_redes.json", {"estado": "esperando", "barrio": "barrio-3", "red": "instagram",
                                        "caduca": hace(minutes=-30)})
c = leer("estado/redes/conexiones.json")
c["cuenta_uno_falsa"]["instagram"]["renovado"] = hace8
escribir("estado/redes/conexiones.json", c)
antes, token_uno = len(MUNDO["llamadas"]), SECRETOS["IG_TOKEN_1"]
leer_cifras()
comprobar(SECRETOS["IG_TOKEN_1"] == token_uno and not [x for x in MUNDO["llamadas"][antes:] if x[2] == token_uno]
          and [x for x in MUNDO["llamadas"][antes:] if x[2] == SECRETOS["IG_TOKEN_4"]],
          "la cuenta que se está conectando ahora mismo no se renueva ni se lee; las demás, sí")
escribir("estado/conexion_redes.json", guardado)

# 5) Token caducado
MUNDO["caducados"].add(SECRETOS["IG_TOKEN_4"])
leer_cifras()
c = leer("estado/redes/conexiones.json")
comprobar(c["cuenta_dos_falsa"]["instagram"]["estado"] == "caducado"
          and c["cuenta_uno_falsa"]["instagram"]["estado"] == "conectado",
          "token caducado: esa cuenta queda «caducado» (la app pide reconectar) y las demás siguen")
c["cuenta_uno_falsa"]["instagram"].update(renovado=hace8)
escribir("estado/redes/conexiones.json", c)
MUNDO["caducados"].add(SECRETOS["IG_TOKEN_1"])
leer_cifras()
comprobar(leer("estado/redes/conexiones.json")["cuenta_uno_falsa"]["instagram"]["estado"] == "caducado",
          "renovación que Meta rechaza (190): «caducado»")

# 5b) Hueco repetido: si el hueco fijo de una cuenta ya es de otra, se para antes de enseñar el enlace y de guardar nada.
#     Y un intento que no sale no pierde la fecha de «sin permiso» ni la huella (hacen falta para borrar a los 30 días).
cfg = leer("config/canales.json")
cfg["barrios"]["cuenta_dos_falsa"]["estadisticas"]["instagram"] = 1
escribir("config/canales.json", cfg)
antes_dos, copia, enlaces = leer("estado/redes/conexiones.json")["cuenta_dos_falsa"]["instagram"], dict(SECRETOS), \
    len(MUNDO["enlaces"])
r = conectar(["barrio-1"], [])
dos = leer("estado/redes/conexiones.json")["cuenta_dos_falsa"]["instagram"]
comprobar(r == 1 and SECRETOS == copia and len(MUNDO["enlaces"]) == enlaces
          and "hueco repetido" in leer("estado/conexion_redes.json").get("motivo", ""),
          "hueco repetido: se para sin enlace y sin pisar el permiso de la otra cuenta (IG_TOKEN_1)")
comprobar(dos.get("estado") == "error" and dos.get("hueco") == 4 and dos.get("huella") == antes_dos["huella"]
          and dos.get("caducado_desde") == antes_dos["caducado_desde"], "y la cuenta guarda su hueco, su huella y su fecha")
cfg["barrios"]["cuenta_dos_falsa"]["estadisticas"]["instagram"] = 4
escribir("config/canales.json", cfg)
conectar(["barrio-1"], [("nada",)])
dos = leer("estado/redes/conexiones.json")["cuenta_dos_falsa"]["instagram"]
comprobar(dos.get("estado") == "caducado" and dos.get("caducado_desde") == antes_dos["caducado_desde"]
          and dos.get("huella") == antes_dos["huella"],
          "un intento de reconectar que caduca no borra la fecha de «sin permiso» ni la huella")

# 6) El Contador ya no mira la página pública de una cuenta con cifras oficiales recientes (de hace 6 h: más que su
#    espera normal de 5 h, pero dentro de los 3 días que mandan las oficiales)
cont = leer("estado/redes/contador.json")
hace6 = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
for clave in ("cuenta_uno_falsa", "cuenta_dos_falsa"):
    cont["cuentas"][clave]["instagram"]["fecha"] = hace6
escribir("estado/redes/contador.json", cont)
mirados = []
contador.instagram = lambda cuenta: mirados.append(cuenta) or {"seguidores": 1}
contador.tiktok = lambda cuenta: None
contador.videos_tiktok = lambda cuenta: []
with contextlib.redirect_stdout(SALIDA):
    contador.contar(paso=lambda t: print(privado.limpiar(t)))
    contador.para_app()
comprobar(USUARIOS["uno"] not in mirados and USUARIOS["dos"] not in mirados,
          "el Contador no mira la web de las cuentas con cifras oficiales")
comprobar(leer("estado/app/cifras.json")["barrios"]["cuenta_uno_falsa"]["cifrasPorRed"]["instagram"]["auto"] == "api",
          "y sus cifras siguen siendo las oficiales")

# 6b) Aviso de borrado de Meta que la API confirma (la cuenta ya no tiene permiso): se borra todo YA, también sus
#     seguidores de cada día en el historial de la app
MUNDO["marcas"] = [{"tipo": "borrado", "usuario": IDS["dos"], "hora": "x", "sin_comprobar": True}]
r = leer_cifras()
dos = leer("estado/redes/conexiones.json")["cuenta_dos_falsa"]["instagram"]
cont, cifras = leer("estado/redes/contador.json"), leer("estado/app/cifras.json")
comprobar(r == 0 and dos.get("borrado") and not os.path.exists(os.path.join(PRIV, "estado/redes/instagram/barrio-1.json"))
          and os.path.exists(os.path.join(PRIV, "estado/redes/instagram/barrio-3.json"))
          and "instagram" not in (cont["cuentas"].get("cuenta_dos_falsa") or {})
          and "cuenta_dos_falsa" not in cont.get("videos_instagram", {})
          and not any("instagram" in (x.get("cuenta_dos_falsa") or {}) for x in cont["dias"].values()),
          "aviso de borrado confirmado: fuera su fichero, su resumen, sus reels y sus seguidores de cada día")
comprobar(not any("instagram" in ((x["barrios"].get("cuenta_dos_falsa") or {}).get("porRed") or {})
                  for x in cifras["historial"].values())
          and "reelsInstagram" not in (cifras["barrios"].get("cuenta_dos_falsa") or {}),
          "y cifras.json ya no los enseña")

# 6c) «Otra cuenta» también se olvida a los 30 días sin permiso
c = leer("estado/redes/conexiones.json")
c["cuenta_uno_falsa"]["instagram"].update(estado="otra_cuenta", caducado_desde=hace(days=31))
escribir("estado/redes/conexiones.json", c)
leer_cifras()
comprobar(leer("estado/redes/conexiones.json")["cuenta_uno_falsa"]["instagram"].get("borrado")
          and not os.path.exists(os.path.join(PRIV, "estado/redes/instagram/barrio-3.json")),
          "«otra_cuenta» también se olvida a los 30 días sin permiso")

# 6d) Una conexión de una cuenta que ya no está en la lista: ni se lee ni se renueva, y en el registro nunca sale su
#     nombre (privado.alias ya no lo conoce); a los 30 días, sus copias se borran
VIEJA, H_VIEJA = "cuenta_vieja_falsa", ig.huella("17840000000000777")
PROHIBIDO.add(VIEJA)
c = leer("estado/redes/conexiones.json")
c[VIEJA] = {"instagram": {"estado": "conectado", "hueco": 7, "huella": H_VIEJA, "desde": hace8, "renovado": hace8,
                          "caduca": hace(days=-50)}}
escribir("estado/redes/conexiones.json", c)
token_viejo = _token_nuevo("largo", "uno")
SECRETOS["IG_TOKEN_7"] = token_viejo
escribir("estado/redes/instagram/barrio-9.json", {"huella": H_VIEJA, "hueco": 7, "alias": "barrio-9", "reels": []})
cont = leer("estado/redes/contador.json")
cont["cuentas"][VIEJA] = {"instagram": {"seguidores": 5, "auto": "api", "fecha": hace6}}
cont.setdefault("videos_instagram", {})[VIEJA] = [{"titulo": "x"}]
cont["dias"].setdefault(hace(days=0)[:10], {})[VIEJA] = {"instagram": {"seguidores": 5, "fuente": "api"}}
escribir("estado/redes/contador.json", cont)
antes = len(MUNDO["llamadas"])
leer_cifras()
vieja = leer("estado/redes/conexiones.json")[VIEJA]["instagram"]
comprobar(vieja["estado"] == "caducado" and vieja["motivo"] == "fuera de la lista" and vieja.get("caducado_desde")
          and SECRETOS["IG_TOKEN_7"] == token_viejo and not [x for x in MUNDO["llamadas"][antes:] if x[2] == token_viejo],
          "una cuenta que ya no está en la lista: ni se lee ni se renueva")
c = leer("estado/redes/conexiones.json")
c[VIEJA]["instagram"]["caducado_desde"] = hace(days=31)
escribir("estado/redes/conexiones.json", c)
leer_cifras()
cont = leer("estado/redes/contador.json")
comprobar(leer("estado/redes/conexiones.json")[VIEJA]["instagram"].get("borrado")
          and not os.path.exists(os.path.join(PRIV, "estado/redes/instagram/barrio-9.json"))
          and VIEJA not in cont.get("videos_instagram", {}) and "instagram" not in cont["cuentas"][VIEJA]
          and not any("instagram" in (x.get(VIEJA) or {}) for x in cont["dias"].values())
          and "instagram una cuenta retirada: sin permiso desde hace 30 días: copias borradas" in SALIDA.getvalue(),
          "a los 30 días se borran sus copias, y en el registro sale como «una cuenta retirada»")

# 6e) Dos versiones de conexiones.json (conectar y leer a la vez): de cada cuenta gana la cambiada más tarde
suya = {"a": {"instagram": {"estado": "conectado", "cambiado": "2026-01-02T00:00:00Z"}}, "solo_suya": {"instagram": {}}}
nuestra = {"a": {"instagram": {"estado": "caducado", "cambiado": "2026-01-01T00:00:00Z", "leido": "x"}},
           "solo_nuestra": {"instagram": {}}}
junta = privado.fusionar("estado/redes/conexiones.json", suya, nuestra)
comprobar(junta["a"]["instagram"]["estado"] == "conectado" and {"solo_suya", "solo_nuestra"} <= set(junta),
          "conexiones.json: de cada cuenta gana la versión cambiada más tarde y no se pierde ninguna cuenta")

# 7) Sin cuentas conectadas: sale 0 sin hacer nada
vacio = os.path.join(TMP, "vacio")
shutil.copytree(os.path.join(PRIV, "config"), os.path.join(vacio, "config"))
os.environ["PRIVADO"] = vacio
antes = len(MUNDO["llamadas"])
r = leer_cifras()
comprobar(r == 0 and len(MUNDO["llamadas"]) == antes and not os.path.exists(os.path.join(vacio, "estado", "app")),
          "sin cuentas conectadas: sale 0 sin llamar a Meta")
os.environ["PRIVADO"] = PRIV

# 8) Nada privado en el registro público ni tokens en el privado
registro = SALIDA.getvalue().splitlines()
tapados = {x[len("::add-mask::"):] for x in registro if x.startswith("::add-mask::")}
visibles = [x for x in registro if not x.startswith("::add-mask::")]
fugas = sorted({p for p in PROHIBIDO if p and any(p in linea for linea in visibles)})
comprobar(not fugas, "el registro público no lleva tokens, códigos, marcas, enlaces, usuarios ni textos"
          + (f" (se cuela: {len(fugas)})" if fugas else ""))
sin_tapar = sorted(v for v in TAPADO_OBLIGATORIO if v not in tapados)
comprobar(not sin_tapar, f"cada token, código, marca, usuario y número se tapa con ::add-mask:: ({len(tapados)})")
tokens = [t for t in PROHIBIDO if t.startswith("IG") or t.startswith("AQCodigo") or "FALSA" in t or "FALSO-" in t]
for raiz, _, ficheros in os.walk(PRIV):
    for f in ficheros:
        contenido = open(os.path.join(raiz, f), encoding="utf-8", errors="replace").read()
        malos = [t for t in tokens if t in contenido]
        comprobar(not malos, f"sin tokens ni llaves en el privado: {os.path.relpath(os.path.join(raiz, f), PRIV)}")
for f in os.listdir(os.path.join(PRIV, "estado", "redes", "instagram")) + ["../conexiones.json", "../contador.json",
                                                                          "../avisos_meta.json", "../metricas.json"]:
    contenido = open(os.path.join(PRIV, "estado", "redes", "instagram", f), encoding="utf-8").read()
    comprobar(not any(u in contenido for u in USUARIOS.values()) and not any(i in contenido for i in IDS.values()),
              f"sin usuarios ni números de cuenta: estado/redes/{os.path.normpath(os.path.join('instagram', f))}")
print("\nAsí se vería el registro público (sin las líneas ::add-mask::, que GitHub no enseña):")
print("\n".join("    " + x for x in visibles))
shutil.rmtree(TMP, ignore_errors=True)
print("\nSimulacro de Instagram: todo bien")
