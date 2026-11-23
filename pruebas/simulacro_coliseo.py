"""Simulacro del Coliseo con una IA de mentira (sin red ni secretos): 8 gladiadores, 7 combates y un campeón.
Comprueba que solo entran vídeos aprobados, que la salida campeona cumple las reglas (#shorts en YouTube, máximo 5
hashtags), que la mención de la voz de ElevenLabs sigue al final, que hay tope diario y que, si la IA no contesta, el
vídeo sale con su salida de siempre.

    python pruebas/simulacro_coliseo.py
"""
import json
import os
import re
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-coliseo-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)

from bots.coliseo import coliseo  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402

MODO = {"falla": False}
LLAMADAS = {"gladiador": 0, "combate": 0, "juez": 0}


def falso(texto, imagenes=(), **kw):
    if MODO["falla"]:
        raise gemini.SinIA("sin cupo")
    if "gladiador del Coliseo" in texto:
        LLAMADAS["gladiador"] += 1
        carta = re.search(r"Tu carta es «([^»]+)»", texto).group(1)
        return {"titulo": f"El secreto de {carta} que nadie te ha contado 😱", "texto": f"Mira hasta el final: {carta}.",
                "hashtags": ["#fyp", "#dinero", "dinero", "#ahorro", "#finanzas", "#motivacion", "#extra"], "por_que": "x"}
    if "Coliseo, combate" in texto and "SALIDA A" in texto:
        LLAMADAS["combate"] += 1
        a = json.loads(texto.split("SALIDA A: ", 1)[1].split("\n", 1)[0])
        b = json.loads(texto.split("SALIDA B: ", 1)[1].split("\n", 1)[0])
        a["titulo"] = a["titulo"].replace("😱", "🔥")      # en el combate los dos corrigen su salida
        b["titulo"] = b["titulo"].replace("😱", "🔥")      # (el juez ciego las ve en orden al azar)
        return {"critica_a_b": "flojo", "critica_b_a": "largo", "a": a, "b": b}
    if "Juez ciego" in texto:
        LLAMADAS["juez"] += 1
        return {"ganador": 1, "razon": "engancha más", "nota_1": 91, "nota_2": 80}
    raise AssertionError("pregunta inesperada: " + texto[:80])


gemini.preguntar = falso


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


yt = {"clave": "gta", "nombre": "Canal de prueba", "destino": "youtube", "idioma": "es", "tema": "GTA 6"}
guion = {"titulo": "Lo que nadie vio en GTA 6 🚗 #shorts", "descripcion": "Un detalle escondido.", "hashtags": ["#gta6"],
         "texto_pantalla": "NADIE LO VIO", "narracion": "En GTA 6 hay un detalle que casi nadie ha visto."}
aprobado = {"veredicto": "aprobado", "total": 93}

# 1. Un vídeo suspendido no entra
comprobar(coliseo.luchar("gta", yt, guion, {"veredicto": "suspendido", "total": 70}) is guion, "suspendido: no entra")

# 2. Torneo completo en YouTube
g = coliseo.luchar("gta", yt, dict(guion), aprobado)
comprobar(LLAMADAS == {"gladiador": 8, "combate": 7, "juez": 7}, f"8 gladiadores, 7 combates y 7 juicios ({LLAMADAS})")
comprobar(g["titulo"].endswith("#shorts") and g["titulo"].count("#shorts") == 1, f"título de YouTube con #shorts: {g['titulo']}")
comprobar(len(g["hashtags"]) <= 5 and all(h.startswith("#") for h in g["hashtags"]) and "#fyp" not in g["hashtags"],
          f"máximo 5 hashtags y sin relleno: {g['hashtags']}")
comprobar(g["coliseo"]["titulo_antes"] == guion["titulo"] and g["coliseo"]["campeon"], "se apunta el campeón y el título de antes")
comprobar("🔥" in g["titulo"], "la salida campeona es la corregida en los combates")
t = json.load(open(os.path.join(TMP, "privado", "estado", "coliseo", "torneos", os.listdir(os.path.join(TMP, "privado", "estado", "coliseo", "torneos"))[0])))
comprobar([c["ronda"] for c in t["combates"]] == ["cuartos"] * 4 + ["semifinal"] * 2 + ["final"],
          "rondas con el nombre que entiende la app (cuartos, semifinal y final)")
nombres = {x["nombre"] for x in t["gladiadores"]}
comprobar(all(c["a"] in nombres and c["b"] in nombres and c["ganador"] in (c["a"], c["b"]) for c in t["combates"]),
          "cada combate con los nombres exactos de sus gladiadores")
r = privado.leer("estado/coliseo/resumen.json")
comprobar(r["hoy"]["torneos"] == 1 and sum(c["ganadas"] for c in r["cartas"].values()) == 1, "se cuenta qué carta gana")
torneos = os.listdir(os.path.join(TMP, "privado", "estado", "coliseo", "torneos"))
comprobar(len(torneos) == 1, "el torneo queda guardado para la app")

# 3. Barrio de TikTok/Instagram: la mención de la voz sigue al final
barrio = {"clave": "barrio.prueba", "nombre": "Barrio", "destino": "parasubir", "idioma": "es", "tema": "dinero"}
gb = {"titulo": "Ahorra así", "texto_tiktok": "Texto viejo\n🎙️ Voz: elevenlabs.io", "texto_instagram": "Texto viejo\n🎙️ Voz: elevenlabs.io",
      "hashtags": ["#dinero"], "escenas": [{"texto": "AHORRA", "voz": "Ahorra así."}]}
nuevo = coliseo.luchar("barrio.prueba", barrio, gb, aprobado)
comprobar(nuevo["texto_tiktok"].endswith("🎙️ Voz: elevenlabs.io") and "Texto viejo" not in nuevo["texto_tiktok"],
          "TikTok: texto nuevo y la mención de la voz al final")
comprobar(nuevo["texto_instagram"] == nuevo["texto_tiktok"] and not nuevo["titulo"].endswith("#shorts"),
          "Instagram igual que TikTok y sin #shorts")

# 4. Si la IA no contesta, sale con su salida de siempre
MODO["falla"] = True
igual = coliseo.luchar("gta", yt, dict(guion), aprobado)
comprobar(igual["titulo"] == guion["titulo"] and "coliseo" not in igual, "sin IA: sale con su salida de siempre")
MODO["falla"] = False

# 5. Tope diario
ruta = os.path.join(TMP, "privado", "config", "fabrica.json")
f = json.load(open(ruta, encoding="utf-8"))
f["coliseo"] = {"por_dia": 2}             # ya ha habido 2 torneos de verdad (el que falló no cuenta)
json.dump(f, open(ruta, "w", encoding="utf-8"))
lleno = coliseo.luchar("gta", yt, dict(guion), aprobado)
comprobar(lleno["titulo"] == guion["titulo"], "tope del día alcanzado: sale con su salida de siempre")
shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro del Coliseo: todo bien")
