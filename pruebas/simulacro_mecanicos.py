"""Simulacro del Taller de los Mecánicos (sin red ni secretos): arrancan la fábrica si lleva horas parada, repiten un
turno que falló al preparar las herramientas, mandan a descansar al canal que falla 3 veces igual, paran los dibujos si
el servicio está caído, limpian los vídeos colgados y dejan el parte para Claude. Y no repiten el mismo arreglo dos veces.

    python pruebas/simulacro_mecanicos.py
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-mecanicos-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ.pop("ANTHROPIC_API_KEY", None)

from bots.comun import gemini, privado  # noqa: E402
from bots.mecanicos import taller  # noqa: E402

AHORA = dt.datetime.now(dt.timezone.utc)
iso = lambda horas: (AHORA - dt.timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
LLAMADAS = []


def gh(*args):
    LLAMADAS.append(args)
    if args[:2] == ("run", "view"):
        return 0, "Herramientas\n"
    return 0, ""


taller._gh = gh
gemini.preguntar = lambda texto, **kw: {"salida": "para_claude", "causa": "falta un campo en el guion",
                                        "para_el_dueno": "No tienes que hacer nada.", "para_claude": "mirar turno.py"}


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


ronda = lambda h, turnos: {"empezada": iso(h), "turnos": turnos}  # noqa: E731
privado.guardar_estado("fabrica.json", {"empezada": iso(0.5), "turnos": [
    {"canal": "terror", "codigo": 1, "error": "KeyError: 'titulo'"},
    {"canal": "gta", "codigo": 1, "error": "RuntimeError: faltan 4 dibujos de 6"}], "rondas": [
    ronda(2.5, [{"canal": "terror", "codigo": 1, "error": "KeyError: 'titulo'"},
                {"canal": "gta", "codigo": 1, "error": "RuntimeError: faltan 4 dibujos de 7"}]),
    ronda(1.5, [{"canal": "terror", "codigo": 1, "error": "KeyError: 'titulo'"},
                {"canal": "curios", "codigo": 1, "error": "SinIA: sin cupo"}])]})
privado.escribir(os.path.join("estado", "obras.json"), {"obras": {
    "colgado": {"canal": "gta", "estado": "en_marcha", "actualizado": iso(5)},
    "vivo": {"canal": "gta", "estado": "en_marcha", "actualizado": iso(0.2)}}})
lista = [{"databaseId": 1, "workflowName": "Fábrica", "status": "completed", "conclusion": "success", "createdAt": iso(4)},
         {"databaseId": 2, "workflowName": "Ojeador de redes", "status": "completed", "conclusion": "failure", "createdAt": iso(1)}]

e = taller.revisar(lista=lista)
comprobar(("workflow", "run", "fabrica.yml") in LLAMADAS, "la fábrica llevaba 4 horas parada: la arrancan")
comprobar(("run", "rerun", "2", "--failed") in LLAMADAS, "un turno que falló en «Herramientas» se repite")
comprobar(bool(taller.en_cuarentena("terror")) and not taller.en_cuarentena("curios"),
          "el canal que falla 3 veces igual descansa; el que no tenía IA, no")
comprobar(taller.dibujos_caidos(), "con el servicio de dibujos caído, los canales que dibujan esperan")
obras = privado.leer(os.path.join("estado", "obras.json"))["obras"]
comprobar(obras["colgado"]["estado"] == "descartado" and obras["vivo"]["estado"] == "en_marcha", "limpian el vídeo colgado y dejan el vivo")
comprobar(len(e["partes"]) == 1 and e["partes"][0]["estado"] == "para_claude", "dejan el parte para Claude, con su diagnóstico")
antes = len(LLAMADAS)
e2 = taller.revisar(lista=lista[1:])
comprobar(not any(x[:2] == ("run", "rerun") for x in LLAMADAS[antes:]) and len(e2["partes"]) == 1,
          "no repiten el mismo arreglo ni duplican el parte")
comprobar(bool(privado.leer(os.path.join("estado", "mecanicos", "taller.json"))["arreglos"]), "lo dejan apuntado para la app")
print("Simulacro del Taller de los Mecánicos: todo bien")
