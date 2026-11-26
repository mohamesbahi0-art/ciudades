"""El Montador de clips: convierte los clips con licencia libre (Creative Commons «CC BY») en Shorts. Esa licencia deja
reutilizar el vídeo de otro creador siempre que se diga de quién es: su nombre y el enlace van en la descripción, y nada
más. Del creador no se ve ni se oye NADA (ni su cara, ni su webcam, ni su nombre, logo o marca de agua, ni su voz): solo
el juego.

El Buscador de clips (buscador_clips.py) elige los momentos que de verdad se harían virales (90 o más) y donde no sale
nada del creador, y los deja en estado/clips/para_grabar.json. YouTube no deja descargar desde los servidores (y eso no
se salta), así que el dueño graba ese trozo con el móvil y lo sube en la app. La ronda del Comisario lo deja en una rama
temporal del repositorio privado (`buzon/<codigo>`, con solo ese archivo: así no entra en el historial) y marca el momento
como «grabado» (las sesiones de Claude no pueden escribir en las estanterías de vídeos; la fábrica sí, y borra la rama en
cuanto el clip se usa o se descarta). Entonces, en el turno de su canal:

1. El Portero de clips mira la grabación: quita las bandas negras, recorta lo que no sea juego (algo del creador, del
   móvil o de YouTube en un borde) y, si se oye al creador o no está seguro, quita el sonido del clip y pone música
   propia. Si el creador sale en medio y no se puede recortar, el clip se descarta.
2. El Escritor escribe una narración corta mirando unas fotos del clip (gancho, qué pasa, por qué es una locura y una
   pregunta), sin nombrar al creador.
3. El Jurado popular la vota antes de grabar la voz (como todos los guiones).
4. El Locutor pone la voz y el Montador monta el Short: el clip en el centro sobre un fondo difuminado del propio clip,
   el gancho arriba y subtítulos palabra a palabra.
5. Después, como cualquier vídeo: Juzgado Mayor (90 o más), Coliseo y subida. La descripción lleva siempre el crédito
   con el enlace al vídeo original, aunque el Coliseo cambie el texto.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

from bots.comun import almacen, gemini, ia, privado

ESTANTERIA = "buzon-clips"
VIDEOTECA = "videoteca"            # las tomas ya limpias por el Portero (videoteca.py), para reutilizarlas
LISTA = os.path.join("estado", "clips", "para_grabar.json")
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
INTENTOS = 2                       # si el Juzgado lo suspende dos veces, ese clip se deja
ORDEN = {"por_grabar": 0, "grabado": 1, "usado": 2, "descartado": 2}    # para juntar dos versiones (privado.fusionar)
REGLA = ("Este vídeo usa un clip con licencia CC BY de otro creador: su crédito va en la descripción. Si en las imágenes "
         "se ve su cara, su webcam, su nombre, su logo o su marca de agua, o cosas del móvil o de YouTube (barra de "
         "estado, botones, barra de progreso), es un fallo grave.")

GUION = """Eres el Escritor del canal de YouTube Shorts «{nombre}» ({tema}). Vas a narrar un clip de GTA. El clip dura
unos {segundos} segundos y en él pasa esto: {que_pasa}
Por qué engancha: {por_que}
Gancho propuesto: {gancho}
{fotos}Escribe un guion CORTO para una voz que lo narra encima del clip, en {idioma}: la primera frase engancha en 2
segundos; después explica qué se ve y por qué es una locura; termina con una pregunta que invite a comentar. Entre 30 y
70 palabras (que dure más o menos lo que el clip). No digas «en este clip» y no nombres a nadie: el crédito del creador ya
va aparte en la descripción. Sin miedo, pero sin inventar nada que no se vea.
{lecciones}
Devuelve SOLO un JSON: {{"titulo": "título con gancho, 1 o 2 emojis, acabado en #shorts",
"texto_pantalla": "de 2 a 5 palabras para los 2 primeros segundos", "narracion": "lo que dice la voz",
"descripcion": "2 o 3 frases", "hashtags": ["#gta6", "..."]}}"""

PORTERO = """Eres el Portero de clips de una fábrica de Shorts. Este clip es un trozo de un vídeo de GTA de otro creador,
con licencia libre (CC BY): se puede usar diciendo de quién es en la descripción, pero el dueño NO quiere que se vea ni se
oiga NADA del creador: ni su cara, ni su webcam, ni su nombre, logo o marca de agua, ni sus textos, flechas o animaciones
(suscríbete, redes), ni su voz. Solo el juego. Además, el dueño lo ha grabado con el móvil, así que puede salir algo del
móvil o de YouTube (barra de estado, botones, barra de progreso, avisos): eso tampoco puede salir.
Mira {que_ves} y contesta:
- "limpio": true si en todo el clip solo se ve el juego.
- "recorte": si hay algo que quitar y está pegado a un borde o a una esquina, el rectángulo que deja SOLO el juego, en
  fracciones de la imagen (x, y, ancho y alto, de 0 a 1; por ejemplo {{"x": 0, "y": 0, "ancho": 0.72, "alto": 1}}).
  null si no hace falta recortar o si no se puede.
