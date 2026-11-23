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
MIN_TOMAS = 4            # tomas para hacer con clips un vídeo de un canal de un solo juego
MIN_PAREJAS = 2          # cosas con toma de GTA 5 y de GTA 6 para hacer un versus
PRIMER_CORTE, PLANO_MAX = 2.0, 2.8
COLORES = {"gta5": "0xE8412F", "gta6": "0x2F7BE8"}

GUION = """Eres el Escritor del canal de YouTube Shorts «{nombre}» ({tema}). Esta vez el vídeo NO lleva dibujos: se monta
con tomas de juego de verdad de la videoteca (abajo). Lo que se ve tiene que ser justo lo que dice la voz: elige para cada
escena la toma que enseña lo que cuentas, y no digas nada que no se vea en ella o que no esté en las fuentes.
Vídeo vertical de {seg_min} a {seg_max} segundos, en {idioma}.
{formato}
Reglas que enganchan:
- Los 2 primeros segundos son el gancho: una frase que abre una pregunta o empieza en mitad de la acción (nada de saludos).
- Frases cortas, una idea por frase. Algo nuevo cada 2 o 3 segundos (el Montador cambia de plano así).
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
  "texto_pantalla": "de 2 a 5 palabras para los 2 primeros segundos", "narracion": "todo lo que dice la voz, entero",
  "escenas": [{escena}],
  "descripcion": "una o dos frases", "hashtags": ["#3 a 5 hashtags del tema"]{fuentes_usadas}}}
Entre {esc_min} y {esc_max} escenas, en orden, que juntas cubran toda la narración."""

FORMATO_UNO = """- Cada escena enseña UNA toma. Varía: no pongas la misma toma en dos escenas seguidas.
- «rotulo» (si quieres): de 1 a 3 palabras grandes que refuerzan lo que se dice («¡MIRA EL AGUA!»)."""
ESCENA_UNO = '{"texto": "las frases exactas de la narración de esta escena", "toma": "código", "rotulo": "opcional"}'

FORMATO_VERSUS = """- Es un GTA 5 contra GTA 6 en pantalla partida: arriba GTA 5 y abajo GTA 6, a la vez.
- Organízalo en 3 o 4 RONDAS. Cada ronda compara UNA cosa que tengan los dos juegos ({parejas}), con una toma de GTA 5
  y otra de GTA 6 de esa misma cosa. La primera escena es el gancho y ya lleva su pareja de tomas.
- En cada ronda di qué se ve en cada juego y quién gana («gana»: "gta5", "gta6" o "empate"). Sé justo: si GTA 5 gana
  en algo, dilo (eso engancha y trae comentarios).
- «rotulo»: el nombre de la ronda, de 1 a 3 palabras («RONDA 1: AGUA»).
- Termina con el marcador y una pregunta: «¿Con cuál te quedas?»."""
ESCENA_VERSUS = ('{"texto": "las frases exactas de esta escena", "gta5": "código de una toma de GTA 5", '
                 '"gta6": "código de una toma de GTA 6", "rotulo": "RONDA 1: AGUA", "gana": "gta6"}')


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
    return [t for t in tomas() if t.get("juego") in juegos]


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
    return len(lista) >= MIN_TOMAS


def catalogo(lista, maximo=30):
    orden = sorted(lista, key=lambda t: (int(t.get("usos") or 0), -float(t.get("calidad") or 0)))[:maximo]
    return "\n".join(f"- {t['id']} [{JUEGOS.get(t.get('juego'), t.get('juego'))}] ({round(float(t.get('segundos') or 0))} s)"
                     f" {', '.join(t.get('etiquetas') or [])}: {t.get('que_se_ve') or t.get('que_pasa') or ''}"[:300]
                     for t in orden)


def creditos(ids):
    """Una línea por vídeo de origen: «🎬 Clip: creador · enlace · licencia Creative Commons (CC BY)»."""
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
        lineas.append(f"🎬 Clip: {t.get('creador', '?')} · {enlace} · licencia Creative Commons (CC BY)")
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
                    "entrada": privado.ahora(), "usos": 0}
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


