"""Simulacro del Jurado popular con una IA de mentira: los 12 votan el guion por separado (cada uno con su piel) antes de
grabarlo; si 9 o más dicen «culpable» lo rechazan, y si no se puede formar el jurado el guion sigue.

    python pruebas/simulacro_jurado.py
"""
import json
import os
import re
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-jurado-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)

from bots.comun import gemini, privado  # noqa: E402
from bots.juzgado import jurado  # noqa: E402

MODO = {"culpables": 0, "falla": False}
VISTOS = []


def falso(texto, imagenes=(), **kw):
    if MODO["falla"]:
        raise gemini.SinIA("sin cupo")
    nombre = re.search(r"Eres ([^,]+), miembro del jurado", texto).group(1)
    VISTOS.append((nombre, "inocente" in texto and "culpable" in texto, "jurado popular" in texto))
    assert "voto de" not in texto.split("Vota tú solo")[0], "un jurado no debe ver los votos de los demás"
    n = len(VISTOS) % 12 or 12
    return {"voto": "culpable" if n <= MODO["culpables"] else "inocente", "nota": 80, "porque": f"desde mi piel ({nombre})"}


gemini.preguntar = falso


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


guion = {"titulo": "Lo que nadie vio en GTA 6", "texto_pantalla": "NADIE LO VIO", "narracion": "Un detalle escondido."}
canal = {"clave": "gta", "nombre": "Canal"}
alegatos = {"defensa": "Va a funcionar.", "fiscalia": "Va a fracasar."}
comun = {"donde": "un canal de YouTube Shorts", "idioma": "español", "gancho": "NADIE LO VIO"}

r = jurado.deliberar(guion, canal, alegatos, comun)
comprobar(len(r["votos"]) == 12 and len({v["piel"] for v in r["votos"]}) == 12, "12 jurados, cada uno con su piel")
comprobar(len(VISTOS) == 12, "votan por separado: una pregunta por jurado")
comprobar(any(n.endswith("-jurado.json") for n in os.listdir(os.path.join(TMP, "privado", "estado", "juzgado", "juicios"))),
          "cada reunión queda como un juicio del guion para la app")
comprobar(r["inocente"] == 12 and not r["rechaza"], "todos inocentes: no lo rechaza")
MODO["culpables"] = 9
VISTOS.clear()
r = jurado.deliberar(guion, canal, alegatos, comun)
comprobar(r["culpable"] == 9 and r["rechaza"] and r["veredicto"] == "culpable", "9 culpables: el jurado lo rechaza")
MODO["culpables"] = 8
VISTOS.clear()
r = jurado.deliberar(guion, canal, alegatos, comun)
comprobar(r["culpable"] == 8 and not r["rechaza"], "8 culpables: no basta para tumbarlo (deciden los jueces)")
MODO["falla"] = True
comprobar(jurado.deliberar(guion, canal, alegatos, comun) is None, "sin IA no hay jurado: deciden los jueces")
MODO["falla"] = False
ruta = os.path.join(TMP, "privado", "config", "fabrica.json")
f = json.load(open(ruta, encoding="utf-8"))
f["juzgado"] = {"jurado": {"por_dia": 3}}             # ya se han reunido 3 veces
json.dump(f, open(ruta, "w", encoding="utf-8"))
comprobar(jurado.deliberar(guion, canal, alegatos, comun) is None, "tope del día: deciden los jueces")
comprobar(privado.leer("estado/juzgado/jurado.json")["hoy"]["jurados"] == 3, "se cuentan los jurados del día")
# En el turno: si el jurado rechaza el guion, se reescribe (hasta 2 veces) antes de gastar en voz y dibujos
f["juzgado"] = {"jurado": {"por_dia": 50}}
json.dump(f, open(ruta, "w", encoding="utf-8"))
from types import SimpleNamespace  # noqa: E402
from bots.central import turno  # noqa: E402
pasos, reescritos = [], []


def reescribir(extra):
    reescritos.append(extra)
    return dict(guion, titulo=f"Versión {len(reescritos) + 1}")


MODO["culpables"] = 10
VISTOS.clear()
g, vale = turno._jurado_guion("gta", canal, dict(guion), lambda r, t, p=None: pasos.append(t), SimpleNamespace(prueba=True),
                              reescribir=reescribir)
comprobar(not vale and len(reescritos) == 2 and "rechazado" in reescritos[0],
          "jurado en contra siempre: se reescribe 2 veces y ese guion no se graba")
MODO["culpables"] = 0
reescritos.clear()
g, vale = turno._jurado_guion("gta", canal, dict(guion), lambda r, t, p=None: pasos.append(t), SimpleNamespace(prueba=True),
                              reescribir=reescribir)
comprobar(vale and not reescritos and g["jurado"]["inocente"] == 12, "jurado a favor: el guion sigue a la voz y los dibujos")
shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro del Jurado popular: todo bien")
