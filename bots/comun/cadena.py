"""La cadena de IA gratis: cuando Gemini no contesta (sin cupo o saturado), la fábrica salta al siguiente servicio
gratis, y de ese al siguiente, para tener con qué pensar las 24 horas (lo pidió el dueño: «que salte a la otra, y de
esta a la otra»). gemini.preguntar() la llama sola cuando Gemini falla: nadie más tiene que saber que existe.

- Cada servicio se enciende solo cuando su llave está en los secretos de GitHub (una cuenta por servicio; nada de
  multiplicar cuentas). Sin llave, ese eslabón no existe y la cadena sigue con los demás.
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
import time
import urllib.error
import urllib.request

AGENTE = "ciudades-bot/1.0"
ESTADO = os.path.join("estado", "cadena.json")
TOPE_SEGUNDOS = 240            # una pregunta no pasa de esto recorriendo la cadena
ESPERA_CORTA = 20              # si un servicio pide esperar menos que esto (límite por minuto), se espera y se repite
MAX_SALIDA = 8000              # tokens de respuesta que se piden como mucho

# Cada servicio: su secreto (la llave), su dirección y sus modelos gratis. «texto» y «vision» van por orden de
# preferencia dentro del servicio. Todos hablan el formato «chat/completions». Lo que puede cada uno:
#   max_imagenes   cuántas imágenes admite por pregunta (si llegan más, se juntan en mosaicos numerados)
#   tokens_minuto  su tope de tokens por minuto: una pregunta que no cabe se la salta sin llamarle
#   tokens_imagen  lo que le cuenta cada imagen
#   max_salida     tokens de respuesta que se le piden
#   cupo_comun     todos sus modelos gastan del mismo cupo del día
#   cuenta         secreto con el número de cuenta que va dentro de la dirección
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
    },
}
# El orden. Texto: Groq para lo pequeño (lo grande no le cabe y se lo salta solo), OpenRouter para lo grande (no tiene
# tope por minuto) y Cloudflare. Imágenes: Groq (su cupo de imágenes es aparte), Cloudflare y, lo último, OpenRouter,
# porque sus 50 preguntas al día rinden más en guiones.
ORDEN_TEXTO = ["groq", "openrouter", "cloudflare"]
ORDEN_VISION = ["groq", "cloudflare", "openrouter"]

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


def encendidos():
    """Los servicios que tienen su llave puesta (los que de verdad forman la cadena ahora)."""
    apagados = set(_ajustes().get("apagados") or [])
    return [k for k, s in SERVICIOS.items() if os.environ.get(s["secreto"]) and k not in apagados
            and (not s.get("cuenta") or os.environ.get(s["cuenta"]))]


def _url(s):
    return s["url"].replace("{cuenta}", os.environ.get(s.get("cuenta") or "", "")).rstrip("/")


def eslabones(vision=False):
    """[(servicio, modelo)] por orden de la cadena, sin los que hoy ya han dicho que no les queda cupo."""
    a = _ajustes()
    orden = a.get("orden_vision" if vision else "orden_texto") or (ORDEN_VISION if vision else ORDEN_TEXTO)
    vivos = encendidos()
    orden = [k for k in orden if k in vivos] + [k for k in vivos if k not in orden]
    agotados = (_estado().get("agotados") or {})
    ahora, iso = time.time(), _ahora().strftime("%Y-%m-%dT%H:%M:%SZ")
    salida = []
    for k in orden:
        for modelo in SERVICIOS[k].get("vision" if vision else "texto") or []:
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


def _cabe(servicio, texto, n_imagenes):
    """¿Le cabe la pregunta a ese servicio en su tope de tokens por minuto? (Cuenta por lo alto: más vale saltárselo.)"""
    s = SERVICIOS[servicio]
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
    if json_salida and modelo not in (s.get("sin_json") or ()):
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
    for servicio, modelo in lista:
        s = SERVICIOS[servicio]
        if APAGADOS.get((servicio, "*"), 0) > time.time():
            continue
        if not _cabe(servicio, texto, len(imagenes)):            # no le cabe en su tope por minuto: ni se le llama
            ultimo = f"{servicio}: la pregunta no le cabe"
            continue
        sencillo = False
        for intento in (1, 2, 3):
            if time.monotonic() - empezo > tope:
                raise SinCadena(f"la cadena no contesta a tiempo: {ultimo}")
            try:
                cuerpo = _cuerpo(servicio, modelo, texto, imagenes, json_salida, temperatura, sencillo=sencillo)
            except Exception as e:                               # una imagen que no se puede abrir, p. ej.
                ultimo = f"{servicio}: no he podido preparar la pregunta ({type(e).__name__})"
                break
            req = urllib.request.Request(
                _url(s) + "/chat/completions", method="POST", data=json.dumps(cuerpo).encode(),
                headers=dict({"Content-Type": "application/json", "User-Agent": AGENTE,
                              "Authorization": "Bearer " + os.environ[s["secreto"]]}, **(s.get("cabeceras") or {})))
            try:
                with urllib.request.urlopen(req, timeout=150) as r:
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
                    hasta = _hasta_manana() if (del_dia or espera is None or espera > 3600) else \
                        _ahora() + dt.timedelta(seconds=max(60, espera))
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


def probar():
    """La prueba de la cadena (turno «Probar la cadena»): qué servicios tienen llave, qué modelos del catálogo existen y
    si contestan. Solo enseña nombres de servicio y de modelo y el código de respuesta: nunca llaves ni textos."""
    vivos = encendidos()
    print("CADENA con llave:", ", ".join(vivos) or "ninguno", flush=True)
    print("CADENA sin llave:", ", ".join(k for k in SERVICIOS if k not in vivos) or "ninguno", flush=True)
    foto = os.path.join(os.environ.get("RUNNER_TEMP") or ".", "prueba_cadena.jpg")
    try:
        from PIL import Image
        Image.new("RGB", (96, 96), (220, 20, 20)).save(foto, "JPEG")
    except Exception:
        foto = None
    FORMA = {"groq": "gsk_", "openrouter": "sk-or-"}
    for k in vivos:
        s = SERVICIOS[k]
        llave = os.environ[s["secreto"]]
        cuenta = os.environ.get(s.get("cuenta") or "", "")
        print(f"CADENA {k} llave: mide {len(llave)}"
              + (f", {'empieza' if llave.strip().startswith(FORMA[k]) else 'NO empieza'} por {FORMA[k]}" if k in FORMA else "")
              + (", lleva espacios o saltos de línea" if llave != llave.strip() or " " in llave else "")
              + (f"; el número de cuenta mide {len(cuenta)} (tiene que medir 32)"
                 + ("" if re.fullmatch(r"[0-9a-f]{32}", cuenta.strip()) else " y NO tiene forma de número de cuenta")
                 if s.get("cuenta") else ""), flush=True)
        try:                                        # qué dice el servicio de la llave (sin enseñarla)
            req = urllib.request.Request(_url(s) + "/chat/completions", method="POST",
                                         data=json.dumps(_cuerpo(k, (s.get("texto") or [""])[0], "Di hola", (), False, 0.5)).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": AGENTE,
                                                  "Authorization": "Bearer " + llave.strip()})
            with urllib.request.urlopen(req, timeout=60):
                print(f"CADENA {k} llave: vale", flush=True)
        except urllib.error.HTTPError as e:
            texto = e.read().decode("utf-8", "replace")[:260].replace(llave.strip(), "***").replace(cuenta.strip() or "§", "***")
            print(f"CADENA {k} dice {e.code}: {' '.join(texto.split())}", flush=True)
        except Exception as e:
            print(f"CADENA {k}: no contesta ({type(e).__name__})", flush=True)
        try:                                        # qué modelos ofrece hoy (para corregir el catálogo si cambian)
            req = urllib.request.Request(_url(s) + "/models", headers={
                "User-Agent": AGENTE, "Authorization": "Bearer " + os.environ[s["secreto"]]})
            with urllib.request.urlopen(req, timeout=60) as r:
                lista = json.load(r)
            ids = [str(m.get("id") or m.get("name")) for m in (lista.get("data") or lista.get("result") or [])]
            gratis = [i for i in ids if ":free" in i] if k == "openrouter" else ids
            print(f"CADENA {k}: ofrece {len(ids)} modelos; del catálogo faltan: "
                  + (", ".join(m for m in s.get("texto", []) + s.get("vision", []) if m not in ids) or "ninguno"), flush=True)
            print(f"CADENA {k} lista: " + ", ".join(sorted(gratis)[:60]), flush=True)
        except Exception as e:
            print(f"CADENA {k}: no deja ver su lista ({type(e).__name__} {getattr(e, 'code', '')})", flush=True)
        for clase, modelos in (("texto", s.get("texto") or []), ("vision", s.get("vision") or [])):
            for modelo in modelos:
                ORDEN = (k, modelo)
                copia = (dict(SERVICIOS), list(ORDEN_TEXTO), list(ORDEN_VISION))
                try:
                    SERVICIOS.clear()
                    SERVICIOS[k] = dict(s, texto=[modelo] if clase == "texto" else [], vision=[modelo] if clase == "vision" else [])
                    APAGADOS.clear()
                    r, _ = preguntar('Contesta solo con JSON: {"color": "el color que ves, o ninguno"}',
                                     imagenes=[foto] if clase == "vision" and foto else (), vision=clase == "vision", tope=90)
                    bien = isinstance(r, dict) and (clase == "texto" or "roj" in str(r).lower() or "red" in str(r).lower())
                    print(f"CADENA {ORDEN[0]} {clase} {ORDEN[1]}: {'BIEN' if bien else 'contesta, pero no lo pedido'}", flush=True)
                except SinCadena as e:
                    print(f"CADENA {ORDEN[0]} {clase} {ORDEN[1]}: NO ({str(e).split(': ', 1)[-1][:60]})", flush=True)
                finally:
                    SERVICIOS.clear()
                    SERVICIOS.update(copia[0])


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["probar"]:
        probar()

