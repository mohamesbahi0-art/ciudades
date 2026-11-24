"""El Dibujante: dibuja cada escena con AI Horde (gratis). Pide todas a la vez, espera y descarga.
Si alguna falla, repite solo esa (hasta 2 veces); si aun así faltan pocas, el Montador aprovecha la escena de al lado.
Antes de pedir mira qué modelos tienen robots dibujando: si el del canal no tiene (o tiene mucha cola), usa el plan B.
Si pasan 7 minutos sin que llegue ninguno, lo que falta se pide a otro modelo; si tampoco, deja de esperar: el turno queda
«esperando» y los Mecánicos deciden."""
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


# Plan B: si el modelo del canal no tiene robots dibujando (pasa a ratos: el servicio es de voluntarios), se usa el
# modelo de uso general que antes vaya a dibujar. Solo modelos «para todo» (nada de anime ni de adultos).
PLAN_B = ("AlbedoBase XL (SDXL)", "Juggernaut XL", "Deliberate 3.0", "Dreamshaper", "AbsoluteReality",
          "ICBINP - I Can't Believe It's Not Photography", "Realistic Vision", "Deliberate")
ESPERA_ACEPTABLE = 420         # segundos de cola a partir de los cuales merece la pena mirar el plan B


def _parametros(modelo):
    """Los modelos grandes (XL) dibujan bien en vertical; los pequeños, más bajos y con «hires_fix», que evita figuras
    duplicadas. El Montador recorta y agranda lo que haga falta."""
    if "XL" in modelo:
        return {"width": 576, "height": 1024, "steps": 25, "cfg_scale": 6.5, "sampler_name": "k_euler_a", "karras": True,
                "n": 1}
    return {"width": 512, "height": 896, "steps": 25, "cfg_scale": 7.0, "sampler_name": "k_euler_a", "karras": True,
            "n": 1, "hires_fix": True}


def pedir(prompt, modelo, ancho=None, alto=None):
    params = _parametros(modelo)
    if ancho and alto:
        params.update(width=ancho, height=alto)
    cuerpo = {"prompt": f"{prompt} ### {NEGATIVO}", "models": [modelo], "nsfw": False, "censor_nsfw": True,
              "r2": True, "shared": False, "params": params}
    return _peticion("POST", "/generate/async", cuerpo)["id"]


def estado_modelos():
    """{modelo: {"robots", "espera", "trabajos"}} de los modelos que alguien está dibujando ahora (dato público)."""
    try:
        return {m["name"]: {"robots": m.get("count") or 0, "espera": m.get("eta") or 0, "trabajos": m.get("jobs") or 0}
                for m in _peticion("GET", "/status/models?type=image") if m.get("name")}
    except (urllib.error.URLError, ValueError, TypeError, KeyError, OSError):
        return {}


def elegir_modelo(modelo, vivos=None, salvo=()):
    """El modelo del canal si tiene robots y poca cola; si no, el del plan B que antes vaya a dibujar.
    Devuelve (modelo, por qué se cambia o «»). Si no se sabe cómo está el servicio, el de siempre."""
    vivos = estado_modelos() if vivos is None else vivos
    if not vivos:
        return modelo, ""
    suyo = vivos.get(modelo) or {"robots": 0, "espera": 0}
    if modelo not in salvo and suyo["robots"] >= 1 and suyo["espera"] <= ESPERA_ACEPTABLE:
        return modelo, ""
    candidatos = sorted((vivos[n]["espera"], -vivos[n]["robots"], n) for n in PLAN_B
                        if n != modelo and n not in salvo and n in vivos and vivos[n]["robots"] >= 2)
    if not candidatos or (modelo not in salvo and suyo["robots"] >= 1 and suyo["espera"] <= candidatos[0][0]):
        return modelo, ""
    return candidatos[0][2], (f"«{modelo}» tiene ahora {suyo['robots']} robots y {round(suyo['espera'])} s de cola: "
                              f"dibuja «{candidatos[0][2]}» (plan B)")


def dibujar(escenas, modelo, carpeta, espera_maxima=1800, sin_avance=420, repeticiones=2):
    """Devuelve la ruta de cada dibujo (None el que falte). Si el servicio lleva `sin_avance` segundos sin entregar
    ninguno, deja de esperar (antes se quedaba media hora parado para acabar fallando igual)."""
    os.makedirs(carpeta, exist_ok=True)
    pendientes, por_pedir = {}, list(range(len(escenas)))
    hechas, fin = {}, time.time() + espera_maxima
    avance = time.time()
    probados = [modelo]
    modelo, motivo = elegir_modelo(modelo)
    if motivo:
        print(f"  dibujos: {motivo}")
        probados.append(modelo)
    while (pendientes or por_pedir) and time.time() < fin:
        if time.time() - avance > sin_avance:
            otro, motivo = elegir_modelo(modelo, salvo=probados) if len(probados) < 3 else (modelo, "")
            if otro == modelo:
                print(f"  dibujos: {sin_avance // 60} min sin que llegue ninguno: el servicio no da para más ahora")
                break
            # el modelo se ha quedado sin robots a mitad: lo que falta se pide a otro (lo ya dibujado se queda)
            print(f"  dibujos: {sin_avance // 60} min sin que llegue ninguno; lo que falta lo dibuja «{otro}»")
            modelo, avance = otro, time.time()
            probados.append(otro)
            por_pedir = sorted(set(por_pedir) | set(pendientes))
            pendientes = {}
        for i in list(por_pedir):           # AI Horde limita cuántos pedidos a la vez: lo que no entra, se pide luego
            try:
                pendientes[i] = {"id": pedir(escenas[i]["dibujo"], modelo), "repetida": 0}
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
                if p["repetida"] < repeticiones:        # solo se repite el dibujo que ha fallado, no todos
                    try:
                        p.update(id=pedir(escenas[i]["dibujo"], modelo), repetida=p["repetida"] + 1)
                    except (urllib.error.URLError, KeyError):
                        pass                             # no deja pedir ahora: se vuelve a mirar en la próxima vuelta
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
                    avance = time.time()
                except (urllib.error.URLError, KeyError, IndexError) as err:
                    print(f"  escena {i + 1}: no se pudo descargar ({err})")
                pendientes.pop(i)
        print(f"  dibujos: {len(hechas)}/{len(escenas)} hechos, {len(pendientes)} esperando, {len(por_pedir)} por pedir")
    return [hechas.get(i) for i in range(len(escenas))]
