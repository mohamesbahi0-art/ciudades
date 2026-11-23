"""Simulacro del Montador de clips con IA, voz y subida DE MENTIRA (sin red ni secretos).

Un clip grabado «con el móvil» (con bandas negras y algo del creador en un borde) pasa por todo el turno: el Portero de
clips lo recorta y le quita el sonido del creador, el Escritor lo narra mirando 3 fotos, el Jurado popular lo vota, el
Juzgado lo juzga (sabiendo que es un clip CC BY), el Coliseo pelea su salida y se sube con el crédito del creador en la
descripción (y en ningún otro sitio). Después: un clip donde el creador sale en medio se descarta, y la fábrica solo hace
el canal de clips cuando hay un clip grabado (y entonces va el primero).

    python pruebas/simulacro_clips.py
"""
import asyncio
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
TMP = tempfile.mkdtemp(prefix="simulacro-clips-")
PRIV = os.path.join(TMP, "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIV)
os.environ["PRIVADO"] = PRIV
os.environ["MEMORIA_DIR"] = os.path.join(PRIV, "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)
for k in ("GTA", "TERROR", "CLIPS"):
    os.environ[f"YT_REFRESH_{k}"] = "x"

cfg = json.load(open(os.path.join(PRIV, "config", "canales.json"), encoding="utf-8"))
cfg["canales"]["clips"] = {"nombre": "Clips de prueba", "tipo": "clips", "horas": ["14:00", "18:00", "21:00"],
                           "voz": "es-MX-JorgeNeural", "categoria": "20", "tema": "momentos increíbles de GTA"}
json.dump(cfg, open(os.path.join(PRIV, "config", "canales.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
BASE = {"creador": "Creador De Prueba", "enlace": "https://youtu.be/abc123?t=10", "video": "abc123", "para": "clips",
        "que_pasa": "un coche sale volando por encima de un puente", "por_que": "es una locura",
        "gancho": "¡VUELA!", "licencia": "CC BY", "habla_creador": False}
os.makedirs(os.path.join(PRIV, "estado", "clips"), exist_ok=True)
json.dump({"momentos": [dict(BASE, codigo="C-001", estado="grabado", archivo="C-001.mp4", nota=95),
                        dict(BASE, codigo="C-002", estado="grabado", archivo="C-002.mp4", nota=91),
                        dict(BASE, codigo="C-003", estado="por_grabar", nota=99)]},
          open(os.path.join(PRIV, "estado", "clips", "para_grabar.json"), "w", encoding="utf-8"), ensure_ascii=False)

from bots.central import clips, fabrica, turno  # noqa: E402
from bots.comun import almacen, gemini, privado  # noqa: E402
import subir as herr  # noqa: E402


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que, flush=True)
    if not cond:
        sys.exit(1)


# --- el buzón: un clip «grabado con el móvil» (1280x720 con bandas negras a los lados y sonido) ---
NO_ESTANTERIA = set()          # clips que solo están en su rama temporal


def falso_bajar(etiqueta, nombre, carpeta):
    if nombre in NO_ESTANTERIA:
        raise RuntimeError("no está en la estantería")
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, nombre)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=330", "-t", "12", "-vf", "pad=1600:720:160:0:black",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", ruta], check=True)
    return ruta


almacen.bajar = falso_bajar
almacen.guardar = lambda etiqueta, ruta, nombre=None: f"https://example.invalid/{etiqueta}/{nombre or os.path.basename(ruta)}"

# --- la IA de mentira ---
MODO = {"portero": "recortar"}
VISTO = {"portero_video": 0, "fotos_guion": [], "abogados": "", "guion": ""}


def falso(texto, imagenes=(), **kw):
    if "Portero de clips" in texto:
        if kw.get("video"):
            VISTO["portero_video"] += 1
        if MODO["portero"] == "descartar":
            return {"limpio": False, "recorte": None, "vale": False, "habla_creador": True,
                    "problemas": ["la cara del creador en el centro"], "que_se_ve": "el creador hablando a cámara"}
        return {"limpio": False, "recorte": {"x": 0, "y": 0, "ancho": 0.8, "alto": 1}, "vale": True,
                "habla_creador": True, "problemas": ["webcam abajo a la derecha"], "que_se_ve": "un coche vuela"}
    if "Vas a narrar un clip" in texto:
        VISTO["fotos_guion"].append(len(imagenes))
        VISTO["guion"] = texto
        return {"titulo": "Este coche VUELA en GTA 6 🚗💨", "texto_pantalla": "¡VUELA!",
                "narracion": ("Este coche acaba de salir volando por encima del puente. Mira cómo gira en el aire antes "
                              "de caer al agua. Nadie sabía que la física de GTA 6 llegaba a tanto. ¿Lo habías visto?"),
                "descripcion": "La física de GTA 6 es una locura.", "hashtags": ["#gta6", "gta", "#gtavi"]}
    if "miembro del jurado" in texto:
        return {"voto": "inocente", "nota": 85, "porque": "engancha"}
    if "Escribe los dos alegatos" in texto:
        VISTO["abogados"] = texto
        return {"defensa": "Engancha desde el segundo uno.", "fiscalia": "Podría ser más corto.", "fallos_graves": []}
    if "Tres jueces deciden" in texto:
        return {"votos": [{"juez": "gancho", "voto": "sube", "nota": 96, "razon": "bien"},
                          {"juez": "reloj", "voto": "sube", "nota": 94, "razon": "bien"},
                          {"juez": "calle", "voto": "sube", "nota": 93, "razon": "bien"}], "consejo": "así"}
    if "gladiador del Coliseo" in texto:
        carta = re.search(r"Tu carta es «([^»]+)»", texto).group(1)
        return {"titulo": f"Nadie esperaba esto en GTA 6 ({carta}) 😱", "texto": f"Mira el final. {carta}.",
                "hashtags": ["#gta6", "#gtavi"], "por_que": "x"}
    if "Coliseo, combate" in texto and "SALIDA A" in texto:
        a = json.loads(texto.split("SALIDA A: ", 1)[1].split("\n", 1)[0])
        b = json.loads(texto.split("SALIDA B: ", 1)[1].split("\n", 1)[0])
        return {"critica_a_b": "flojo", "critica_b_a": "largo", "a": a, "b": b}
    if "Juez ciego" in texto:
        return {"ganador": 1, "razon": "engancha más", "nota_1": 92, "nota_2": 80}
    raise AssertionError("pregunta inesperada: " + texto[:100])


gemini.preguntar = falso


# --- la voz de mentira (8 s de tono y sus palabras) ---
async def falsa_voz(texto, voz, velocidad, tono, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220", "-t", "8",
                    "-c:a", "libmp3lame", os.path.join(carpeta, "voz.mp3")], check=True)
    palabras = [{"palabra": p, "inicio": i * 0.35, "fin": i * 0.35 + 0.3} for i, p in enumerate(texto.split()[:22])]
    json.dump(palabras, open(os.path.join(carpeta, "palabras.json"), "w", encoding="utf-8"), ensure_ascii=False)


