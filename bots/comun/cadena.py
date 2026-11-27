"""La cadena de IA gratis: cuando Gemini no contesta (sin cupo o saturado), la fábrica salta al siguiente servicio
gratis, y de ese al siguiente, para tener con qué pensar las 24 horas (lo pidió el dueño: «que salte a la otra, y de
esta a la otra»). gemini.preguntar() la llama sola cuando Gemini falla: nadie más tiene que saber que existe.

- Cada servicio se enciende solo cuando su llave está en los secretos de GitHub (una cuenta por servicio; nada de
  multiplicar cuentas). Sin llave, ese eslabón no existe y la cadena sigue con los demás.
- Los servicios SIN llave (los que su documentación deja usar sin cuenta: OVH y AI Horde) van siempre al final, detrás de
  todos los de llave, y con su tope por minuto contado aquí (por máquina, que es por dirección de internet). Se apagan
  todos con config/fabrica.json → "cadena": {"sin_llave": false} o, en las pruebas, con CADENA_SIN_LLAVE=0.
- El Explorador de IA gratis (bots/mecanicos/explorador.py) deja cada semana en estado/explorador/modelos.json qué
  modelos del catálogo ya no existen y cuáles nuevos ha probado: la cadena lo aplica al leer, sin tocar el código.
- Hay dos cadenas: la de texto (guiones, ideas, votos) y la de los que ven imágenes (los jueces miran fotogramas).
- Si un servicio dice que ya no le queda cupo hoy, se apunta en estado/cadena.json (privado) hasta cuándo, y ni esta
  ronda ni las otras líneas vuelven a llamarle antes: no se pierde tiempo ni se le molesta.
- En los registros públicos solo sale el nombre del servicio y el código de la respuesta; nunca el texto.

El catálogo (qué servicios, con qué modelos y en qué orden) está en SERVICIOS. Se puede reordenar o apagar alguno sin
tocar el código en config/fabrica.json → "cadena": {"orden_texto": [...], "orden_vision": [...], "apagados": [...]}.
"""
import base64
import datetime as dt
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request

AGENTE = "ciudades-bot/1.0"
ESTADO = os.path.join("estado", "cadena.json")
TOPE_SEGUNDOS = 240            # una pregunta no pasa de esto recorriendo la cadena
ESPERA_CORTA = 20              # si un servicio pide esperar menos que esto (límite por minuto), se espera y se repite
MAX_SALIDA = 8000              # tokens de respuesta que se piden como mucho
CORRECCIONES = os.path.join("estado", "explorador", "modelos.json")   # lo que deja el Explorador (privado)
# las peticiones de cada minuto a los servicios con tope de peticiones (las cuenta la máquina entera: el tope de los sin
# llave es por dirección de internet, y en una máquina de GitHub todos los procesos salen por la misma)
MINUTO = os.path.join(tempfile.gettempdir(), "ciudades_cadena_minuto.json")

