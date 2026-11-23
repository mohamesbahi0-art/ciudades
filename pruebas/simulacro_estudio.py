"""Simulacro del estudio de animación: un turno de una cuenta animada con IA de mentira (sin secretos). Comprueba
que el guion se dibuja fotograma a fotograma, que suena y que el Juzgado lo juzga y va a «Para subir».

    PRIVADO=<copia de pruebas/privado_ejemplo> python pruebas/simulacro_estudio.py
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.environ.setdefault("PRIVADO", os.path.join(RAIZ, "pruebas", "privado_ejemplo"))
os.environ.setdefault("MEMORIA_DIR", os.path.join(os.environ["PRIVADO"], "memoria"))
from bots.comun import almacen, gemini, privado  # noqa: E402
from bots.central import turno  # noqa: E402

GUION = {"formato": "carrera", "titulo": "Prueba A vs B", "titulo_arriba": "A vs B",
         "columnas": [{"etiqueta": "A", "color": "#FF5A5F", "desde": 1, "hasta": 2, "unidad": "COSAS", "curva": "cae"},
                      {"etiqueta": "B", "color": "#4ADE80", "desde": 1, "hasta": 9, "unidad": "COSAS"}],
         "objeto": "ladrillos", "dias": ["L", "M", "X"],
         "escenas": [{"texto": "Mismo punto de partida.", "resaltar": ["Mismo"], "dia": "L", "progreso": [0.1, 0.1]},
                     {"texto": "Uno espera. El otro empieza.", "resaltar": ["empieza"], "dia": "X", "progreso": [0.2, 1.0]}],
         "final": {"lineas": [{"texto": "Empieza hoy.", "resaltar": ["hoy"]}], "pregunta": "¿Cuál eres tú?"},
         "descripcion": "prueba", "hashtags": ["#prueba"], "texto_instagram": "Prueba", "texto_tiktok": "Prueba"}


def falso(texto, imagenes=(), **kw):
    if "Escribe los dos alegatos" in texto:
        return {"defensa": "bien", "fiscalia": "regular", "fallos_graves": []}
    if "Tres jueces deciden" in texto:
        return {"votos": [{"juez": "gancho", "voto": "sube", "nota": 70}, {"juez": "reloj", "voto": "sube", "nota": 66},
                          {"juez": "calle", "voto": "no", "nota": 50}], "consejo": "ok"}
    return json.loads(json.dumps(GUION))


gemini.preguntar = falso
almacen.guardar = lambda etiqueta, ruta, nombre=None: f"https://example.invalid/{etiqueta}/{nombre or os.path.basename(ruta)}"
cfg = privado.config()
for b in cfg.get("barrios", {}).values():
    b["estudio"] = "animacion"
privado.escribir(os.path.join("config", "canales.json"), cfg)
codigo = turno.main(["--canal", "barrio-1", "--salida", os.path.join(os.environ["PRIVADO"], "trabajo")])
estado = privado.leer(os.path.join("estado", "central", "barrio.prueba.json"), {})["ultimo_turno"]
print("CODIGO", codigo, "DESTINO", estado.get("destino_resultado"), "SEGUNDOS", estado.get("segundos"))
sys.exit(0 if codigo == 0 and estado.get("destino_resultado") == "para_subir" else 1)