turno.locutor.generar = falsa_voz
turno.locutor.apretar = lambda carpeta, **kw: 0.0

# --- la subida de mentira ---
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


def medidas(ruta):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", ruta], capture_output=True, text=True)
    return r.stdout.strip()


# 1. Las piezas sueltas: bandas negras, recortes que valen y que no
prueba = falso_bajar("x", "suelto.mp4", os.path.join(TMP, "suelto"))
comprobar(clips.bandas(prueba) == "1280:720:160:0", f"quita las bandas negras del móvil ({clips.bandas(prueba)})")
comprobar(clips._recorte_valido({"x": 0, "y": 0, "ancho": 0.8, "alto": 1}) is not None, "un recorte de un borde vale")
comprobar(clips._recorte_valido({"x": 0.3, "y": 0.3, "ancho": 0.3, "alto": 0.3}) is None,
          "un recorte que deja muy poco juego no vale")
comprobar(clips.listo_para("clips")["codigo"] == "C-001", "elige el clip grabado con más nota (no el que falta grabar)")
cortado = clips.cortar(prueba, {"desde": 2, "hasta": 7})
comprobar(abs(clips._segundos(cortado) - 5) < 0.3, f"si el móvil no pudo recortar, la fábrica corta el trozo ({clips._segundos(cortado):.1f} s)")
comprobar(clips.cortar(prueba, None) == prueba, "sin corte, el clip se queda como está")