- "vale": false si algo del creador sale en el centro o en casi todo el clip y no se puede quitar recortando.
- "habla_creador": {habla}
- "problemas": lista corta de lo que has visto que no es juego (vacía si nada).
- "que_se_ve": una frase con lo que pasa en el clip.
Devuelve SOLO un JSON: {{"limpio": true, "recorte": null, "vale": true, "habla_creador": false, "problemas": [],
"que_se_ve": "..."}}"""


def momentos():
    return (privado.leer(LISTA, {}) or {}).get("momentos") or []


def _nota(m):
    try:
        return float(m.get("nota") or 0)
    except (TypeError, ValueError):
        return 0.0


def listo_para(clave):
    """El mejor momento grabado y con su archivo en el buzón para este canal (o None)."""
    for m in sorted(momentos(), key=lambda x: -_nota(x)):
        if m.get("para") == clave and m.get("estado") == "grabado" and m.get("archivo"):
            return m
    return None


def canales_con_clips():
    return {m.get("para") for m in momentos() if m.get("estado") == "grabado" and m.get("archivo")}


def marcar(codigo, **cambios):
    datos = privado.leer(LISTA, {}) or {}
    for m in datos.get("momentos") or []:
        if m.get("codigo") == codigo:
            m.update({k: v for k, v in cambios.items() if v is not None})
    datos.pop("actualizado", None)
    privado.guardar_estado("clips/para_grabar.json", dict(datos, momentos=datos.get("momentos") or []))


def texto_licencia(licencia):
    return "dominio público (CC0)" if str(licencia or "").upper().startswith("CC0") else "licencia Creative Commons (CC BY)"


def credito(m):
    return f"🎬 Clip: {m.get('creador', '?')} · {m.get('enlace') or ''} · {texto_licencia(m.get('licencia'))}".strip()


def añadir(momento):
    """Un momento nuevo en la lista (los que trae solo el Recolector entran ya «grabado» y en la videoteca)."""
    datos = privado.leer(LISTA, {}) or {}
    lista = [m for m in datos.get("momentos") or [] if m.get("codigo") != momento.get("codigo")] + [momento]
    datos.pop("actualizado", None)
    privado.guardar_estado("clips/para_grabar.json", dict(datos, momentos=lista))


def _segundos(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ruta],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _tiene_audio(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                        ruta], capture_output=True, text=True)
    return bool(r.stdout.strip())


def _area(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", ruta], capture_output=True, text=True)
    try:
        ancho, alto = (int(x) for x in r.stdout.strip().split(",")[:2])
        return ancho * alto
    except ValueError:
        return 0


def _git(*args, **kw):
    return subprocess.run(["git", "-C", privado.carpeta(), *args], capture_output=True, **kw)


def _de_la_rama(rama, archivo, destino):
    """Saca el clip de su rama temporal (buzon/<codigo>) del repositorio privado."""
    if _git("fetch", "-q", "--depth", "1", "origin", f"refs/heads/{rama}").returncode != 0:
        return False
    r = _git("show", f"FETCH_HEAD:{archivo}")
    if r.returncode != 0 or not r.stdout:
        return False
    with open(destino, "wb") as f:
        f.write(r.stdout)
    return True


def bajar(m, carpeta):
    """El clip grabado: ya limpio de la videoteca, de su rama temporal o de la estantería «buzon-clips»."""
    os.makedirs(carpeta, exist_ok=True)
    if m.get("en_videoteca"):
        nombre = f"{m['codigo']}.mp4"
        try:
            almacen.bajar(VIDEOTECA, nombre, carpeta)
        except Exception:
            pass
        ruta = os.path.join(carpeta, nombre)
        if os.path.exists(ruta) and _segundos(ruta) >= 2:
            return ruta
    ruta = os.path.join(carpeta, m["archivo"])
    if not (m.get("rama") and _de_la_rama(m["rama"], m["archivo"], ruta)):
        try:
            almacen.bajar(ESTANTERIA, m["archivo"], carpeta)
        except Exception:
            pass
    if not os.path.exists(ruta) or _segundos(ruta) < 2:
        raise RuntimeError(f"el clip {m.get('codigo')} no está en el buzón o está vacío")
    return cortar(ruta, m.get("corte"))


def cortar(ruta, corte):
    """Si el móvil no pudo recortar la grabación, la app la sube entera con «corte» {desde, hasta} (segundos de ese
    archivo): aquí se queda solo ese trozo."""
    try:
        desde, hasta = float((corte or {})["desde"]), float((corte or {})["hasta"])
    except (KeyError, TypeError, ValueError):
        return ruta
    total = _segundos(ruta)
    desde, hasta = max(0.0, desde), min(hasta, total) if total else hasta
    if hasta - desde < 2 or (desde < 0.1 and total and hasta > total - 0.1):
        return ruta
    salida = os.path.join(os.path.dirname(ruta), "cortado-" + os.path.splitext(os.path.basename(ruta))[0] + ".mp4")
    args = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{desde:.2f}", "-i", ruta, "-t", f"{hasta - desde:.2f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-b:a", "128k"] if _tiene_audio(ruta) else ["-an"]
    subprocess.run(args + [salida], check=True)
    return salida


def soltar_rama(m):
    """Borra la rama temporal del clip (cuando ya se ha usado o descartado). Solo puede la fábrica de GitHub."""
    if m.get("rama"):
        return _git("push", "-q", "origin", "--delete", m["rama"]).returncode == 0
    return False


def limpiar_ramas():
    """Borra las ramas buzon/<codigo> de clips ya usados o descartados (y las que no son de ningún clip)."""
    r = _git("ls-remote", "origin", "refs/heads/buzon/*", text=True)
    if r.returncode != 0:
        return 0
    vivos = {m.get("rama") for m in momentos() if m.get("estado") == "grabado" and m.get("rama")}
    borradas = 0
    for linea in r.stdout.splitlines():
        rama = linea.split("refs/heads/", 1)[-1].strip()
        if rama and rama not in vivos and _git("push", "-q", "origin", "--delete", rama).returncode == 0:
            borradas += 1
    return borradas


def bandas(clip):
    """Las bandas negras de la grabación del móvil: devuelve el recorte «ancho:alto:x:y» que las quita, o None."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", clip, "-vf", "cropdetect=limit=24:round=2:reset=0",
                        "-frames:v", "300", "-f", "null", "-"], capture_output=True, text=True)
    hallados = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
    if not hallados:
        return None
    w, h, x, y = (int(v) for v in hallados[-1])
    area = _area(clip)
    if not area or w * h >= 0.97 * area or w * h < 0.35 * area:
        return None              # no hay bandas (o el detector se ha liado con una escena oscura)
    return f"{w}:{h}:{x}:{y}"


