"""El Constructor de canales (Ciudad Central): levanta un canal de YouTube o una cuenta de TikTok/Instagram nueva con
toda la maquinaria. El dueño solo crea el canal (o la cuenta) y, si es de YouTube, pulsa «Permitir».

Cuando el dueño pide «crea otro canal», Claude deja la petición en el repositorio PRIVADO, en config/nuevos/<alias>.json:
    {"alias": "nuevo-1", "red": "youtube" | "tiktok" | "instagram" | "tiktok+instagram", "clave": "clave_corta",
     "nombre": "Nombre", "tema": "de qué va", "idioma": "es", "parecido_a": "clave de un canal o cuenta parecida (opcional)",
     "cuenta": "usuario de TikTok/Instagram (solo barrios)"}
y escribe peticiones/canal_nuevo.json ({"alias": "nuevo-1"}) en el público para que arranque constructor.yml. Aquí:
1. Con el cerebro de las ideas escribe la ficha: el tema afinado, la descripción con hashtags, las etiquetas, el estilo de
   dibujo, las búsquedas del nicho, los temas del Ojeador, las horas, 10 primeras ideas y los colores.
2. Crea su entrada en config/canales.json copiando lo técnico de la cuenta más parecida (voz, dibujos, formato…). Un canal
   de YouTube trabaja en cuanto tenga permiso; una cuenta de TikTok/Instagram queda en pausa hasta que el dueño vea su
   primera muestra (cada cuenta tiene el formato que acuerda con él).
3. Dibuja la foto de perfil (800×800) y el banner (2560×1440) y los guarda en la estantería «canales».
4. Si el canal de YouTube ya está conectado, le pone la descripción, las etiquetas y el banner (la foto la pone el dueño:
   YouTube no deja ponerla desde fuera).
Deja todo en estado/constructor/<alias>.json para la app, con los pasos que le tocan al dueño y a Claude.
Los registros públicos solo llevan el alias.

Uso:  python bots/central/constructor.py [--alias nuevo-1] [--prueba]
"""
import argparse
import json
import os
import re
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.comun import almacen, gemini, ia, privado  # noqa: E402

ROBOT = "constructor_canales"
ESTANTERIA = "canales"
NUEVOS = os.path.join("config", "nuevos")
REDES = {"youtube": ["youtube"], "tiktok": ["tiktok"], "instagram": ["instagram"],
         "tiktok+instagram": ["instagram", "tiktok"], "instagram+tiktok": ["instagram", "tiktok"]}
TECNICO = ("tipo", "voz", "dibujos", "velocidad", "tono", "formato_estudio", "estudio", "musica_estudio", "voz_estudio",
           "voz_estudio_nombre", "velocidad_estudio", "tono_estudio", "segundos", "nota_minima", "eleven_gratis",
           "cola_estudio", "hueco_estudio", "videoteca", "dibujos_estilo")

FICHA = """Eres el Constructor de canales de una fábrica de vídeos cortos. Hay que levantar {que} nuevo:
- Nombre: «{nombre}»
- De qué va (lo dice el dueño): {tema}
- Idioma de los vídeos: {idioma}
- Se parece a: {parecido}
Cuentas que ya tiene el dueño (para no pisarlas): {otras}

Devuelve SOLO un JSON:
{{"tema": "el tema afinado en una frase clara (como lo leerá el guionista)",
  "descripcion": "{desc}",
  "etiquetas": ["de 10 a 15 palabras clave que busca la gente, en {idioma}"],
  "estilo_dibujo": "cómo son los dibujos, en inglés, para el dibujante (estilo, luz, colores)",
  "busquedas": ["3 búsquedas del nicho en {idioma}"],
  "ojeador_temas": ["4 temas para mirar en TikTok e Instagram"],
  "categorias": ["1 o 2 de: Educación, Juegos, Sociedad, Drama, Animes y cómics, Animales, Comedia, Deportes"],
  "horas": ["de 1 a 3 horas de subida HH:MM, hora de España, cuando más ve ese público"],
  "ideas": ["10 primeras ideas de vídeo, cada una un título con gancho"],
  "colores": ["#RRGGBB fondo", "#RRGGBB acento"],
  "lema": "una frase corta para el banner, en {idioma}"}}"""


def peticiones(alias=None):
    carpeta = os.path.join(privado.carpeta(), NUEVOS)
    if not os.path.isdir(carpeta):
        return []
    hay = []
    for f in sorted(os.listdir(carpeta)):
        if f.endswith(".json") and (not alias or f == f"{alias}.json"):
            try:
                p = json.load(open(os.path.join(carpeta, f), encoding="utf-8"))
            except ValueError:
                continue
            if isinstance(p, dict):
                hay.append(dict(p, alias=p.get("alias") or f[:-5]))
    return hay


