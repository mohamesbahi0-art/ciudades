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

GUION = {"formato": "famoso", "titulo": "Prueba del plató",
         "famoso": {"nombre": "PRUEBA", "piel": "#C68B5E", "pelo": "rizado", "color_pelo": "#1A1310", "camiseta": "#F7D417",
                    "detalle": "#1E7F3A", "dorsal": "11", "color_dorsal": "#111111", "pantalon": "#1B2A6B",
                    "medias": "#FFFFFF", "botas": "#111111"},
         "escenas": [{"voz": "Con quince años ya era el mejor.", "texto": "Con 15 años ya era el mejor.", "resaltar": ["15 años"],
                      "fondo": "estadio", "actores": [{"id": "p", "tipo": "famoso", "pos": "centro", "accion": "magia"}],
                      "objetos": [{"tipo": "chispas"}, {"tipo": "balon", "anim": "orbita"}]},
                     {"voz": "Muchos dicen que es suerte.", "texto": "Muchos dicen que es suerte.", "resaltar": ["suerte"],
                      "color": "rojo", "fondo": "escenario",
                      "actores": [{"id": "m1", "tipo": "maniqui", "pos": "izq2", "etiqueta": "SUERTE", "accion": "senala_der"},
                                  {"id": "p", "tipo": "famoso", "pos": "centro", "accion": "brazos_cruzados"}]},
                     {"voz": "¿Y tú, qué entrenas hoy?", "texto": "¿Y tú, qué entrenas hoy?", "resaltar": ["hoy"],
                      "fondo": "barrio", "actores": [{"id": "tu", "tipo": "maniqui", "pos": "izq", "etiqueta": "TÚ",
                                                      "color_etiqueta": "oro"}],
                      "objetos": [{"tipo": "numero", "texto": "304", "sub": "PRUEBA", "pos": "der"},
                                  {"tipo": "bocadillo", "texto": "?"}, {"tipo": "inventado"}]}],
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