# ---------- el guion con tomas ----------

def _parecida(lista, juego, texto, evitar=()):
    """La toma que mejor pega con un texto (por sus etiquetas y lo que se ve), mejor si no se acaba de usar."""
    palabras = set(re.findall(r"\w+", _normal(texto)))
    candidatas = [t for t in lista if not juego or t.get("juego") == juego] or lista

    def puntos(t):
        sus = set(re.findall(r"\w+", _normal(" ".join(t.get("etiquetas") or []) + " " + (t.get("que_se_ve") or ""))))
        return (t["id"] not in evitar, len(palabras & sus), -int(t.get("usos") or 0))
    return max(candidatas, key=puntos)


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
        **escritor.medidas(canal))
    ultimo = ""
    for _ in range(2):
        g = ia.preguntar(texto + ultimo, papel="guionista")
        if isinstance(g, list) and g:
            g = g[0]
        try:
            g = _arreglar(g if isinstance(g, dict) else {}, lista, versus)
            break
        except ValueError as e:
            ultimo = f"\n\nEl intento anterior no valía ({e}). Corrígelo."
    else:
        raise gemini.SinIA("el guion con tomas no ha salido con la forma pedida")
    g["titulo"] = str(g["titulo"]).strip()[:100]
    if "#shorts" not in g["titulo"].lower():
        g["titulo"] = f"{g['titulo'][:90]} #shorts"
    g["hashtags"] = [h if str(h).startswith("#") else f"#{h}" for h in (g.get("hashtags") or [])][:5] or ["#gta6"]
    g["descripcion"] = "\n\n".join([str(g.get("descripcion") or "").strip(), "\n".join(creditos(g["tomas_usadas"]))]).strip()
    g["formato"] = "versus_clips" if versus else "clips"
    g["cerebro"] = ia.quien().get("motor", "gemini")
    return g


# ---------- el montaje ----------

