"""Conecta los canales de YouTube del dueño sin ordenador, con el flujo de Google para dispositivos.

Lo lanza GitHub Actions (flujo «Conectar canales») cuando aparece peticiones/conectar.json:
  {"canales": {"<clave>": "<huella del id del canal>", ...}}
Para cada canal que falta:
  1. pide a Google un código y lo deja en estado/conexion.json (el dueño lo escribe en google.com/device
     desde el móvil, elige el canal y pulsa Permitir);
  2. espera a que lo apruebe;
  3. comprueba qué canal ha elegido, por la huella de su id, sin escribir el id en ningún sitio público;
  4. guarda el permiso y el id del canal directamente en los secretos de GitHub (YT_REFRESH_<CLAVE> y YT_ID_<CLAVE>),
     cerrados con la llave pública del repositorio. Nunca pasan por el repositorio ni por los registros.
Necesita los secretos YT_CLIENT_ID y YT_CLIENT_SECRET (cliente de Google del tipo «TVs y dispositivos de entrada
limitada») y GH_SECRETOS (llave de GitHub con permiso solo para escribir secretos de este repositorio).
"""
import base64
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from nacl import encoding, public

PETICION = "peticiones/conectar.json"
ESTADO = "estado/conexion.json"
GOOGLE_CODIGO = "https://oauth2.googleapis.com/device/code"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
MIS_CANALES = "https://www.googleapis.com/youtube/v3/channels?part=id&mine=true"
# El flujo para dispositivos solo admite algunos permisos de YouTube: se prueba el general y, si no, el equivalente.
PERMISOS = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.force-ssl"]


def ahora():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def post(url, datos):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(datos).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"error": f"http_{e.code}"}
    except urllib.error.URLError as e:
        return {"error": "sin_conexion", "error_description": str(e.reason)}


def huella(texto):
    """Huella corta de un id: sirve para saber qué canal es sin escribir su id en el repositorio."""
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


