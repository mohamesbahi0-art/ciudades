"""La Videoteca de juego: las tomas de GTA 5 y GTA 6 (licencia libre, CC BY) que el dueño ha grabado, ya limpias por el
Portero de clips y guardadas en la estantería «videoteca» del repositorio privado. Con ellas, los canales de GTA hacen
vídeos donde lo que se ve es justo lo que dice la voz, en vez de dibujos que se mueven (el dueño, 23 nov: «con vídeos que
representen lo que queramos decir es mucho mejor»).

- El Archivero de clips (al empezar cada ronda de la fábrica) pasa cada clip grabado por el Portero; si vale, guarda la
  versión limpia en la videoteca, con su juego, sus etiquetas y lo que se ve, y borra su rama temporal. Cada toma se
  reutiliza en muchos vídeos (cada vez un trozo distinto), así que con pocas grabaciones hay para mucho.
- En el turno de un canal de GTA (gta, curios o versus), si hay tomas suficientes, el Escritor escribe a partir de ellas:
  cada escena dice qué toma enseña y solo cuenta lo que se ve (y lo que digan las fuentes).
- El Montador corta cada toma en planos de 2-3 s (siempre algo nuevo en pantalla). En GTA 5 contra GTA 6, pantalla
  partida: GTA 5 arriba y GTA 6 abajo, a la vez, por rondas, con rótulo y ganador de cada ronda.
- Del creador de cada toma solo va su nombre y el enlace en la descripción.
Si no hay tomas suficientes, el canal sigue como siempre.
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import unicodedata

from bots.central import clips
from bots.comun import almacen, gemini, ia, privado

ESTANTERIA = clips.VIDEOTECA
INDICE = os.path.join("estado", "clips", "videoteca.json")
ETIQUETAS = ["ciudad", "coches", "conducir", "policía", "persecución", "agua", "playa", "explosiones", "armas",
             "personajes", "animales", "clima", "noche", "gráficos", "físicas", "interiores", "aviones", "motos",
             "barcos", "detalle", "humor", "mapa", "tiendas", "naturaleza"]
JUEGOS = {"gta5": "GTA 5", "gta6": "GTA 6"}
MIN_TOMAS = 6            # tomas para hacer con clips un vídeo de un canal de un solo juego...
MIN_FUENTES = 2          # ...sacadas de al menos 2 vídeos distintos (si no, todos los vídeos enseñarían lo mismo)
MIN_PAREJAS = 2          # cosas con toma de GTA 5 y de GTA 6 para hacer un versus
PRIMER_CORTE, PLANO_MAX = 1.6, 2.0      # el Cerebro: primer cambio antes del segundo 2 y un plano nuevo cada 1,5-2 s
VERSUS = {"seg_min": 25, "seg_max": 30, "pal_min": 55, "pal_max": 80, "esc_min": 7, "esc_max": 9}   # 3 rondas de ~8 s
PALABRAS_ESCENA = {True: 10, False: 14}  # voz por escena como mucho (versus / un solo juego)
COLORES = {"gta5": "0xE8412F", "gta6": "0x2F7BE8"}

GUION = """Eres el Escritor del canal de YouTube Shorts «{nombre}» ({tema}). Esta vez el vídeo NO lleva dibujos: se monta
con tomas de juego de verdad de la videoteca (abajo). Lo que se ve tiene que ser justo lo que dice la voz: elige para cada
escena la toma que enseña lo que cuentas, y no digas nada que no se vea en ella o que no esté en las fuentes.
Vídeo vertical de {seg_min} a {seg_max} segundos, en {idioma}.
{formato}
Reglas que enganchan:
- Los 2 primeros segundos son el gancho: una frase que abre una pregunta o empieza en mitad de la acción (nada de saludos).
- Frases cortas, una idea por frase. Algo nuevo cada 2 segundos (el Montador cambia de plano así). Como mucho
  {pal_escena} palabras de voz por escena.
- De un juego que todavía no ha salido (GTA 6) solo vale lo que SE VE en la toma o lo que traen las fuentes, y dicho así
  («en esta toma se ve…», «en el tráiler se ve…»). Nada de mecánicas, sistemas, secretos ni fechas sin confirmar contados
  como hechos; si no se ve ni está en las fuentes, no lo digas.