# Cada servicio: su secreto (la llave), su dirección y sus modelos gratis. «texto» y «vision» van por orden de
# preferencia dentro del servicio. Todos hablan el formato «chat/completions». Lo que puede cada uno:
#   max_imagenes   cuántas imágenes admite por pregunta (si llegan más, se juntan en mosaicos numerados)
#   tokens_minuto  su tope de tokens por minuto: una pregunta que no cabe se la salta sin llamarle
#   tokens_imagen  lo que le cuenta cada imagen
#   max_salida     tokens de respuesta que se le piden
#   cupo_comun     todos sus modelos gastan del mismo cupo del día
#   cuenta         secreto con el número de cuenta que va dentro de la dirección
#   sin_llave      su documentación deja usarlo sin cuenta: no lleva secreto («llave_fija» si pide una de pega)
#   peticiones_minuto  su tope de peticiones por minuto (por modelo si «tope_por_modelo»); se cuenta por máquina
#   sin_cupo_diario    no tiene cupo del día: un 429 suyo es del minuto, nunca «hasta mañana»
#   max_pregunta   caracteres de pregunta como mucho (solo trabajos pequeños)
#   espera         segundos que se le espera la respuesta; espera_minima: si queda menos tiempo, ni se le llama
#   json_nunca     no entiende «response_format»: el JSON lo pide la propia pregunta
#   lista_viva     sus modelos cambian cada día: si el catálogo no tiene, se usan los de su lista oficial de hoy
#   lista_modelos  dirección de su lista oficial de modelos, si no es «/models»
# Solo están los que dejan usarlo así (automático, para publicar) con una cuenta gratis y sin tarjeta. Fuera se quedan
# los que ya no son gratis o los que solo dejan «probar» (ver bots/mecanicos/MANUAL.md → La cadena de IA gratis).
SERVICIOS = {
    "groq": {
        "nombre": "Groq", "secreto": "GROQ_API_KEY", "url": "https://api.groq.com/openai/v1",
        "texto": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"], "vision": ["qwen/qwen3.8-27b"],
        "max_imagenes": 1, "tokens_minuto": 8000, "tokens_imagen": 2048, "max_salida": 3000,
        # que piensen poco: lo que piensan cuenta como respuesta y se come el tope por minuto
        "extra_modelo": {"openai/gpt-oss-120b": {"reasoning_effort": "low"},
                         "openai/gpt-oss-20b": {"reasoning_effort": "low"}},
    },
    "openrouter": {
        # solo los Gemma gratis: los gratis de otras casas llevan condiciones de «solo para probar» sin aclarar
        "nombre": "OpenRouter", "secreto": "OPENROUTER_API_KEY", "url": "https://openrouter.ai/api/v1",
        "texto": ["google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free"],
        "vision": ["google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free"], "cupo_comun": True,
    },
    "cloudflare": {
        "nombre": "Cloudflare", "secreto": "CLOUDFLARE_AI_TOKEN", "cuenta": "CLOUDFLARE_ACCOUNT_ID",
        "url": "https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/v1",
        "texto": ["@cf/google/gemma-4-26b-a4b-it", "@cf/openai/gpt-oss-120b"],
        "vision": ["@cf/google/gemma-4-26b-a4b-it"], "cupo_comun": True, "max_salida": 4000,
        "lista_modelos": "https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/models/search?per_page=1000"
                         "&task=Text%20Generation",
    },
    # --- los SIN llave: van detrás de todos los de llave ---
    "ovh": {
        # OVHcloud AI Endpoints: acceso anónimo documentado, 2 peticiones por minuto por dirección y por modelo (en la
        # práctica, más estricto entre modelos: aquí se cuentan 2 por minuto para todo el servicio). Sin cupo del día.
        "nombre": "OVH", "secreto": None, "sin_llave": True, "url": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        "texto": ["gpt-oss-120b", "Meta-Llama-3_3-70B-Instruct"], "vision": [],
        "peticiones_minuto": 2, "sin_cupo_diario": True, "max_salida": 3000, "espera": 120,
        "extra_modelo": {"gpt-oss-120b": {"reasoning_effort": "low"}},
    },
    "horde": {
        # AI Horde (texto): voluntarios, anónimo con la llave de pega «0000000000» y la prioridad más baja de la cola. Su
        # puerta OpenAI (oai.aihorde.net, en pruebas) espera a que un voluntario conteste: lento. Solo trabajos
        # pequeños, con respuesta corta y un tiempo máximo; los modelos cambian según quién esté conectado.
        "nombre": "AI Horde", "secreto": None, "sin_llave": True, "llave_fija": "0000000000",
        "url": "https://oai.aihorde.net/v1", "texto": [], "vision": [], "lista_viva": True,
        "cabeceras": {"Client-Agent": "ciudades:1:anon"}, "peticiones_minuto": 2, "sin_cupo_diario": True,
        "max_pregunta": 6000, "max_salida": 400, "espera": 170, "espera_minima": 60, "json_nunca": True,
    },
}
# El orden. Texto: Groq para lo pequeño (lo grande no le cabe y se lo salta solo), OpenRouter para lo grande (no tiene
# tope por minuto) y Cloudflare. Imágenes: Groq (su cupo de imágenes es aparte), Cloudflare y, lo último, OpenRouter,
# porque sus 50 preguntas al día rinden más en guiones. Detrás, siempre, los sin llave (OVH y, lo último, AI Horde).
ORDEN_TEXTO = ["groq", "openrouter", "cloudflare", "ovh", "horde"]
ORDEN_VISION = ["groq", "cloudflare", "openrouter", "ovh", "horde"]
CORREGIR = True                # aplicar lo que deja el Explorador (él mismo lo quita para ver el catálogo de verdad)
VIVOS = {}                     # {servicio: [modelos de su lista de hoy]} para los de «lista_viva», en esta ronda
VIVA = "(lista de hoy)"

APAGADOS = {}                  # {(servicio, modelo o "*"): hasta cuándo (epoch)} en esta ronda
USO = {}                       # {servicio: {"bien": n, "sin_cupo": n, "fallos": n}} en esta ronda


class SinCadena(RuntimeError):
    """Ningún servicio gratis de la cadena ha contestado."""


def _ahora():
    return dt.datetime.now(dt.timezone.utc)


def _privado():
    from bots.comun import privado
    return privado


def _ajustes():
    try:
        return (_privado().ajustes() or {}).get("cadena") or {}
    except Exception:
        return {}


def _estado():
    try:
        return _privado().leer(ESTADO, {}) or {}
    except Exception:
        return {}


