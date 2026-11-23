"""Simulacro del Presentador de directos con una IA de mentira: prepara el directo de la semana de cada cuenta
encendida, en su idioma, y lo deja para la app; las cuentas en pausa no se tocan.

    python pruebas/simulacro_directos.py
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-directos-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.argv = ["directos.py"]

from bots.central import directos  # noqa: E402
from bots.comun import gemini, privado  # noqa: E402

PEDIDOS = []


def falso(texto, imagenes=(), **kw):
    assert "Presentador de directos" in texto
    PEDIDOS.append(texto)
    return {"titulo": "Directo de prueba", "cuando": {"dia": "jueves", "hora": "21:00", "por_que": "más gente"},
            "duracion_minutos": 30, "gancho": "¡Hola!", "bloques": [{"minuto": 0, "tema": "a", "que_decir": "b",
            "pregunta_chat": "c"}, {"minuto": 10, "tema": "d", "que_decir": "e", "pregunta_chat": "f"}],
            "encuesta": {"pregunta": "¿?", "opciones": ["sí", "no"]}, "reto": "r", "saludo": "s", "seguir": "sigue",
            "preguntas_previstas": [], "cierre": "adiós", "consejos": ["x"], "no_hacer": ["no pidas regalos"]}


gemini.preguntar = falso


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


cfg = privado.config()
activas = [k for k, b in cfg.get("barrios", {}).items() if b.get("estado") == "activo"]
comprobar(directos.main() == 0, "prepara sin fallos")
comprobar(len(PEDIDOS) == len(activas) and activas, "un directo por cada cuenta encendida")
for k in activas:
    d = privado.leer(os.path.join("estado", "directos", f"{privado.alias(k)}.json"))
    comprobar(bool(d) and len(d["bloques"]) == 2 and d["semana"], f"deja el directo de {privado.alias(k)} para la app")
comprobar("nada de pedir regalos" in PEDIDOS[0], "le recuerda las normas de TikTok")
print("Simulacro del Presentador de directos: todo bien")
