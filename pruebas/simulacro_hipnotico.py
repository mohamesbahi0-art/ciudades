"""Simulacro del formato «hipnotico» (bolas de neón con una historia de terror narrada), sin IA: un guion fijo se
limpia, se le pone voz y se dibuja un vídeo de verdad. Comprueba la duración, que hay voz, que el primer fotograma ya
trae el gancho y las bolas (no está vacío), que la imagen cambia de plano cada 3 s como mucho y que el final no se
queda en negro. Con SIMULACRO_GUARDA=<carpeta> deja ahí el vídeo y unos fotogramas para mirarlos.

    python pruebas/simulacro_hipnotico.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
TMP = tempfile.mkdtemp(prefix="simulacro-hipnotico-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)

from bots.central import escritor  # noqa: E402
from bots.estudio import estudio, hipnotico  # noqa: E402

CANAL = {"clave": "terror", "nombre": "prueba", "formato_estudio": "hipnotico", "idioma": "es", "destino": "youtube",
         "voz_estudio": "es-MX-JorgeNeural"}
GUION = {"titulo": "Mi hija habla con alguien bajo su cama 😨 #shorts", "texto_pantalla": "No mires bajo la cama",
         "descripcion": "Una historia para no dormir.", "hashtags": ["#terror", "#historias"],
         "escenas": [
             {"texto": "Anoche mi hija me pidió que mirara debajo de su cama.", "icono": "cama"},
             {"texto": "Me agaché con la linterna del teléfono, medio dormido. Y ahí estaba ella, abrazada a su peluche, "
                       "temblando.", "icono": "telefono"},
             {"texto": "Me susurró: papá, hay alguien en mi cama.", "dibujo": "a child whispering in the dark"},
             {"texto": "Levanté la vista muy despacio. Desde el colchón, mi hija me sonreía con los ojos muy abiertos.",
              "icono": "ojo"},
             {"texto": "Entonces sonó la puerta de casa. Era mi mujer, que volvía con la niña en brazos.", "icono": "puerta"},
             {"texto": "¿Quién me pidió entonces que mirara debajo de la cama?", "icono": "inventado"}]}


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


def numero(orden):
    r = subprocess.run(orden, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def fotograma(video, segundo, ruta):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{segundo:.3f}", "-i", video, "-frames:v", "1", ruta], check=True)
    return ruta


def medir(ruta, recorte=None):
    """(luz media, puntos encendidos de cada mil) de un fotograma o de un trozo suyo (x, y, ancho, alto)."""
    from PIL import Image
    im = Image.open(ruta).convert("L")
    if recorte:
        x, y, w, h = recorte
        im = im.crop((x, y, x + w, y + h))
    h = im.histogram()
    total = sum(h) or 1
    return sum(i * n for i, n in enumerate(h)) / total, 1000 * sum(h[130:]) / total


def distinto(a, b):
    """Cuánto cambia la imagen entre dos fotogramas (0 = iguales), mirándolos en pequeño."""
    from PIL import Image, ImageChops
    x, y = (Image.open(r).convert("L").resize((54, 96)) for r in (a, b))
    h = ImageChops.difference(x, y).histogram()
    return sum(i * n for i, n in enumerate(h)) / (sum(h) or 1)


# 1) El encargo al guionista: terror con gancho inmediato y giro final, y lo que necesita este formato
pedido = hipnotico.encargo(CANAL)
comprobar("giro" in pedido.lower() and "gancho" in pedido.lower() and "icono" in pedido, "el encargo pide gancho inmediato, giro final e icono por escena")
visto = {}
escritor.escribir = lambda canal, lecciones, titulos, **kw: (visto.update(lecciones=lecciones, canal=canal)
                                                              or json.loads(json.dumps(GUION)))
g0 = hipnotico.guionizar(CANAL, "- lección de prueba")
comprobar(pedido in visto["lecciones"] and "lección de prueba" in visto["lecciones"], "el Escritor recibe sus lecciones y el encargo del formato")
comprobar(max(visto["canal"]["segundos"]) <= 40, "se le pide una historia corta (40 s como mucho)")

# 2) El guion, limpio
comprobar(all(len(e["voz"].split()) <= hipnotico.PALABRAS for e in g0["escenas"]) and len(g0["escenas"]) >= 8,
          f"ninguna frase pasa de {hipnotico.PALABRAS} palabras (las largas se parten)")
comprobar(" ".join(e["voz"] for e in g0["escenas"]) == " ".join(e["texto"] for e in GUION["escenas"]), "no se pierde ni una palabra de la historia")
comprobar(g0["texto_pantalla"] == "NO MIRES BAJO LA CAMA" and len(g0["texto_pantalla"]) <= hipnotico.GANCHO, "el gancho va entero y en mayúsculas")
iconos = [e["icono"] for e in g0["escenas"]]
comprobar(all(i in hipnotico.ICONOS for i in iconos) and iconos[0] == "cama" and "inventado" not in iconos,
          "cada escena lleva un icono que el dibujo conoce (el inventado se cambia)")
comprobar(g0["escenas"][-1]["icono"] == "pregunta" and "ojo" in iconos and "puerta" in iconos and iconos[3] == "voz",
          "sin icono, se elige por lo que dice la frase (susurró → voz; ¿quién…? → pregunta)")
largo = hipnotico.limpiar({"texto_pantalla": "Esto es un gancho larguísimo que no cabría nunca entero en la pantalla del móvil",
                           "escenas": [{"voz": "Uno."}, {"voz": "Dos."}]})
comprobar(len(largo["texto_pantalla"]) <= hipnotico.GANCHO and not largo["texto_pantalla"].endswith(("QUE", "EN", "LA", "DEL")),
          "un gancho demasiado largo se corta por una palabra entera")
sin = hipnotico.limpiar({"titulo": "La llamada que nadie debió contestar 😱 #shorts", "escenas": [{"voz": "Uno."}, {"voz": "Dos."}]})
comprobar(sin["texto_pantalla"] == "LA LLAMADA QUE NADIE DEBIÓ CONTESTAR", "sin gancho escrito, sale del título (sin emojis ni #shorts)")
try:
    hipnotico.limpiar({"escenas": [{"voz": "Solo una."}]})
    comprobar(False, "un guion de una sola frase no vale")
except ValueError:
    comprobar(True, "un guion de una sola frase no vale")

# 3) El vídeo de verdad
video, g = estudio.hacer(CANAL, carpeta=os.path.join(TMP, "video"), guion=GUION, avisar=lambda x: print("      " + x))
dur = float(numero(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video]) or 0)
comprobar(18 <= dur <= 45 and abs(dur - g["duracion"]) < 0.5, f"el vídeo dura {dur:.1f} s")
tam = numero(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", video])
comprobar(tam == "1080,1920", "es vertical (1080×1920)")
vol = numero(["ffmpeg", "-hide_banner", "-nostats", "-i", os.path.join(TMP, "video", "voz.mp3"), "-af", "volumedetect", "-f", "null", "-"])
media = float(vol.split("mean_volume:")[1].split("dB")[0]) if "mean_volume:" in vol else -99
comprobar(media > -40 and all(e.get("palabras") for e in g["escenas"]), "hay voz, y cada palabra tiene su momento")
comprobar("audio" in numero(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", video]),
          "el vídeo lleva sonido")

fotos = os.path.join(TMP, "fotos")
os.makedirs(fotos)
f0 = fotograma(video, 0, os.path.join(fotos, "s00.png"))
luz, _ = medir(f0)
comprobar(luz > 6, "el primer fotograma no está vacío")
_, letras = medir(f0, (40, 150, 1000, 330))
comprobar(letras > 60, "el gancho ya está escrito arriba en el primer fotograma")
_, centro = medir(f0, (110, 430, 860, 860))
comprobar(centro > 25, "el aro y las bolas ya están encendidos en el primer fotograma")
f1 = fotograma(video, 0.2, os.path.join(fotos, "s00b.png"))
comprobar(distinto(f0, f1) > 1.0, "desde el primer instante hay algo en movimiento")
comprobar(g["planos"] and max(b - a for a, b in zip([0] + g["planos"], g["planos"] + [g["duracion"]])) <= 3.0,
          f"hay cambio de plano cada 3 s como mucho ({len(g['planos']) + 1} planos)")
cambios = []
for k, corte in enumerate(g["planos"]):
    a = fotograma(video, max(0, corte - 0.12), os.path.join(fotos, f"c{k}a.png"))
    b = fotograma(video, corte + 0.2, os.path.join(fotos, f"c{k}b.png"))
    cambios.append(distinto(a, b))
quieto = distinto(fotograma(video, 1.0, os.path.join(fotos, "q1.png")), fotograma(video, 1.3, os.path.join(fotos, "q2.png")))
comprobar(sum(cambios) / len(cambios) > quieto * 1.25 and min(cambios) > 2.0, "en cada cambio de plano la imagen cambia de verdad")
fin = fotograma(video, dur - 0.25, os.path.join(fotos, "fin.png"))
comprobar(medir(fin)[0] > 6, "el último fotograma no es una pantalla negra (el vídeo vuelve a empezar sin corte)")
for k, s in enumerate((1, 3, dur / 2, dur - 1.2)):
    fotograma(video, s, os.path.join(fotos, f"s{k + 1:02d}.png"))

guarda = os.environ.get("SIMULACRO_GUARDA")
if guarda:
    os.makedirs(guarda, exist_ok=True)
    shutil.copy(video, os.path.join(guarda, "hipnotico.mp4"))
    shutil.copy(os.path.join(TMP, "video", "guion_estudio.json"), os.path.join(guarda, "guion_estudio.json"))
    shutil.copytree(fotos, os.path.join(guarda, "fotos"), dirs_exist_ok=True)
shutil.rmtree(TMP, ignore_errors=True)
print("SIMULACRO DEL FORMATO HIPNÓTICO: TODO BIEN")