def _esquinas(pila):
    """Del montón de fotos (en gris), lo que se queda quieto y con bordes en cada esquina: devuelve el rectángulo que se
    puede quedar (x0, y0, x1, y1 en píxeles) o None si no hay nada que quitar."""
    import numpy as np
    quieto = pila.std(axis=0) < 6
    if quieto.mean() > 0.6:              # la cámara apenas se mueve: no se puede distinguir un rótulo del juego
        return None
    media = pila.mean(axis=0)
    bordes = (np.abs(np.diff(media, axis=1, prepend=media[:, :1])) + np.abs(np.diff(media, axis=0, prepend=media[:1, :]))) > 18
    marca = quieto & bordes
    alto, ancho = marca.shape
    zh, zw, margen = int(alto * 0.25), int(ancho * 0.4), 4
    x0, y0, x1, y1 = 0, 0, ancho, alto
    for arriba in (True, False):
        for izquierda in (True, False):
            ys = slice(0, zh) if arriba else slice(alto - zh, alto)
            xs = slice(0, zw) if izquierda else slice(ancho - zw, ancho)
            zona = marca[ys, xs]
            if zona.sum() < 20:
                continue
            yy, xx = np.nonzero(zona)
            top, bot = int(yy.min()) + ys.start, int(yy.max()) + ys.start
            izq, der = int(xx.min()) + xs.start, int(xx.max()) + xs.start
            caja_al, caja_an = bot - top + 1, der - izq + 1
            # un logo o un rótulo es compacto (o una franja de texto): una raya del propio juego no se toca
            if (min(caja_al, caja_an) < 6 or (caja_al > alto * 0.2 and caja_an > ancho * 0.2)
                    or zona.sum() / (caja_al * caja_an) < 0.06):
                continue
            pierde_h = (bot + margen) if arriba else (alto - top + margen)       # quitar una franja de arriba/abajo
            pierde_v = (der + margen) if izquierda else (ancho - izq + margen)   # o una de un lado
            if pierde_h / alto <= pierde_v / ancho:
                if arriba:
                    y0 = max(y0, bot + margen)
                else:
                    y1 = min(y1, top - margen)
            elif izquierda:
                x0 = max(x0, der + margen)
            else:
                x1 = min(x1, izq - margen)
    return None if (x0, y0, x1, y1) == (0, 0, ancho, alto) else (x0, y0, x1, y1)


