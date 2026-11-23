"""Simulacro del formato «ciencia» (Wist je dat): un turno de una cuenta animada en neerlandés con IA de mentira (sin
secretos). Comprueba que el guion se limpia, que se graba la voz escena a escena, que ciencia.html lo dibuja, que suena
y que el Juzgado lo juzga y va a «Para subir».

    PRIVADO=<copia de pruebas/privado_ejemplo> python pruebas/simulacro_ciencia.py
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

GUION = {"titulo": "Een octopus heeft drie harten", "escenas": [
    {"voz": "Een octopus heeft drie harten.", "clave": ["harten."], "plano": "grande", "ilustracion": "emoji:🐙",
     "color": "paars", "componentes": [{"tipo": "numero", "valor": "3", "titulo": "harten"}]},
    {"voz": "Als hij zwemt, stopt er een.", "clave": ["stopt"], "plano": "grafica", "ilustracion": "corazon",
     "color": "rood", "componentes": [{"tipo": "onda", "label": "ZWEMMEN", "color": "rood", "picos": 0},
                                      {"tipo": "inventado"}]},
    {"voz": "En zijn bloed is blauw.", "clave": ["blauw."], "plano": "lado", "ilustracion": "noexiste",
     "ilustracion2": "gota", "color": "rosa_inventado"},
    {"voz": "Wist jij dit al?", "clave": ["al?"], "plano": "grande", "ilustracion": "emoji:🐙", "botones": ["ja", "nee"]}],
    "descripcion": "test", "hashtags": ["octopus"]}


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
    b.update(estudio="animacion", formato_estudio="ciencia", voz_estudio="nl-NL-MaartenNeural|nl-BE-ArnaudNeural", idioma="nl",
             musica_estudio="ninguna",
             velocidad_estudio="-4%", tono_estudio="+0Hz")
privado.escribir(os.path.join("config", "canales.json"), cfg)
codigo = turno.main(["--canal", "barrio-1", "--salida", os.path.join(os.environ["PRIVADO"], "trabajo")])
estado = privado.leer(os.path.join("estado", "central", "barrio.prueba.json"), {})["ultimo_turno"]
print("CODIGO", codigo, "DESTINO", estado.get("destino_resultado"), "FORMATO", estado.get("formato"), "SEGUNDOS", estado.get("segundos"))
sys.exit(0 if codigo == 0 and estado.get("destino_resultado") == "para_subir" and estado.get("formato") == "ciencia" else 1)