def github(metodo, ruta, llave, datos=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/{ruta}", method=metodo,
                                 data=json.dumps(datos).encode() if datos is not None else None,
                                 headers={"Authorization": f"Bearer {llave}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        cuerpo = r.read()
        return json.loads(cuerpo) if cuerpo else {}


def guardar_secreto(nombre, valor, llave):
    """Cierra el valor con la llave pública del repositorio y lo guarda como secreto de GitHub Actions."""
    clave_publica = github("GET", "actions/secrets/public-key", llave)
    caja = public.SealedBox(public.PublicKey(clave_publica["key"].encode(), encoding.Base64Encoder()))
    cifrado = base64.b64encode(caja.encrypt(valor.encode())).decode()
    github("PUT", f"actions/secrets/{nombre}", llave, {"encrypted_value": cifrado, "key_id": clave_publica["key_id"]})


def mis_canales(token):
    req = urllib.request.Request(MIS_CANALES, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return [x["id"] for x in json.load(r).get("items", [])]


def guardar_en_repo(mensaje):
    rama = os.environ.get("GITHUB_REF_NAME")
    subprocess.run(["git", "add", "-A", "estado", "peticiones"], check=False)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", mensaje], check=True)
    if not rama:            # fuera de GitHub Actions (pruebas): no se sube nada
        return
    for intento in range(1, 6):
        if (subprocess.run(["git", "pull", "-q", "--rebase", "origin", rama]).returncode == 0
                and subprocess.run(["git", "push", "-q", "origin", f"HEAD:{rama}"]).returncode == 0):
            return
        time.sleep(5 * intento)
    print("No pude guardar el estado en el repositorio.", file=sys.stderr)


def publicar(estado, mensaje):
    os.makedirs("estado", exist_ok=True)
    estado["actualizado"] = ahora()
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    print(f"[{estado['actualizado']}] {mensaje}")
    guardar_en_repo(mensaje)


def pedir_codigo(cliente):
    for permiso in PERMISOS:
        r = post(GOOGLE_CODIGO, {"client_id": cliente, "scope": permiso})
        if "device_code" in r:
            return r, permiso
        if r.get("error") != "invalid_scope":
            return {"error": r.get("error", "desconocido"), "detalle": r.get("error_description", "")}, None
    return {"error": "invalid_scope", "detalle": "Google no deja pedir permisos de YouTube con este cliente"}, None


def esperar_permiso(cliente, secreto, codigo):
    intervalo = int(codigo.get("interval", 5))
    fin = time.time() + int(codigo.get("expires_in", 1800))
    while time.time() < fin:
        time.sleep(intervalo)
        r = post(GOOGLE_TOKEN, {"client_id": cliente, "client_secret": secreto, "device_code": codigo["device_code"],
                                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if "access_token" in r:
            return r
        error = r.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            intervalo += 5
            continue
        return {"error": error or "desconocido"}
    return {"error": "expired_token"}


def main():
    cliente, secreto, llave = (os.environ.get(v) for v in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "GH_SECRETOS"))
    faltan_secretos = [n for n, v in (("YT_CLIENT_ID", cliente), ("YT_CLIENT_SECRET", secreto), ("GH_SECRETOS", llave)) if not v]
    if faltan_secretos:
        publicar({"estado": "faltan_secretos", "faltan": faltan_secretos}, "conexión: faltan secretos " + ", ".join(faltan_secretos))
        return 1
    try:
        existentes = {x["name"] for x in github("GET", "actions/secrets?per_page=100", llave).get("secrets", [])}
    except urllib.error.HTTPError as e:
        publicar({"estado": "error", "detalle": f"la llave GH_SECRETOS no vale ({e.code})"}, "conexión: GH_SECRETOS no vale")
        return 1
    with open(PETICION, encoding="utf-8") as f:
        peticion = json.load(f)
    canales = peticion["canales"]                      # clave -> huella del id
    por_huella = {h: clave for clave, h in canales.items()}
    rehacer = set(canales) if peticion.get("rehacer") else set()
    hechos, saltados = set(), set()

    while True:
        faltan = [c for c in canales if c not in hechos and c not in saltados
                  and (c in rehacer or f"YT_REFRESH_{c.upper()}" not in existentes)]
        if not faltan:
            break
        clave = faltan[0]
        codigo, permiso = pedir_codigo(cliente)
        if "device_code" not in codigo:
            publicar({"estado": "error", "canal": clave, "detalle": f"{codigo.get('error')}: {codigo.get('detalle', '')}"},
                     f"conexión: Google no da código ({codigo.get('error')})")
            return 1
        caduca = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(codigo.get("expires_in", 1800))))
        publicar({"estado": "esperando", "canal": clave, "codigo": codigo["user_code"],
                  "url": codigo.get("verification_url", "https://www.google.com/device"),
                  "caduca": caduca.strftime("%Y-%m-%dT%H:%M:%SZ"), "quedan": len(faltan)},
                 f"conexión: código para {clave}")
        token = esperar_permiso(cliente, secreto, codigo)
        if "error" in token:
            if token["error"] == "access_denied":
                saltados.add(clave)
                publicar({"estado": "rechazado", "canal": clave}, f"conexión: {clave} rechazado por el dueño")
                continue
            publicar({"estado": "caducado" if token["error"] == "expired_token" else "error", "canal": clave,
                      "detalle": token["error"]}, f"conexión: {clave} sin conectar ({token['error']})")
            return 1
        if "refresh_token" not in token:
            publicar({"estado": "error", "canal": clave, "detalle": "Google no ha dado permiso duradero"},
                     f"conexión: {clave} sin permiso duradero")
            return 1
        try:
            ids = mis_canales(token["access_token"])
        except urllib.error.HTTPError as e:
            publicar({"estado": "error", "canal": clave, "detalle": f"youtube_{e.code}"}, f"conexión: YouTube dio {e.code}")
            return 1
        destino = next((por_huella[huella(i)] for i in ids if huella(i) in por_huella), None)
        if not destino:
            publicar({"estado": "otro_canal", "canal": clave, "sin_canal": not ids},
                     f"conexión: el permiso de {clave} es de una cuenta que no está en la lista")
            continue
        id_canal = next(i for i in ids if huella(i) == canales[destino])
        try:
            guardar_secreto(f"YT_REFRESH_{destino.upper()}", token["refresh_token"], llave)
            guardar_secreto(f"YT_ID_{destino.upper()}", id_canal, llave)
        except urllib.error.HTTPError as e:
            publicar({"estado": "error", "canal": destino, "detalle": f"no pude guardar el secreto ({e.code})"},
                     f"conexión: no pude guardar el permiso de {destino}")
            return 1
        existentes.update({f"YT_REFRESH_{destino.upper()}", f"YT_ID_{destino.upper()}"})
        hechos.add(destino)
        rehacer.discard(destino)
        publicar({"estado": "conectado", "canal": destino, "pedido": clave, "coincide": destino == clave,
                  "quedan": len(faltan) - 1}, f"conexión: {destino} conectado")

    if os.path.exists(PETICION):
        os.remove(PETICION)
    conectados = sorted(n[len("YT_REFRESH_"):].lower() for n in existentes if n.startswith("YT_REFRESH_"))
    publicar({"estado": "terminado", "conectados": conectados, "rechazados": sorted(saltados)}, "conexión: terminado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