def sin_llave_permitidos(ajustes=None):
    """¿Entran hoy los servicios sin llave? Sí, salvo que el dueño los apague en config o una prueba sin red lo pida."""
    if os.environ.get("CADENA_SIN_LLAVE", "1").strip() in ("0", "no", "false"):
        return False
    return (ajustes if ajustes is not None else _ajustes()).get("sin_llave", True) is not False


def encendidos():
    """Los servicios que forman la cadena ahora: los que tienen su llave puesta y, detrás, los que no necesitan llave."""
    a = _ajustes()
    apagados = set(a.get("apagados") or [])
    con = [k for k, s in SERVICIOS.items() if not s.get("sin_llave") and s.get("secreto") and os.environ.get(s["secreto"])
           and k not in apagados and (not s.get("cuenta") or os.environ.get(s["cuenta"]))]
    sin = [k for k, s in SERVICIOS.items() if s.get("sin_llave") and k not in apagados] if sin_llave_permitidos(a) else []
    return con + sin


def _url(s):
    return s["url"].replace("{cuenta}", os.environ.get(s.get("cuenta") or "", "")).rstrip("/")


def _llave(s):
    """La llave que se manda (la del secreto, la de pega de un servicio anónimo o ninguna)."""
    if s.get("sin_llave"):
        return s.get("llave_fija")
    return (os.environ.get(s.get("secreto") or "") or "").strip() or None


def cabeceras(s):
    h = {"Content-Type": "application/json", "User-Agent": AGENTE}
    llave = _llave(s)
    if llave:
        h["Authorization"] = "Bearer " + llave
    h.update(s.get("cabeceras") or {})
    return h


def _correcciones():
    """Lo que el Explorador ha visto en las listas oficiales: {servicio: {"quitados": [...], "nuevos": {"texto": [...],
    "vision": [...]}}}. Solo cuenta para los servicios que ya están en el catálogo: nunca mete uno nuevo."""
    if not CORREGIR:
        return {}
    try:
        return (_privado().leer(CORRECCIONES, {}) or {}).get("servicios") or {}
    except Exception:
        return {}


def lista_oficial(servicio, tiempo=30):
    """Los modelos que ofrece hoy un servicio según su lista oficial: [ids]. Lanza la excepción si no contesta."""
    s = SERVICIOS[servicio]
    url = (s.get("lista_modelos") or (s["url"] + "/models")).replace(
        "{cuenta}", os.environ.get(s.get("cuenta") or "", "")).rstrip("/")
    h = cabeceras(s)
    h.pop("Content-Type", None)
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=tiempo) as r:
        lista = json.load(r)
    if isinstance(lista, dict):
        filas = lista.get("data") or lista.get("result") or lista.get("models") or []
    else:
        filas = lista
    ids = []
    for m in filas or []:
        if isinstance(m, dict):              # Cloudflare da en «id» un número interno; su nombre de uso va en «name»
            nombre = str(m.get("name") or "")
            i = nombre if nombre.startswith("@") else (m.get("id") or m.get("name"))
        else:
            i = m
        if i:
            ids.append(str(i))
    return ids


def _lista_viva(servicio):
    """Para los servicios cuyos modelos cambian cada día (AI Horde): los de su lista de hoy, una vez por ronda."""
    if servicio not in VIVOS:
        try:
            ids = [i for i in lista_oficial(servicio, tiempo=20)
                   if not re.search(r"nsfw|erot|lewd|porn|uncensor|abliterat", i, re.I)]
        except Exception:
            ids = []
        VIVOS[servicio] = ids[:2]
    return VIVOS[servicio]


def modelos(servicio, clase="texto"):
    """Los modelos de un servicio para esa clase («texto» o «vision»): los del catálogo, sin los que el Explorador ha
    visto que ya no existen, más los nuevos que ha probado; y, si es de lista viva y no tiene, los de su lista de hoy."""
    s = SERVICIOS[servicio]
    base = list(s.get(clase) or [])
    c = _correcciones().get(servicio) or {}
    quitados = set(c.get("quitados") or [])
    lista = [m for m in base if m not in quitados]
    lista += [m for m in ((c.get("nuevos") or {}).get(clase) or []) if m not in lista and m not in quitados]
    if not lista and s.get("lista_viva") and clase == "texto":
        lista = [VIVA]                   # su lista de hoy se pide solo si de verdad se llega a él (_expandir)
    return lista


def _expandir(lista):
    """Cambia el «(lista de hoy)» de un servicio de lista viva por sus modelos de hoy, solo cuando se llega a él."""
    for servicio, modelo in lista:
        if modelo != VIVA:
            yield servicio, modelo
            continue
        quitados = set((_correcciones().get(servicio) or {}).get("quitados") or [])
        for m in _lista_viva(servicio):
            if m not in quitados and APAGADOS.get((servicio, m), 0) <= time.time():
                yield servicio, m


