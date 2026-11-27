"""El Explorador de IA gratis (ciudad de los Mecánicos): una vez por semana, sin Claude y sin gastar dinero.

a) Pone al día los modelos de los servicios que YA están en la cadena (Gemini, los de llave y los sin llave): pide a
   cada uno su lista oficial de modelos y
   - el modelo del catálogo que ya no sale en la lista y, al preguntarle, contesta «no existe», se apaga;
   - los nuevos gratis que sirven para lo mismo (texto o ver imágenes, de tamaño para escribir guiones) se prueban con
     una pregunta cortita: el que contesta bien entra detrás de los del catálogo (2 por clase y servicio como mucho).
   Lo deja en estado/explorador/modelos.json (privado) y cadena.py lo aplica al leer, sin tocar el código. Nunca cambia de
   servicio ni mete uno nuevo. Los nuevos de Google solo los propone (un juez de primera lo elige Claude o el dueño).
   Lo que la cadena ya hace sola en cada ronda (un 400/404 aparta ese modelo 3 horas) sigue igual: esto es lo que dura.
b) Busca servicios nuevos en dos listas públicas (FreeLLMAPI y awesome-freellm-apis, en raw.githubusercontent.com),
   los compara con lo que ya hay y con los descartados del MANUAL, y apunta los candidatos que podrían cumplir las normas
   (gratis, sin tarjeta, condiciones que lo permiten) en estado/explorador/novedades.json, con lo que haría falta, para
   que Claude o el dueño decidan. Cada novedad se apunta una sola vez y lo descartado no se vuelve a proponer.

En el registro público solo salen nombres de servicio y cifras: nunca una llave ni el cuerpo de una respuesta.

Uso:  python bots/mecanicos/explorador.py [--solo modelos|novedades] [--prueba]
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.comun import cadena, gemini, privado  # noqa: E402

MODELOS = cadena.CORRECCIONES                                    # estado/explorador/modelos.json
NOVEDADES = os.path.join("estado", "explorador", "novedades.json")
GOOGLE = "https://generativelanguage.googleapis.com/v1beta"
CRUDO = "https://raw.githubusercontent.com"
FUENTES = {
    "freellmapi_plataformas": CRUDO + "/tashfeenahmed/freellmapi/main/docs/en/providers/01-supported-platforms.md",
    "freellmapi_condiciones": CRUDO + "/tashfeenahmed/freellmapi/main/docs/en/architecture/00-high-level-index.md",
    "awesome_freellm": CRUDO + "/open-free-llm-api/awesome-freellm-apis/main/README.md",
}
PRUEBAS_POR_SERVICIO = 3           # modelos nuevos que se prueban por servicio y semana (para no gastar cupo)
NUEVOS_POR_CLASE = 2               # los que entran en la cadena por servicio y clase, como mucho
TAMANO_MINIMO = 20                 # miles de millones de parámetros: los más pequeños no escriben guiones

# Los descartados del MANUAL (bots/mecanicos/MANUAL.md → La cadena de IA gratis), con su porqué. Si cambia allí, aquí.
DESCARTADOS = {
    "mistral": "ya no hay API gratis", "together": "ya no hay API gratis", "cerebras": "pide tarjeta",
    "huggingface": "quitó el cupo gratis", "githubmodels": "cerrado", "cohere": "su cuenta gratis prohíbe usarlo en producción",
    "nvidia": "su cuenta gratis prohíbe usarlo en producción", "sambanova": "20 preguntas al día y solo para probar",
    "openrouter": "ya es de pago",
}
# Nombres que usan las listas para lo mismo
ALIAS = {"google": "gemini", "googlegemini": "gemini", "gemini": "gemini", "cloudflareworkersai": "cloudflare",
         "workersai": "cloudflare", "ovhcloudaiendpoints": "ovh", "ovhaiendpoints": "ovh", "ovhcloud": "ovh",
         "aihorde": "horde", "stablehorde": "horde", "nvidianim": "nvidia", "mistralai": "mistral",
         "togetherai": "together", "hf": "huggingface", "huggingfaceinference": "huggingface",
         "githubmodel": "githubmodels", "kilocode": "kilo", "kilogateway": "kilo", "grokxai": "xai", "grok": "xai",
         "zaizhipuai": "zhipu", "zhipuzaibigmodelcn": "zhipu", "zhipuai": "zhipu", "ollamacloud": "ollama",
         "opencodezen": "opencode", "llm7io": "llm7", "chutesai": "chutes", "glhfchat": "glhf", "agnesai": "agnes",
         "aionlabs": "aion"}
IGNORAR = {"custom", "local", "ollamalocal"}        # no son servicios: huecos para poner uno propio
NO_SIRVE = re.compile(r"whisper|tts|speech|audio|transcri|embed|guard|rerank|moderat|orpheus|playai|compound|image|flux|"
                      r"diffusion|sdxl|dall|ocr|translat|bge|m2m|clip|resnet|detr|lora|tiny|minilm|nsfw|erot|lewd|porn|"
                      r"uncensor|abliterat|live|native-audio|computer-use|robotics|veo|imagen|lyria|aqa", re.I)
VE = re.compile(r"vision|[-_/]vl\b|[-_]vl[-_]|llava|pixtral|scout|maverick|multimodal", re.I)


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _iso():
    return _ahora().strftime("%Y-%m-%dT%H:%M:%SZ")


def _di(texto):
    print("explorador: " + texto, flush=True)


# --- a) los modelos de los servicios que ya están ----------------------------------------------------------------
def _sirve(modelo, google=False):
    """¿Sirve para lo mismo que el catálogo (texto o ver imágenes, y con tamaño para escribir guiones)?"""
    m = str(modelo)
    if NO_SIRVE.search(m):
        return False
    if google and not re.match(r"(gemini-.*flash|gemma-)", m, re.I):
        return False
    tam = re.search(r"(?<![a-z])(\d+(?:\.\d+)?)b\b", m.lower())    # «26b» de «26b-a4b»: el tamaño total
    return not tam or float(tam.group(1)) >= TAMANO_MINIMO


def _clase(modelo):
    return "vision" if VE.search(str(modelo)) else "texto"


def _foto():
    ruta = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "explorador_rojo.jpg")
    try:
        from PIL import Image
        Image.new("RGB", (96, 96), (220, 20, 20)).save(ruta, "JPEG")
        return ruta
    except Exception:
        return None


def _lista_google():
    llave = os.environ.get("GEMINI_API_KEY", "").strip()
    ids, pagina = [], ""
    for _ in range(10):
        url = GOOGLE + "/models?pageSize=1000" + (f"&pageToken={pagina}" if pagina else "")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"x-goog-api-key": llave,
                                                                         "User-Agent": cadena.AGENTE}), timeout=30) as r:
            d = json.load(r)
        for m in d.get("models") or []:
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                ids.append(str(m.get("name", "")).split("/", 1)[-1])
        pagina = d.get("nextPageToken") or ""
        if not pagina:
            break
    return ids


def _probar_google(modelo):
    """Una pregunta cortita a un modelo de Google: (veredicto, código), como cadena.probar_modelo."""
    cuerpo = {"contents": [{"role": "user", "parts": [{"text": 'Contesta solo con JSON: {"ok": true}'}]}],
              "generationConfig": {"temperature": 0.2}}
    req = urllib.request.Request(gemini.URL.format(modelo=modelo), method="POST", data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": cadena.AGENTE,
                                          "x-goog-api-key": os.environ.get("GEMINI_API_KEY", "").strip()})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.load(r)
        texto = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        return ("bien" if isinstance(cadena._json(texto), dict) else "contesta_mal"), 200
    except urllib.error.HTTPError as e:
        return {404: "no_existe", 410: "no_existe", 429: "sin_cupo", 401: "no_deja", 403: "no_deja"}.get(e.code, "falla"), e.code
    except (KeyError, IndexError, ValueError, TypeError):
        return "contesta_mal", 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return "no_contesta", 0


def _catalogo(servicio):
    if servicio == "gemini":
        return {m: ("vision" if m in gemini.BUENOS or m in gemini.SEGUNDA else "texto")
                for m in gemini.BUENOS + gemini.LIGEROS + gemini.SEGUNDA}
    s = cadena.SERVICIOS[servicio]
    return dict({m: "texto" for m in s.get("texto") or []}, **{m: "vision" for m in s.get("vision") or []})


def poner_al_dia(prueba=False):
    """Mira la lista oficial de cada servicio de la cadena y deja en modelos.json lo que ya no existe y lo nuevo probado."""
    anterior = privado.leer(MODELOS, {}) or {}
    viejos = anterior.get("servicios") or {}
    servicios, resumen = {}, {}
    vivos = cadena.encendidos()
    foto = None
    for servicio in ["gemini"] + list(cadena.SERVICIOS):
        antes = dict(viejos.get(servicio) or {})
        ficha = {"quitados": list(antes.get("quitados") or []),
                 "nuevos": {k: list(v) for k, v in (antes.get("nuevos") or {}).items()},
                 "rechazados": dict(antes.get("rechazados") or {}),
                 "propuestos": list(antes.get("propuestos") or [])}
        google = servicio == "gemini"
        if google and not os.environ.get("GEMINI_API_KEY"):
            servicios[servicio] = dict(antes, sin_lista="sin llave puesta")
            continue
        if not google and servicio not in vivos:
            servicios[servicio] = dict(antes, sin_lista="apagado o sin llave puesta")
            continue
        try:
            ids = _lista_google() if google else cadena.lista_oficial(servicio)
        except urllib.error.HTTPError as e:
            ids, motivo = None, f"HTTP {e.code}"
        except Exception as e:
            ids, motivo = None, type(e).__name__
        if not ids:                              # sin lista (o vacía) no se decide nada: se queda lo de la otra semana
            motivo = "lista vacía" if ids == [] else motivo
            servicios[servicio] = dict(antes, sin_lista=motivo, mirado=_iso())
            _di(f"{servicio}: no deja ver su lista ({motivo}); sigue con lo de la semana pasada")
            continue
        if google:
            def probar(m, c, f):
                return _probar_google(m)
        else:
            def probar(m, c, f, servicio=servicio):
                return cadena.probar_modelo(servicio, m, c, foto=f)
        catalogo = _catalogo(servicio)
        cifras = {"ofrece": len(ids), "ya_no_existen": 0, "vuelven": 0, "probados": 0, "entran": 0}
        # 1. lo del catálogo que ya no sale en su lista: se le pregunta y, si dice «no existe», se apaga
        for modelo, clase in catalogo.items():
            if modelo in ids:
                if modelo in ficha["quitados"]:
                    ficha["quitados"].remove(modelo)
                    cifras["vuelven"] += 1
                continue
            if modelo in ficha["quitados"]:
                continue
            veredicto, _ = (_probar_google(modelo) if google else cadena.probar_modelo(servicio, modelo, "texto"))
            if veredicto == "no_existe":
                ficha["quitados"].append(modelo)
                cifras["ya_no_existen"] += 1
        # 2. los nuevos que ya no están en su lista, fuera
        for clase in list(ficha["nuevos"]):
            ficha["nuevos"][clase] = [m for m in ficha["nuevos"][clase] if m in ids]
        ficha["propuestos"] = [p for p in ficha["propuestos"] if p.get("modelo") in ids]
        # 3. los nuevos que sirven para lo mismo: se prueban con una pregunta cortita
        ya = set(catalogo) | {m for v in ficha["nuevos"].values() for m in v} | set(ficha["rechazados"]) | \
            {p.get("modelo") for p in ficha["propuestos"]}
        candidatos = [m for m in ids if m not in ya and _sirve(m, google)]
        if cadena.SERVICIOS.get(servicio, {}).get("lista_viva"):
            candidatos = candidatos[:2]          # sus modelos cambian cada día: solo se mira cómo va, no se guardan
        for modelo in candidatos[:PRUEBAS_POR_SERVICIO]:
            clase = "texto" if google else _clase(modelo)
            if clase == "vision" and foto is None:
                foto = _foto() or ""
            if clase == "vision" and not foto:
                continue
            if not google and len(ficha["nuevos"].get(clase) or []) >= NUEVOS_POR_CLASE:
                continue
            veredicto, codigo = probar(modelo, clase, foto if clase == "vision" else None)
            cifras["probados"] += 1
            if veredicto == "sin_cupo" or veredicto == "no_contesta":
                continue                         # no es culpa del modelo: se vuelve a probar la semana que viene
            if veredicto != "bien":
                ficha["rechazados"][modelo] = f"{veredicto} {codigo}".strip()
                continue
            if google:
                ficha["propuestos"].append({"modelo": modelo, "clase": "texto", "prueba": "bien", "fecha": _iso()})
            elif cadena.SERVICIOS[servicio].get("lista_viva"):
                ficha.setdefault("probados_hoy", []).append(modelo)
            else:
                ficha["nuevos"].setdefault(clase, []).append(modelo)
                cifras["entran"] += 1
        ficha["rechazados"] = dict(list(ficha["rechazados"].items())[-60:])
        ficha.update(mirado=_iso(), ofrece=len(ids))
        servicios[servicio] = ficha
        resumen[servicio] = cifras
        _di(f"{servicio}: ofrece {cifras['ofrece']} modelos; {cifras['ya_no_existen']} del catálogo ya no existen, "
            f"{cifras['vuelven']} vuelven; {cifras['probados']} nuevos probados, {cifras['entran']} entran"
            + (f", {len(ficha['propuestos'])} propuestos para Claude" if google and ficha["propuestos"] else ""))
    datos = {"servicios": servicios, "actualizado": privado.ahora(),
             "nota": "Lo aplica bots/comun/cadena.py al leer (y gemini.py, solo los «quitados»). Los «propuestos» de "
                     "Google los decide Claude o el dueño."}
    if not prueba:
        privado.escribir(MODELOS, datos)
    return datos, resumen


# --- b) servicios nuevos en las listas públicas ------------------------------------------------------------------
def _clave(nombre):
    t = re.sub(r"\(.*?\)", "", html.unescape(str(nombre)))
    t = re.sub(r"<[^>]+>|`|\*", "", t).strip().lower()
    t = re.sub(r"[^a-z0-9]", "", t)
    return ALIAS.get(t, t)


def _limpio(texto, largo=300):
    t = re.sub(r"<[^>]+>", " ", html.unescape(str(texto)))
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[`*_]", "", t)
    return " ".join(t.split())[:largo]


def _tablas(md):
    """Las tablas de un markdown: [(título de la sección, [{cabecera: celda}])]."""
    salida, titulo, cabecera, filas = [], "", None, []
    for linea in md.splitlines() + [""]:
        l = linea.strip()
        if l.startswith("|"):
            celdas = [c.strip() for c in l.strip("|").split("|")]
            if cabecera is None:
                cabecera = [_limpio(c, 60).lower() for c in celdas]
            elif all(re.fullmatch(r":?-{2,}:?", c) for c in celdas if c):
                continue
            else:
                filas.append(dict(zip(cabecera, celdas)))
            continue
        if cabecera is not None:
            salida.append((titulo, filas))
            cabecera, filas = None, []
        if l.startswith("#"):
            titulo = l.lstrip("#").strip()
    return salida


def _bajar(url):
    req = urllib.request.Request(url, headers={"User-Agent": cadena.AGENTE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(2_000_000).decode("utf-8", "replace")


def _leer_fuentes(fuentes):
    """{clave: {nombre, fuentes, auth, tarjeta, condiciones, notas, base_url, creditos}} y el estado de cada fuente."""
    vistos, estado = {}, {}

    def ficha(nombre):
        k = _clave(nombre)
        if not k:
            return None
        return vistos.setdefault(k, {"nombre": _limpio(nombre, 60), "fuentes": [], "notas": []})

    for fuente, url in FUENTES.items():
        try:
            md = _bajar(url)
            estado[fuente] = {"estado": "bien", "fecha": _iso()}
        except urllib.error.HTTPError as e:
            estado[fuente] = {"estado": f"HTTP {e.code}", "fecha": _iso()}
            continue
        except Exception as e:
            estado[fuente] = {"estado": f"no contesta ({type(e).__name__})", "fecha": _iso()}
            continue
        for titulo, filas in _tablas(md):
            for f in filas:
                if fuente == "freellmapi_plataformas" and "platform" in f:
                    x = ficha(f.get("platform", ""))     # su nombre corto (`kilo`, `ovh`…) es el que vale
                    if x is None:
                        continue
                    x["nombre"] = _limpio(f.get("display name") or f.get("platform"), 60)
                    x["auth"] = _limpio(f.get("auth", ""), 120)
                    x["notas"].append(_limpio(f.get("notes", "")))
                elif fuente == "freellmapi_condiciones" and "verdict" in f:
                    x = ficha(f.get("provider", ""))
                    if x is None:
                        continue
                    x["condiciones"] = _limpio(f.get("verdict", ""), 40)
                    x["notas"].append(_limpio(f.get("notes", "")))
                elif fuente == "awesome_freellm" and "provider" in f:
                    x = ficha(f.get("provider", ""))
                    if x is None:
                        continue
                    if "credit card?" in f and "free models" in f:
                        x["tarjeta"] = _limpio(f["credit card?"], 40)
                    if "credit model" in f:
                        x["creditos"] = _limpio(f["credit model"], 120)
                    if "base url" in f and "`" in f["base url"]:
                        x["base_url"] = _limpio(f["base url"], 120)
                else:
                    continue
                if fuente not in x["fuentes"]:
                    x["fuentes"].append(fuente)
    return vistos, estado


FUERA = [
    (lambda x: re.search(r"retired|not registered", x.get("auth", ""), re.I), "ya no tiene parte gratis"),
    (lambda x: re.search(r"\byes\b|\bs[ií]\b|card|required", x.get("tarjeta", ""), re.I), "pide tarjeta"),
    (lambda x: x.get("creditos"), "solo créditos (hay que recargar o poner tarjeta)"),
    (lambda x: "❌" in x.get("condiciones", "") or re.search(r"avoid", x.get("condiciones", ""), re.I),
     "sus condiciones lo prohíben"),
    (lambda x: re.search(r"payment method|evaluation only|not production|trial|one-time|top-?up|credit card|paid only|"
                         r"moved to paid|pago", " ".join(x["notas"]) + " " + x.get("auth", ""), re.I),
     "pide pago o tarjeta, o solo deja probar"),
]


def buscar_novedades(prueba=False):
    """Compara las listas públicas con lo que ya hay y con los descartados, y apunta los candidatos nuevos una vez."""
    n = privado.leer(NOVEDADES, {}) or {}
    candidatos, descartados = dict(n.get("candidatos") or {}), dict(n.get("descartados") or {})
    vistos, estado = _leer_fuentes(FUENTES)
    ya = {_clave(k) for k in cadena.SERVICIOS} | {_clave(s.get("nombre", "")) for s in cadena.SERVICIOS.values()} | {"gemini"}
    nuevas, fuera = [], []
    for clave, x in sorted(vistos.items()):
        if clave in IGNORAR or clave in ya or clave in candidatos or clave in descartados:
            if clave in candidatos:
                candidatos[clave]["visto"] = _iso()
            continue
        if clave in DESCARTADOS:                 # los del MANUAL: se apuntan como descartados, una vez, con su porqué
            descartados[clave] = {"nombre": x["nombre"], "motivo": DESCARTADOS[clave], "quien": "manual", "fecha": _iso()}
            continue
        motivo = next((m for regla, m in FUERA if regla(x)), None)
        if motivo:
            descartados[clave] = {"nombre": x["nombre"], "motivo": motivo, "quien": "explorador", "fecha": _iso(),
                                  "fuentes": x["fuentes"]}
            fuera.append(clave)
            continue
        sin_llave = bool(re.search(r"keyless|anonymous", x.get("auth", ""), re.I))
        secreto = re.sub(r"[^A-Z0-9]", "_", clave.upper()) + "_API_KEY"
        candidatos[clave] = {
            "nombre": x["nombre"], "fuentes": x["fuentes"], "estado": "para_decidir", "apuntado": _iso(), "visto": _iso(),
            "tarjeta": x.get("tarjeta") or "no lo dice", "condiciones": x.get("condiciones") or "sin revisar",
            "base_url": x.get("base_url"), "notas": [t for t in x["notas"] if t][:3],
            "hace_falta": ("nada en principio: va sin llave (comprobar en su documentación el acceso anónimo y su tope)"
                           if sin_llave else f"una cuenta gratis (una sola) y su llave como secreto de GitHub ({secreto})"),
            "comprobar": "que sea gratis de verdad y sin tarjeta, que sus condiciones dejen usarlo así (automático y "
                         "para publicar) y que no guarde las preguntas para entrenar",
        }
        nuevas.append(clave)
    datos = {"candidatos": candidatos, "descartados": descartados, "fuentes": estado, "actualizado": privado.ahora(),
             "nota": "Candidatos para que Claude o el dueño decidan. Para descartar uno para siempre, pásalo a "
                     "«descartados» con su motivo. El Explorador no mete ninguno en la cadena."}
    if not prueba:
        privado.escribir(NOVEDADES, datos)
    for fuente, e in estado.items():
        _di(f"fuente {fuente}: {e['estado']}")
    _di(f"novedades: {len(nuevas)} nuevas" + (f" ({', '.join(nuevas[:20])})" if nuevas else "")
        + f", {len(fuera)} descartadas por las normas; {len(candidatos)} candidatos en total para decidir")
    return datos, nuevas, fuera


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", choices=("modelos", "novedades"))
    p.add_argument("--prueba", action="store_true", help="mira y dice lo que haría, sin guardar nada")
    a = p.parse_args()
    cuaderno = privado.cuaderno("explorador")
    lecciones = [l for l in cuaderno.datos.get("lecciones", []) if l.get("del_dueno")]
    if lecciones:
        _di(f"{len(lecciones)} lección(es) del dueño en su cuaderno")
    resumen, nuevas, fuera = {}, [], []
    if a.solo != "novedades":
        try:
            _, resumen = poner_al_dia(a.prueba)
        except Exception as e:                   # un fallo aquí no para la otra mitad
            _di(f"poner al día ha fallado ({type(e).__name__})")
    if a.solo != "modelos":
        try:
            _, nuevas, fuera = buscar_novedades(a.prueba)
        except Exception as e:
            _di(f"buscar novedades ha fallado ({type(e).__name__})")
    if not a.prueba:
        cuaderno.apuntar("modelos", {k: dict(v) for k, v in resumen.items()})
        cuaderno.apuntar("novedades", {"nuevas": nuevas, "descartadas": fuera})
        for servicio, c in resumen.items():
            if c.get("ya_no_existen"):
                cuaderno.aprender(f"{servicio} retira modelos sin avisar: mirar su lista oficial cada semana",
                                  confianza=0.6)
        cuaderno.guardar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
