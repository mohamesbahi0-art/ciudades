"""La IA gratis de las ciudades (Gemini), con turnos y plan B.

preguntar(texto, imagenes=[...], json_salida=True) prueba primero el modelo bueno y, si no queda cupo, el ligero.
El ligero confunde imágenes (lección de la fábrica antigua): para mirar fotogramas pasa solo_bueno=True.
Necesita el secreto GEMINI_API_KEY.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

# Cada modelo tiene su propio cupo gratis: si uno se agota (429), está saturado (503) o ya no existe (404), se prueba el
# siguiente. Los «buenos» también saben mirar imágenes; los ligeros, solo para texto (confunden imágenes).
BUENOS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-flash-latest", "gemini-3.7-flash",
          "gemini-3.8-flash"]
LIGEROS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
BUENO, LIGERO = BUENOS[0], LIGEROS[0]
AGOTADOS = set()          # los que hoy ya han dicho que no les queda cupo (en esta ronda no se vuelven a probar)
USO = {}                  # el Portero de Gemini lleva la cuenta: {modelo: {"bien": n, "sin_cupo": n, "fallos": n}}


def _contar(modelo, que):
    uso = USO.setdefault(modelo, {"bien": 0, "sin_cupo": 0, "fallos": 0})
    uso[que] = uso.get(que, 0) + 1          # «saturado» (503) se cuenta aparte dentro de los fallos


def apuntar_portero():
    """El Portero de Gemini apunta en su cuaderno cuánto se ha pedido a cada modelo y cuáles se han quedado sin cupo."""
    if not USO:
        return
    from bots.comun import privado
    portero = privado.cuaderno("portero_gemini")
    portero.apuntar("reparto", {"uso": USO, "sin_cupo": sorted(AGOTADOS)})
    portero.guardar()
    anterior = privado.leer("estado/gemini.json", {}) or {}
    privado.guardar_estado("gemini.json", {"ultimo_reparto": USO, "sin_cupo": sorted(AGOTADOS),
                                           "anteriores": (anterior.get("anteriores", []) + [anterior.get("ultimo_reparto")])[-20:]
                                           if anterior.get("ultimo_reparto") else [],
                                           "ve_videos": VE_VIDEOS or anterior.get("ve_videos")})
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
VIDEO_MAXIMO = 14_000_000      # bytes: en base64 crece un tercio y la petición entera no puede pasar de unos 20 MB


class SinIA(RuntimeError):
    """Gemini no ha contestado: sin cupo, caído o sin clave."""


def _limpiar_json(texto):
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(texto)


PACIENCIA = 2                  # vueltas de más por todos los modelos cuando están saturados (503) pero vivos
ESPERAS = (20, 45, 60)         # segundos entre vuelta y vuelta


def preguntar(texto, imagenes=(), json_salida=True, solo_bueno=False, temperatura=0.9, intentos=3, ligero_primero=False,
              audio=None, video=None, paciencia=None):
    """Pregunta a Gemini. Si todos los modelos fallan pero alguno está «vivo» (saturado, lento o con el límite por
    minuto, no sin cupo del día), espera un poco y da otra vuelta (hasta `paciencia` más): a mediodía los modelos
    ligeros contestan 1 de cada 5 veces y rendirse a la primera tiraba vídeos a medio hacer."""
    clave = os.environ.get("GEMINI_API_KEY")
    if not clave:
        raise SinIA("falta el secreto GEMINI_API_KEY")
    partes = [{"text": texto}]
    for ruta in imagenes:
        with open(ruta, "rb") as f:
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read()).decode()}})
    if audio and os.path.exists(audio) and os.path.getsize(audio) < 8_000_000:   # que los jueces también lo oigan
        with open(audio, "rb") as f:
            partes.append({"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(f.read()).decode()}})
    if video and os.path.exists(video) and os.path.getsize(video) < VIDEO_MAXIMO:   # un vídeo corto entero (Ojeador)
        with open(video, "rb") as f:
            partes.append({"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(f.read()).decode()}})
    cuerpo = {"contents": [{"role": "user", "parts": partes}], "generationConfig": {"temperature": temperatura}}
    if json_salida:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
    ultimo = "sin intentar"
    orden = BUENOS if solo_bueno else (LIGEROS + BUENOS if ligero_primero else BUENOS + LIGEROS)
    paciencia = PACIENCIA if paciencia is None else max(0, int(paciencia))
    for vuelta in range(paciencia + 1):
        modelos = [m for m in orden if m not in AGOTADOS]    # para texto sencillo, los ligeros primero: guardan cupo bueno
        vivos = False                 # ¿alguno está saturado o lento, pero con cupo? Entonces merece otra vuelta
        for modelo in modelos:
            for intento in range(intentos):
                req = urllib.request.Request(URL.format(modelo=modelo), data=json.dumps(cuerpo).encode(), method="POST",
                                             headers={"Content-Type": "application/json", "x-goog-api-key": clave})
                try:
                    with urllib.request.urlopen(req, timeout=180) as r:
                        datos = json.load(r)
                    texto_respuesta = "".join(p.get("text", "") for p in datos["candidates"][0]["content"]["parts"])
                    salida = _limpiar_json(texto_respuesta) if json_salida else texto_respuesta
                    _contar(modelo, "bien")
                    return salida
                except urllib.error.HTTPError as e:
                    ultimo = f"{modelo}: HTTP {e.code}"
                    if e.code == 429:
                        try:
                            detalle = e.read().decode("utf-8", "replace")
                        except Exception:
                            detalle = ""
                        _contar(modelo, "sin_cupo")
                        if "PerDay" in detalle:            # sin cupo hasta mañana: no se vuelve a probar en esta ronda
                            AGOTADOS.add(modelo)
                            ultimo += " (sin cupo hoy)"
                            break
                        vivos = True
                        if intento >= 1:                   # límite por minuto y ya ha esperado una vez: el siguiente modelo
                            break
                        time.sleep(25)                     # límite por minuto: esperar un poco y repetir con este modelo
                        continue
                    if e.code in (404, 403):               # modelo que no existe o sin permiso: siguiente modelo
                        AGOTADOS.add(modelo)
                        _contar(modelo, "sin_cupo")
                        break
                    _contar(modelo, "fallos")
                    if e.code in (500, 502, 503, 504):
                        vivos = True
                        _contar(modelo, "saturado")
                        if intento >= 1:                   # saturado: mejor probar otro modelo que esperar
                            break
                        time.sleep(8)
                        continue
                    break                                  # este modelo no acepta la petición (p. ej. audio): el siguiente
                except (KeyError, IndexError, ValueError) as e:
                    ultimo = f"{modelo}: respuesta rara ({type(e).__name__})"
                    vivos = True
                    time.sleep(3)
                except urllib.error.URLError as e:
                    ultimo = f"{modelo}: sin conexión ({e.reason})"
                    vivos = True
                    time.sleep(5)
                except (TimeoutError, OSError) as e:          # tarda demasiado en contestar: otro intento u otro modelo
                    ultimo = f"{modelo}: no contesta a tiempo ({type(e).__name__})"
                    vivos = True
                    time.sleep(5)
        if not vivos or vuelta >= paciencia:
            break
        espera = ESPERAS[min(vuelta, len(ESPERAS) - 1)]
        print(f"gemini: saturado; espero {espera} s y doy otra vuelta ({vuelta + 1} de {paciencia})", flush=True)
        time.sleep(espera)
    raise SinIA(f"Gemini no contesta: {ultimo}")


VE_VIDEOS = None     # el último modelo que supo ver un vídeo de YouTube por su enlace: se prueba el primero


def ver_youtube(url, texto, temperatura=0.3, json_salida=True, espera=300):
    """Gemini «ve» un vídeo público de YouTube por su enlace (no se descarga nada) y contesta a `texto`.
    No todos los modelos saben hacerlo: prueba los buenos, empezando por el último que supo, y salta los que no pueden."""
    global VE_VIDEOS
    clave = os.environ.get("GEMINI_API_KEY")
    if not clave:
        raise SinIA("falta el secreto GEMINI_API_KEY")
    if VE_VIDEOS is None:            # el que supo la última vez (lo apunta el Portero): así no se pierde tiempo probando
        try:
            from bots.comun import privado
            VE_VIDEOS = (privado.leer("estado/gemini.json", {}) or {}).get("ve_videos") or ""
        except Exception:
            VE_VIDEOS = ""
    cuerpo = {"contents": [{"role": "user", "parts": [{"file_data": {"file_uri": url}}, {"text": texto}]}],
              "generationConfig": {"temperature": temperatura}}
    if json_salida:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
    orden = ([VE_VIDEOS] if VE_VIDEOS else []) + [m for m in BUENOS if m != VE_VIDEOS]
    pendientes, esperado, ultimo = [m for m in orden if m not in AGOTADOS], set(), "sin intentar"
    while pendientes:
        modelo = pendientes.pop(0)
        req = urllib.request.Request(URL.format(modelo=modelo), data=json.dumps(cuerpo).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": clave})
        try:
            with urllib.request.urlopen(req, timeout=espera) as r:
                datos = json.load(r)
            respuesta = "".join(p.get("text", "") for p in datos["candidates"][0]["content"]["parts"])
            salida = _limpiar_json(respuesta) if json_salida else respuesta
            _contar(modelo, "bien")
            VE_VIDEOS = modelo
            return salida
        except urllib.error.HTTPError as e:
            ultimo = f"{modelo}: HTTP {e.code}"
            if e.code == 429:
                try:
                    detalle = e.read().decode("utf-8", "replace")
                except Exception:
                    detalle = ""
                _contar(modelo, "sin_cupo")
                if "PerDay" in detalle:               # sin cupo hasta mañana: no se vuelve a probar hoy
                    AGOTADOS.add(modelo)
                    ultimo += " (sin cupo hoy)"
                elif modelo not in esperado:          # límite por minuto (un vídeo gasta mucho): esperar y repetir
                    esperado.add(modelo)
                    time.sleep(60)
                    pendientes.insert(0, modelo)
                continue
            if e.code == 404:                         # modelo que ya no existe
                AGOTADOS.add(modelo)
            _contar(modelo, "fallos")                 # este modelo no sabe ver vídeos (o no ese): el siguiente
        except (KeyError, IndexError, ValueError) as e:
            ultimo = f"{modelo}: respuesta rara ({type(e).__name__})"
            _contar(modelo, "fallos")
        except (urllib.error.URLError, TimeoutError, OSError) as e:   # tarda demasiado: el siguiente modelo
            ultimo = f"{modelo}: no contesta a tiempo ({type(e).__name__})"
            _contar(modelo, "fallos")
    raise SinIA(f"Gemini no ha podido ver el vídeo: {ultimo}")
