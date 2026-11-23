"""El Dibujante: dibuja cada escena con AI Horde (gratis). Pide todas a la vez, espera y descarga.
Si alguna falla, la repite una vez; si aun así faltan 2 como mucho, el Montador aprovecha la escena de al lado."""
import json
import os
import time
import urllib.error
import urllib.request

API = "https://aihorde.net/api/v2"
# Cloudflare (delante de AI Horde) bloquea el nombre que pone Python por defecto: nos presentamos con el nuestro.
AGENTE = "ciudades-bot/1.0 (cliente de AI Horde)"
CABECERAS = {"apikey": os.environ.get("AIHORDE_KEY") or "0000000000", "Client-Agent": "ciudades:1:anon",
             "Content-Type": "application/json", "User-Agent": AGENTE}
NEGATIVO = "text, letters, words, watermark, signature, logo, blurry, deformed, extra fingers, gore"


def _peticion(metodo, ruta, datos=None):
    req = urllib.request.Request(API + ruta, method=metodo, headers=CABECERAS,
                                 data=json.dumps(datos).encode() if datos is not None else None)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def pedir(prompt, modelo, ancho=576, alto=1024):
    cuerpo = {"prompt": f"{prompt} ### {NEGATIVO}", "models": [modelo], "nsfw": False, "censor_nsfw": True,
              "r2": True, "shared": False,
              "params": {"width": ancho, "height": alto, "steps": 25, "cfg_scale": 6.5, "sampler_name": "k_euler_a",
                         "karras": True, "n": 1}}
    return _peticion("POST", "/generate/async", cuerpo)["id"]


def dibujar(escenas, modelo, carpeta, espera_maxima=1800):
    os.makedirs(carpeta, exist_ok=True)
    pendientes, por_pedir = {}, list(range(len(escenas)))
    hechas, fin = {}, time.time() + espera_maxima
    while (pendientes or por_pedir) and time.time() < fin:
        for i in list(por_pedir):           # AI Horde limita cuántos pedidos a la vez: lo que no entra, se pide luego
            try:
                pendientes[i] = {"id": pedir(escenas[i]["dibujo"], modelo), "repetida": False}
                por_pedir.remove(i)
            except (urllib.error.URLError, KeyError) as err:
                print(f"  escena {i + 1}: todavía no se puede pedir ({err})")
                break
        time.sleep(20)
        for i, p in list(pendientes.items()):
            try:
                estado = _peticion("GET", f"/generate/check/{p['id']}")
            except urllib.error.URLError:
                continue
            if estado.get("faulted") or (estado.get("done") is False and not estado.get("is_possible", True)):
                if not p["repetida"]:
                    p.update(id=pedir(escenas[i]["dibujo"], modelo), repetida=True)
                else:
                    pendientes.pop(i)
                continue
            if estado.get("done"):
                try:
                    gen = _peticion("GET", f"/generate/status/{p['id']}")["generations"][0]
                    ruta = os.path.join(carpeta, f"escena{i + 1:02d}.webp")
                    req = urllib.request.Request(gen["img"], headers={"User-Agent": AGENTE})
                    with urllib.request.urlopen(req, timeout=120) as r, open(ruta, "wb") as f:
                        f.write(r.read())
                    hechas[i] = ruta
                except (urllib.error.URLError, KeyError, IndexError) as err:
                    print(f"  escena {i + 1}: no se pudo descargar ({err})")
                pendientes.pop(i)
        print(f"  dibujos: {len(hechas)}/{len(escenas)} hechos, {len(pendientes)} esperando, {len(por_pedir)} por pedir")
    return [hechas.get(i) for i in range(len(escenas))]