- No prometas nada que el vídeo no enseñe o no diga después, y no dejes la última frase a medias.
- El final remata con una pregunta que invite a comentar y, si puede ser, enlaza con la primera frase.
- Escribe los números como se dicen. Entre {pal_min} y {pal_max} palabras en total.
- No nombres a los creadores de las tomas: su crédito va en la descripción.
- Sin miedo, pero con tres límites: verdad sobre gente real, nada de odio contra grupos y nada que rompa las normas de YouTube.
Lo que ha aprendido este canal (lo del dueño manda):
{lecciones}
Títulos ya hechos (imita el estilo, NO repitas sus temas):
{titulos}
{fuentes}
TOMAS DISPONIBLES (usa solo estas, por su código):
{catalogo}
{idea}
Devuelve SOLO un JSON:
{{"idea": "una línea", "titulo": "título de 70 caracteres como mucho, con gancho, 1 o 2 emojis y acabado en #shorts",
  "texto_pantalla": "{pantalla}", "narracion": "todo lo que dice la voz, entero",
  "escenas": [{escena}],
  "descripcion": "una o dos frases", "hashtags": ["#3 a 5 hashtags del tema"]{fuentes_usadas}}}
Entre {esc_min} y {esc_max} escenas, en orden, que juntas cubran toda la narración."""

FORMATO_UNO = """- Cada escena enseña UNA toma. Varía: no pongas la misma toma en dos escenas seguidas.
- La toma de la PRIMERA escena tiene que enseñar ya la cosa de la que habla el título (nada de planos de ambiente antes),
  y «texto_pantalla» la nombra con 3 a 5 palabras («EL PERRO EN MOTO»). Si ninguna toma enseña eso, cambia de tema.
- «rotulo» (si quieres): de 1 a 3 palabras grandes que refuerzan lo que se dice («¡MIRA EL AGUA!»)."""
ESCENA_UNO = '{"texto": "las frases exactas de la narración de esta escena", "toma": "código", "rotulo": "opcional"}'

FORMATO_VERSUS = """- Es un GTA 5 contra GTA 6 en pantalla partida: arriba GTA 5 y abajo GTA 6, a la vez. El Montador pone solo
  la etiqueta de cada juego, el rótulo «GANA GTA 5/6» al acabar cada ronda, el MARCADOR (1-0, 1-1, 2-1) y el veredicto
  final escrito: tú solo marca bien «gana» y di lo mismo con la voz.
- «texto_pantalla»: 3 o 4 palabras que nombran la cosa exacta que se compara («FÍSICAS DE COCHES»). La primera palabra de
  la voz es ese tema, no «En GTA cinco».
- Escena 1: el gancho (sin «gana»), con una pareja de tomas que ya enseña lo que se compara.
- Después, 3 RONDAS de 2 escenas cada una. Cada ronda compara UN detalle concreto que tengan los dos juegos ({parejas}),
  con una toma de GTA 5 y otra de GTA 6 de ese mismo detalle, y que a simple vista se vean distintas. La primera escena
  de la ronda dice qué se ve; la segunda dice quién gana y lleva «gana»: "gta5", "gta6" o "empate". Solo la escena que
  cierra la ronda lleva «gana».
- Sé justo: no puede ganar siempre el mismo si las tomas no lo enseñan. Si GTA 5 gana en algo concreto, dilo (eso trae
  comentarios).