def marcas(clip, previo="", n=18):
    """Busca lo que se queda QUIETO pegado a una esquina mientras el juego se mueve: logos, marcas de agua, nombres o
    rótulos del creador (aunque solo salgan un rato). Devuelve el recorte que lo quita (fracciones de la imagen, después
    de `previo`) o None. No depende de la IA: la IA a veces no ve un logo pequeño."""
    import numpy as np
    from PIL import Image
    total = _segundos(clip)
    tmp = tempfile.mkdtemp()
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-vf",
                        f"{previo}fps={n / max(total, 1.0):.4f},scale=320:180,format=gray",
                        os.path.join(tmp, "f%03d.png")], check=True, capture_output=True)
        fotos = [np.asarray(Image.open(os.path.join(tmp, f)), dtype=np.float32) for f in sorted(os.listdir(tmp))]
    except (subprocess.CalledProcessError, OSError):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(fotos) < 6:
        return None
    pila = np.stack(fotos)
    alto, ancho = pila.shape[1:]
    cajas = [_esquinas(pila)]                     # lo que está todo el clip...
    tramo = max(5, len(fotos) // 3)
    for i in range(0, len(fotos) - tramo + 1, tramo):   # ...y lo que sale solo un rato (un rótulo de capítulo)
        cajas.append(_esquinas(pila[i:i + tramo]))
    cajas = [c for c in cajas if c]
    if not cajas:
        return None
    x0, y0 = max(c[0] for c in cajas), max(c[1] for c in cajas)
    x1, y1 = min(c[2] for c in cajas), min(c[3] for c in cajas)
    return {"x": x0 / ancho, "y": y0 / alto, "ancho": max(0, x1 - x0) / ancho, "alto": max(0, y1 - y0) / alto}


def juntar_recortes(a, b):
    """Lo que queda después de quitar lo de los dos recortes (None si ninguno quita nada)."""
    if not a or not b:
        return a or b
    x0, y0 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x1, y1 = min(a["x"] + a["ancho"], b["x"] + b["ancho"]), min(a["y"] + a["alto"], b["y"] + b["alto"])
    return {"x": x0, "y": y0, "ancho": max(0.0, x1 - x0), "alto": max(0.0, y1 - y0)}


def _recorte_valido(r):
    """El rectángulo que propone el Portero, si tiene sentido (deja al menos media imagen de juego)."""
    if not isinstance(r, dict):
        return None
    try:
        x, y = float(r.get("x", 0)), float(r.get("y", 0))
        ancho, alto = float(r.get("ancho", r.get("w", 0))), float(r.get("alto", r.get("h", 0)))
    except (TypeError, ValueError):
        return None
    x, y = max(0.0, x), max(0.0, y)
    ancho, alto = min(ancho, 1.0 - x), min(alto, 1.0 - y)
    if ancho < 0.5 or alto < 0.5 or ancho * alto < 0.4 or (ancho > 0.98 and alto > 0.98):
        return None
    return {"x": round(x, 4), "y": round(y, 4), "ancho": round(ancho, 4), "alto": round(alto, 4)}


def _previo(revision):
    """Los recortes que hay que hacer al clip antes de montarlo (bandas negras y lo que no es juego)."""
    previo = ""
    if (revision or {}).get("bandas"):
        previo += f"crop={revision['bandas']},"
    r = (revision or {}).get("recorte")
    if r:
        previo += (f"crop=trunc(iw*{r['ancho']}/2)*2:trunc(ih*{r['alto']}/2)*2:"
                   f"trunc(iw*{r['x']}):trunc(ih*{r['y']}),")
    return previo


def fotos(clip, carpeta, cuantas=3, previo=""):
    """Unas fotos del clip grabado, repartidas de principio a fin (ya recortado, si hace falta)."""
    os.makedirs(carpeta, exist_ok=True)
    total, rutas = _segundos(clip), []
    for i in range(cuantas):
        ruta = os.path.join(carpeta, f"foto{i + 1}.jpg")
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{total * (i + 0.5) / cuantas:.2f}", "-i", clip,
                            "-frames:v", "1", "-vf", f"{previo}scale=720:-2", ruta], capture_output=True)
        if r.returncode == 0 and os.path.exists(ruta):
            rutas.append(ruta)
    return rutas


