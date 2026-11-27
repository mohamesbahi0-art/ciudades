"""Simulacro del Explorador de IA gratis: con servicios, listas y llaves de mentira (sin red), comprueba que apaga el
modelo que ya no existe, prueba los nuevos antes de usarlos, que la cadena lo lee sin tocar el código, que los nuevos de
Google solo se proponen, que apunta cada novedad una sola vez sin volver a proponer lo descartado, que sigue si una lista
no contesta y que en el registro no sale ninguna llave ni ninguna respuesta.

    python pruebas/simulacro_explorador.py
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PRIVADO = os.path.join(tempfile.mkdtemp(prefix="explorador-"), "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
os.environ["CADENA_SIN_LLAVE"] = "1"
LLAVE_UNO, LLAVE_GOOGLE = "llave-secreta-uno-123", "llave-secreta-google-456"
os.environ["UNO_API_KEY"], os.environ["GEMINI_API_KEY"] = LLAVE_UNO, LLAVE_GOOGLE
from bots.comun import cadena, gemini, privado  # noqa: E402
from bots.mecanicos import explorador  # noqa: E402

FALLOS = 0
SECRETO_RESPUESTA = "texto-de-respuesta-que-no-debe-salir"


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    FALLOS += 0 if vale else 1


cadena.MINUTO = os.path.join(PRIVADO, "minuto.json")
cadena.time.sleep = lambda s: None
cadena.SERVICIOS = {
    "uno": {"nombre": "Uno", "secreto": "UNO_API_KEY", "url": "https://uno.invalid/v1",
            "texto": ["uno-viejo-70b", "uno-sigue-70b"], "vision": []},
    "anon": {"nombre": "Anon", "secreto": None, "sin_llave": True, "url": "https://anon.invalid/v1", "texto": ["anon-a"],
             "vision": [], "peticiones_minuto": 2, "sin_cupo_diario": True},
}
cadena.ORDEN_TEXTO, cadena.ORDEN_VISION = ["uno", "anon"], ["uno", "anon"]
gemini.BUENOS, gemini.LIGEROS, gemini.SEGUNDA = ["gemini-bueno-flash"], ["gemini-desaparecido-flash"], []

LISTA_UNO = ["uno-sigue-70b", "uno-nuevo-120b", "uno-whisper-large", "uno-roto-70b", "uno-chico-8b", "uno-vision-90b"]
GOOGLE = ["gemini-bueno-flash", "gemini-9-flash", "text-embedding-9"]
PLATAFORMAS = """# Supported platforms
| Platform | Display name | Auth | Adapter | Notes |
| --- | --- | --- | --- | --- |
| `uno` | Uno | Keyed | OpenAI-compat | ya está |
| `nuevaia` | Nueva IA | Keyless | OpenAI-compat | Anonymous 10 req/min per IP. |
| `pagona` | Pagona | Keyed | OpenAI-compat | Free credit while a payment method is attached. |
| `mistral` | Mistral | Keyed | OpenAI-compat | `api.mistral.ai/v1`. |
| `custom` | Custom | Keyed | OpenAI-compat | hueco para uno propio |
"""
CONDICIONES = """## Terms of Service review
| Provider | Verdict | Notes |
|---|---|---|
| Nueva IA | ✅ Likely OK | anonymous use documented |
| Prohibida | ❌ Avoid | forbids personal use |
"""
LLAMADAS, FUENTE_CAIDA = [], {"awesome": True}


class Respuesta:
    def __init__(self, datos):
        self.datos = datos

    def __enter__(self):
        return io.BytesIO(self.datos if isinstance(self.datos, bytes) else json.dumps(self.datos).encode())

    def __exit__(self, *a):
        return False


def error(req, codigo, cuerpo=""):
    import email.message
    return urllib.error.HTTPError(req.full_url, codigo, "x", email.message.Message(), io.BytesIO(cuerpo.encode()))


def servidor(req, timeout=0):
    url = req.full_url
    cuerpo = json.loads(req.data) if req.data else None
    if "raw.githubusercontent.com" in url:
        LLAMADAS.append(("lista", url.rsplit("/", 1)[-1]))
        if "awesome" in url and FUENTE_CAIDA["awesome"]:
            raise urllib.error.URLError("no contesta")
        texto = PLATAFORMAS if "supported-platforms" in url else CONDICIONES if "high-level" in url else \
            "### ⚡ Permanent Free Tiers\n| Provider | Free Models | Credit Card? |\n|---|---|---|\n| Tarjetera | 3 | Yes |\n"
        return Respuesta(texto.encode())
    if "generativelanguage" in url:
        if cuerpo is None:
            return Respuesta({"models": [{"name": "models/" + m, "supportedGenerationMethods": ["generateContent"]}
                                         for m in GOOGLE]})
        modelo = url.split("/models/")[1].split(":")[0]
        LLAMADAS.append(("gemini", modelo))
        if modelo == "gemini-desaparecido-flash":
            raise error(req, 404, '{"error": "not found"}')
        return Respuesta({"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})
    servicio = url.split("//")[1].split(".")[0]
    if cuerpo is None:                                      # la lista de modelos
        if servicio == "anon":
            raise error(req, 401, '{"error": "' + SECRETO_RESPUESTA + '"}')
        return Respuesta({"data": [{"id": m} for m in LISTA_UNO]})
    modelo = cuerpo["model"]
    LLAMADAS.append((servicio, modelo))
    if modelo == "uno-viejo-70b":
        raise error(req, 404, '{"error": {"message": "The model does not exist ' + SECRETO_RESPUESTA + '"}}')
    if modelo == "uno-roto-70b":
        return Respuesta({"choices": [{"message": {"content": "no sé hacer JSON " + SECRETO_RESPUESTA}}]})
    contenido = cuerpo["messages"][0]["content"]
    if isinstance(contenido, list):
        return Respuesta({"choices": [{"message": {"content": '{"color": "rojo"}'}}]})
    return Respuesta({"choices": [{"message": {"content": '{"ok": true, "x": "' + SECRETO_RESPUESTA + '"}'}}]})


cadena.urllib.request.urlopen = servidor


def turno():
    sys.argv = ["explorador.py"]
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        explorador.main()
    return salida.getvalue()


registro = turno()
m = privado.leer(explorador.MODELOS, {})["servicios"]
uno = m["uno"]
comprobar("el modelo del catálogo que ya no sale en la lista y dice «no existe» se apaga", uno["quitados"] == ["uno-viejo-70b"])
comprobar("el nuevo que sirve se prueba y entra", "uno-nuevo-120b" in (uno["nuevos"].get("texto") or []))
comprobar("el nuevo que ve imágenes se prueba con una foto y entra para mirar", uno["nuevos"].get("vision") == ["uno-vision-90b"])
comprobar("el que no contesta lo pedido no entra y queda apuntado", "uno-roto-70b" in uno["rechazados"])
comprobar("los que no sirven para lo mismo (voz, muy pequeños) ni se prueban",
          not any(x[1] in ("uno-whisper-large", "uno-chico-8b") for x in LLAMADAS))
lista = cadena.eslabones()
comprobar("la cadena lo lee sin tocar el código: el viejo fuera, el nuevo dentro",
          ("uno", "uno-nuevo-120b") in lista and ("uno", "uno-viejo-70b") not in lista and ("uno", "uno-sigue-70b") in lista)
comprobar("y el nuevo va detrás de los del catálogo", [x for x in lista if x[0] == "uno"][0] == ("uno", "uno-sigue-70b"))
comprobar("los sin llave siguen en la cadena, detrás", lista[-1][0] == "anon")
comprobar("si un servicio no deja ver su lista, se apunta y no se toca nada suyo",
          m["anon"].get("sin_lista") and not m["anon"].get("quitados") and ("anon", "anon-a") in lista)
g = m["gemini"]
comprobar("Google: el que ya no existe se apaga", g["quitados"] == ["gemini-desaparecido-flash"])
gemini._QUITADOS.clear()
comprobar("y gemini.py deja de llamarle", "gemini-desaparecido-flash" in gemini._quitados())
comprobar("Google: el nuevo se prueba y SOLO se propone (un juez de primera lo eligen Claude o el dueño)",
          [p["modelo"] for p in g["propuestos"]] == ["gemini-9-flash"] and "gemini-9-flash" not in gemini.BUENOS)
n = privado.leer(explorador.NOVEDADES, {})
comprobar("la novedad que podría cumplir las normas queda apuntada para decidir, con lo que haría falta",
          "nuevaia" in n["candidatos"] and "sin llave" in n["candidatos"]["nuevaia"]["hace_falta"]
          and n["candidatos"]["nuevaia"]["condiciones"].startswith("✅"))
comprobar("la que pide pago o tarjeta se descarta sola, con su porqué", "pagona" in n["descartados"] and "nuevaia" not in n["descartados"])
comprobar("la que sus condiciones prohíben, también", "prohibida" in n["descartados"])
comprobar("lo descartado en el MANUAL no se propone", "mistral" in n["descartados"] and n["descartados"]["mistral"]["quien"] == "manual")
comprobar("lo que ya está en la cadena no es novedad, ni los huecos para uno propio",
          "uno" not in n["candidatos"] and "custom" not in n["candidatos"] and "anon" not in n["candidatos"])
comprobar("si una lista pública no contesta, se apunta y sigue con las demás",
          "no contesta" in n["fuentes"]["awesome_freellm"]["estado"] and n["fuentes"]["freellmapi_plataformas"]["estado"] == "bien")
comprobar("en el registro no sale ninguna llave ni ninguna respuesta",
          LLAVE_UNO not in registro and LLAVE_GOOGLE not in registro and SECRETO_RESPUESTA not in registro)
c = privado.cuaderno("explorador")
comprobar("apunta en su cuaderno lo que ha hecho", any(e["accion"] == "modelos" for e in c.datos["diario"]))

# Segunda semana: la lista caída vuelve, el dueño descarta una novedad y nada se repite
FUENTE_CAIDA["awesome"] = False
n["descartados"]["nuevaia"] = dict(n["candidatos"].pop("nuevaia"), motivo="no me fío", quien="dueño")
privado.escribir(explorador.NOVEDADES, n)
LLAMADAS.clear()
registro = turno()
n2 = privado.leer(explorador.NOVEDADES, {})
m2 = privado.leer(explorador.MODELOS, {})["servicios"]
comprobar("lo descartado no se vuelve a proponer", "nuevaia" not in n2["candidatos"])
comprobar("cada novedad se apunta una sola vez (la de la lista que vuelve, ahora sí)",
          set(n2["candidatos"]) == set(n["candidatos"]) and "tarjetera" in n2["descartados"])
comprobar("lo rechazado y lo ya probado no se vuelve a probar",
          not any(x[1] in ("uno-roto-70b", "uno-nuevo-120b", "uno-vision-90b", "gemini-9-flash") for x in LLAMADAS))
comprobar("lo apagado sigue apagado", m2["uno"]["quitados"] == ["uno-viejo-70b"] and m2["gemini"]["quitados"] == ["gemini-desaparecido-flash"])
LISTA_UNO.append("uno-viejo-70b")
turno()
comprobar("y si vuelve a salir en su lista, vuelve a la cadena", not privado.leer(explorador.MODELOS, {})["servicios"]["uno"]["quitados"])

# El turno y su sitio (si esta máquina no tiene PyYAML, como la de GitHub, no se mira el workflow)
try:
    import yaml  # noqa: E402
except ImportError:
    yaml = None
if yaml:
    w = yaml.safe_load(open(os.path.join(RAIZ, ".github", "workflows", "explorador.yml"), encoding="utf-8"))
    disparos = w.get("on") or w.get(True)
    paso = [p for p in w["jobs"]["explorar"]["steps"] if p.get("name") == "Explorar"][0]
    comprobar("explorador.yml: los lunes a las 05:41 UTC, a mano con peticiones/explorador.json, y guarda en el privado",
              disparos["schedule"][0]["cron"] == "41 5 * * 1" and "peticiones/explorador.json" in disparos["push"]["paths"]
              and any("git_guardar" in (p.get("run") or "") for p in w["jobs"]["explorar"]["steps"]))
    comprobar("y solo con las llaves que ya existen", set(paso["env"]) == {"PRIVADO", "MEMORIA_DIR", "GEMINI_API_KEY", "GROQ_API_KEY",
                                                                           "CLOUDFLARE_AI_TOKEN", "CLOUDFLARE_ACCOUNT_ID"})
else:
    print("(sin PyYAML en esta máquina: no se mira explorador.yml)")
bots = json.load(open(os.path.join(RAIZ, "ciudades.json"), encoding="utf-8"))["bots"]
comprobar("está en la ciudad de los Mecánicos", any(b.get("id") == "explorador_ia" and b.get("ciudad") == "taller" for b in bots))

print("Simulacro del Explorador: " + ("todo bien" if not FALLOS else f"{FALLOS} fallo(s)"))
sys.exit(1 if FALLOS else 0)
