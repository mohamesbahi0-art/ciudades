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

BUENO = "gemini-flash-latest"
LIGERO = "gemini-flash-lite-latest"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


class SinIA(RuntimeError):
    """Gemini no ha contestado: sin cupo, caído o sin clave."""


def _limpiar_json(texto):
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(texto)


def preguntar(texto, imagenes=(), json_salida=True, solo_bueno=False, temperatura=0.9, intentos=3):
    clave = os.environ.get("GEMINI_API_KEY")
    if not clave:
        raise SinIA("falta el secreto GEMINI_API_KEY")
    partes = [{"text": texto}]
    for ruta in imagenes:
        with open(ruta, "rb") as f:
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(f.read()).decode()}})
    cuerpo = {"contents": [{"role": "user", "parts": partes}], "generationConfig": {"temperature": temperatura}}
    if json_salida:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
    ultimo = "sin intentar"
    for modelo in ([BUENO] if solo_bueno else [BUENO, LIGERO]):
        for intento in range(intentos):
            req = urllib.request.Request(URL.format(modelo=modelo), data=json.dumps(cuerpo).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": clave})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    datos = json.load(r)
                texto_respuesta = "".join(p.get("text", "") for p in datos["candidates"][0]["content"]["parts"])
                return _limpiar_json(texto_respuesta) if json_salida else texto_respuesta
            except urllib.error.HTTPError as e:
                ultimo = f"{modelo}: HTTP {e.code}"
                if e.code in (429, 404, 403):          # sin cupo, modelo que no existe o sin permiso: siguiente modelo
                    break
                if e.code in (500, 502, 503, 504):
                    time.sleep(8 * (intento + 1))
                    continue
                raise SinIA(ultimo)
            except (KeyError, IndexError, ValueError) as e:
                ultimo = f"{modelo}: respuesta rara ({type(e).__name__})"
                time.sleep(3)
            except urllib.error.URLError as e:
                ultimo = f"{modelo}: sin conexión ({e.reason})"
                time.sleep(5)
    raise SinIA(f"Gemini no contesta: {ultimo}")