def revisar(clip, carpeta, m=None):
    """El Portero de clips. Devuelve {"vale", "bandas", "recorte", "sonido", "problemas", "que_se_ve", "quien", "fotos"}.
    Gemini mira el clip entero con su sonido; si no puede, mira 5 fotos (Gemini o Claude) y el sonido del clip se quita."""
    os.makedirs(carpeta, exist_ok=True)
    franjas = bandas(clip)
    base = f"crop={franjas}," if franjas else ""
    vistas = fotos(clip, os.path.join(carpeta, "fotos"), cuantas=5, previo=base)
    r, quien, oido = None, None, False
    muestra = os.path.join(carpeta, "muestra.mp4")
    hecho = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-t", "60", "-vf", f"{base}scale=-2:480",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "32", "-c:a", "aac", "-b:a", "48k", "-ac", "1",
                            muestra], capture_output=True)
    if hecho.returncode == 0 and os.path.exists(muestra) and os.path.getsize(muestra) <= gemini.VIDEO_MAXIMO:
        try:
            r = gemini.preguntar(PORTERO.format(que_ves="el clip entero, con su sonido",
                                                habla="true si se oye la voz del creador comentando (no las voces del juego)"),
                                 video=muestra, temperatura=0.2, ligero_primero=True)  # los buenos, para los jueces
            quien, oido = "gemini", True
        except gemini.SinIA:
            r = None
    if not isinstance(r, dict):
        r = ia.preguntar(PORTERO.format(que_ves=f"estas {len(vistas)} fotos del clip, de principio a fin",
                                        habla="null (con fotos no se puede oír)"),
                         papel="juez", imagenes=vistas, temperatura=0.2)      # sin IA: lanza SinIA y el clip espera
        quien = ia.quien().get("motor")
        if isinstance(r, list) and r:
            r = r[0]
        if not isinstance(r, dict):
            raise gemini.SinIA("el Portero de clips no ha contestado con la forma pedida")
    quieto = marcas(clip, previo=base)          # logos y marcas de agua quietos en una esquina (la IA a veces no los ve)
    junto = juntar_recortes(_recorte_valido(r.get("recorte")), quieto)
    recorte = _recorte_valido(junto) if junto else None
    demasiado = bool(junto) and recorte is None and (junto["ancho"] < 0.98 or junto["alto"] < 0.98)
    limpio = r.get("limpio") is True and recorte is None and not demasiado
    vale = r.get("vale") is not False and not demasiado and (r.get("limpio") is True or recorte is not None)
    # el sonido del juego solo se queda si alguien lo ha oído y el creador no habla; si no, música propia
    sonido = bool(oido and r.get("habla_creador") is False and not (m or {}).get("habla_creador") and _tiene_audio(clip))
    problemas = [str(p)[:120] for p in (r.get("problemas") or [])][:6]
    if quieto:
        problemas.append("algo quieto en una esquina (logo o marca de agua): recortado")
    return {"vale": vale, "bandas": franjas, "recorte": recorte, "sonido": sonido, "limpio": limpio,
            "problemas": problemas, "que_se_ve": str(r.get("que_se_ve") or "")[:300], "quien": quien, "fotos": vistas}


