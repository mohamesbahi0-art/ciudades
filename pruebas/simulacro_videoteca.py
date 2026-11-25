"""Simulacro de la Videoteca de juego con IA, voz, estanterías y subida DE MENTIRA (sin red ni secretos).

1. El Archivero pasa por el Portero los clips grabados: guarda limpios los buenos en la videoteca (con su juego y sus
   etiquetas) y descarta el que enseña al creador.
2. Un GTA 5 contra GTA 6 con tomas: pantalla partida (GTA 5 arriba, GTA 6 abajo), rondas y ganador; el guion solo usa
   tomas que existen y del juego que toca; los créditos de los creadores van en la descripción.
3. Un vídeo de noticias de GTA 6 con tomas en vez de dibujos (el Escritor ve las fuentes y el catálogo de tomas).
4. Un canal sin videoteca sigue como siempre.

    python pruebas/simulacro_videoteca.py
"""
import asyncio  # noqa: F401  (la voz de mentira es una corrutina)
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
TMP = tempfile.mkdtemp(prefix="simulacro-videoteca-")
PRIV = os.path.join(TMP, "privado")
ESTANTES = os.path.join(TMP, "estanterias")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIV)
os.environ["PRIVADO"] = PRIV
os.environ["MEMORIA_DIR"] = os.path.join(PRIV, "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)
for k in ("GTA", "TERROR", "VERSUS", "CLIPS"):
    os.environ[f"YT_REFRESH_{k}"] = "x"


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que, flush=True)
    if not cond:
        sys.exit(1)


