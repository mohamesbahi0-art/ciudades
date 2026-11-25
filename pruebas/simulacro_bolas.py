"""Simulacro del canal de mapas («bolas») con una IA de mentira: el Archivero elige país y parte sin repetir y en orden,
el guion se limpia (encuadres del Cartógrafo, bolas con bandera, el país borrado desde el primer fotograma y sin su
bola, 12 palabras de voz por escena, lo que promete el título puesto como objeto, «(Parte N)» en el título y el crédito
de los mapas) y se dibuja un vídeo de verdad con voz, mapa y bolas. Con SIMULACRO_GUARDA=<carpeta> deja ahí el vídeo.

    python pruebas/simulacro_bolas.py
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
TMP = tempfile.mkdtemp(prefix="simulacro-bolas-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)

from bots.comun import gemini, privado  # noqa: E402
from bots.estudio import archivero_mapas, bolas, cartografo  # noqa: E402

PEDIDOS = []


def falso(texto, imagenes=(), **kw):
    PEDIDOS.append(texto)
    pais = texto.split("ISO de 2 letras del país al que mira la cámara (normalmente ")[1][:2]
    return {"titulo": "País desaparece y una arepa gigante tapa el hueco 🫓😱", "texto_pantalla": "¿Y SI DESAPARECIERA? PARTE 1",
            "descripcion": "Parte del caos. #shorts #countryballs", "pregunta": "¿Quién se queda el hueco? 👇",
            "escenas": [
                {"voz": "Un día, sin avisar, el país se borra del mapa, y todos los vecinos se asoman al hueco enorme que deja.",
                 "plano": "zona", "foco": pais, "accion": "desaparece",
                 "texto": "¡ADIÓS!", "bolas": [{"pais": pais, "expresion": "triste", "dice": "¡Adiós!"}]},
                {"voz": "El hueco crece y se come la frontera.", "plano": "bolas", "foco": pais, "accion": "crece",
                 "texto": "EL HUECO", "bolas": [{"pais": "FR", "expresion": "sorprendido", "dice": "¿Y eso?"},
                                                {"pais": "zz", "expresion": "rara"}]},
                {"voz": "El mar aprovecha y se cuela dentro.", "plano": "zona", "foco": pais, "accion": "agua",
                 "texto": "¡AGUA!", "bolas": [{"pais": "PT", "expresion": "asustado", "dice": "¡Que me mojo!"}]},
                {"voz": "Un vecino estira su color y se queda un trozo.", "plano": "pais", "foco": "XX", "accion": "conquista",
                 "texto": "¡MÍO!", "bolas": [{"pais": "FR", "expresion": "malvado", "dice": "Es mío"},
                                              {"pais": "PT", "expresion": "enfadado", "dice": "¡Ni hablar!"}]},
                {"voz": "Otro se asoma demasiado y se cae dentro.", "plano": "zona", "foco": pais, "accion": "cae",
                 "texto": "¡AY!", "bolas": [{"pais": "IT", "expresion": "asustado"}, {"pais": "FR", "expresion": "feliz"}]},
                {"voz": "Y empieza la pelea por lo que queda.", "plano": "bolas", "foco": pais, "accion": "pelea", "texto": "PELEA",
                 "bolas": [{"pais": "FR", "expresion": "enfadado"}, {"pais": "PT", "expresion": "enfadado"}]},
                {"voz": "Mañana, la segunda parte.", "plano": "zona", "foco": pais, "accion": "rie", "texto": "MAÑANA",
                 "bolas": [{"pais": "IT", "expresion": "feliz", "dice": "Jaja"}]}]}


gemini.preguntar = falso


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


comprobar(len(cartografo.mundo()["paises"]) > 150 and cartografo.tiene_bandera("ES"), "el Cartógrafo tiene el mapa y las banderas")
comprobar(archivero_mapas.pais_del_titulo("México desaparece y Estados Unidos se queda sin guacamole (Parte 1)") == "MX",
          "el país del título es el que sale primero")
canal = {"clave": "mapas", "nombre": "Canal de prueba", "destino": "youtube"}
primero = archivero_mapas.siguiente("mapas")
comprobar(primero["parte"] == 1 and primero["pais"] not in archivero_mapas.FUERA, f"empieza un país nuevo: {primero['pais']}")
g = bolas.guionizar(canal, "")
comprobar(g["pais"] == primero["pais"] and g["parte"] == 1 and g["partes"] == 3, "el guion es del país y la parte que tocan")
comprobar(g["titulo"].endswith("(Parte 1) #shorts"), "el título lleva «(Parte 1)»")
comprobar(g["borrado_desde"] == 0 and all(e["accion"] in bolas.ACCIONES for e in g["escenas"]),
          "el país ya está borrado en el primer fotograma (nadie lo vuelve a pintar)")
comprobar(all(b["pais"] != g["pais"] for e in g["escenas"] for b in e["bolas"]), "la bola del país borrado no sale")
comprobar(g["escenas"][0]["plano"] == "pais" and len(g["escenas"][0]["bolas"]) >= 2, "arranca con el hueco de cerca y dos vecinos asomados")
comprobar(all(len(e["voz"].split()) <= 12 for e in g["escenas"]) and len(g["escenas"]) == 8, "12 palabras de voz por escena (la larga se parte)")
comprobar(any(e["objeto"] == "🫓" and e["accion"] == "tapa" for e in g["escenas"]), "lo que promete el título (🫓) cae sobre el hueco")
comprobar("PARTE" not in g["texto_pantalla"].upper() and g["pregunta"].startswith("¿QUIÉN"), "sin «Parte» en pantalla y con pregunta final")
comprobar(len(PEDIDOS) == 3 and "NO vale" in PEDIDOS[-1] and any("título promete" in x for x in bolas.revisar(falso(PEDIDOS[0]))),
          "al guionista se le dice lo que no cumple y repite")
comprobar(all(e["voces"] is not None and len(e["voces"]) <= 1 for e in g["escenas"]), "una bola con voz por escena como mucho")
comprobar(all(len(e["caja"]) == 4 for e in g["escenas"]), "cada escena tiene su encuadre")
comprobar(all(cartografo.tiene_bandera(b["pais"]) for e in g["escenas"] for b in e["bolas"]), "solo bolas con bandera")
comprobar(g["escenas"][4]["foco"] == g["pais"], "un foco que no existe vuelve al país")
comprobar("Natural Earth" in g["descripcion"], "la descripción lleva el crédito de los mapas")
privado.apuntar_titulo("mapas", g["titulo"])
segundo = archivero_mapas.siguiente("mapas")
comprobar(segundo["pais"] == primero["pais"] and segundo["parte"] == 2 and segundo["anteriores"], "después toca la Parte 2 del mismo país")

from bots.estudio import estudio  # noqa: E402
sin_parte = bolas.limpiar(json.loads(json.dumps(g)))
comprobar(len(sin_parte["escenas"]) == len(g["escenas"]) and sin_parte["escenas"][0]["bolas"] == g["escenas"][0]["bolas"],
          "limpiar dos veces deja el guion igual")
canal.update(voz_estudio="es-MX-JorgeNeural", formato_estudio="bolas", musica_estudio="energia")
carpeta = os.path.join(TMP, "video")
try:
    video, g2 = estudio.hacer(canal, guion=json.loads(json.dumps(g)), carpeta=carpeta, avisar=lambda t: None)
except Exception as e:                       # sin red para la voz gratis no se puede dibujar: se dice y se sigue
    print(f"aviso  no se ha podido dibujar el vídeo aquí ({type(e).__name__}); el resto está bien")
    print("Simulacro del canal de mapas: todo bien")
    sys.exit(0)
dura = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                            capture_output=True, text=True).stdout or 0)
comprobar(os.path.exists(video) and dura > 4, f"dibuja el vídeo ({dura:.1f} s)")
tomas = sorted(t for i, e in enumerate(g2["escenas"]) for t in bolas.cortes(e, i == 0))
comprobar(tomas[1] < 1.5 and max(b - a for a, b in zip(tomas, tomas[1:] + [dura])) <= 2.5,
          f"primer corte en el segundo {tomas[1]:.2f} y ninguna toma pasa de 2,5 s")
if os.environ.get("SIMULACRO_GUARDA"):
    os.makedirs(os.environ["SIMULACRO_GUARDA"], exist_ok=True)
    shutil.copy(video, os.path.join(os.environ["SIMULACRO_GUARDA"], "bolas.mp4"))
    shutil.copy(os.path.join(carpeta, "guion_estudio.json"), os.path.join(os.environ["SIMULACRO_GUARDA"], "guion.json"))
print("Simulacro del canal de mapas: todo bien")