def clave_de(p):
    c = re.sub(r"[^a-z0-9._]+", "", str(p.get("clave") or p.get("cuenta") or p.get("nombre") or "").lower())
    return c[:30] or p["alias"].replace("-", "")


def parecido(p, cfg, red):
    """La cuenta más parecida, para copiar lo técnico: la que diga la petición o una de la misma red."""
    todas = dict(cfg.get("canales", {}), **cfg.get("barrios", {}))
    if p.get("parecido_a") in todas:
        return p["parecido_a"], todas[p["parecido_a"]]
    grupo = cfg.get("canales", {}) if red == ["youtube"] else cfg.get("barrios", {})
    activos = [(k, v) for k, v in grupo.items() if not v.get("pausado") and v.get("estado", "activo") == "activo"]
    return (activos or list(grupo.items()) or [(None, {})])[0]


def ficha(p, cfg, red, base_clave):
    idioma = {"es": "español de España", "nl": "neerlandés", "en": "inglés"}.get(str(p.get("idioma") or "es")[:2], "español")
    youtube = red == ["youtube"]
    desc = ("la descripción del canal de YouTube: 2 o 3 frases con gancho que digan qué encontrará quien lo siga y cada "
            "cuánto, y al final de 3 a 5 hashtags (el primero #shorts)") if youtube else \
        "la biografía de la cuenta: como mucho 150 caracteres, con 1 o 2 emojis"
    otras = ", ".join(f"{v.get('nombre', k)} ({(v.get('tema') or '')[:60]})"
                      for k, v in list(cfg.get("canales", {}).items()) + list(cfg.get("barrios", {}).items()))
    texto = FICHA.format(que="un canal de YouTube Shorts" if youtube else "una cuenta de " + " e ".join(red),
                         nombre=p.get("nombre", ""), tema=p.get("tema", ""), idioma=idioma, parecido=base_clave or "nada",
                         otras=otras[:1500] or "ninguna", desc=desc)
    f = ia.preguntar(texto, papel="ideas", temperatura=0.7)
    if isinstance(f, list) and f:
        f = f[0]
    if not isinstance(f, dict) or not f.get("tema"):
        raise gemini.SinIA("la ficha no ha salido con la forma pedida")
    return f


def _hora(h):
    m = re.fullmatch(r"(\d{2}):(\d{2})", str(h))
    return bool(m) and int(m.group(1)) < 24 and int(m.group(2)) < 60