def eslabones(vision=False):
    """[(servicio, modelo)] por orden de la cadena, sin los que hoy ya han dicho que no les queda cupo. Los de llave
    siempre delante de los que no la necesitan."""
    a = _ajustes()
    orden = a.get("orden_vision" if vision else "orden_texto") or (ORDEN_VISION if vision else ORDEN_TEXTO)
    vivos = encendidos()
    orden = [k for k in orden if k in vivos] + [k for k in vivos if k not in orden]
    orden = [k for k in orden if not SERVICIOS[k].get("sin_llave")] + [k for k in orden if SERVICIOS[k].get("sin_llave")]
    agotados = (_estado().get("agotados") or {})
    ahora, iso = time.time(), _ahora().strftime("%Y-%m-%dT%H:%M:%SZ")
    salida = []
    for k in orden:
        for modelo in modelos(k, "vision" if vision else "texto"):
            if APAGADOS.get((k, "*"), 0) > ahora or APAGADOS.get((k, modelo), 0) > ahora:
                continue
            if str(agotados.get(f"{k}:{modelo}") or agotados.get(f"{k}:*") or "") > iso:
                continue
            salida.append((k, modelo))
    return salida


def _contar(servicio, que):
    u = USO.setdefault(servicio, {"bien": 0, "sin_cupo": 0, "fallos": 0})
    u[que] = u.get(que, 0) + 1


def _json(texto):
    """El JSON de una respuesta, aunque venga con «pensamientos», vallas de código o una frase delante."""
    t = re.sub(r"<think>.*?</think>", "", str(texto), flags=re.S).strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in t else t.strip("`")
    try:
        return json.loads(t)
    except ValueError:
        pass
    ini = min((i for i in (t.find("{"), t.find("[")) if i >= 0), default=-1)
    fin = max(t.rfind("}"), t.rfind("]"))
    if ini < 0 or fin <= ini:
        raise ValueError("la respuesta no trae JSON")
    return json.loads(t[ini:fin + 1])