def bajar(ids, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    por_id, rutas = {t["id"]: t for t in tomas()}, {}
    for i in sorted(set(ids)):
        nombre = por_id[i]["archivo"]
        almacen.bajar(ESTANTERIA, nombre, carpeta)
        ruta = os.path.join(carpeta, nombre)
        if not os.path.exists(ruta) or clips._segundos(ruta) < 1:
            raise RuntimeError(f"la toma {i} no está en la videoteca")
        rutas[i] = ruta
    return rutas


def _planos(escenas, duraciones):
    """Cada escena en planos de 2-3 s; el primer cambio llega a los 2 s."""
    planos = []
    for n, (e, d) in enumerate(zip(escenas, duraciones)):
        partes, resto = [], d
        if n == 0 and d > PRIMER_CORTE + 0.8:
            partes.append(PRIMER_CORTE)
            resto -= PRIMER_CORTE
        while resto > PLANO_MAX + 0.8:
            partes.append(PLANO_MAX)
            resto -= PLANO_MAX
        partes.append(resto)
        planos += [(n, e, p, k == len(partes) - 1) for k, p in enumerate(partes)]
    return planos


def _texto(carpeta, nombre, texto):
    with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as f:
        f.write(texto)
    return nombre


def _rotulo(carpeta, k, texto, y):
    if not texto:
        return ""
    fuente = f":fontfile={clips.FUENTE}" if os.path.exists(clips.FUENTE) else ""
    archivo = _texto(carpeta, f"rotulo{k}.txt", str(texto).upper()[:28])
    return (f",drawtext=textfile={archivo}{fuente}:fontsize=74:fontcolor=0xFFD43B:borderw=7:bordercolor=black"
            f":x=(w-text_w)/2:y={y}")


def _plano_uno(carpeta, k, ruta, inicio, d, rotulo):
    filtro = ("[0:v]fps=30,split=2[f][p];"
              "[f]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.15[fondo];"
              "[p]scale=1080:1500:force_original_aspect_ratio=decrease[c];"
              f"[fondo][c]overlay=(W-w)/2:(H-h)/2-40{_rotulo(carpeta, k, rotulo, 150)},format=yuv420p[v]")
    salida = os.path.join(carpeta, f"p{k:03d}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-ss", f"{inicio:.2f}", "-i", ruta,
                    "-filter_complex", filtro, "-map", "[v]", "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "20", "-r", "30", salida], cwd=carpeta, check=True)
    return salida


def _plano_versus(carpeta, k, r5, i5, r6, i6, d, rotulo, gana):
    fuente = f":fontfile={clips.FUENTE}" if os.path.exists(clips.FUENTE) else ""
    l5, l6 = _texto(carpeta, "l5.txt", "GTA 5"), _texto(carpeta, "l6.txt", "GTA 6")
    filtro = ("[0:v]fps=30,scale=1080:608:force_original_aspect_ratio=increase,crop=1080:608[a];"
              "[1:v]fps=30,scale=1080:608:force_original_aspect_ratio=increase,crop=1080:608[b];"
              "[2:v][a]overlay=0:250:shortest=1[t];[t][b]overlay=0:1062:shortest=1"
              f",drawbox=x=24:y=270:w=210:h=74:color={COLORES['gta5']}@0.95:t=fill"
              f",drawtext=textfile={l5}{fuente}:fontsize=52:fontcolor=white:x=46:y=281"
              f",drawbox=x=24:y=1082:w=210:h=74:color={COLORES['gta6']}@0.95:t=fill"
              f",drawtext=textfile={l6}{fuente}:fontsize=52:fontcolor=white:x=46:y=1093"
              + _rotulo(carpeta, k, rotulo, 140))
    if gana in ("gta5", "gta6", "empate"):          # al final de la ronda, el ganador
        desde = round(d * 0.45, 2)
        texto = _texto(carpeta, f"gana{k}.txt", "EMPATE" if gana == "empate" else f"GANA {JUEGOS[gana]}")
        if gana != "empate":
            filtro += (f",drawbox=x=0:y={250 if gana == 'gta5' else 1062}:w=1080:h=608:color=0x3BD16F:t=12"
                       f":enable='gte(t,{desde})'")
        filtro += (f",drawtext=textfile={texto}{fuente}:fontsize=80:fontcolor=0x3BD16F:borderw=7:bordercolor=black"
                   f":x=(w-text_w)/2:y=1730:enable='gte(t,{desde})'")
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
        for k, (n, e, d, final) in enumerate(_planos(g["escenas"], durs)):
            rotulo = e.get("rotulo") if k > 0 else None           # en el primer plano manda el gancho
            if versus:
                planos.append(_plano_versus(tmp, k, rutas[e["gta5"]], inicio(e["gta5"], d), rutas[e["gta6"]],
                                            inicio(e["gta6"], d), d, rotulo, e.get("gana") if final else None))
            else:
                planos.append(_plano_uno(tmp, k, rutas[e["toma"]], inicio(e["toma"], d), d, rotulo))
        with open(os.path.join(tmp, "lista.txt"), "w") as f:
            f.writelines(f"file '{p}'\n" for p in planos)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy",
                        "imagen.mp4"], cwd=tmp, check=True)
        if versus:                              # subtítulos en la franja del medio, entre los dos juegos
            subtitulos.escribir_ass(palabras, os.path.join(tmp, "s.ass"), mayus=True, tamano=80, altura=905)
        else:
            subtitulos.escribir_ass(palabras, os.path.join(tmp, "s.ass"), mayus=True, altura=380)
        fuente = f":fontfile={clips.FUENTE}" if os.path.exists(clips.FUENTE) else ""
        filtro = "[0:v]ass=s.ass"
        for n, linea in enumerate(montador._gancho(g.get("texto_pantalla") or g["titulo"]).split("\n")):
            archivo = _texto(tmp, f"gancho{n}.txt", linea)
            filtro += (f",drawtext=textfile={archivo}{fuente}:fontsize=80:fontcolor=white:borderw=8:bordercolor=black"
                       f":x=(w-text_w)/2:y={40 + n * 96 if versus else 120 + n * 100}:enable='lt(t,2.6)'")
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