def _color(x, defecto):
    return x if isinstance(x, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", x) else defecto


def imagenes(nombre, lema, colores, carpeta):
    """Foto de perfil (800×800) y banner (2560×1440, lo importante en el centro, que es lo que se ve en el móvil)."""
    from PIL import Image, ImageDraw, ImageFilter
    import portada
    colores = list(colores or [])
    fondo = _color(colores[0] if colores else None, "#141A33")
    acento = _color(colores[1] if len(colores) > 1 else None, "#FFC93C")

    def rgb(c):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

    def degradado(w, h):
        claro = tuple(min(255, int(x * 1.6) + 12) for x in rgb(fondo))          # arriba, un poco más claro
        img = Image.composite(Image.new("RGB", (w, h), fondo), Image.new("RGB", (w, h), claro),
                              Image.linear_gradient("L").resize((w, h)))
        mascara = Image.new("L", (w, h), 0)                                       # una luz suave detrás del texto
        r = min(w, h) * 0.38
        ImageDraw.Draw(mascara).ellipse((w / 2 - r * 1.7, h / 2 - r, w / 2 + r * 1.7, h / 2 + r), fill=55)
        return Image.composite(Image.new("RGB", (w, h), acento), img, mascara.filter(ImageFilter.GaussianBlur(min(w, h) // 7)))

    def texto(img, frase, caja, tam_max, color="#FFFFFF"):
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = caja
        tam = tam_max
        while tam > 20:
            f = portada.fuente(None, tam)
            ancho = d.textlength(frase, font=f)
            if ancho <= x1 - x0:
                break
            tam -= 4
        f = portada.fuente(None, tam)
        ancho, alto = d.textlength(frase, font=f), tam
        d.text(((x0 + x1 - ancho) / 2, (y0 + y1 - alto) / 2), frase, font=f, fill=color,
               stroke_width=max(2, tam // 14), stroke_fill="#000000")

    iniciales = "".join(w[0] for w in re.findall(r"\w+", nombre)[:2]).upper() or "?"
    foto = degradado(800, 800)
    ImageDraw.Draw(foto).ellipse((70, 70, 730, 730), outline=acento, width=18)
    texto(foto, iniciales, (130, 150, 670, 650), 380)
    banner = degradado(2560, 1440)
    texto(banner, nombre, (560, 560, 2000, 760), 190)
    if lema:
        texto(banner, lema, (560, 780, 2000, 880), 80, color=acento)
    rutas = {"foto": os.path.join(carpeta, "foto.png"), "banner": os.path.join(carpeta, "banner.png")}
    foto.save(rutas["foto"])
    banner.save(rutas["banner"])
    return rutas


def a_youtube(clave, f, banner):
    """Pone descripción, etiquetas y banner en el canal si ya está conectado. Devuelve lo que ha hecho."""
    refresh = os.environ.get("YT_REFRESH_" + clave.upper())
    if not (refresh and os.environ.get("YT_CLIENT_ID") and os.environ.get("YT_CLIENT_SECRET")):
        return {"conectado": False}
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    cred = Credentials(None, refresh_token=refresh, client_id=os.environ["YT_CLIENT_ID"],
                       client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
    yt = build("youtube", "v3", credentials=cred, cache_discovery=False)
    mios = yt.channels().list(part="brandingSettings", mine=True).execute().get("items", [])
    esperado = os.environ.get("YT_ID_" + clave.upper())
    if not mios or (esperado and mios[0]["id"] != esperado):
        return {"conectado": True, "hecho": False, "motivo": "el permiso es de otro canal"}
    canal = mios[0]
    marca = canal.get("brandingSettings") or {}
    marca.setdefault("channel", {})
    marca["channel"]["description"] = str(f.get("descripcion") or "")[:1000]
    marca["channel"]["keywords"] = " ".join(f'"{e}"' if " " in e else e for e in (f.get("etiquetas") or [])[:15])[:500]
    hecho = {"conectado": True, "descripcion": True}
    try:
        subida = yt.channelBanners().insert(media_body=MediaFileUpload(banner, mimetype="image/png")).execute()
        marca.setdefault("image", {})["bannerExternalUrl"] = subida["url"]
        hecho["banner"] = True
    except Exception as e:                    # sin banner no pasa nada: la descripción va igual
        hecho["banner"] = False
        hecho["motivo_banner"] = type(e).__name__
    yt.channels().update(part="brandingSettings", body={"id": canal["id"], "brandingSettings": marca}).execute()
    return hecho


def construir(p, prueba=False, paso=print):
    cfg = privado.config()
    red = REDES.get(str(p.get("red") or "youtube").lower().replace(" ", ""), ["youtube"])
    youtube = red == ["youtube"]
    clave = clave_de(p)
    ya = privado.leer(os.path.join("estado", "constructor", f"{p['alias']}.json"), {}) or {}
    base_clave, base = parecido(p, cfg, red)
    paso(f"constructor: {p['alias']}: ficha nueva (copia lo técnico de {privado.alias(base_clave) if base_clave else 'nada'})")
    f = ya.get("ficha") or ficha(p, cfg, red, base_clave)
    entrada = {k: v for k, v in (base or {}).items() if k in TECNICO}
    entrada.update({"nombre": p.get("nombre") or clave, "tema": f["tema"], "estilo_dibujo": f.get("estilo_dibujo", ""),
                    "busqueda": (f.get("busquedas") or [p.get("nombre", "")])[0],
                    "nicho": {"busquedas": (f.get("busquedas") or [])[:3], "idioma": str(p.get("idioma") or "es")[:2],
                              "cada": 3},
                    "ojeador": {"categorias": (f.get("categorias") or ["Educación"])[:2],
                                "temas": (f.get("ojeador_temas") or [])[:4]},
                    "idioma": p.get("idioma") or "es", "construido": privado.ahora(), "constructor": p["alias"]})
    horas = [h for h in f.get("horas") or [] if _hora(h)][:3]
    if youtube:
        entrada["horas"] = horas or base.get("horas") or ["20:00"]
        entrada["descripcion"] = f.get("descripcion", "")
        entrada["etiquetas"] = (f.get("etiquetas") or [])[:15]
    else:
        entrada.update(redes=red, red=red[0], cuenta=p.get("cuenta") or clave, hora=(horas or [base.get("hora") or "19:00"])[0],
                       estado="en_pausa", motivo="Recién construida: falta que el dueño vea y apruebe su primera muestra.")
    pasos_dueno, pasos_claude = [], []
    with tempfile.TemporaryDirectory() as t:
        rutas = imagenes(entrada["nombre"], f.get("lema", ""), f.get("colores") or [], t)
        guardadas = {}
        if not prueba:                       # copia pequeña en el repositorio privado: el Comisario la sube a la app
            from PIL import Image
            carpeta_app = os.path.join(privado.carpeta(), "estado", "constructor", p["alias"])
            os.makedirs(carpeta_app, exist_ok=True)
            Image.open(rutas["foto"]).convert("RGB").save(os.path.join(carpeta_app, "foto.jpg"), quality=90)
            Image.open(rutas["banner"]).convert("RGB").save(os.path.join(carpeta_app, "banner.jpg"), quality=88)
            for que, ruta in rutas.items():
                nombre = f"{p['alias']}-{que}.png"
                try:
                    almacen.guardar(ESTANTERIA, ruta, nombre)
                    guardadas[que] = nombre
                except Exception as e:
                    paso(f"constructor: no he podido guardar la {que} ({type(e).__name__})")
        else:
            guardadas = {que: os.path.basename(r) for que, r in rutas.items()}
        yt = a_youtube(clave, f, rutas["banner"]) if youtube and not prueba else {"conectado": False}
    if youtube and not yt.get("conectado"):
        pasos_dueno = [f"Crea el canal «{entrada['nombre']}» en YouTube (con tu cuenta de Google de siempre).",
                       "Dime «ya está» y te doy el código para conectarlo (google.com/device → «Permitir»).",
                       "Pon la foto de perfil que te dejo en la app (YouTube no deja ponerla desde fuera)."]
        pasos_claude = [f"Cuando el dueño lo cree: conectarlo (peticiones/conectar.json, clave «{clave}»), y añadir "
                        f"YT_REFRESH_{clave.upper()} e YT_ID_{clave.upper()} a fabrica.yml, revisar-canales.yml y "
                        "constructor.yml. Después relanzar el Constructor para que ponga la descripción y el banner."]
    elif not youtube:
        pasos_dueno = [f"Crea la cuenta en {' y '.join(r.capitalize() for r in red)} con el nombre «{entrada['nombre']}», "
                       "pon la foto y la biografía que te dejo en la app.",
                       "Mira la primera muestra y dime si te gusta: entonces empieza a dejarte vídeos en «Para subir»."]
    destino = "canales" if youtube else "barrios"
    if not prueba:
        ruta_cfg = os.path.join(privado.carpeta(), "config", "canales.json")
        todo = json.load(open(ruta_cfg, encoding="utf-8"))
        anterior = todo.setdefault(destino, {}).get(clave, {})
        todo[destino][clave] = dict(anterior, **entrada) if anterior else entrada
        with open(ruta_cfg, "w", encoding="utf-8") as fh:
            json.dump(todo, fh, ensure_ascii=False, indent=1)
    resultado = {"alias": p["alias"], "clave": clave, "red": red, "nombre": entrada["nombre"], "donde": destino,
                 "estado": "listo" if (youtube and yt.get("descripcion")) else "construido", "ficha": f,
                 "imagenes": guardadas, "youtube": yt, "pasos_dueno": pasos_dueno, "pasos_claude": pasos_claude,
                 "parecido_a": base_clave, "prueba": prueba}
    if not prueba:
        privado.guardar_estado(os.path.join("constructor", f"{p['alias']}.json"), resultado)
        c = privado.cuaderno(ROBOT)
        c.apuntar("canal_construido", {"alias": p["alias"], "red": red, "estado": resultado["estado"]})
        c.guardar()
    return resultado


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--alias")
    p.add_argument("--prueba", action="store_true", help="hace la ficha y las imágenes, pero no guarda nada")
    a = p.parse_args()
    lista = peticiones(a.alias)
    if not lista:
        print("constructor: no hay canales nuevos que construir")
        return 0
    codigo = 0
    for pet in lista:
        ya = privado.leer(os.path.join("estado", "constructor", f"{pet['alias']}.json"), {}) or {}
        if ya.get("estado") == "listo" and not a.alias:
            continue
        try:
            r = construir(pet, prueba=a.prueba, paso=lambda t: print(privado.limpiar(t), flush=True))
            print(f"constructor: {pet['alias']}: {r['estado']}", flush=True)
        except gemini.SinIA as e:
            print(f"constructor: {pet['alias']}: la IA no contesta ahora ({str(e)[:60]}); se intenta luego", flush=True)
            codigo = 1
    return codigo


if __name__ == "__main__":
    sys.exit(main())
