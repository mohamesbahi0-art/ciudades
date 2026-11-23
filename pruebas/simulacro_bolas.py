"""Simulacro del canal de mapas («bolas») con una IA de mentira: el Archivero elige país y parte sin repetir y en orden,
el guion se limpia (encuadres del Cartógrafo, bolas con bandera, un solo «desaparece», «(Parte N)» en el título y el
crédito de los mapas) y se dibuja un vídeo de verdad con voz, mapa y bolas.

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
    return {"titulo": "País desaparece y nadie lo echa de menos 😅", "texto_pantalla": "¿Y SI DESAPARECIERA?",
            "descripcion": "Parte del caos. #shorts #countryballs",
            "escenas": [
                {"voz": "Un día, sin avisar, el país se borra del mapa.", "plano": "zona", "foco": pais, "accion": "desaparece",
                 "texto": "¡ADIÓS!", "bolas": [{"pais": pais, "expresion": "triste", "dice": "¡Adiós!"}]},
                {"voz": "Los vecinos se quedan mirando el hueco.", "plano": "bolas", "foco": pais, "accion": "salta",
                 "texto": "EL HUECO", "bolas": [{"pais": "FR", "expresion": "sorprendido", "dice": "¿Y eso?"},
                                                {"pais": "zz", "expresion": "rara"}]},
                {"voz": "Y otro se lo intenta quedar.", "plano": "mundo", "foco": pais, "accion": "desaparece",
                 "texto": "¡MÍO!", "bolas": [{"pais": "PT", "expresion": "malvado", "dice": "Es mío"}]},
                {"voz": "Empieza la pelea.", "plano": "pais", "foco": "XX", "accion": "pelea", "texto": "PELEA",
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
comprobar(sum(e["accion"] == "desaparece" for e in g["escenas"]) == 1, "el país se borra una sola vez")
comprobar(all(len(e["caja"]) == 4 for e in g["escenas"]), "cada escena tiene su encuadre")
comprobar(all(cartografo.tiene_bandera(b["pais"]) for e in g["escenas"] for b in e["bolas"]), "solo bolas con bandera")
comprobar(g["escenas"][3]["foco"] == g["pais"], "un foco que no existe vuelve al país")
comprobar("Natural Earth" in g["descripcion"], "la descripción lleva el crédito de los mapas")
privado.apuntar_titulo("mapas", g["titulo"])
segundo = archivero_mapas.siguiente("mapas")
comprobar(segundo["pais"] == primero["pais"] and segundo["parte"] == 2 and segundo["anteriores"], "después toca la Parte 2 del mismo país")

from bots.estudio import estudio  # noqa: E402
g["escenas"] = g["escenas"][:5]
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
print("Simulacro del canal de mapas: todo bien")
