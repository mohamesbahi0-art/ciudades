"""Simulacro del Recolector de clips con Internet Archive, IA, estanterías y subida DE MENTIRA (sin red ni secretos).

1. Solo valen CC BY y CC0: fuera las licencias NC/ND/SA, la «marca de dominio público» y lo filtrado.
2. De un vídeo corto de GTA 6 trae una toma y un momento viral; de uno largo de GTA 5, tomas de varias muestras (sin
   bajarlo entero). Cada toma va limpia a la Videoteca con su crédito (autor, enlace y licencia).
3. El momento traído así sale en su propio Short sin que el dueño haga nada.
4. No repite vídeos ya mirados y para cuando la videoteca está llena.

    python pruebas/simulacro_recolector.py
"""
import asyncio  # noqa: F401
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
TMP = tempfile.mkdtemp(prefix="simulacro-recolector-")
PRIV = os.path.join(TMP, "privado")
ESTANTES = os.path.join(TMP, "estanterias")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIV)
os.environ["PRIVADO"] = PRIV
os.environ["MEMORIA_DIR"] = os.path.join(PRIV, "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)
for k in ("GTA", "TERROR", "CLIPS"):
    os.environ[f"YT_REFRESH_{k}"] = "x"
cfg = json.load(open(os.path.join(PRIV, "config", "canales.json"), encoding="utf-8"))
cfg["canales"]["clips"] = {"nombre": "Clips de prueba", "tipo": "clips", "horas": ["14:00"], "voz": "es-MX-JorgeNeural",
                           "categoria": "20", "tema": "momentos increíbles de GTA"}
json.dump(cfg, open(os.path.join(PRIV, "config", "canales.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

from bots.central import clips, fabrica, recolector, turno, videoteca  # noqa: E402
from bots.comun import almacen, gemini, privado  # noqa: E402
import subir as herr  # noqa: E402


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que, flush=True)
    if not cond:
        sys.exit(1)


def clip_falso(ruta, segundos, tono=0):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                    "-f", "lavfi", "-i", "sine=frequency=300", "-t", str(segundos), "-vf", f"hue=h={tono}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", ruta], check=True)
    return ruta


# --- Internet Archive de mentira ---
CC_BY, CC0 = "https://creativecommons.org/licenses/by/4.0/", "http://creativecommons.org/publicdomain/zero/1.0/"
DOCS = [{"identifier": "gta6-pesca", "title": "You Can Fish in GTA 6", "licenseurl": CC_BY, "creator": "Pescador"},
        {"identifier": "gta5-broll", "title": "GTA V B-Roll Set", "licenseurl": CC0, "creator": "Broll"},
        {"identifier": "gta6-leak", "title": "GTA 6 Leaked videos", "licenseurl": CC0},
        {"identifier": "gta6-nd", "title": "GTA 6 is great", "licenseurl": "https://creativecommons.org/licenses/by-nd/4.0/"},
        {"identifier": "gta6-pdm", "title": "GTA 6 VOD", "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/"}]
VIDEOS = {"gta6-pesca": clip_falso(os.path.join(TMP, "archive", "pesca.mp4"), 20, 40),
          "gta5-broll": clip_falso(os.path.join(TMP, "archive", "broll.mp4"), 200, 160)}
META = {"gta6-pesca": {"files": [{"name": "pesca.mp4", "length": "20.0", "height": "360"}],
                       "metadata": {"creator": "Pescador", "licenseurl": CC_BY, "title": "You Can Fish in GTA 6",
                                    "originalurl": "https://www.youtube.com/watch?v=pesca123"}},
        "gta5-broll": {"files": [{"name": "broll.mp4", "length": "200", "height": "360"},
                                 {"name": "broll_512kb.mp4", "length": "200", "height": "240"}],
                       "metadata": {"creator": ["Broll"], "licenseurl": CC0, "title": "GTA V B-Roll Set"}}}
PEDIDOS = []


def falso_pedir(url, espera=60):
    PEDIDOS.append(url)
    if "advancedsearch" in url:
        return {"response": {"docs": DOCS}}
    ident = url.rsplit("/", 1)[-1]
    return META[ident]


recolector._pedir = falso_pedir
recolector.url_de = lambda ident, nombre: VIDEOS[ident]


def falso_guardar(etiqueta, ruta, nombre=None):
    destino = os.path.join(ESTANTES, etiqueta, nombre or os.path.basename(ruta))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copy(ruta, destino)
    return f"https://example.invalid/{etiqueta}/{os.path.basename(destino)}"


def falso_bajar(etiqueta, nombre, carpeta):
    origen = os.path.join(ESTANTES, etiqueta, nombre)
    if not os.path.exists(origen):
        raise RuntimeError(f"{nombre} no está en {etiqueta}")
    os.makedirs(carpeta, exist_ok=True)
    shutil.copy(origen, os.path.join(carpeta, nombre))
    return os.path.join(carpeta, nombre)


almacen.guardar, almacen.bajar = falso_guardar, falso_bajar

# --- la IA de mentira ---
MIRADAS = {"pesca": 0, "broll": 0}


def falso(texto, imagenes=(), **kw):
    if "Eres el Recolector de clips" in texto:
        if "You Can Fish" in texto:
            MIRADAS["pesca"] += 1
            return {"juego_principal": "gta6",
                    "tomas": [{"desde": 2, "hasta": 10, "juego": "gta6", "etiquetas": ["agua", "naturaleza"],
                               "que_se_ve": "pescando en un muelle al atardecer", "habla_creador": False, "calidad": 90}],
                    "momentos": [{"desde": 5, "hasta": 15, "para": "clips", "juego": "gta6",
                                  "que_pasa": "pesca un pez enorme que casi le tira al agua", "por_que": "nadie lo espera",
                                  "gancho": "¡QUÉ PEZ!", "habla_creador": False, "nota": 95},
                                 {"desde": 1, "hasta": 9, "para": "versus", "juego": "gta6", "que_pasa": "el agua",
                                  "habla_creador": False, "nota": 92}]}
        MIRADAS["broll"] += 1
        return {"juego_principal": "gta5",
                "tomas": [{"desde": 3, "hasta": 15, "juego": "gta5", "etiquetas": ["coches"], "que_se_ve": "un coche por la autopista",
                           "habla_creador": True, "recorte": {"x": 0, "y": 0, "ancho": 0.8, "alto": 1}, "calidad": 85},
                          {"desde": 20, "hasta": 30, "juego": "gta5", "etiquetas": ["ciudad"], "que_se_ve": "borroso",
                           "calidad": 60}], "momentos": []}
    if "Vas a narrar un clip" in texto:
        return {"titulo": "Este pez casi le tira al agua 🎣", "texto_pantalla": "¡QUÉ PEZ!",
                "narracion": "Está pescando tranquilo y de repente el pez tira tan fuerte que casi se cae. ¿Lo habías visto?",
                "descripcion": "La pesca de GTA 6.", "hashtags": ["#gta6"]}
    if "miembro del jurado" in texto:
        return {"voto": "inocente", "nota": 85, "porque": "engancha"}
    if "Escribe los dos alegatos" in texto:
        return {"defensa": "Engancha.", "fiscalia": "Corto.", "fallos_graves": []}
    if "Tres jueces deciden" in texto:
        return {"votos": [{"juez": "gancho", "voto": "sube", "nota": 95, "razon": "bien"},
                          {"juez": "reloj", "voto": "sube", "nota": 94, "razon": "bien"},
                          {"juez": "calle", "voto": "sube", "nota": 93, "razon": "bien"}], "consejo": "así"}
    if "gladiador del Coliseo" in texto:
        carta = re.search(r"Tu carta es «([^»]+)»", texto).group(1)
        return {"titulo": f"El pez que casi le tira al agua en GTA 6 ({carta}) 🎣", "texto": f"Mira el final. {carta}.",
                "hashtags": ["#gta6"], "por_que": "x"}
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
    SUBIDAS.append({"canal": canal, "titulo": titulo, "descripcion": kw.get("descripcion", "")})
    lista = json.load(open(registro)) if os.path.exists(registro) else []
    lista.append({"canal": canal, "archivo": os.path.basename(video), "id": f"VID{len(SUBIDAS)}", "titulo": titulo,
                  "publica": hora})
    os.makedirs(os.path.dirname(registro), exist_ok=True)
    json.dump(lista, open(registro, "w"))
    return 0, "OK", f"VID{len(SUBIDAS)}"


herr.subir = falso_subir

# 1. Qué licencias valen
comprobar([d["identifier"] for d in recolector.buscar()] == ["gta6-pesca", "gta5-broll"],
          "solo CC BY y CC0: fuera lo filtrado, lo que no deja cambiar el vídeo y la «marca de dominio público»")
comprobar(recolector.licencia("https://creativecommons.org/licenses/by-sa/4.0/") is None
          and recolector.licencia("https://creativecommons.org/licenses/by-nc/4.0/") is None,
          "tampoco las que obligan a compartir igual o prohíben el uso comercial")

# 2. La recogida
traidas = recolector.recoger(maximo=5, paso=print)
comprobar(traidas == {"tomas": 6, "momentos": 1, "vistos": 2}, f"trae tomas y un momento de los dos vídeos ({traidas})")
comprobar(MIRADAS == {"pesca": 1, "broll": 4}, f"el corto se mira entero; el largo, en 4 muestras ({MIRADAS})")
tomas = {t["id"]: t for t in videoteca.tomas()}
comprobar(all(t.get("origen") == "archive.org" for t in tomas.values()) and len(tomas) == 7,
          f"todo va a la videoteca ({len(tomas)} tomas)")
pesca = [t for t in tomas.values() if t["creador"] == "Pescador"]
broll = [t for t in tomas.values() if t["creador"] == "Broll"]
comprobar(pesca and all(t["enlace"] == "https://www.youtube.com/watch?v=pesca123" and t["licencia"] == "CC BY" for t in pesca),
          "el crédito lleva al vídeo original del autor")
comprobar(broll and all(t["juego"] == "gta5" and t["licencia"] == "CC0" and not t["sonido"] for t in broll),
          "las de GTA 5 se marcan como GTA 5 y, si hablaba el autor, van sin su voz")
comprobar("dominio público (CC0)" in "\n".join(videoteca.creditos([broll[0]["id"]])),
          "el crédito de un vídeo de dominio público lo dice así")
anchos = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0",
                         os.path.join(ESTANTES, "videoteca", f"{broll[0]['id']}.mp4")], capture_output=True, text=True).stdout