# 2. Un turno entero con un clip que hay que recortar
salida = os.path.join(TMP, "trabajo")
codigo = turno.main(["--canal", "clips", "--salida", salida])
carpeta = os.path.join(salida, os.listdir(salida)[0])
resumen = json.load(open(os.path.join(carpeta, "resumen.json"), encoding="utf-8"))
comprobar(codigo == 0 and resumen.get("resultado") == "hecho", f"el turno del clip termina bien ({resumen.get('error')})")
comprobar(VISTO["portero_video"] == 1, "el Portero mira el clip entero con su sonido")
comprobar(VISTO["fotos_guion"][:1] == [3], f"el Escritor narra mirando 3 fotos ({VISTO['fotos_guion']})")
comprobar("no nombres a nadie" in VISTO["guion"] and "Creador De Prueba" not in VISTO["guion"],
          "la narración no nombra al creador")
comprobar("CC BY" in VISTO["abogados"], "el Juzgado sabe que es un clip CC BY (fallo grave si se ve al creador)")
videos = [f for f in os.listdir(carpeta) if f.endswith(".mp4")]
comprobar(len(videos) == 1 and medidas(os.path.join(carpeta, videos[0])) == "1080,1920", "el Short sale en 1080x1920")
comprobar(len(SUBIDAS) == 1 and resumen.get("destino_resultado") == "subido", "se sube a YouTube")
desc = SUBIDAS[0]["descripcion"]
comprobar("🎬 Clip: Creador De Prueba · https://youtu.be/abc123?t=10" in desc,
          "la descripción lleva el crédito del creador con su enlace")
comprobar(resumen.get("coliseo") and "Nadie esperaba" in SUBIDAS[0]["titulo"],
          "el Coliseo ha peleado la salida y el crédito sigue ahí")
m1 = momento("C-001")
comprobar(m1["estado"] == "usado" and m1.get("nota_juzgado") == resumen.get("nota"), "el clip queda como usado, con su nota")
diario = json.load(open(os.path.join(PRIV, "memoria", "portero_clips.json"), encoding="utf-8")).get("diario", [])
comprobar(diario and diario[-1].get("datos", diario[-1]).get("recorte") is not False,
          "el Portero de clips apunta en su cuaderno lo que ha hecho")

# 3. Un clip donde el creador sale en medio: se descarta y no se sube nada
MODO["portero"] = "descartar"
codigo = turno.main(["--canal", "clips", "--salida", os.path.join(TMP, "trabajo2")])
m2 = momento("C-002")
comprobar(codigo == 0 and m2["estado"] == "descartado" and "creador" in m2.get("motivo", ""),
          "si sale el creador en medio, el clip se descarta")
comprobar(len(SUBIDAS) == 1, "y no se sube nada")

# 4. La fábrica: sin clip grabado, el canal de clips espera; con clip, va el primero
plan, esperan = fabrica.planear(privado.ajustes(), privado.config(), fabrica.revisiones(privado.config()))
comprobar("clips" not in [k for k, _ in plan] and "grabes un clip" in esperan.get("clips", ""),
          f"sin clip grabado, el canal de clips espera ({esperan.get('clips')})")