- «rotulo»: el nombre de la ronda, de 1 a 3 palabras («RONDA 1: AGUA»), igual en las dos escenas de la ronda.
- Última escena (sin «gana»): el veredicto con el marcador que sale de tus rondas («GTA seis gana dos a uno») y una
  pregunta corta para comentar («¿Qué ronda le darías a GTA cinco?»)."""
ESCENA_VERSUS = ('{"texto": "las frases exactas de esta escena (10 palabras como mucho)", '
                 '"gta5": "código de una toma de GTA 5", "gta6": "código de una toma de GTA 6", '
                 '"rotulo": "RONDA 1: AGUA", "gana": "gta6 (solo en la escena que cierra la ronda)"}')


# ---------- el índice de la videoteca ----------

def tomas():
    return [t for t in (privado.leer(INDICE, {}) or {}).get("tomas") or [] if isinstance(t, dict) and t.get("id")]


def _guardar(lista):
    privado.guardar_estado("clips/videoteca.json", {"tomas": lista})


def juego_de(m):
    """GTA 5 o GTA 6, por lo que dijo el Buscador o por el título del vídeo de donde sale."""
    j = str(m.get("juego") or "").lower().replace(" ", "")
    if j in JUEGOS:
        return j
    t = f"{m.get('titulo_original', '')} {m.get('que_pasa', '')}".upper()
    if re.search(r"GTA\s*(5|V)\b|GTAV\b", t) and not re.search(r"GTA\s*(6|VI)\b", t):
        return "gta5"
    return "gta6"


def _normal(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def etiquetas_de(m):
    puestas = [e for e in (m.get("etiquetas") or []) if isinstance(e, str)]
    texto = _normal(f"{m.get('que_pasa', '')} {m.get('que_se_ve', '')} {' '.join(puestas)}")
    return sorted({e for e in ETIQUETAS if _normal(e) in texto} | {e for e in puestas if e in ETIQUETAS}) or ["ciudad"]


def disponibles(canal):
    juegos = canal.get("videoteca_juegos") or (["gta5", "gta6"] if canal.get("tipo") == "versus" else ["gta6"])
    fuera = perdidas()                                  # las que ya se sabe que no están en la estantería
    return [t for t in tomas() if t.get("juego") in juegos and t.get("id") not in fuera]


def parejas(lista):
    """Las cosas (etiquetas) que tienen toma de GTA 5 y de GTA 6: con ellas se hace una ronda de versus."""
    por = {}
    for t in lista:
        for e in t.get("etiquetas") or []:
            por.setdefault(e, set()).add(t.get("juego"))
    return sorted(e for e, juegos in por.items() if {"gta5", "gta6"} <= juegos)


def suficientes(canal):
    if not canal.get("videoteca"):
        return False
    lista = disponibles(canal)
    if canal.get("tipo") == "versus":
        return len(parejas(lista)) >= MIN_PAREJAS
    fuentes = {t.get("fuente") or t.get("enlace") or t.get("creador") for t in lista}
    return len(lista) >= MIN_TOMAS and len(fuentes) >= MIN_FUENTES


def catalogo(lista, maximo=30):
    orden = sorted(lista, key=lambda t: (int(t.get("usos") or 0), -float(t.get("calidad") or 0)))[:maximo]
    return "\n".join(f"- {t['id']} [{JUEGOS.get(t.get('juego'), t.get('juego'))}] ({round(float(t.get('segundos') or 0))} s)"
                     f" {', '.join(t.get('etiquetas') or [])}: {t.get('que_se_ve') or t.get('que_pasa') or ''}"[:300]
                     for t in orden)


def creditos(ids):
    """Una línea por vídeo de origen: «🎬 Clip: creador · enlace · licencia» (CC BY o dominio público)."""
    por_id = {t["id"]: t for t in tomas()}
    lineas, vistos = [], set()
    for i in ids:
        t = por_id.get(i)
        if not t:
            continue
        enlace = re.sub(r"[?&]t=\d+s?$", "", str(t.get("enlace") or ""))
        if (t.get("creador"), enlace) in vistos:
            continue
        vistos.add((t.get("creador"), enlace))
        lineas.append(f"🎬 Clip: {t.get('creador', '?')} · {enlace} · {clips.texto_licencia(t.get('licencia'))}")
    return lineas


def apuntar_usos(ids):
    ahora, lista = privado.ahora(), tomas()
    for t in lista:
        if t["id"] in ids:
            t["usos"] = int(t.get("usos") or 0) + 1
            t["ultimo_uso"] = ahora
    _guardar(lista)


# ---------- el Archivero de clips ----------

def limpiar(clip, rev, salida):
    """La toma limpia: sin bandas negras ni lo que no es juego, como mucho 1920 de ancho y 60 s, y con el sonido del juego
    solo si el Portero lo ha dado por bueno."""
    args = ["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-t", "60", "-vf",
            f"{clips._previo(rev)}scale='min(1920,iw)':-2,fps=30,format=yuv420p", "-c:v", "libx264", "-preset",
            "veryfast", "-crf", "20"]
    args += ["-c:a", "aac", "-b:a", "128k"] if rev.get("sonido") and clips._tiene_audio(clip) else ["-an"]
    subprocess.run(args + ["-movflags", "+faststart", salida], check=True)
    return salida


def archivar(paso=print, maximo=6):
    """Cada clip grabado que todavía no está en la videoteca pasa por el Portero; si vale, se guarda limpio y se borra su
    rama temporal. Devuelve cuántos se han guardado."""
    pendientes = [m for m in clips.momentos()
                  if m.get("estado") == "grabado" and m.get("archivo") and not m.get("en_videoteca")]
    if not pendientes:
        return 0
    lista, hechos = tomas(), 0
    cuaderno = privado.cuaderno("portero_clips")
    for m in sorted(pendientes, key=lambda x: -clips._nota(x))[:maximo]:
        tmp = tempfile.mkdtemp(prefix="archivero-")
        try:
            ruta = clips.bajar(m, os.path.join(tmp, "clip"))
            rev = clips.revisar(ruta, os.path.join(tmp, "portero"), m)
            cuaderno.apuntar("revision", {"clip": m["codigo"], "vale": rev["vale"], "recorte": bool(rev["recorte"]),
                                          "bandas": bool(rev["bandas"]), "sonido": rev["sonido"],
                                          "problemas": rev["problemas"]})
            if not rev["vale"]:
                motivo = "sale algo del creador y no se puede quitar: " + (", ".join(rev["problemas"]) or "sin detalle")
                clips.descartar(m, motivo[:300])
                paso(f"archivero: {m['codigo']} descartado (sale algo del creador)")
                continue
            nombre = f"{m['codigo']}.mp4"
            limpio = limpiar(ruta, rev, os.path.join(tmp, nombre))
            almacen.guardar(ESTANTERIA, limpio, nombre)
            toma = {"id": m["codigo"], "archivo": nombre, "juego": juego_de(m),
                    "etiquetas": etiquetas_de(dict(m, que_se_ve=rev["que_se_ve"])),
                    "que_se_ve": rev["que_se_ve"] or m.get("que_pasa", ""), "segundos": round(clips._segundos(limpio), 1),
                    "sonido": bool(rev["sonido"]), "creador": m.get("creador"), "enlace": m.get("enlace"),
                    "licencia": m.get("licencia", "CC BY"), "calidad": clips._nota(m), "para": m.get("para"),
                    "entrada": privado.ahora(), "usos": 0, "marcas": "revisada"}
            lista = [t for t in lista if t.get("id") != m["codigo"]] + [toma]
            _guardar(lista)
            es_toma = m.get("tipo") == "toma" or m.get("para") in ("videoteca", "versus")
            clips.marcar(m["codigo"], en_videoteca=True, que_se_ve=toma["que_se_ve"],
                         estado="en_videoteca" if es_toma else None)
            clips.soltar_rama(m)
            hechos += 1
            paso(f"archivero: {m['codigo']} guardado en la videoteca ({JUEGOS[toma['juego']]}: "
                 f"{', '.join(toma['etiquetas'])})")
        except gemini.SinIA:
            paso("archivero: la IA no contesta; los clips grabados esperan a la siguiente ronda")
            break
        except Exception as e:                   # ese clip se queda como estaba y se prueba en la siguiente ronda
            paso(f"archivero: {m['codigo']} no se ha podido guardar ({type(e).__name__})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    cuaderno.guardar()
    return hechos


def repasar_marcas(paso=print):
    """Las tomas guardadas antes del detector de logos: se bajan, se les quita lo que esté quieto en una esquina (logo o
    marca de agua del autor) y se vuelven a guardar. Solo las que no lo tienen hecho; sin IA."""
    lista, hechas = tomas(), 0
    for t in lista:
        if t.get("marcas"):
            continue
        tmp = tempfile.mkdtemp(prefix="repaso-")
        try:
            ruta = almacen.bajar(ESTANTERIA, t["archivo"], tmp)
            quieto = clips._recorte_valido(clips.marcas(ruta))
            if quieto:
                limpio = limpiar(ruta, {"recorte": quieto, "sonido": t.get("sonido")}, os.path.join(tmp, "limpio.mp4"))
                almacen.guardar(ESTANTERIA, limpio, t["archivo"])
                t["marcas"] = "quitadas"
                hechas += 1
                paso(f"videoteca: {t['id']} sin el logo del autor")
            else:
                t["marcas"] = "revisada"
        except Exception as e:                # se vuelve a probar en la próxima pasada
            paso(f"videoteca: no he podido repasar {t['id']} ({type(e).__name__})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    _guardar(lista)
    return hechas


# ---------- el guion con tomas ----------

def _parecida(lista, juego, texto, evitar=()):
    """La toma que mejor pega con un texto (por sus etiquetas y lo que se ve), mejor si no se acaba de usar."""
    palabras = set(re.findall(r"\w+", _normal(texto)))
    candidatas = [t for t in lista if not juego or t.get("juego") == juego] or lista

    def puntos(t):
        sus = set(re.findall(r"\w+", _normal(" ".join(t.get("etiquetas") or []) + " " + (t.get("que_se_ve") or ""))))
        return (t["id"] not in evitar, len(palabras & sus), -int(t.get("usos") or 0))
    return max(candidatas, key=puntos)


def _palabras(texto):
    return re.findall(r"\w+", str(texto or ""))


def marcador(escenas):
    """El marcador (GTA 5, GTA 6) después de cada escena (sube cuando una ronda termina con ganador)."""
    cuenta, pasos = [0, 0], []
    for e in escenas:
        if e.get("gana") in ("gta5", "gta6"):
            cuenta[0 if e["gana"] == "gta5" else 1] += 1
        pasos.append(tuple(cuenta))
    return pasos


def veredicto(escenas):
    """El rótulo del final: «GTA 6 GANA 2-1» o «EMPATE 1-1» (None si el guion no trae rondas con ganador)."""
    if not any(e.get("gana") for e in escenas):
        return None
    a, b = marcador(escenas)[-1]
    return f"EMPATE {a}-{b}" if a == b else f"{JUEGOS['gta5' if a > b else 'gta6']} GANA {max(a, b)}-{min(a, b)}"


def _medidas(canal, versus):
    from bots.central import escritor
    return dict(VERSUS) if versus and not canal.get("segundos") else escritor.medidas(canal)


def _fallos(g, canal, versus):
    """Lo que pide el Cerebro y se puede contar: si falla, el Escritor lo repite (con números) antes de darlo por bueno."""
    m, escenas, fallos = _medidas(canal, versus), g["escenas"], []
    tope = PALABRAS_ESCENA[versus]
    largas = [n + 1 for n, e in enumerate(escenas) if len(_palabras(e["texto"])) > tope + 1]
    if largas:
        fallos.append(f"las escenas {largas} pasan de {tope} palabras de voz: pártelas o recórtalas")
    total = len(_palabras(g.get("narracion")))
    if total > int(m["pal_max"] * 1.15):
        fallos.append(f"la narración tiene {total} palabras y el tope es {m['pal_max']}")
    pantalla = len(_palabras(g.get("texto_pantalla")))
    if not 2 <= pantalla <= (4 if versus else 5):
        fallos.append(f"«texto_pantalla» tiene {pantalla} palabras: de 3 a {4 if versus else 5} que nombren la cosa")
    if versus:
        rondas = [n for n, e in enumerate(escenas) if e.get("gana")]
        if len(rondas) != 3:
            fallos.append(f"hay {len(rondas)} rondas con «gana» y tienen que ser 3")
        if rondas and (rondas[0] == 0 or rondas[-1] == len(escenas) - 1):
            fallos.append("la primera escena (gancho) y la última (veredicto y pregunta) no llevan «gana»")
        if re.match(r"\s*en gta\b", _normal(escenas[0]["texto"])):
            fallos.append("la voz empieza por «En GTA…»: tiene que empezar por la cosa que se compara")
    return fallos


def _arreglar(g, lista, versus):
    """Comprueba que cada escena usa tomas que existen (y del juego que toca); si no, pone la que mejor pega."""
    por_id = {t["id"]: t for t in lista}
    escenas = [e for e in g.get("escenas") or [] if isinstance(e, dict) and str(e.get("texto") or "").strip()]
    if len(escenas) < 2 or not str(g.get("narracion") or "").strip() or not g.get("titulo"):
        raise ValueError("el guion con tomas no tiene la forma pedida")
    usadas = []
    for e in escenas:
        huecos = ("gta5", "gta6") if versus else ("toma",)
        for hueco in huecos:
            juego = hueco if versus else None
            t = por_id.get(str(e.get(hueco) or "").strip())
            if not t or (juego and t.get("juego") != juego):
                t = _parecida(lista, juego, f"{e.get('rotulo') or ''} {e['texto']}", evitar=usadas[-2:])
            e[hueco] = t["id"]
            usadas.append(t["id"])
        if versus and e.get("gana") not in ("gta5", "gta6", "empate"):
            e.pop("gana", None)
    g["escenas"] = escenas
    g["tomas_usadas"] = sorted(set(usadas))
    return g


def guionizar(canal, lista, lecciones="", titulos=(), fuentes=None, idea=None):
    from bots.central import escritor
    versus = canal.get("tipo") == "versus"
    texto = GUION.format(
        nombre=canal.get("nombre", ""), tema=canal.get("tema") or escritor.ESTILOS.get(canal.get("tipo"), ""),
        idioma=escritor.IDIOMAS.get((canal.get("idioma") or "es")[:2], "español de España"),
        formato=FORMATO_VERSUS.format(parejas=", ".join(parejas(lista))) if versus else FORMATO_UNO,
        lecciones=lecciones or "- (nada todavía)", titulos="\n".join(f"- {t}" for t in titulos) or "- (ninguno todavía)",
        fuentes=f"\nFUENTES (lo único que puedes contar como hecho, además de lo que se ve):\n{fuentes}\n" if fuentes else "",
        catalogo=catalogo(lista), escena=ESCENA_VERSUS if versus else ESCENA_UNO,
        idea=(f"\nLa Sala de Ideas ha elegido ESTA idea: escribe su guion con las tomas.\nIdea: {idea.get('idea')}\n"
              f"Título propuesto: {idea.get('titulo')}\nGancho: {idea.get('gancho')}\n") if idea else "",
        fuentes_usadas=',\n  "fuentes_usadas": ["los números de las fuentes usadas"]' if fuentes else "",
        pal_escena=PALABRAS_ESCENA[versus],
        pantalla=("3 o 4 palabras: la cosa exacta que se compara" if versus
                  else "de 3 a 5 palabras que nombran la cosa que se ve en la primera toma"),
        **_medidas(canal, versus))
    ultimo, intentos = "", 3
    for n in range(intentos):
        g = ia.preguntar(texto + ultimo, papel="guionista")
        if isinstance(g, list) and g:
            g = g[0]
        try:
            g = _arreglar(g if isinstance(g, dict) else {}, lista, versus)
            fallos = _fallos(g, canal, versus)
            if fallos and n < intentos - 1:      # el último intento vale con la forma buena: mejor un vídeo que ninguno
                raise ValueError("; ".join(fallos))
            break
        except ValueError as e:
            ultimo = f"\n\nEl intento anterior no valía ({e}). Corrígelo y devuelve el JSON entero."
    else:
        raise gemini.SinIA("el guion con tomas no ha salido con la forma pedida")
    g["texto_pantalla"] = " ".join(str(g.get("texto_pantalla") or "").split()[:4 if versus else 5])
    g["titulo"] = str(g["titulo"]).strip()[:100]
    if "#shorts" not in g["titulo"].lower():
        g["titulo"] = f"{g['titulo'][:90]} #shorts"
    g["hashtags"] = [h if str(h).startswith("#") else f"#{h}" for h in (g.get("hashtags") or [])][:5] or ["#gta6"]
    g["descripcion"] = "\n\n".join([str(g.get("descripcion") or "").strip(), "\n".join(creditos(g["tomas_usadas"]))]).strip()
    g["formato"] = "versus_clips" if versus else "clips"
    g["cerebro"] = ia.quien().get("motor", "gemini")
    return g


# ---------- el montaje ----------

PERDIDAS = os.path.join("estado", "clips", "perdidas.json")    # tomas apuntadas cuyo archivo no está en la estantería


def perdidas():
    return set((privado.leer(PERDIDAS, {}) or {}).get("ids") or [])


def _apuntar_perdida(i):
    try:
        d = privado.leer(PERDIDAS, {}) or {}
        d["ids"] = sorted(set(d.get("ids") or []) | {i})
        d["actualizado"] = privado.ahora()
        privado.escribir(PERDIDAS, d)
    except Exception:
        pass


def bajar(ids, carpeta):
    """Baja las tomas del montaje. Una toma cuyo archivo ya no está en la estantería no rompe el turno: se apunta como
    perdida (no se vuelve a elegir) y el vídeo sigue con las demás. Solo falla si no queda ninguna."""
    os.makedirs(carpeta, exist_ok=True)
    por_id, rutas = {t["id"]: t for t in tomas()}, {}
    for i in sorted(set(ids)):
        if i not in por_id:
            continue
        nombre = por_id[i]["archivo"]
        try:
            almacen.bajar(ESTANTERIA, nombre, carpeta)
        except Exception:
            pass
        ruta = os.path.join(carpeta, nombre)
        if not os.path.exists(ruta) or clips._segundos(ruta) < 1:
            print(f"videoteca: la toma {i} no está en la estantería: se aparta y se sigue con las demás", flush=True)
            _apuntar_perdida(i)
            continue
        rutas[i] = ruta
    if not rutas:
        raise RuntimeError("ninguna de las tomas elegidas está en la videoteca")
    # la que falta se cubre con otra que sí está, del mismo juego si puede ser (en versus, cada mitad es de su juego)
    for i in sorted(set(ids)):
        if i in rutas:
            continue
        juego = (por_id.get(i) or {}).get("juego")
        mismas = [r for j, r in rutas.items() if (por_id.get(j) or {}).get("juego") == juego]
        rutas[i] = (mismas or list(rutas.values()))[0]
    return rutas


def _planos(escenas, duraciones):
    """Cada escena en planos iguales de 2 s como mucho (el Cerebro: un cambio cada 1,5-2 s); el primero, antes del 2."""
    planos = []
    for n, (e, d) in enumerate(zip(escenas, duraciones)):
        partes = []
        if n == 0 and d > PRIMER_CORTE + 1.0:
            partes.append(PRIMER_CORTE)
        resto = d - sum(partes)
        trozos = max(1, math.ceil((resto - 0.3) / PLANO_MAX))
        partes += [resto / trozos] * trozos
        planos += [(n, e, p, k == len(partes) - 1) for k, p in enumerate(partes)]
    return planos


def _texto(carpeta, nombre, texto):
    with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as f:
        f.write(texto)
    return nombre


def _rotulo(carpeta, k, texto, y, color="0xFFD43B"):
    if not texto:
        return ""
    fuente = f":fontfile={clips.FUENTE}" if os.path.exists(clips.FUENTE) else ""
    texto = str(texto).upper()[:28]
    archivo = _texto(carpeta, f"rotulo{k}.txt", texto)
    tamano = min(74, int(1000 / (0.66 * max(1, len(texto)))))       # que quepa entero a lo ancho
    return (f",drawtext=textfile={archivo}{fuente}:fontsize={tamano}:fontcolor={color}:borderw=7:bordercolor=black"
            f":x=(w-text_w)/2:y={y}")


def _plano_uno(carpeta, k, ruta, inicio, d, rotulo):
    filtro = ("[0:v]fps=30,split=2[f][p];"
              "[f]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.15[fondo];"
              "[p]crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080[c];"       # un cuadrado grande, centrado en la acción
              f"[fondo][c]overlay=0:330{_rotulo(carpeta, k, rotulo, 150)},format=yuv420p[v]")
    salida = os.path.join(carpeta, f"p{k:03d}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-ss", f"{inicio:.2f}", "-i", ruta,
                    "-filter_complex", filtro, "-map", "[v]", "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "20", "-r", "30", salida], cwd=carpeta, check=True)
    return salida


def _marcador(carpeta, k, antes, despues, desde, fuente):
    """El marcador entre el rótulo y la mitad de GTA 5: «GTA 5  1 - 0  GTA 6», que cambia al salir el ganador."""
    l5, l6 = _texto(carpeta, "m5.txt", "GTA 5"), _texto(carpeta, "m6.txt", "GTA 6")
    filtro = (f",drawbox=x=196:y=150:w=200:h=84:color={COLORES['gta5']}@0.95:t=fill"
              f",drawtext=textfile={l5}{fuente}:fontsize=50:fontcolor=white:x=196+(200-text_w)/2:y=168"
              f",drawbox=x=684:y=150:w=200:h=84:color={COLORES['gta6']}@0.95:t=fill"
              f",drawtext=textfile={l6}{fuente}:fontsize=50:fontcolor=white:x=684+(200-text_w)/2:y=168")
    for n, (cuenta, cuando) in enumerate(((antes, f"lt(t,{desde})"), (despues, f"gte(t,{desde})"))):
        if antes == despues and n:
            break
        archivo = _texto(carpeta, f"marca{k}_{n}.txt", f"{cuenta[0]} - {cuenta[1]}")
        filtro += (f",drawtext=textfile={archivo}{fuente}:fontsize=84:fontcolor=white:borderw=6:bordercolor=black"
                   f":x=(w-text_w)/2:y=152" + ("" if antes == despues else f":enable='{cuando}'"))
    return filtro


def _plano_versus(carpeta, k, r5, i5, r6, i6, d, rotulo, gana, cuenta=None, antes=None, grande=False, final=None):
    """Un plano de la pantalla partida. «grande»: las etiquetas de cada juego en grande (el gancho). «cuenta»/«antes»: el
    marcador después y antes de este plano. «final»: el veredicto escrito («GTA 6 GANA 2-1»)."""
    fuente = f":fontfile={clips.FUENTE}" if os.path.exists(clips.FUENTE) else ""
    l5, l6 = _texto(carpeta, "l5.txt", "GTA 5"), _texto(carpeta, "l6.txt", "GTA 6")
    ancho, alto, letra = (380, 128, 96) if grande else (210, 74, 52)
    filtro = ("[0:v]fps=30,scale=1080:608:force_original_aspect_ratio=increase,crop=1080:608[a];"
              "[1:v]fps=30,scale=1080:608:force_original_aspect_ratio=increase,crop=1080:608[b];"
              "[2:v][a]overlay=0:250:shortest=1[t];[t][b]overlay=0:1062:shortest=1"
              f",drawbox=x=24:y=270:w={ancho}:h={alto}:color={COLORES['gta5']}@0.95:t=fill"
              f",drawtext=textfile={l5}{fuente}:fontsize={letra}:fontcolor=white"
              f":x=24+({ancho}-text_w)/2:y=270+({alto}-{letra})/2+{letra // 8}"
              f",drawbox=x=24:y=1082:w={ancho}:h={alto}:color={COLORES['gta6']}@0.95:t=fill"
              f",drawtext=textfile={l6}{fuente}:fontsize={letra}:fontcolor=white"
              f":x=24+({ancho}-text_w)/2:y=1082+({alto}-{letra})/2+{letra // 8}"
              + _rotulo(carpeta, k, final or rotulo, 44, "0x3BD16F" if final else "0xFFD43B"))
    desde = round(d * 0.4, 2)
    if cuenta is not None:
        filtro += _marcador(carpeta, k, antes if antes is not None else cuenta, cuenta, desde, fuente)
    if gana in ("gta5", "gta6", "empate"):          # al final de la ronda, el ganador (en grande, sobre su mitad)
        texto = _texto(carpeta, f"gana{k}.txt", "EMPATE" if gana == "empate" else f"GANA {JUEGOS[gana]}")
        y = {"gta5": 700, "gta6": 1512, "empate": 1700}[gana]
        if gana != "empate":
            filtro += (f",drawbox=x=0:y={250 if gana == 'gta5' else 1062}:w=1080:h=608:color=0x3BD16F:t=14"
                       f":enable='gte(t,{desde})'")
        filtro += (f",drawtext=textfile={texto}{fuente}:fontsize=104:fontcolor=0x3BD16F:borderw=9:bordercolor=black"
                   f":box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y={y}:enable='gte(t,{desde})'")
    filtro += ",format=yuv420p[v]"
    salida = os.path.join(carpeta, f"p{k:03d}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-ss", f"{i5:.2f}", "-i", r5,
                    "-stream_loop", "-1", "-ss", f"{i6:.2f}", "-i", r6,
                    "-f", "lavfi", "-i", f"color=c=0x0d0f14:s=1080x1920:r=30:d={d:.3f}",
                    "-filter_complex", filtro, "-map", "[v]", "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "20", "-r", "30", salida], cwd=carpeta, check=True)
    return salida


def montar(g, rutas, voz, palabras_json, salida, ambiente=None):
    """El Short con tomas: planos de 2-3 s de la toma de cada escena (cada vez un trozo distinto), gancho arriba,
    subtítulos y la voz con música propia debajo. En versus, pantalla partida con rótulos, rondas y ganador."""
    from bots.central import montador
    import musica
    import subtitulos
    versus = g.get("formato") == "versus_clips"
    azar = random.Random(os.path.basename(salida))
    tmp = tempfile.mkdtemp()
    try:
        palabras = subtitulos.cargar(palabras_json)
        total = clips._segundos(voz) + 0.4
        durs = montador.duraciones_escenas([{"texto": e["texto"]} for e in g["escenas"]],
                                           [{"inicio": w["i"]} for w in palabras], total)
        largos = {i: clips._segundos(r) for i, r in rutas.items()}
        ultimos = {}

        def inicio(i, d):                       # un trozo distinto de la toma en cada plano
            hueco = max(0.0, largos[i] - d - 0.1)
            if hueco < 0.5:
                return 0.0
            for _ in range(6):
                x = round(azar.uniform(0, hueco), 2)
                if all(abs(x - y) > min(2.0, hueco / 3) for y in ultimos.get(i, [])):
                    break
            ultimos.setdefault(i, []).append(x)
            return x
        planos = []
        cuentas = [(0, 0)] + marcador(g["escenas"]) if versus else []      # el marcador antes de cada escena
        cierre = veredicto(g["escenas"]) if versus else None
        ultima = len(g["escenas"]) - 1
        for k, (n, e, d, final) in enumerate(_planos(g["escenas"], durs)):
            if versus:
                sube = bool(final and e.get("gana"))              # el marcador cambia cuando sale el ganador
                planos.append(_plano_versus(
                    tmp, k, rutas[e["gta5"]], inicio(e["gta5"], d), rutas[e["gta6"]], inicio(e["gta6"], d), d,
                    e.get("rotulo") if n > 0 else None,           # en la primera escena manda el gancho
                    e.get("gana") if final else None, grande=n == 0,
                    cuenta=(cuentas[n + 1] if sube or not e.get("gana") else cuentas[n]) if n > 0 and cierre else None,
                    antes=cuentas[n] if sube else None,
                    final=cierre if n == ultima and n > 0 and not e.get("gana") else None))
                continue
            planos.append(_plano_uno(tmp, k, rutas[e["toma"]], inicio(e["toma"], d), d,
                                     e.get("rotulo") if n > 0 else None))
        with open(os.path.join(tmp, "lista.txt"), "w") as f:
            f.writelines(f"file '{p}'\n" for p in planos)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy",
                        "imagen.mp4"], cwd=tmp, check=True)
        if versus:                              # subtítulos en la franja del medio, entre los dos juegos
            subtitulos.escribir_ass(palabras, os.path.join(tmp, "s.ass"), mayus=True, tamano=80, altura=905)
        else:                                   # debajo del cuadrado del clip
            subtitulos.escribir_ass(palabras, os.path.join(tmp, "s.ass"), mayus=True, altura=300)
        fuente = f":fontfile={clips.FUENTE}" if os.path.exists(clips.FUENTE) else ""
        filtro = "[0:v]ass=s.ass"
        # el gancho nombra la cosa desde el fotograma 0; en versus dura lo que la primera escena (después va el marcador)
        hasta = min(4.0 if versus else 2.6, max(1.5, durs[0]))     # nunca encima del rótulo de la escena siguiente
        for n, linea in enumerate(montador._gancho(g.get("texto_pantalla") or g["titulo"]).split("\n")[:2]):
            archivo = _texto(tmp, f"gancho{n}.txt", linea)
            filtro += (f",drawtext=textfile={archivo}{fuente}:fontsize=80:fontcolor=white:borderw=8:bordercolor=black"
                       f":x=(w-text_w)/2:y={40 + n * 96 if versus else 120 + n * 100}:enable='lt(t,{hasta:.2f})'")
        filtro += ",format=yuv420p[v]"
        entradas, audio = ["-i", "imagen.mp4", "-i", os.path.abspath(voz)], "1:a"
        pista = musica.crear(ambiente, total, os.path.join(tmp, "musica.m4a")) if ambiente else None
        if pista:                               # música propia por debajo de la voz (del creador no se oye nada)
            entradas += ["-i", pista]
            filtro += ";[2:a]volume=0.30[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            audio = "[a]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro, "-map", "[v]",
                        "-map", audio, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", "30",
                        "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart",
                        os.path.abspath(salida)], cwd=tmp, check=True)
        return salida
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
