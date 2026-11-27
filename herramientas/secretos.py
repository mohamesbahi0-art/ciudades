"""Secretos de GitHub Actions de este repositorio, sin que pasen nunca por el repositorio ni por los registros.

Cada valor se cierra con la llave pública del repositorio antes de enviarlo: solo GitHub puede abrirlo. Lo usan
conectar_canal.py (permisos de YouTube), el Buzón de vuelta (vuelta/desplegar.py, VUELTA_LLAVE) y el turno que conecta
las cuentas de Instagram (IG_TOKEN_<n>). Necesita la llave GH_SECRETOS (permiso solo para escribir secretos de este
repositorio). Nada de aquí imprime valores: el registro de Actions es público.
"""
import base64
import json
import os
import urllib.error
import urllib.request

from nacl import encoding, public


def github(metodo, ruta, llave, datos=None):
    """Llama a la API de GitHub para este repositorio (GITHUB_REPOSITORY) y devuelve la respuesta ya leída."""
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


def nombres(llave):
    """Los nombres de los secretos que ya hay (nunca sus valores), página a página."""
    vistos, pagina = set(), 1
    while pagina <= 10:
        lote = github("GET", f"actions/secrets?per_page=100&page={pagina}", llave).get("secrets", [])
        vistos.update(x["name"] for x in lote)
        if len(lote) < 100:
            break
        pagina += 1
    return vistos


def puede_guardar(llave):
    """True si la llave deja escribir secretos ahora mismo. Sirve para no renovar un permiso que luego no se podría
    guardar (el viejo dejaría de valer y habría que volver a conectar la cuenta)."""
    if not llave:
        return False
    try:
        return "key_id" in github("GET", "actions/secrets/public-key", llave)
    except (urllib.error.URLError, ValueError, KeyError):
        return False