def _mosaicos(rutas, cuantos):
    """Junta las imágenes en `cuantos` mosaicos numerados (para los servicios que admiten pocas por pregunta)."""
    from PIL import Image, ImageDraw
    import io
    por_hoja = -(-len(rutas) // cuantos)
    hojas = []
    for i in range(0, len(rutas), por_hoja):
        grupo = rutas[i:i + por_hoja]
        columnas = min(len(grupo), 4)
        filas = -(-len(grupo) // columnas)
        celdas = []
        for ruta in grupo:
            with Image.open(ruta) as im:
                im = im.convert("RGB")
                im.thumbnail((432, 768))
                celdas.append(im.copy())
        ancho, alto = max(c.width for c in celdas), max(c.height for c in celdas)
        hoja = Image.new("RGB", (columnas * ancho, filas * alto), (0, 0, 0))
        lapiz = ImageDraw.Draw(hoja)
        for j, celda in enumerate(celdas):
            x, y = (j % columnas) * ancho, (j // columnas) * alto
            hoja.paste(celda, (x, y))
            lapiz.rectangle([x, y, x + 46, y + 40], fill=(0, 0, 0))
            lapiz.text((x + 12, y + 8), str(i + j + 1), fill=(255, 255, 255))
        b = io.BytesIO()
        hoja.save(b, "JPEG", quality=80)
        hojas.append(b.getvalue())
    return hojas


def _fotos(servicio, imagenes):
    """Las imágenes como las quiere ese servicio: [bytes]. Si admite menos de las que hay, van en mosaicos."""
    tope = SERVICIOS[servicio].get("max_imagenes")
    if tope and len(imagenes) > tope:
        return _mosaicos(imagenes, tope), True
    datos = []
    for ruta in imagenes:
        with open(ruta, "rb") as f:
            datos.append(f.read())
    return datos, False


def _minuto_leer():
    try:
        with open(MINUTO, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _clave_minuto(servicio, modelo):
    return f"{servicio}:{modelo if SERVICIOS[servicio].get('tope_por_modelo') else '*'}"


def espera_turno(servicio, modelo):
    """Segundos que faltan para que ese servicio admita otra petición sin pasar de su tope por minuto (0 = ya)."""
    tope = SERVICIOS[servicio].get("peticiones_minuto")
    if not tope:
        return 0
    ahora = time.time()
    hechas = sorted(t for t in _minuto_leer().get(_clave_minuto(servicio, modelo), []) if t > ahora - 60)
    if len(hechas) < tope:
        return 0
    return max(0.0, hechas[-tope] + 60 - ahora) + 0.5


def apuntar_turno(servicio, modelo):
    """Cuenta una petición hecha a un servicio con tope por minuto (en un fichero de la máquina: lo comparten todos sus
    procesos, que salen por la misma dirección de internet)."""
    if not SERVICIOS.get(servicio, {}).get("peticiones_minuto"):
        return
    ahora = time.time()
    d = {k: [t for t in v if t > ahora - 60] for k, v in _minuto_leer().items() if isinstance(v, list)}
    d.setdefault(_clave_minuto(servicio, modelo), []).append(ahora)
    try:
        with open(MINUTO + ".tmp", "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in d.items() if v}, f)
        os.replace(MINUTO + ".tmp", MINUTO)
    except OSError:
        pass


def _cabe(servicio, texto, n_imagenes, modelo=None):
    """¿Le cabe la pregunta a ese servicio ahora? Por tamaño (trabajos pequeños), por su tope de peticiones por minuto
    (si hay que esperar más que un respiro, se le salta) y por su tope de tokens por minuto (cuenta por lo alto: más vale
    saltárselo)."""
    s = SERVICIOS[servicio]
    if s.get("max_pregunta") and len(texto) > s["max_pregunta"]:
        return False
    if s.get("peticiones_minuto") and espera_turno(servicio, modelo) > ESPERA_CORTA:
        return False
    tope = s.get("tokens_minuto")
    if not tope:
        return True
    tope_fotos = s.get("max_imagenes")
    fotos = min(n_imagenes, tope_fotos) if tope_fotos else n_imagenes
    salida = min(s.get("max_salida", MAX_SALIDA), 2000 if fotos else MAX_SALIDA)
    return len(texto) // 3 + fotos * s.get("tokens_imagen", 1000) + salida <= tope


def _cuerpo(servicio, modelo, texto, imagenes, json_salida, temperatura, sencillo=False):
    s = SERVICIOS[servicio]
    salida = s.get("max_salida", MAX_SALIDA)
    if imagenes:
        fotos, juntas = _fotos(servicio, imagenes)
        if juntas:
            texto = ("(Las imágenes van juntas en un mosaico: cada una lleva su número arriba a la izquierda, en orden.)\n"
                     + texto)
        if s.get("tokens_minuto"):
            salida = min(salida, 2000)
        contenido = [{"type": "text", "text": texto}]
        for dato in fotos:
            contenido.append({"type": "image_url",
                              "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(dato).decode()}})
    else:
        contenido = texto
    cuerpo = {"model": modelo, "messages": [{"role": "user", "content": contenido}],
              s.get("campo_salida", "max_tokens"): salida}
    if sencillo:                 # la pregunta pelada, por si el servicio no entiende alguna de las opciones
        return cuerpo
    cuerpo["temperature"] = min(1.0, temperatura)
    if json_salida and not s.get("json_nunca") and modelo not in (s.get("sin_json") or ()):
        cuerpo["response_format"] = {"type": "json_object"}
    cuerpo.update(s.get("extra") or {})
    cuerpo.update((s.get("extra_modelo") or {}).get(modelo) or {})
    return cuerpo


def _hasta_manana():
    m = (_ahora() + dt.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return m


def _apuntar_agotado(servicio, modelo, hasta):
    """Deja dicho (para esta ronda y para las demás) que ese modelo no tiene cupo hasta `hasta`."""
    if SERVICIOS.get(servicio, {}).get("cupo_comun") and hasta - _ahora() > dt.timedelta(minutes=30):
        modelo = "*"             # el cupo del día es de toda la cuenta: no le queda a ninguno de sus modelos
    APAGADOS[(servicio, modelo)] = hasta.timestamp()
    try:
        p = _privado()
        e = p.leer(ESTADO, {}) or {}
        e.setdefault("agotados", {})[f"{servicio}:{modelo}"] = hasta.strftime("%Y-%m-%dT%H:%M:%SZ")
        e["actualizado"] = p.ahora()
        p.escribir(ESTADO, e)
    except Exception:
        pass


def _avisar_llave(servicio, codigo):
    """Una llave que no vale: se apunta para que los Mecánicos avisen al dueño (una vez) y no se insiste en esta ronda."""
    APAGADOS[(servicio, "*")] = time.time() + 6 * 3600
    try:
        p = _privado()
        e = p.leer(ESTADO, {}) or {}
        e.setdefault("llaves_malas", {})[servicio] = {"desde": p.ahora(), "codigo": codigo}
        p.escribir(ESTADO, e)
    except Exception:
        pass


def _espera_que_pide(error, cuerpo_error):
    """Segundos que el servicio pide esperar (cabecera retry-after o lo que diga el mensaje); None si no lo dice."""
    for cabecera in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        valor = (error.headers.get(cabecera) or "").strip() if error.headers else ""
        if not valor:
            continue
        try:
            return float(valor)
        except ValueError:
            m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)s)?(?:(\d+)ms)?", valor)
            if m and any(m.groups()):
                return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0) + int(m.group(4) or 0) / 1000
    reinicio = (error.headers.get("x-ratelimit-reset") or "").strip() if error.headers else ""
    if reinicio.isdigit():                       # la hora a la que vuelve el cupo (en segundos o en milésimas)
        cuando = int(reinicio) / (1000 if len(reinicio) > 11 else 1)
        if cuando > time.time():
            return cuando - time.time()
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", cuerpo_error or "")
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3))
    return None


def preguntar(texto, imagenes=(), json_salida=True, temperatura=0.9, vision=False, tope=TOPE_SEGUNDOS):
    """Pregunta a la cadena. Devuelve (respuesta, servicio que contestó). Lanza SinCadena si nadie puede."""
    imagenes = [r for r in imagenes or () if r and os.path.exists(r)]
    lista = eslabones(vision=vision or bool(imagenes))
    if not lista:
        raise SinCadena("no hay ningún servicio gratis de reserva con llave y con cupo")
    empezo, ultimo = time.monotonic(), "sin intentar"
    for servicio, modelo in _expandir(lista):
        s = SERVICIOS[servicio]
        if APAGADOS.get((servicio, "*"), 0) > time.time():
            continue
        if not _cabe(servicio, texto, len(imagenes), modelo):    # no le cabe (tamaño o tope por minuto): ni se le llama
            ultimo = f"{servicio}: la pregunta no le cabe"
            continue
        if s.get("espera_minima") and tope - (time.monotonic() - empezo) < s["espera_minima"]:
            ultimo = f"{servicio}: no queda tiempo para esperarle"
            continue
        sencillo = False
        for intento in (1, 2, 3):
            if time.monotonic() - empezo > tope:
                raise SinCadena(f"la cadena no contesta a tiempo: {ultimo}")
            turno = espera_turno(servicio, modelo)
            if turno > ESPERA_CORTA:                             # su tope por minuto ya está lleno: el siguiente
                ultimo = f"{servicio}: tope por minuto lleno"
                break
            if turno:
                time.sleep(turno)
            try:
                cuerpo = _cuerpo(servicio, modelo, texto, imagenes, json_salida, temperatura, sencillo=sencillo)
            except Exception as e:                               # una imagen que no se puede abrir, p. ej.
                ultimo = f"{servicio}: no he podido preparar la pregunta ({type(e).__name__})"
                break
            req = urllib.request.Request(_url(s) + "/chat/completions", method="POST", data=json.dumps(cuerpo).encode(),
                                         headers=cabeceras(s))
            apuntar_turno(servicio, modelo)
            try:
                with urllib.request.urlopen(req, timeout=s.get("espera", 150)) as r:
                    datos = json.load(r)
                contenido = datos["choices"][0]["message"]["content"]
                if isinstance(contenido, list):                  # algunos lo devuelven por trozos
                    contenido = "".join(str(x.get("text", "")) for x in contenido if isinstance(x, dict))
                salida = _json(contenido) if json_salida else re.sub(r"<think>.*?</think>", "", str(contenido), flags=re.S).strip()
                if not salida and salida != 0:
                    raise ValueError("respuesta vacía")
                _contar(servicio, "bien")
                return salida, servicio
            except urllib.error.HTTPError as e:
                try:
                    detalle = e.read().decode("utf-8", "replace")[:600]
                except Exception:
                    detalle = ""
                ultimo = f"{servicio}: HTTP {e.code}"
                if e.code in (401, 403) and s.get("sin_llave"):  # sin llave no hay llave mala: hoy no deja (carga alta)
                    _contar(servicio, "fallos")
                    _apuntar_agotado(servicio, "*", _ahora() + dt.timedelta(hours=6))
                    break
                if e.code in (401, 403):                         # la llave no vale (o el servicio no deja): fuera hoy
                    _contar(servicio, "fallos")
                    _avisar_llave(servicio, e.code)
                    break
                if e.code == 429:
                    _contar(servicio, "sin_cupo")
                    espera = _espera_que_pide(e, detalle)
                    del_dia = bool(re.search(r"per day|daily|\bRPD\b|\bTPD\b|quota|free[- ]tier limit|free-models-per-day"
                                             r"|neurons|\b3036\b", detalle, re.I))
                    if espera is not None and espera <= ESPERA_CORTA and intento == 1 and not del_dia:
                        time.sleep(espera + 1)                   # límite por minuto: un respiro y se repite
                        continue
                    if s.get("sin_cupo_diario") and not (espera and espera > 3600):   # solo tiene tope por minuto
                        hasta = _ahora() + dt.timedelta(seconds=max(120, espera or 0))
                    elif espera is not None and espera > 3600:   # el servicio dice cuándo vuelve: se le cree
                        hasta = _ahora() + dt.timedelta(seconds=min(espera, 26 * 3600))
                    elif del_dia or espera is None:              # (antes, cerca de medianoche, «mañana» eran minutos)
                        hasta = _hasta_manana()
                    else:
                        hasta = _ahora() + dt.timedelta(seconds=max(60, espera))
                    _apuntar_agotado(servicio, modelo, hasta)
                    break
                if e.code == 402:                                # la cuenta no tiene saldo: hoy no cuenta con él
                    _contar(servicio, "sin_cupo")
                    _apuntar_agotado(servicio, "*", _hasta_manana())
                    break
                _contar(servicio, "fallos")
                if e.code == 413:                                # la pregunta es demasiado grande para él: el siguiente
                    break
                if e.code in (400, 422) and not sencillo:        # no entiende alguna opción: la pregunta pelada
                    sencillo = True
                    continue
                if e.code in (400, 404, 410, 422):               # ese modelo ya no existe o no acepta la pregunta
                    APAGADOS[(servicio, modelo)] = time.time() + 3 * 3600
                    break
                if e.code >= 500 and intento == 1:
                    time.sleep(4)
                    continue
                break
            except (KeyError, IndexError, ValueError, TypeError) as e:
                ultimo = f"{servicio}: respuesta rara ({type(e).__name__})"
                _contar(servicio, "fallos")
                break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                ultimo = f"{servicio}: no contesta ({type(e).__name__})"
                _contar(servicio, "fallos")
                break
        print(f"cadena: {ultimo}; salta al siguiente", flush=True)
    raise SinCadena(f"ningún servicio de la cadena ha contestado: {ultimo}")


def apuntar_uso():
    """Deja en estado/cadena.json quién ha contestado hoy (para la app y para la Élite). Se llama al acabar la ronda."""
    if not USO:
        return
    try:
        p = _privado()
        e = p.leer(ESTADO, {}) or {}
        dia = _ahora().strftime("%Y-%m-%d")
        hoy = e.setdefault("uso", {}).setdefault(dia, {})
        for servicio, u in USO.items():
            h = hoy.setdefault(servicio, {"bien": 0, "sin_cupo": 0, "fallos": 0})
            for k, v in u.items():
                h[k] = h.get(k, 0) + v
        e["uso"] = {d: v for d, v in e["uso"].items() if d >= (_ahora() - dt.timedelta(days=14)).strftime("%Y-%m-%d")}
        iso = _ahora().strftime("%Y-%m-%dT%H:%M:%SZ")
        e["agotados"] = {k: v for k, v in (e.get("agotados") or {}).items() if v > iso}
        if e.get("llaves_malas"):            # la que ha vuelto a contestar bien (llave nueva) ya no es mala
            e["llaves_malas"] = {k: v for k, v in e["llaves_malas"].items() if not USO.get(k, {}).get("bien")}
        e["encendidos"] = encendidos()
        e["actualizado"] = p.ahora()
        p.escribir(ESTADO, e)
        try:                                 # el Relevista lo apunta en su cuaderno
            c = p.cuaderno("relevista")
            c.apuntar("relevos", {"uso": {k: dict(v) for k, v in USO.items()},
                                  "sin_cupo": sorted(k for k, v in e["agotados"].items())})
            c.guardar()
        except Exception:
            pass
        USO.clear()
    except Exception:
        pass


def probar_modelo(servicio, modelo, clase="texto", foto=None, tiempo=None):
    """Una pregunta cortita a un modelo de un servicio del catálogo, para saber si sirve: devuelve (veredicto, código).
    Veredictos: «bien», «contesta_mal» (contesta, pero no lo pedido), «no_existe» (404/410, o 400/422 que habla del
    modelo), «sin_cupo» (429/402), «no_deja» (401/403), «falla» (otro código) o «no_contesta». Nunca enseña el texto."""
    s = SERVICIOS[servicio]
    vision = clase == "vision" and foto
    texto = 'Contesta solo con JSON: {"color": "el color que ves, o ninguno"}' if vision else \
        'Contesta solo con JSON: {"ok": true}'
    for intento in (1, 2):
        turno = espera_turno(servicio, modelo)
        if turno:
            time.sleep(min(turno, 65))
        cuerpo = _cuerpo(servicio, modelo, texto, [foto] if vision else (), True, 0.2, sencillo=intento == 2)
        cuerpo[s.get("campo_salida", "max_tokens")] = min(300, s.get("max_salida", MAX_SALIDA))
        req = urllib.request.Request(_url(s) + "/chat/completions", method="POST", data=json.dumps(cuerpo).encode(),
                                     headers=cabeceras(s))
        apuntar_turno(servicio, modelo)
        try:
            with urllib.request.urlopen(req, timeout=tiempo or s.get("espera", 90)) as r:
                datos = json.load(r)
            contenido = datos["choices"][0]["message"]["content"]
            if isinstance(contenido, list):
                contenido = "".join(str(x.get("text", "")) for x in contenido if isinstance(x, dict))
            try:
                r = _json(contenido)
            except ValueError:
                return "contesta_mal", 200
            if vision and not re.search(r"roj|red", json.dumps(r, ensure_ascii=False), re.I):
                return "contesta_mal", 200
            return ("bien" if isinstance(r, dict) else "contesta_mal"), 200
        except urllib.error.HTTPError as e:
            try:
                detalle = e.read().decode("utf-8", "replace")[:600]
            except Exception:
                detalle = ""
            if e.code in (400, 422) and intento == 1 and not re.search(r"model", detalle, re.I):
                continue                                   # alguna opción que no entiende: la pregunta pelada
            if e.code in (404, 410) or (e.code in (400, 422) and re.search(
                    r"model.{0,40}(not (found|exist|available|supported)|does ?n.t exist|unknown|invalid|decommission|deprecat)"
                    r"|(unknown|invalid|no such) model", detalle, re.I | re.S)):
                return "no_existe", e.code
            if e.code in (429, 402):
                return "sin_cupo", e.code
            if e.code in (401, 403):
                return "no_deja", e.code
            return "falla", e.code
        except (KeyError, IndexError, ValueError, TypeError):
            return "contesta_mal", 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return "no_contesta", 0
    return "falla", 400


def probar():
    """La prueba de la cadena (turno «Probar la cadena»): qué servicios tienen llave y cuáles van sin ella, qué modelos
    del catálogo existen y si contestan. Solo enseña nombres de servicio y de modelo y el código de respuesta: nunca
    llaves ni textos."""
    vivos = encendidos()
    print("CADENA con llave:", ", ".join(k for k in vivos if not SERVICIOS[k].get("sin_llave")) or "ninguno", flush=True)
    print("CADENA sin llave:", ", ".join(k for k in vivos if SERVICIOS[k].get("sin_llave")) or "ninguno", flush=True)
    print("CADENA apagados o sin su llave:", ", ".join(k for k in SERVICIOS if k not in vivos) or "ninguno", flush=True)
    foto = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "prueba_cadena.jpg")
    try:
        from PIL import Image
        Image.new("RGB", (96, 96), (220, 20, 20)).save(foto, "JPEG")
    except Exception:
        foto = None
    FORMA = {"groq": "gsk_", "openrouter": "sk-or-"}
    for k in vivos:
        s = SERVICIOS[k]
        llave = "" if s.get("sin_llave") else os.environ[s["secreto"]]
        cuenta = os.environ.get(s.get("cuenta") or "", "")
        if not s.get("sin_llave"):
            print(f"CADENA {k} llave: mide {len(llave)}"
                  + (f", {'empieza' if llave.strip().startswith(FORMA[k]) else 'NO empieza'} por {FORMA[k]}" if k in FORMA else "")
                  + (", lleva espacios o saltos de línea" if llave != llave.strip() or " " in llave else "")
                  + (f"; el número de cuenta mide {len(cuenta)} (tiene que medir 32)"
                     + ("" if re.fullmatch(r"[0-9a-f]{32}", cuenta.strip()) else " y NO tiene forma de número de cuenta")
                     if s.get("cuenta") else ""), flush=True)
        else:
            print(f"CADENA {k}: sin llave; tope {s.get('peticiones_minuto') or '-'} peticiones por minuto", flush=True)
        try:                                        # qué modelos ofrece hoy (para corregir el catálogo si cambian)
            ids = lista_oficial(k, tiempo=60)
            gratis = [i for i in ids if ":free" in i] if k == "openrouter" else ids
            print(f"CADENA {k}: ofrece {len(ids)} modelos; del catálogo faltan: "
                  + (", ".join(m for m in s.get("texto", []) + s.get("vision", []) if m not in ids) or "ninguno"), flush=True)
            print(f"CADENA {k} lista: " + ", ".join(sorted(gratis)[:60]), flush=True)
        except Exception as e:
            print(f"CADENA {k}: no deja ver su lista ({type(e).__name__} {getattr(e, 'code', '')})", flush=True)
        for clase in ("texto", "vision"):
            for _, modelo in _expandir([(k, m) for m in modelos(k, clase)]):
                veredicto, codigo = probar_modelo(k, modelo, clase, foto=foto if clase == "vision" else None)
                print(f"CADENA {k} {clase} {modelo}: "
                      + {"bien": "BIEN", "contesta_mal": "contesta, pero no lo pedido"}.get(veredicto, f"NO ({veredicto} {codigo})"),
                      flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["probar"]:
        probar()