def clip_falso(ruta, tono, segundos=14, barras=False):
    """Un clip de juego de mentira; cada toma con su color para distinguirlas."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    vf = f"hue=h={tono}" + (",pad=1600:720:160:0:black" if barras else "")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                    "-t", str(segundos), "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-an", ruta], check=True)
    return ruta


# --- configuración: un versus y el canal de noticias con videoteca ---
cfg = json.load(open(os.path.join(PRIV, "config", "canales.json"), encoding="utf-8"))
cfg["canales"]["gta"]["videoteca"] = True
cfg["canales"]["versus"] = {"nombre": "Versus de prueba", "tipo": "versus", "horas": ["13:00", "20:00"], "videoteca": True,
                            "voz": "es-MX-JorgeNeural", "categoria": "20", "tema": "GTA 5 contra GTA 6, punto por punto"}
cfg["canales"]["clips"] = {"nombre": "Clips de prueba", "tipo": "clips", "horas": ["14:00"], "voz": "es-MX-JorgeNeural",
                           "categoria": "20", "tema": "momentos increíbles de GTA"}
json.dump(cfg, open(os.path.join(PRIV, "config", "canales.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# --- la videoteca que ya había y los clips recién grabados por el dueño ---
YA = [("V-1", "gta6", ["coches", "conducir"]), ("V-2", "gta6", ["policía", "persecución"]), ("V-3", "gta6", ["ciudad"]),
      ("V-4", "gta6", ["playa", "agua"]), ("V-5", "gta5", ["coches"]), ("V-6", "gta5", ["policía"])]
tomas = []
for n, (i, juego, etiquetas) in enumerate(YA):
    clip_falso(os.path.join(ESTANTES, "videoteca", f"{i}.mp4"), n * 50)
    tomas.append({"id": i, "archivo": f"{i}.mp4", "juego": juego, "etiquetas": etiquetas, "segundos": 14.0,
                  "que_se_ve": f"toma de {juego} con {', '.join(etiquetas)}", "sonido": False, "usos": 0,
                  "creador": f"Creador {n % 3}", "enlace": f"https://youtu.be/vid{n % 3}?t={n * 10}", "licencia": "CC BY"})
os.makedirs(os.path.join(PRIV, "estado", "clips"), exist_ok=True)
json.dump({"tomas": tomas}, open(os.path.join(PRIV, "estado", "clips", "videoteca.json"), "w", encoding="utf-8"),
          ensure_ascii=False)
BASE = {"creador": "Creador Nuevo", "enlace": "https://youtu.be/nuevo?t=30", "video": "nuevo", "licencia": "CC BY",
        "estado": "grabado", "tipo": "toma", "para": "videoteca", "sale_creador": "no"}
json.dump({"momentos": [
    dict(BASE, codigo="M-1", archivo="M-1.mp4", juego="gta6", tipo="momento", para="clips", etiquetas=["coches"],
         que_pasa="un coche sale volando por un puente", gancho="¡VUELA!", por_que="es una locura", nota=96),
    dict(BASE, codigo="T-1", archivo="T-1.mp4", juego="gta5", etiquetas=["agua"], que_pasa="el agua del puerto", nota=95),
    dict(BASE, codigo="T-2", archivo="T-2.mp4", juego="gta6", etiquetas=["agua"], que_pasa="olas en la playa", nota=94),
    dict(BASE, codigo="T-3", archivo="T-3.mp4", juego="gta6", etiquetas=["armas"], que_pasa="un tiroteo", nota=93)]},
    open(os.path.join(PRIV, "estado", "clips", "para_grabar.json"), "w", encoding="utf-8"), ensure_ascii=False)

from bots.central import clips, reportero, turno, videoteca  # noqa: E402
from bots.comun import almacen, gemini, privado  # noqa: E402
import subir as herr  # noqa: E402


# --- las estanterías de mentira (el buzón trae la grabación del móvil, con bandas negras) ---
def falso_guardar(etiqueta, ruta, nombre=None):
    destino = os.path.join(ESTANTES, etiqueta, nombre or os.path.basename(ruta))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copy(ruta, destino)
    return f"https://example.invalid/{etiqueta}/{os.path.basename(destino)}"


def falso_bajar(etiqueta, nombre, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    origen = os.path.join(ESTANTES, etiqueta, nombre)
    if os.path.exists(origen):
        shutil.copy(origen, os.path.join(carpeta, nombre))
    elif etiqueta == clips.ESTANTERIA:
        clip_falso(os.path.join(carpeta, nombre), 200, barras=True)
    else:
        raise RuntimeError(f"{nombre} no está en {etiqueta}")
    return os.path.join(carpeta, nombre)


almacen.guardar, almacen.bajar = falso_guardar, falso_bajar
reportero.noticias = lambda b, idioma="es", pais="ES", dias=4: [
    {"titulo": f"Noticia de GTA 6 número {i}", "fuente": "Fuente", "fecha": "2026-11-23 10:00", "enlace": ""} for i in range(3)]
reportero.wikipedia = lambda a, idioma="en", maximo=6000: f"Texto de {a}"

# --- la IA de mentira ---
VISTO = {"portero": 0, "ideas": [], "guiones": []}


def falso(texto, imagenes=(), **kw):
    if "Portero de clips" in texto:
        VISTO["portero"] += 1
        if VISTO["portero"] == 4:
            return {"limpio": False, "vale": False, "recorte": None, "habla_creador": True,
                    "problemas": ["la cara del creador en medio"], "que_se_ve": "el creador hablando"}
        return {"limpio": True, "vale": True, "recorte": None, "habla_creador": False, "problemas": [],
                "que_se_ve": "el agua se mueve con olas y reflejos"}
    if "Vas a narrar un clip" in texto:
        return {"titulo": "Este coche VUELA en GTA 6 🚗", "texto_pantalla": "¡VUELA!",
                "narracion": "Este coche sale volando por encima del puente y gira en el aire. ¿Lo habías visto?",
                "descripcion": "Física de locos.", "hashtags": ["#gta6"]}
    if "Propón" in texto:
        VISTO["ideas"].append(texto)
        return {"ideas": [{"idea": f"idea {i}", "titulo": f"Título {i}", "gancho": "gancho"} for i in range(1, 4)]}
    if texto.startswith("Eres la Sala de Ideas"):
        return {"juicios": [{"n": 1, "defensa": "a", "fiscalia": "b", "gancho": 70, "reloj": 70, "calle": 70}]}
    if "Esta vez el vídeo NO lleva dibujos" in texto:
        VISTO["guiones"].append(texto)
        narr = ("¿GTA 6 ha dejado en ridículo a GTA 5? Ronda uno, los coches: en GTA 5 se ven bien, pero en GTA 6 "
                "brillan de verdad. Ronda dos, la policía: en GTA 6 te rodean en segundos. Ronda tres, el agua: "
                "las olas de GTA 6 parecen reales. Tres a cero. ¿Con cuál te quedas?")
        if "pantalla partida" in texto and "Corrígelo" in texto:      # a la segunda, como pide el Cerebro
            narr = ("¿Coches, policía o agua? Tres rondas, un ganador. Ronda uno, los coches: en GTA cinco brillan poco. "
                    "En GTA seis reflejan toda la calle. Gana GTA seis. Ronda dos, la policía: en GTA cinco tarda en "
                    "llegar. En GTA seis te rodean en segundos. Gana GTA seis. Ronda tres, el agua: el puerto de GTA "
                    "cinco sorprende. Las olas de GTA seis salen planas. Gana GTA cinco. GTA seis gana dos a uno. "
                    "¿Con cuál te quedas?")
            escenas = [{"texto": "¿Coches, policía o agua? Tres rondas, un ganador.", "gta5": "V-5", "gta6": "V-1"},
                       {"texto": "Ronda uno, los coches: en GTA cinco brillan poco.",
                        "gta5": "V-5", "gta6": "V-1", "rotulo": "RONDA 1: COCHES"},
                       {"texto": "En GTA seis reflejan toda la calle. Gana GTA seis.",
                        "gta5": "V-5", "gta6": "V-1", "rotulo": "RONDA 1: COCHES", "gana": "gta6"},
                       {"texto": "Ronda dos, la policía: en GTA cinco tarda en llegar.",
                        "gta5": "NO-EXISTE", "gta6": "V-2", "rotulo": "RONDA 2: POLICÍA"},
                       {"texto": "En GTA seis te rodean en segundos. Gana GTA seis.",
                        "gta5": "V-6", "gta6": "V-2", "rotulo": "RONDA 2: POLICÍA", "gana": "gta6"},
                       {"texto": "Ronda tres, el agua: el puerto de GTA cinco sorprende.",
                        "gta5": "V-4", "gta6": "T-2", "rotulo": "RONDA 3: AGUA"},
                       {"texto": "Las olas de GTA seis salen planas. Gana GTA cinco.",
                        "gta5": "T-1", "gta6": "T-2", "rotulo": "RONDA 3: AGUA", "gana": "gta5"},
                       {"texto": "GTA seis gana dos a uno. ¿Con cuál te quedas?", "gta5": "T-1", "gta6": "V-3"}]
            return {"idea": "prueba", "titulo": "GTA 6 contra GTA 5: no hay color 😱",
                    "texto_pantalla": "COCHES, POLICÍA Y AGUA", "narracion": narr, "escenas": escenas,
                    "descripcion": "La comparación.", "hashtags": ["#gta6", "gta5"], "fuentes_usadas": [1]}
        if "pantalla partida" in texto:              # a la primera, escenas largas y todo para GTA 6: se lo devuelven
            escenas = [{"texto": "¿GTA 6 ha dejado en ridículo a GTA 5?", "gta5": "V-5", "gta6": "V-1"},
                       {"texto": "Ronda uno, los coches: en GTA 5 se ven bien, pero en GTA 6 brillan de verdad.",
                        "gta5": "V-5", "gta6": "V-1", "rotulo": "RONDA 1: COCHES", "gana": "gta6"},
                       {"texto": "Ronda dos, la policía: en GTA 6 te rodean en segundos.",
                        "gta5": "NO-EXISTE", "gta6": "V-2", "rotulo": "RONDA 2: POLICÍA", "gana": "gta6"},
                       {"texto": "Ronda tres, el agua: las olas de GTA 6 parecen reales.",
                        "gta5": "V-4", "gta6": "T-2", "rotulo": "RONDA 3: AGUA", "gana": "gta6"},
                       {"texto": "Tres a cero. ¿Con cuál te quedas?", "gta5": "T-1", "gta6": "V-3"}]
        else:
            narr = ("Esto acaba de salir sobre GTA 6 y casi nadie lo ha visto. La ciudad está llena de vida. "
                    "Los coches se ensucian y se rompen de verdad. La policía te persigue por toda la costa. "
                    "Y en la playa, el agua se mueve como en la vida real. ¿Qué es lo que más ganas te da?")
            escenas = [{"texto": "Esto acaba de salir sobre GTA 6 y casi nadie lo ha visto.", "toma": "V-3"},
                       {"texto": "La ciudad está llena de vida.", "toma": "V-3", "rotulo": "¡MIRA!"},
                       {"texto": "Los coches se ensucian y se rompen de verdad.", "toma": "V-1"},
                       {"texto": "La policía te persigue por toda la costa.", "toma": "INVENTADA"},
                       {"texto": "Y en la playa, el agua se mueve como en la vida real.", "toma": "V-4"},
                       {"texto": "¿Qué es lo que más ganas te da?", "toma": "T-2"}]
        return {"idea": "prueba", "titulo": "GTA 6 contra GTA 5: no hay color 😱", "texto_pantalla": "¿GTA 6 GANA?",
                "narracion": narr, "escenas": escenas, "descripcion": "La comparación.", "hashtags": ["#gta6", "gta5"],
                "fuentes_usadas": [1]}
    if "miembro del jurado" in texto:
        return {"voto": "inocente", "nota": 85, "porque": "engancha"}
    if "Escribe los dos alegatos" in texto:
        return {"defensa": "Engancha.", "fiscalia": "Podría ser más corto.", "fallos_graves": []}
    if "Tres jueces deciden" in texto:
        return {"votos": [{"juez": "gancho", "voto": "sube", "nota": 95, "razon": "bien"},
                          {"juez": "reloj", "voto": "sube", "nota": 94, "razon": "bien"},
                          {"juez": "calle", "voto": "sube", "nota": 93, "razon": "bien"}], "consejo": "así"}
    if "gladiador del Coliseo" in texto:
        carta = re.search(r"Tu carta es «([^»]+)»", texto).group(1)
        return {"titulo": f"GTA 6 humilla a GTA 5 en todo ({carta}) 🔥", "texto": f"Mira la ronda tres. {carta}.",
                "hashtags": ["#gta6", "#gta5"], "por_que": "x"}
    if "Coliseo, combate" in texto and "SALIDA A" in texto:
        a = json.loads(texto.split("SALIDA A: ", 1)[1].split("\n", 1)[0])
        b = json.loads(texto.split("SALIDA B: ", 1)[1].split("\n", 1)[0])
        return {"critica_a_b": "x", "critica_b_a": "y", "a": a, "b": b}
    if "Juez ciego" in texto:
        return {"ganador": 1, "razon": "engancha más", "nota_1": 92, "nota_2": 80}
    raise AssertionError("pregunta inesperada: " + texto[:100])


gemini.preguntar = falso


async def falsa_voz(texto, voz, velocidad, tono, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    palabras = texto.split()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220",
                    "-t", f"{len(palabras) * 0.32 + 0.5:.2f}", "-c:a", "libmp3lame", os.path.join(carpeta, "voz.mp3")],
                   check=True)
    json.dump([{"palabra": p, "inicio": i * 0.32, "fin": i * 0.32 + 0.28} for i, p in enumerate(palabras)],
              open(os.path.join(carpeta, "palabras.json"), "w", encoding="utf-8"), ensure_ascii=False)


turno.locutor.generar = falsa_voz
turno.locutor.apretar = lambda carpeta, **kw: 0.0
SUBIDAS = []


def falso_subir(canal, video, titulo, hora, registro, **kw):
    SUBIDAS.append({"canal": canal, "video": video, "titulo": titulo, "descripcion": kw.get("descripcion", "")})
    lista = json.load(open(registro)) if os.path.exists(registro) else []
    lista.append({"canal": canal, "archivo": os.path.basename(video), "id": f"VID{len(SUBIDAS)}", "titulo": titulo,
                  "publica": hora})
    os.makedirs(os.path.dirname(registro), exist_ok=True)
    json.dump(lista, open(registro, "w"))
    return 0, "OK", f"VID{len(SUBIDAS)}"


herr.subir = falso_subir


def momento(codigo):
    return next(m for m in clips.momentos() if m["codigo"] == codigo)


def color(video, segundo, x, y):
    from PIL import Image
    foto = os.path.join(TMP, "foto.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(segundo), "-i", video, "-frames:v", "1", foto],
                   check=True)
    return Image.open(foto).convert("RGB").getpixel((x, y))


def turno_de(clave):
    salida = os.path.join(TMP, f"trabajo-{clave}")
    codigo = turno.main(["--canal", clave, "--salida", salida])
    carpeta = os.path.join(salida, os.listdir(salida)[0])
    resumen = json.load(open(os.path.join(carpeta, "resumen.json"), encoding="utf-8"))
    videos = [os.path.join(carpeta, f) for f in os.listdir(carpeta) if f.endswith(".mp4")]
    guion = json.load(open(os.path.join(carpeta, "guion.json"), encoding="utf-8"))
    return codigo, resumen, videos, guion


# 1. El Archivero
guardados = videoteca.archivar()
comprobar(guardados == 3, f"el Archivero guarda limpios los 3 clips buenos ({guardados})")
comprobar(momento("M-1")["estado"] == "grabado" and momento("M-1").get("en_videoteca"),
          "un momento viral queda en la videoteca y sigue esperando su propio Short")
comprobar(momento("T-1")["estado"] == "en_videoteca" and momento("T-2")["estado"] == "en_videoteca",
          "las tomas grabadas quedan en la videoteca")
comprobar(momento("T-3")["estado"] == "descartado", "el clip donde sale el creador se descarta")
nuevas = {t["id"]: t for t in videoteca.tomas()}
comprobar({"T-1", "T-2"} <= set(nuevas) and nuevas["T-1"]["juego"] == "gta5" and "agua" in nuevas["T-1"]["etiquetas"],
          "cada toma nueva lleva su juego y sus etiquetas")
comprobar(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0",
                          os.path.join(ESTANTES, "videoteca", "T-1.mp4")], capture_output=True, text=True).stdout.strip()
          == "1280", "la toma se guarda sin las bandas negras del móvil")
comprobar(videoteca.parejas(videoteca.tomas()) == ["agua", "coches", "policía"],
          f"parejas para el versus: {videoteca.parejas(videoteca.tomas())}")

# 1b. Las tomas de antes del detector de logos se repasan: la del logo se guarda otra vez, ya sin él
logo = os.path.join(ESTANTES, "videoteca", "V-9.mp4")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x360:rate=30", "-t", "8",
                "-vf", "crop=640:360:'mod(t*160,640)':0,drawbox=x=560:y=10:w=64:h=44:color=white:t=fill,"
                "drawbox=x=574:y=20:w=36:h=24:color=black:t=fill", "-c:v", "libx264", "-preset", "ultrafast", "-an", logo],
               check=True)
indice = json.load(open(os.path.join(PRIV, "estado", "clips", "videoteca.json"), encoding="utf-8"))
indice["tomas"].append({"id": "V-9", "archivo": "V-9.mp4", "juego": "gta5", "etiquetas": ["armas"], "segundos": 8.0,
                        "que_se_ve": "toma con el logo del autor", "sonido": False, "usos": 0, "creador": "Logo",
                        "enlace": "https://youtu.be/logo", "licencia": "CC BY"})
json.dump(indice, open(os.path.join(PRIV, "estado", "clips", "videoteca.json"), "w", encoding="utf-8"), ensure_ascii=False)
repasadas = videoteca.repasar_marcas(paso=print)
marcadas = {t["id"]: t.get("marcas") for t in videoteca.tomas()}
ancho = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0", logo],
                       capture_output=True, text=True).stdout.strip()
comprobar(repasadas == 1 and marcadas["V-9"] == "quitadas" and int(ancho) < 640,
          f"la toma con logo se repasa y se guarda sin él ({repasadas}, {ancho} px)")
comprobar(all(m for m in marcadas.values()), "todas las tomas quedan repasadas")

# 2. GTA 5 contra GTA 6 con tomas
codigo, resumen, videos, guion = turno_de("versus")
comprobar(codigo == 0 and resumen.get("formato") == "versus_clips" and resumen.get("destino_resultado") == "subido",
          f"el versus con clips se hace y se sube ({resumen.get('error')})")
comprobar(all(videoteca.juego_de(nuevas.get(e["gta5"]) or {"juego": "gta5"}) == "gta5" for e in guion["escenas"])
          and all(e["gta5"] in {t["id"] for t in videoteca.tomas() if t["juego"] == "gta5"} for e in guion["escenas"]),
          "en la mitad de GTA 5 solo van tomas de GTA 5 (las que no existían se cambian)")
comprobar("pantalla partida" in VISTO["guiones"][0] and "agua, coches, policía" in VISTO["guiones"][0],
          "el Escritor sabe qué parejas hay")
comprobar("TOMAS DE JUEGO DISPONIBLES" in VISTO["ideas"][0], "la Sala de Ideas propone ideas con las tomas que hay")
video = videos[0]
comprobar(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip() == "1080,1920",
          "el vídeo sale en 1080x1920")
if os.environ.get("SIMULACRO_GUARDAR"):           # para mirar los fotogramas a mano
    os.makedirs(os.environ["SIMULACRO_GUARDAR"], exist_ok=True)
    shutil.copy(video, os.path.join(os.environ["SIMULACRO_GUARDAR"], "versus.mp4"))
comprobar(len(VISTO["guiones"]) >= 2 and "pasan de 10 palabras" in VISTO["guiones"][1]
          and "tienen que ser 3" not in VISTO["guiones"][1],
          "un guion con escenas de más de 10 palabras se devuelve al Escritor con el fallo")
comprobar(all(len(re.findall(r"\w+", e["texto"])) <= 10 for e in guion["escenas"])
          and sum(1 for e in guion["escenas"] if e.get("gana")) == 3,
          "el versus sale con 3 rondas y 10 palabras de voz como mucho por escena " + str([(len(re.findall(r"\w+", e["texto"])), e.get("gana")) for e in guion["escenas"]]))
comprobar(videoteca.marcador(guion["escenas"])[2::2] == [(0, 1), (0, 2), (1, 2)]
          and videoteca.veredicto(guion["escenas"]) == "GTA 6 GANA 2-1",
          f"el marcador sube ronda a ronda y da el veredicto ({videoteca.veredicto(guion['escenas'])})")
comprobar(25 <= resumen["segundos"] <= 30, f"dura entre 25 y 30 s ({resumen['segundos']})")
planos = videoteca._planos(guion["escenas"], [2.6, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2])
comprobar(max(p[2] for p in planos) <= 2.3 and planos[0][2] < 2, "cambio de plano cada 2 s o menos, el primero antes del 2")
grande, pequeno = color(video, 0.2, 392, 300), color(video, 3.0, 392, 300)
comprobar(grande[0] > 180 and grande[2] < 90 and not (pequeno[0] > 180 and pequeno[2] < 90),
          f"segundo 0: la etiqueta de cada juego sale en grande {grande}")
marco = color(video, 8.4, 6, 1300)                # al acabar la ronda 1, marco verde en la mitad que gana (GTA 6)
comprobar(marco[1] > 150 and marco[0] < 120, f"la ronda termina señalando al ganador {marco}")
rojo, azul = color(video, 3.0, 30, 300), color(video, 3.0, 30, 1112)
comprobar(rojo[0] > 180 and rojo[2] < 90 and azul[2] > 180 and azul[0] < 90,
          f"pantalla partida: rótulo rojo de GTA 5 arriba {rojo} y azul de GTA 6 abajo {azul}")
desc = SUBIDAS[-1]["descripcion"]
comprobar(desc.count("🎬 Clip:") >= 2 and "Creador Nuevo" in desc, "la descripción lleva el crédito de cada creador")
usos = {t["id"]: t.get("usos") for t in videoteca.tomas()}
comprobar(all(usos[i] == 1 for i in guion["tomas_usadas"]), "cada toma usada apunta su uso (para variar la próxima vez)")

# 3. Noticias de GTA 6 con tomas en vez de dibujos
codigo, resumen, videos, guion = turno_de("gta")
comprobar(codigo == 0 and resumen.get("formato") == "clips", f"las noticias van con clips ({resumen.get('error')})")
comprobar(all(e["toma"] in {t["id"] for t in videoteca.tomas() if t["juego"] == "gta6"} for e in guion["escenas"]),
          "solo tomas de GTA 6 en un canal de GTA 6")
comprobar("FUENTES" in VISTO["guiones"][-1] and "pantalla partida" not in VISTO["guiones"][-1],
          "el Escritor de noticias ve las fuentes y el catálogo de tomas")
comprobar(not any("dibujo" in e for e in guion["escenas"]), "ni un dibujo")
comprobar("enseñar ya la cosa de la que habla el título" in VISTO["guiones"][-1],
          "al Escritor se le pide que la primera toma enseñe ya la cosa del título")
if os.environ.get("SIMULACRO_GUARDAR"):
    shutil.copy(videos[0], os.path.join(os.environ["SIMULACRO_GUARDAR"], "gta.mp4"))

# 3b. El momento viral, ya limpio en la videoteca, se convierte en su Short (sin volver a pasar por el Portero)
antes = VISTO["portero"]
codigo, resumen, videos, guion = turno_de("clips")
comprobar(codigo == 0 and resumen.get("formato") == "clip" and resumen.get("destino_resultado") == "subido"
          and VISTO["portero"] == antes, f"el momento sale de la videoteca y se sube ({resumen.get('error')})")
comprobar(momento("M-1")["estado"] == "usado" and "🎬 Clip: Creador Nuevo" in SUBIDAS[-1]["descripcion"],
          "queda usado y con el crédito en la descripción")

# 4. Sin videoteca, como siempre
comprobar(not videoteca.suficientes(privado.canal("terror")), "un canal sin videoteca sigue con sus dibujos")

# 5. Dos rondas tocan la videoteca a la vez: no se pierde ninguna toma ni ningún uso
junto = privado.fusionar("estado/clips/videoteca.json",
                         {"tomas": [{"id": "A", "usos": 3}, {"id": "B", "usos": 1}]},
                         {"tomas": [{"id": "A", "usos": 2, "ultimo_uso": "x"}, {"id": "C", "usos": 0}]})
por = {t["id"]: t for t in junto["tomas"]}
comprobar(set(por) == {"A", "B", "C"} and por["A"]["usos"] == 3, "al juntar dos versiones no se pierde nada")

shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro de la videoteca: todo bien")
