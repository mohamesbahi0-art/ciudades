"""Simulacro de la fábrica: una ronda completa con IA, dibujos, subidas y almacén DE MENTIRA (sin secretos; solo la voz usa internet).
Sirve para pillar fallos del código antes de que llegue la ronda de verdad. Lo lanza GitHub en cada cambio de bots/ o
herramientas/ (simulacro.yml) y también se puede lanzar a mano:

    PRIVADO=<carpeta con config/ de ejemplo> python pruebas/simulacro.py --solo gta,barrio-1

Usa los datos de ejemplo de pruebas/privado_ejemplo/ (sin nada privado).
"""
import json, os, sys, datetime as dt
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("PRIVADO", os.path.join(RAIZ, "pruebas", "privado_ejemplo"))
os.environ.setdefault("MEMORIA_DIR", os.path.join(os.environ["PRIVADO"], "memoria"))
for k in ("GTA", "CURIOS", "VERSUS", "TERROR", "SOBSHORTS", "NIVSHORTS", "MAPAS", "CLIPS"):
    os.environ[f"YT_REFRESH_{k}"] = "x"
from PIL import Image
from bots.comun import gemini, almacen
from bots.central import dibujante, reportero, subidor, fabrica, turno
import subir as herr

JUICIOS = []
def falso_gemini(texto, imagenes=(), **kw):
    if "Propón" in texto:
        return {"ideas": [{"idea": f"idea {i}", "titulo": f"Título {i}", "gancho": "gancho"} for i in range(1, 4)]}
    if texto.startswith("Eres la Sala de Ideas"):
        return {"juicios": [{"n": 1, "defensa": "a", "fiscalia": "b", "gancho": 50, "reloj": 50, "calle": 50},
                            {"n": 2, "defensa": "a", "fiscalia": "b", "gancho": 80, "reloj": 70, "calle": 75}]}
    if "Escribe los dos alegatos" in texto:
        return {"defensa": "Va a funcionar porque...", "fiscalia": "No funcionará porque...", "fallos_graves": []}
    if "Tres jueces deciden" in texto:
        JUICIOS.append(1)
        if len(JUICIOS) == 1:
            return {"votos": [{"juez": "gancho", "voto": "no", "nota": 40, "razon": "flojo"}, {"juez": "reloj", "voto": "no", "nota": 42, "razon": "x"}, {"juez": "calle", "voto": "sube", "nota": 60, "razon": "y"}], "consejo": "gancho más fuerte"}
        return {"votos": [{"juez": "gancho", "voto": "sube", "nota": 70, "razon": "bien"}, {"juez": "reloj", "voto": "sube", "nota": 66, "razon": "x"}, {"juez": "calle", "voto": "no", "nota": 50, "razon": "y"}], "consejo": "ok"}
    if "La Sala de Ideas ha elegido ESTA idea" in texto:
        print("  (el Escritor recibió la idea elegida)")
    if texto.startswith("Eres el Juez de guardia"):
        JUICIOS.append(1)
        if len(JUICIOS) == 1:
            return {"gancho": 10, "retencion": 10, "claridad": 10, "final": 10, "fallos_graves": ["título que no pega"], "consejo": "cambia el título"}
        return {"gancho": 20, "retencion": 18, "claridad": 20, "final": 15, "fallos_graves": [], "consejo": "más ritmo"}
    if "Juez de guardia, sobre la versión anterior" in texto:
        print("  (el Escritor recibió el aviso del Juez)")
    corto = "una cuenta de Instagram" in texto
    n = 45 if corto else 95
    frases = ["Esta es la frase número %d del guion de prueba." % i for i in range(n // 9 + 1)]
    narr = " ".join(frases)
    esc = 4 if corto else 6
    trozos = [narr[i*len(narr)//esc:(i+1)*len(narr)//esc] for i in range(esc)]
    g = {"idea": "prueba", "titulo": "Título de prueba 😨 #shorts", "texto_pantalla": "Mira tu radiografía ya", "narracion": narr,
         "escenas": [{"texto": t, "dibujo": "a dark room"} for t in trozos], "descripcion": "desc", "hashtags": ["#a", "#b", "#c"],
         "fuentes_usadas": [1, 2]}
    if corto:
        g.update(texto_instagram="Gancho\nlinea 2\n¿Y tú?", texto_tiktok="Gancho corto")
    return g
gemini.preguntar = falso_gemini

def falso_dibujar(escenas, modelo, carpeta, espera_maxima=1800):
    os.makedirs(carpeta, exist_ok=True)
    rutas = []
    for i, _ in enumerate(escenas):
        r = os.path.join(carpeta, f"e{i}.png"); Image.new("RGB", (576, 1024), (30*i % 255, 40, 90)).save(r); rutas.append(r)
    return rutas
dibujante.dibujar = falso_dibujar
reportero.noticias = lambda b, idioma="es", pais="ES", dias=4: [{"titulo": f"Noticia {b} {i}", "fuente": "Fuente", "fecha": "2026-11-22 10:00", "enlace": ""} for i in range(3)]
reportero.wikipedia = lambda a, idioma="en", maximo=6000: f"Texto de {a}"
SUBIDAS = []
def falso_subir(canal, video, titulo, hora, registro, **kw):
    SUBIDAS.append((canal, hora))
    lista = json.load(open(registro)) if os.path.exists(registro) else []
    lista.append({"canal": canal, "archivo": os.path.basename(video), "id": "VID%d" % len(SUBIDAS), "titulo": titulo, "publica": hora})
    os.makedirs(os.path.dirname(registro), exist_ok=True); json.dump(lista, open(registro, "w"))
    return 0, "OK", "VID%d" % len(SUBIDAS)
herr.subir = falso_subir
almacen.guardar = lambda etiqueta, ruta, nombre=None: f"https://github.com/x/ciudades-memoria/releases/download/{etiqueta}/{nombre}"
sys.argv = ["fabrica.py", "--sin-guardar", "--maximo", "5"] + sys.argv[1:]
codigo = fabrica.main()
print("CODIGO", codigo, "SUBIDAS", len(SUBIDAS))
sys.exit(codigo)