def guionizar(canal, m, lecciones="", segundos=15, imagenes=()):
    idioma = {"es": "español de España", "nl": "neerlandés", "en": "inglés"}.get((canal.get("idioma") or "es")[:2],
                                                                                "español de España")
    texto = GUION.format(nombre=canal.get("nombre", ""), tema=(canal.get("tema") or "")[:200], segundos=round(segundos),
                         que_pasa=m.get("que_pasa", ""), por_que=m.get("por_que", ""), gancho=m.get("gancho", ""),
                         idioma=idioma,
                         fotos=(f"Te paso {len(imagenes)} fotos del clip tal y como ha quedado (de principio a fin): "
                                "narra lo que se ve en ellas.\n") if imagenes else "",
                         lecciones=f"Lo que ha aprendido el canal (lo del dueño manda):\n{lecciones[:2500]}" if lecciones else "")
    g = ia.preguntar(texto, papel="guionista", imagenes=list(imagenes), temperatura=0.8)
    if isinstance(g, list) and g:
        g = g[0]
    if not isinstance(g, dict) or not g.get("narracion") or not g.get("titulo"):
        raise gemini.SinIA("el guion del clip no ha salido con la forma pedida")
    g["titulo"] = str(g["titulo"]).strip()[:100]
    if "#shorts" not in g["titulo"].lower():
        g["titulo"] = f"{g['titulo'][:90]} #shorts"
    g["descripcion"] = f"{str(g.get('descripcion') or '').strip()}\n\n{credito(m)}".strip()
    g["hashtags"] = [h if str(h).startswith("#") else f"#{h}" for h in (g.get("hashtags") or [])][:5] or ["#gta6"]
    g["clip"] = {k: m.get(k) for k in ("codigo", "video", "creador", "enlace", "licencia")}
    g["escenas"] = [{"texto": g.get("texto_pantalla", ""), "voz": g["narracion"]}]
    return g


