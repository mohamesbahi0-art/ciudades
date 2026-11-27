"""Simulacro de la cadena de IA gratis: con servicios y llaves de mentira (sin red), comprueba que cuando Gemini no
contesta la fábrica salta de un servicio al siguiente, respeta a los que se quedan sin cupo y avisa de una llave mala.

    python pruebas/simulacro_cadena.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PRIVADO = os.path.join(tempfile.mkdtemp(prefix="cadena-"), "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
os.environ["CADENA_SIN_LLAVE"] = "1"                       # aquí sí se prueban los sin llave (todo es de mentira)
from bots.comun import cadena, gemini, ia, privado  # noqa: E402
cadena.MINUTO = os.path.join(PRIVADO, "minuto.json")

FALLOS = 0


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    FALLOS += 0 if vale else 1


REAL, REAL_TEXTO, REAL_VISION = dict(cadena.SERVICIOS), list(cadena.ORDEN_TEXTO), list(cadena.ORDEN_VISION)
cadena.SERVICIOS = {
    "uno": {"nombre": "Uno", "secreto": "UNO_API_KEY", "url": "https://uno.invalid/v1", "texto": ["uno-grande"], "vision": []},
    "dos": {"nombre": "Dos", "secreto": "DOS_API_KEY", "url": "https://dos.invalid/v1", "texto": ["dos-a"], "vision": ["dos-ve"]},
    "tres": {"nombre": "Tres", "secreto": "TRES_API_KEY", "url": "https://tres.invalid/v1", "texto": ["tres-a"], "vision": ["tres-ve"]},
    "cuatro": {"nombre": "Cuatro", "secreto": "CUATRO_API_KEY", "url": "https://cuatro.invalid/v1", "texto": ["cuatro-a"], "vision": []},
}
cadena.ORDEN_TEXTO, cadena.ORDEN_VISION = ["uno", "dos", "tres", "cuatro"], ["dos", "tres"]
for k in ("UNO", "DOS", "TRES"):
    os.environ[f"{k}_API_KEY"] = "llave-de-mentira"          # «cuatro» no tiene llave: no forma parte de la cadena
LLAMADAS, GUION = [], {}
cadena.time.sleep = lambda s: None


def error(req, codigo, cuerpo="", cabeceras=None):
    import email.message
    h = email.message.Message()
    for k, v in (cabeceras or {}).items():
        h[k] = v
    return urllib.error.HTTPError(req.full_url, codigo, "x", h, io.BytesIO(cuerpo.encode()))


class Respuesta:
    def __init__(self, texto):
        self.texto = texto

    def __enter__(self):
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": self.texto}}]}).encode())

    def __exit__(self, *a):
        return False


CABECERAS, LISTAS = [], {}


class Lista:
    def __init__(self, ids):
        self.ids = ids

    def __enter__(self):
        return io.BytesIO(json.dumps({"data": [{"id": i} for i in self.ids]}).encode())

    def __exit__(self, *a):
        return False


def servidor(req, timeout=0):
    servicio = req.full_url.split("//")[1].split(".")[0]
    if req.data is None and req.full_url.endswith("/models"):
        return Lista(LISTAS.get(servicio, []))
    cuerpo = json.loads(req.data)
    LLAMADAS.append((servicio, cuerpo["model"], isinstance(cuerpo["messages"][0]["content"], list)))
    CABECERAS.append((servicio, req.get_header("Authorization"), req.get_header("Client-agent"), "response_format" in cuerpo))
    que = GUION.get(servicio, "bien")
    if callable(que):
        que = que()
    if que == "sin_cupo_hoy":
        raise error(req, 429, '{"error": "Rate limit reached: requests per day (RPD)"}')
    if que == "un_minuto":
        raise error(req, 429, '{"error": "rate limit"}', {"retry-after": "3"})
    if que == "caido":
        raise error(req, 503)
    if que == "llave_mala":
        raise error(req, 401, '{"error": "invalid api key"}')
    if que == "no_entiende" and "response_format" in cuerpo:
        raise error(req, 400, '{"error": "unknown parameter"}')
    if que == "muy_grande":
        raise error(req, 413, '{"error": "request too large"}')
    if que == "minuto_sin_aviso":
        raise error(req, 429, '{"error": "too many requests"}')
    if que == "vuelve_manana":
        raise error(req, 429, '{"error": {"metadata": {"error_type": "rate_limit_exceeded"}}}',
                    {"X-RateLimit-Reset": str(int((time.time() + 9 * 3600) * 1000))})
    return Respuesta('<think>pienso</think>```json\n{"quien": "%s"}\n```' % servicio)


cadena.urllib.request.urlopen = servidor
comprobar("la cadena son solo los servicios con llave", cadena.encendidos() == ["uno", "dos", "tres"])

# 1. El primero contesta
r, quien = cadena.preguntar("Devuelve SOLO un JSON")
comprobar("contesta el primero de la cadena y se entiende su JSON aunque venga envuelto", r == {"quien": "uno"} and quien == "uno")

# 2. El primero sin cupo hoy, el segundo caído: salta hasta el tercero, y el primero queda apuntado hasta mañana
GUION.update(uno="sin_cupo_hoy", dos="caido")
LLAMADAS.clear()
r, quien = cadena.preguntar("JSON")
estado = privado.leer(cadena.ESTADO, {})
comprobar("salta de uno a otro hasta el que contesta", quien == "tres" and [x[0] for x in LLAMADAS] == ["uno", "dos", "dos", "tres"])
comprobar("el que no tiene cupo hoy queda apuntado para todas las líneas", "uno:uno-grande" in (estado.get("agotados") or {}))
LLAMADAS.clear()
cadena.APAGADOS.clear()                   # otra línea de la fábrica (otro proceso): solo sabe lo que está apuntado
r, quien = cadena.preguntar("JSON")
comprobar("y nadie le vuelve a llamar antes de tiempo", "uno" not in [x[0] for x in LLAMADAS])

# 3. Límite por minuto: espera lo que pide y repite con el mismo
veces = {"n": 0}


def minuto():
    veces["n"] += 1
    return "un_minuto" if veces["n"] == 1 else "bien"


GUION.update(dos=minuto)
LLAMADAS.clear()
r, quien = cadena.preguntar("JSON")
comprobar("con el límite por minuto espera un momento y repite", quien == "dos" and len(LLAMADAS) == 2)

# 4. Imágenes: solo los que ven, y la foto viaja dentro de la pregunta
foto = os.path.join(PRIVADO, "f.jpg")
open(foto, "wb").write(b"\xff\xd8\xff\xd9")
GUION.update(dos="bien")
LLAMADAS.clear()
r, quien = cadena.preguntar("JSON", imagenes=[foto])
comprobar("para mirar imágenes usa un modelo que ve", LLAMADAS == [("dos", "dos-ve", True)])

# 5. Llave mala: se apunta para avisar al dueño y se sigue con el siguiente
GUION.update(dos="llave_mala")
LLAMADAS.clear()
r, quien = cadena.preguntar("JSON", imagenes=[foto])
comprobar("una llave que no vale no para la cadena y queda apuntada", quien == "tres"
          and "dos" in (privado.leer(cadena.ESTADO, {}).get("llaves_malas") or {}))

# 6. Enganchada a la IA gratis de la fábrica: si Gemini no contesta, contesta la cadena sin que nadie lo note
GUION.clear()
cadena.APAGADOS.clear()
privado.escribir(cadena.ESTADO, {})
pedidos = []


def gemini_caido(texto, **kw):
    pedidos.append(kw.get("paciencia"))
    raise gemini.SinIA("Gemini no contesta: HTTP 503")


gemini._solo_gemini = gemini_caido
r = gemini.preguntar("Devuelve SOLO un JSON")
comprobar("Gemini caído → contesta la cadena, y a Gemini no se le hace esperar", r == {"quien": "uno"} and pedidos == [0]
          and gemini.QUIEN["servicio"] == "uno")
ia.claude.puede = lambda papel, **k: False
r = ia.preguntar("Devuelve SOLO un JSON", papel="guionista")
comprobar("y queda apuntado quién escribió de verdad", ia.quien().get("motor") == "uno")
try:
    gemini.preguntar("mira este vídeo", video="/no/existe.mp4")
    comprobar("un vídeo entero solo lo ve Gemini: la cadena no se mete", False)
except gemini.SinIA:
    comprobar("un vídeo entero solo lo ve Gemini: la cadena no se mete", True)

# 7. Todos fuera: se dice claro y la fábrica lo trata como «sin IA» (espera, no avería)
GUION.update(uno="caido", dos="caido", tres="caido")
try:
    gemini.preguntar("JSON")
    comprobar("si nadie contesta, es «sin IA»", False)
except gemini.SinIA as e:
    comprobar("si nadie contesta, es «sin IA»", "cadena" in str(e))

# 7b. Lo que puede cada servicio: lo que no le cabe se lo salta, las fotos de más van en mosaico, y lo raro no le para
GUION.clear()
cadena.APAGADOS.clear()
privado.escribir(cadena.ESTADO, {})
cadena.SERVICIOS["uno"].update(tokens_minuto=1000, max_salida=300)
LLAMADAS.clear()
r, quien = cadena.preguntar("x" * 6000)
comprobar("una pregunta que no le cabe a un servicio (tope por minuto) ni se le manda", quien == "dos" and [x[0] for x in LLAMADAS] == ["dos"])
r, quien = cadena.preguntar("corta")
comprobar("y la que sí cabe, sí", quien == "uno")
cadena.SERVICIOS["uno"].pop("tokens_minuto")
from PIL import Image  # noqa: E402
fotos = []
for i in range(7):
    ruta = os.path.join(PRIVADO, f"foto{i}.jpg")
    Image.new("RGB", (1080, 1920), (30 * i, 80, 120)).save(ruta, "JPEG")
    fotos.append(ruta)
cadena.SERVICIOS["dos"].update(max_imagenes=2)
vistos = []
servidor_normal = cadena.urllib.request.urlopen


def espia(req, timeout=0):
    vistos.append(json.loads(req.data))
    return servidor_normal(req, timeout)


cadena.urllib.request.urlopen = espia
r, quien = cadena.preguntar("mira", imagenes=fotos)
contenido = vistos[-1]["messages"][0]["content"]
comprobar("7 fotogramas para un servicio que admite 2: van en 2 mosaicos numerados, y se le avisa",
          quien == "dos" and sum(1 for x in contenido if x["type"] == "image_url") == 2 and "mosaico" in contenido[0]["text"])
cadena.SERVICIOS["dos"].pop("max_imagenes")
r, quien = cadena.preguntar("mira", imagenes=fotos)
comprobar("y al que las admite todas le llegan las 7", sum(1 for x in vistos[-1]["messages"][0]["content"] if x["type"] == "image_url") == 7)
cadena.urllib.request.urlopen = servidor_normal
GUION.update(uno="no_entiende")
LLAMADAS.clear()
r, quien = cadena.preguntar("JSON")
comprobar("si un servicio no entiende una opción, se le repite la pregunta pelada y contesta", quien == "uno" and len(LLAMADAS) == 2)
GUION.update(uno="muy_grande")
r, quien = cadena.preguntar("JSON")
comprobar("«demasiado grande» para uno no le apaga: salta al siguiente", quien == "dos" and not cadena.APAGADOS)
cadena.SERVICIOS["uno"].update(cupo_comun=True)
GUION.update(uno="vuelve_manana")
r, quien = cadena.preguntar("JSON")
comprobar("cupo del día de toda la cuenta (lo dice su cabecera): queda apuntado el servicio entero",
          quien == "dos" and "uno:*" in (privado.leer(cadena.ESTADO, {}).get("agotados") or {}))
cadena.SERVICIOS["uno"].pop("cupo_comun")
GUION.clear()
cadena.APAGADOS.clear()
privado.escribir(cadena.ESTADO, {})
r, quien = cadena.preguntar("JSON")

# 8. El uso del día queda apuntado y se junta bien entre líneas
cadena.apuntar_uso()
e = privado.leer(cadena.ESTADO, {})
dia = list((e.get("uso") or {}))[0]
comprobar("queda apuntado quién ha contestado hoy", e["uso"][dia].get("uno", {}).get("bien", 0) >= 1 and e.get("encendidos") == ["uno", "dos", "tres"])
junto = privado.fusionar("estado/cadena.json", {"agotados": {"a:b": "2026-01-01T00:00:00Z"}, "uso": {"d": {"uno": {"bien": 3}}}},
                         {"agotados": {"a:b": "2026-01-02T00:00:00Z", "c:d": "2026-01-01T00:00:00Z"}, "uso": {"d": {"uno": {"bien": 5}}}})
comprobar("dos líneas a la vez no se pisan lo apuntado", junto["agotados"] == {"a:b": "2026-01-02T00:00:00Z", "c:d": "2026-01-01T00:00:00Z"}
          and junto["uso"]["d"]["uno"]["bien"] == 5)

# 9. Los servicios SIN llave: entran solos, van detrás de todos los de llave y respetan su tope por minuto
comprobar("en el catálogo de verdad, OVH y AI Horde van sin llave y con su tope por minuto",
          all(REAL[k].get("sin_llave") and not REAL[k].get("secreto") and REAL[k].get("peticiones_minuto") for k in ("ovh", "horde")))
comprobar("y en el orden de verdad van los últimos, detrás de los de llave",
          REAL_TEXTO[-2:] == ["ovh", "horde"] and REAL_VISION[-2:] == ["ovh", "horde"])
comprobar("AI Horde solo para trabajos pequeños, con respuesta corta y un tiempo máximo",
          REAL["horde"].get("max_pregunta") and REAL["horde"].get("max_salida", 9999) <= 512 and REAL["horde"].get("espera"))
GUION.clear()
cadena.APAGADOS.clear()
privado.escribir(cadena.ESTADO, {})
cadena.SERVICIOS.update({
    "anon": {"nombre": "Anon", "secreto": None, "sin_llave": True, "url": "https://anon.invalid/v1", "texto": ["anon-a"],
             "vision": [], "peticiones_minuto": 2, "sin_cupo_diario": True},
    "lento": {"nombre": "Lento", "secreto": None, "sin_llave": True, "llave_fija": "0000000000",
              "url": "https://lento.invalid/v1", "texto": ["lento-a"], "vision": [], "max_pregunta": 100,
              "json_nunca": True, "cabeceras": {"Client-Agent": "ciudades:1:anon"}, "espera_minima": 30},
})
cadena.ORDEN_TEXTO = ["anon", "uno", "dos", "tres", "cuatro", "lento"]   # aunque alguien lo ponga delante
comprobar("los sin llave entran en la cadena sin secreto, detrás de los de llave",
          cadena.encendidos() == ["uno", "dos", "tres", "anon", "lento"])
comprobar("y en los eslabones también van detrás, aunque el orden diga otra cosa",
          [x[0] for x in cadena.eslabones()] == ["uno", "dos", "tres", "anon", "lento"])
GUION.update(uno="caido", dos="caido", tres="caido")
LLAMADAS.clear()
CABECERAS.clear()
r, quien = cadena.preguntar("JSON")
comprobar("si los de llave no contestan, contesta el sin llave", quien == "anon")
comprobar("y a un sin llave no se le manda ninguna llave", [c for c in CABECERAS if c[0] == "anon"][0][1] is None)
r, quien = cadena.preguntar("JSON")
LLAMADAS.clear()
r, quien = cadena.preguntar("JSON")
comprobar("con su tope (2 por minuto) lleno, ni se le llama: salta al siguiente",
          quien == "lento" and "anon" not in [x[0] for x in LLAMADAS])
c = [x for x in CABECERAS if x[0] == "lento"][-1]
comprobar("al de la llave de pega se le manda esa y su cabecera, sin pedirle modo JSON",
          c[1] == "Bearer 0000000000" and c[2] == "ciudades:1:anon" and c[3] is False)
LLAMADAS.clear()
try:
    cadena.preguntar("y" * 500)
    comprobar("una pregunta grande no va al de trabajos pequeños", False)
except cadena.SinCadena:
    comprobar("una pregunta grande no va al de trabajos pequeños", "lento" not in [x[0] for x in LLAMADAS])
os.remove(cadena.MINUTO)                  # pasa el minuto
GUION.update(anon="llave_mala")
r, quien = cadena.preguntar("JSON")
e = privado.leer(cadena.ESTADO, {})
comprobar("un 401 de un sin llave no es «llave mala» (no hay llave que cambiar): se aparta unas horas",
          quien == "lento" and "anon" not in (e.get("llaves_malas") or {}) and "anon:*" in (e.get("agotados") or {}))
cadena.APAGADOS.clear()
privado.escribir(cadena.ESTADO, {})
os.remove(cadena.MINUTO)
GUION.update(anon="minuto_sin_aviso")
r, quien = cadena.preguntar("JSON")
hasta = (privado.leer(cadena.ESTADO, {}).get("agotados") or {}).get("anon:anon-a", "")
comprobar("su 429 es del minuto (no tiene cupo del día): vuelve en un par de minutos, no mañana",
          quien == "lento" and hasta and hasta < (cadena._ahora() + cadena.dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))
os.environ["CADENA_SIN_LLAVE"] = "0"
comprobar("con CADENA_SIN_LLAVE=0 (pruebas sin red) los sin llave no entran", cadena.encendidos() == ["uno", "dos", "tres"])
os.environ["CADENA_SIN_LLAVE"] = "1"
cfg = privado.leer("config/fabrica.json", {})
privado.escribir("config/fabrica.json", dict(cfg, cadena={"sin_llave": False}))
comprobar("y el dueño los puede apagar todos en config (cadena.sin_llave: false)", cadena.encendidos() == ["uno", "dos", "tres"])
privado.escribir("config/fabrica.json", cfg)

# 10. Lo que deja el Explorador corrige el catálogo sin tocar el código (y nunca mete un servicio nuevo)
GUION.clear()
cadena.APAGADOS.clear()
privado.escribir(cadena.ESTADO, {})
privado.escribir(cadena.CORRECCIONES, {"servicios": {
    "dos": {"quitados": ["dos-a"], "nuevos": {"texto": ["dos-b"]}},
    "nadie": {"nuevos": {"texto": ["nadie-a"]}}}})
lista = cadena.eslabones()
comprobar("el modelo que ya no existe se apaga y el nuevo probado entra", ("dos", "dos-b") in lista and ("dos", "dos-a") not in lista)
comprobar("un servicio que no está en el catálogo no entra aunque lo diga el fichero", "nadie" not in [x[0] for x in lista])
privado.escribir(cadena.CORRECCIONES, {})
cadena.SERVICIOS["lento"].update(texto=[], lista_viva=True)
LISTAS["lento"] = ["algo-nsfw-13b", "viva-a", "viva-b", "viva-c"]
LLAMADAS.clear()
comprobar("la lista viva no se pide hasta que de verdad se llega a ese servicio",
          ("lento", cadena.VIVA) in cadena.eslabones() and "lento" not in cadena.VIVOS)
comprobar("y entonces usa los de su lista de hoy (sin los de adultos)",
          [m for k, m in cadena._expandir(cadena.eslabones()) if k == "lento"] == ["viva-a", "viva-b"])
GUION.update(uno="caido", dos="caido", tres="caido", anon="caido")
r, quien = cadena.preguntar("JSON")
comprobar("y le pregunta con uno de ellos", quien == "lento" and LLAMADAS[-1] == ("lento", "viva-a", False))

print("Simulacro de la cadena: " + ("todo bien" if not FALLOS else f"{FALLOS} fallo(s)"))
sys.exit(1 if FALLOS else 0)