comprobar(anchos.strip().splitlines()[0] == "512", f"el recorte del Recolector quita lo que no es juego ({anchos.strip()})")
momento = next(m for m in clips.momentos() if m.get("origen") == "archive.org")
comprobar(momento["estado"] == "grabado" and momento["en_videoteca"] and momento["para"] == "clips",
          "el momento viral queda listo para su Short, sin grabar nada")
estado = privado.leer(recolector.ESTADO, {})
comprobar(set(estado["vistos"]) == {"gta6-pesca", "gta5-broll"}, "apunta los vídeos que ya ha mirado")
comprobar(recolector.recoger(maximo=5, paso=print)["vistos"] == 0, "no vuelve a mirar los mismos")

# 3. El momento sale en su Short solo
plan, esperan = fabrica.planear(privado.ajustes(), privado.config(), fabrica.revisiones(privado.config()))
comprobar(plan and plan[0][0] == "clips", f"el canal de clips pasa el primero ({[k for k, _ in plan]})")
salida = os.path.join(TMP, "trabajo")
codigo = turno.main(["--canal", "clips", "--salida", salida])
resumen = json.load(open(os.path.join(salida, os.listdir(salida)[0], "resumen.json"), encoding="utf-8"))
comprobar(codigo == 0 and resumen.get("destino_resultado") == "subido", f"el Short se sube ({resumen.get('error')})")
comprobar("🎬 Clip: Pescador · https://www.youtube.com/watch?v=pesca123 · licencia Creative Commons (CC BY)"
          in SUBIDAS[-1]["descripcion"], "con el crédito del autor en la descripción")
comprobar(next(m for m in clips.momentos() if m["codigo"] == momento["codigo"])["estado"] == "usado", "y queda usado")

# 4. Con la videoteca llena, no recoge más
recolector.TOPE_VIDEOTECA = 5
comprobar(recolector.recoger(maximo=5, paso=print) == {"tomas": 0, "momentos": 0, "vistos": 0},
          "con la videoteca llena, para")

shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro del Recolector: todo bien")
