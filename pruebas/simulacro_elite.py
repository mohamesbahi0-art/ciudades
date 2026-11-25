"""Simulacro de la Élite: con datos y cerebro de mentira, comprueba que los tres mandamases miran, deciden, ejecutan solo
lo permitido, deshacen lo que empeora y no tocan nunca lo del dueño.

    python pruebas/simulacro_elite.py
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PRIVADO = os.path.join(tempfile.mkdtemp(prefix="elite-"), "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
from bots.comun import ia, privado  # noqa: E402
from bots.central import fabrica  # noqa: E402
from bots.elite import elite  # noqa: E402

CUENTA, CANAL = "barrio.prueba", "terror"
FALLOS, N = 0, [0]


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    FALLOS += 0 if vale else 1


def juicio(clave, nota, guionista="gemini", minutos=60, version=1):
    N[0] += 1
    cuando = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutos)
    privado.guardar_estado(f"juzgado/juicios/{cuando.strftime('%Y%m%d-%H%M%S')}-{N[0]}-{clave}.json".replace(".prueba", "-prueba"), {
        "canal": clave, "tipo": "video", "titulo": f"Vídeo {N[0]}", "nota": nota, "fecha": cuando.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "guionista": guionista, "version": version, "consejo": "va lento y el gancho no se ve", "prueba": False})


MOTOR = ["claude"]
RESPUESTAS = {}
PREGUNTAS = []


def cerebro(texto, **kw):
    PREGUNTAS.append(texto)
    ids = [i for i in RESPUESTAS if f'"{i}"' in texto]
    return {"decisiones": [dict(RESPUESTAS[i], id=i) for i in ids]}


ia.preguntar = cerebro
ia.quien = lambda: {"motor": MOTOR[0]}
hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
dueno = privado.cuaderno("guionista")
dueno.aprender("Sin música en los vídeos de las cuentas.", confianza=1, del_dueno=True)
dueno.guardar()
for nota in (84, 86, 85):
    juicio(CUENTA, nota, "claude", minutos=300)
for nota in (70, 72, 68):
    juicio(CUENTA, nota, "gemini", minutos=240)
for nota in (60, 64, 70, 66, 62, 69):
    juicio(CANAL, nota, "gemini", minutos=200)
ID_CEREBRO, ID_FORMATO = "cerebro-barrio-1", f"formato-{CANAL}"

# 1. Miran: el parte general y los problemas
parte = elite.parte_general(dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24))
c = parte["cuentas"].get("barrio-1") or {}
comprobar("el Espía junta el parte de cada cuenta (notas, quién escribió, sin nombres de cuentas)",
          c.get("juicios") == 6 and c.get("mejor") == 86 and c["por_guionista"]["claude"]["media"] == 85.0
          and CUENTA not in json.dumps({k: v for k, v in parte["cuentas"].items()}, ensure_ascii=False).replace('"clave": "barrio.prueba"', ""))
problemas = {p["id"]: p for p in elite.estratega(parte)}
comprobar("la Estratega ve que el guion gratis saca 15 puntos menos y que el canal no pasa de 70",
          ID_CEREBRO in problemas and ID_FORMATO in problemas and problemas[ID_FORMATO]["mejor"] == 70)

# 2. Una palanca que no está en la lista (la nota mínima del dueño) no se toca
RESPUESTAS[ID_CEREBRO] = {"salida": "palanca", "ambito": "canal", "canal": "barrio-1", "campo": "nota_minima", "valor": 50}
elite.main([])
e = elite.leer()
ultima = [d for d in e["decisiones"] if d["id"] == ID_CEREBRO][-1]
comprobar("la nota mínima del dueño no se puede tocar: la palanca se rechaza y no cambia nada",
          ultima["salida"] == "nada" and "rechazada" in ultima and not privado.cambios_elite()["canales"]
          and privado.canal(CUENTA).get("nota_minima") != 50)
comprobar("al Arquitecto le llegan sus skills y el parte entero", "Skill: diagnóstico" in PREGUNTAS[-1]
          and "PARTE GENERAL" in PREGUNTAS[-1] and "guionista" in PREGUNTAS[-1])

# 3. Sin el cerebro bueno no se decide ningún cambio de verdad (se deja para la hora siguiente)
e["vistos"] = {}
privado.escribir(elite.ESTADO, e)
MOTOR[0] = "gemini"
RESPUESTAS[ID_CEREBRO] = {"salida": "palanca", "ambito": "canal", "canal": "barrio-1", "campo": "guionista", "valor": "claude",
                          "causa": "el guion gratis no llega"}
RESPUESTAS[ID_FORMATO] = {"salida": "reforma", "texto": "rehacer el formato del canal", "causa": "el formato no llega"}
elite.main([])
e = elite.leer()
comprobar("con el cerebro gratis no hay palancas ni reformas, y el problema sigue pendiente",
          not privado.cambios_elite()["canales"] and not e["reformas"] and ID_CEREBRO not in e["vistos"])

# 4. Con el cerebro bueno: palanca aplicada (y deshacible) y cuenta a reforma con su obra para Claude
MOTOR[0] = "claude"
elite.main([])
e = elite.leer()
cambio = [x for x in e["cambios"] if x["estado"] == "activo"]
comprobar("palanca: la cuenta pasa a escribir solo con el cerebro de pago, sin tocar config/",
          privado.canal(CUENTA).get("guionista") == "claude"
          and "guionista" not in json.load(open(os.path.join(PRIVADO, "config", "canales.json")))["barrios"][CUENTA]
          and len(cambio) == 1 and cambio[0]["base"]["media"] is not None)
plan, esperan = fabrica.planear(privado.ajustes(), privado.config(), {}, linea="dibujos")
comprobar("reforma: el canal descansa (la fábrica lo respeta) y queda la obra para Claude con sus pruebas",
          elite.en_reforma(CANAL) and "reforma" in esperan.get(CANAL, "") and CANAL not in [k for k, _ in plan]
          and any(o["id"] == ID_FORMATO and o["estado"] == "para_claude" and o.get("pruebas") for o in e["obras"]))
elite.main([])
comprobar("no decide dos veces lo mismo", len([d for d in elite.leer()["decisiones"] if d["id"] == ID_CEREBRO and d["salida"] == "palanca"]) == 1)

# 5. Lección al robot que toca, sin pisar lo del dueño
ID_DESC = "descartes-barrio-1-prueba"
RESPUESTAS[ID_DESC] = {"salida": "leccion", "robot": "escritor", "texto": "Empieza por la frase más chocante."}
e = elite.leer()
hechas = elite.arquitecto([{"id": ID_DESC, "tipo": "descartes", "canal": "barrio-1", "clave": CUENTA, "pruebas": ["x"]}],
                          parte, e)
lecciones = privado.cuaderno("guionista").datos["lecciones"]
comprobar("lección: va al cuaderno del guionista de esa cuenta y no como si la dijera el dueño",
          hechas and hechas[0]["robot"] == "guionista" and any("más chocante" in x["texto"] and not x.get("del_dueno") for x in lecciones))
comprobar("lo que dijo el dueño sigue igual", any(x["texto"].startswith("Sin música") and x.get("del_dueno")
                                                    and x["confianza"] == 1.0 for x in lecciones))

# 5 bis. Al Juzgado no le da lecciones ella sola (sería una forma de ablandar la nota): pasa a ser una obra para Claude
RESPUESTAS["juez-1"] = {"salida": "leccion", "robot": "juez", "texto": "No bajes la nota por el ritmo."}
e = elite.leer()
antes_juez = len(privado.cuaderno("juez_guardia").datos["lecciones"])
hechas = elite.arquitecto([{"id": "juez-1", "tipo": "caso", "canal": "barrio-1", "clave": CUENTA, "pruebas": ["x"]},
                           {"id": "sin-respuesta", "tipo": "caso", "canal": "", "pruebas": ["x"]}], parte, e)
comprobar("una lección para el juez no se ejecuta: queda como obra para Claude",
          hechas and hechas[0]["salida"] == "obra" and len(privado.cuaderno("juez_guardia").datos["lecciones"]) == antes_juez
          and any(o["id"] == "juez-1" for o in e["obras"]))
comprobar("lo que el cerebro no contesta sigue pendiente (no se da por visto)", "sin-respuesta" not in e["vistos"])
e["llamadas"] = {}
privado.escribir(elite.ESTADO, e)

# 6. Palanca de la fábrica entera, y otra fuera de sus límites
RESPUESTAS["fab-1"] = {"salida": "palanca", "ambito": "fabrica", "campo": "juzgado.jurado.encendido", "valor": False}
RESPUESTAS["fab-2"] = {"salida": "palanca", "ambito": "fabrica", "campo": "videos_por_ronda", "valor": 40}
e = elite.leer()
hechas = elite.arquitecto([{"id": "fab-1", "tipo": "caso", "canal": "", "pruebas": ["x"]},
                           {"id": "fab-2", "tipo": "caso", "canal": "", "pruebas": ["x"]}], parte, e)
privado.escribir(elite.ESTADO, e)
comprobar("palanca de la fábrica: se aplica por encima de los ajustes; la que se sale de sus límites, no",
          privado.ajustes()["juzgado"]["jurado"]["encendido"] is False if isinstance(privado.ajustes().get("juzgado"), dict) else False)
comprobar("fuera de límites (40 vídeos por ronda): rechazada", privado.ajustes()["videos_por_ronda"] != 40
          and [h for h in hechas if h["id"] == "fab-2"][0].get("rechazada"))

# 7. Seguimiento: el cambio de la cuenta empeora las notas → se deshace solo y se aprende
e = elite.leer()
for x in e["cambios"]:
    if x.get("clave") == CUENTA:
        x["fecha"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=120)).strftime("%Y-%m-%dT%H:%M:%SZ")
        x["base"]["media"] = 80.0
privado.escribir(elite.ESTADO, e)
for nota in (70, 71, 69):
    juicio(CUENTA, nota, "claude", minutos=5)
elite.main([])
e = elite.leer()
cambio = [x for x in e["cambios"] if x.get("clave") == CUENTA][-1]
aprendido = privado.cuaderno("elite_arquitecto").datos["lecciones"]
comprobar("un cambio que empeora se deshace solo", cambio["estado"] == "deshecho" and privado.canal(CUENTA).get("guionista") != "claude")
comprobar("y el Arquitecto lo apunta en su cuaderno para no repetirlo", any("NO FUNCIONÓ" in x["texto"] for x in aprendido))
comprobar("lo deja todo apuntado para la app (parte, decisiones, cambios, obras)",
          all(k in e for k in ("parte", "decisiones", "cambios", "obras", "reformas", "ultimo", "mirado")))

# 8. Tope de veces al día que piensa con el cerebro caro, y nada de decidir dos veces con las mismas pruebas
e = elite.leer()
e["llamadas"] = {dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"): elite.LLAMADAS_DIA}
antes = len(PREGUNTAS)
hechas = elite.arquitecto([{"id": "nuevo-1", "tipo": "caso", "canal": "", "pruebas": ["x"]}], parte, e)
comprobar("con el tope del día gastado no vuelve a preguntar al cerebro caro", hechas == [] and len(PREGUNTAS) == antes)
e["llamadas"] = {}
visto = {"id": ID_FORMATO, "tipo": "formato", "canal": CANAL, "clave": CANAL, "pruebas": ["x"]}
e["vistos"][ID_FORMATO] = privado.ahora()
e["ultimas"][ID_FORMATO] = {"fecha": privado.ahora(), "juicios": 6}
comprobar("un problema ya decidido no se vuelve a decidir sin pruebas nuevas ni horas de por medio",
          elite.arquitecto([visto], parte, e) == [] and len(PREGUNTAS) == antes)

print("Simulacro de la Élite: " + ("todo bien" if not FALLOS else f"{FALLOS} fallo(s)"))
sys.exit(1 if FALLOS else 0)