def montar(clip, guion, voz, palabras_json, salida, revision=None, ambiente=None):
    """El Short: el clip (ya recortado) en el centro sobre un fondo difuminado del mismo clip, gancho arriba y subtítulos.
    Debajo de la voz, el sonido del juego bajito si el Portero lo ha dado por bueno; si no, música propia."""
    from bots.central import montador
    import musica
    import subtitulos
    revision = revision or {}
    total = _segundos(voz) + 0.6
    tmp = tempfile.mkdtemp()
    try:
        palabras = subtitulos.cargar(palabras_json)
        subtitulos.escribir_ass(palabras, os.path.join(tmp, "s.ass"), mayus=True, altura=420)
        fuente = f":fontfile={FUENTE}" if os.path.exists(FUENTE) else ""
        filtro = (f"[0:v]{_previo(revision)}split=2[f][p];"
                  "[f]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.12[fondo];"
                  "[p]scale=1080:1600:force_original_aspect_ratio=decrease[clip];"
                  "[fondo][clip]overlay=(W-w)/2:(H-h)/2-60,ass=s.ass")
        for n, linea in enumerate(montador._gancho(guion.get("texto_pantalla") or guion["titulo"]).split("\n")):
            with open(os.path.join(tmp, f"gancho{n}.txt"), "w", encoding="utf-8") as f:
                f.write(linea)
            filtro += (f",drawtext=textfile=gancho{n}.txt{fuente}:fontsize=86:fontcolor=white:borderw=8:bordercolor=black"
                       f":x=(w-text_w)/2:y=h*0.08+{n * 100}:enable='lt(t,2.6)'")
        filtro += ",format=yuv420p[v]"
        entradas = ["-stream_loop", "-1", "-i", os.path.abspath(clip), "-i", os.path.abspath(voz)]
        audio = "1:a"
        if revision.get("sonido") and _tiene_audio(clip):          # el sonido del juego, bajito, debajo de la voz
            filtro += ";[0:a]volume=0.18[c];[1:a][c]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            audio = "[a]"
        else:                                                       # del creador no se oye nada: música propia
            pista = musica.crear(ambiente, total, os.path.join(tmp, "musica.m4a")) if ambiente else None
            if pista:
                entradas += ["-i", pista]
                filtro += ";[2:a]volume=0.35[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
                audio = "[a]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro, "-map", "[v]",
                        "-map", audio, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
                        "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart",
                        os.path.abspath(salida)], cwd=tmp, check=True)
        return salida
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def tras_juicio(m, aprobado, nota=None, titulo=None, destino=None):
    """Después del Juzgado: si se aprueba, el clip queda usado; si no, se reintenta una vez y luego se deja."""
    if aprobado:
        marcar(m["codigo"], estado="usado", usado=privado.ahora(), nota_juzgado=nota, titulo=titulo, destino=destino)
        soltar_rama(m)
        return
    fallos = int(m.get("suspensos", 0)) + 1
    marcar(m["codigo"], suspensos=fallos, estado="grabado" if fallos < INTENTOS else "descartado", nota_juzgado=nota,
           descartado=privado.ahora() if fallos >= INTENTOS else None,
           motivo="el Juzgado lo ha suspendido dos veces" if fallos >= INTENTOS else None)
    if fallos >= INTENTOS:
        soltar_rama(m)


def descartar(m, motivo):
    marcar(m["codigo"], estado="descartado", descartado=privado.ahora(), motivo=motivo)
    soltar_rama(m)


def guardar_guion(carpeta, g):
    with open(os.path.join(carpeta, "guion.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