clips.marcar("C-003", estado="grabado", archivo="C-003.mp4")
plan, esperan = fabrica.planear(privado.ajustes(), privado.config(), fabrica.revisiones(privado.config()))
comprobar(plan and plan[0][0] == "clips", f"con un clip grabado, ese canal va el primero ({[k for k, _ in plan]})")

# 5. Dos robots tocan la lista a la vez: gana lo más avanzado de cada momento
suyo = {"momentos": [dict(BASE, codigo="C-009", estado="grabado", archivo="a.mp4", nota=90)]}
nuestro = {"momentos": [dict(BASE, codigo="C-009", estado="usado", nota=90, suspensos=1),
                        dict(BASE, codigo="C-010", estado="por_grabar", nota=93)]}
junto = privado.fusionar("estado/clips/para_grabar.json", suyo, nuestro)
c9 = next(m for m in junto["momentos"] if m["codigo"] == "C-009")
comprobar(c9["estado"] == "usado" and c9["archivo"] == "a.mp4" and len(junto["momentos"]) == 2,
          "al juntar dos versiones de la lista no se pierde nada")

# 6. El viaje del clip por su rama temporal: el Comisario la sube y la fábrica la usa y la borra
origen = os.path.join(TMP, "origen.git")
subprocess.run(["git", "init", "-q", "--bare", origen], check=True)
subprocess.run(["git", "-C", PRIV, "init", "-q"], check=True)
subprocess.run(["git", "-C", PRIV, "remote", "add", "origin", origen], check=True)


def subir_rama(rama, archivo, ruta):
    """Lo que hace el Comisario (RONDA.md, k): un commit suelto con solo el clip, empujado a su rama."""
    git = ["git", "-C", PRIV, "-c", "user.name=bot", "-c", "user.email=bot@example.invalid"]
    blob = subprocess.run(git + ["hash-object", "-w", ruta], capture_output=True, text=True, check=True).stdout.strip()
    arbol = subprocess.run(git + ["mktree"], input=f"100644 blob {blob}\t{archivo}\n", capture_output=True, text=True,
                           check=True).stdout.strip()
    commit = subprocess.run(git + ["commit-tree", arbol, "-m", f"clip {archivo}"], capture_output=True, text=True,
                            check=True).stdout.strip()
    subprocess.run(git + ["push", "-q", "origin", f"{commit}:refs/heads/{rama}"], check=True)


def ramas_remotas():
    r = subprocess.run(["git", "-C", origen, "for-each-ref", "--format=%(refname:short)", "refs/heads/buzon/"],
                       capture_output=True, text=True)
    return sorted(r.stdout.split())


NO_ESTANTERIA.add("C-004.mp4")
grabado = falso_bajar("x", "grabacion.mp4", os.path.join(TMP, "movil"))
subir_rama("buzon/C-004", "C-004.mp4", grabado)
open(os.path.join(TMP, "prueba.txt"), "w").write("prueba")
subir_rama("buzon/prueba", "prueba.txt", os.path.join(TMP, "prueba.txt"))
datos = json.load(open(os.path.join(PRIV, "estado", "clips", "para_grabar.json"), encoding="utf-8"))
datos["momentos"].append(dict(BASE, codigo="C-004", estado="grabado", archivo="C-004.mp4", rama="buzon/C-004", nota=92))
json.dump(datos, open(os.path.join(PRIV, "estado", "clips", "para_grabar.json"), "w", encoding="utf-8"), ensure_ascii=False)
ruta = clips.bajar(momento("C-004"), os.path.join(TMP, "bajado"))
comprobar(os.path.getsize(ruta) == os.path.getsize(grabado), "el clip llega a la fábrica desde su rama temporal")
comprobar(clips.limpiar_ramas() == 1 and ramas_remotas() == ["buzon/C-004"],
          f"la fábrica borra las ramas que no son de ningún clip pendiente ({ramas_remotas()})")
clips.descartar(momento("C-004"), "prueba")
comprobar(ramas_remotas() == [], "cuando el clip termina, su rama se borra")

shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro de clips: todo bien")
