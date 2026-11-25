"""Simulacro de los jueces suplentes y la Sala de espera (sin red): cuando a los jueces de primera no les queda cupo,
juzga la IA gratis de reserva. Comprueba que un suplente puede suspender, pero que su aprobado NO publica nada: el vídeo
espera en la sala hasta que lo confirma un juez de primera, y entonces sigue su camino de siempre.

    python pruebas/simulacro_espera.py
"""
import json
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
PRIVADO = os.path.join(tempfile.mkdtemp(prefix="espera-"), "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
os.environ.pop("NTFY_TEMA", None)
from bots.comun import almacen, claude, gemini, ia, privado  # noqa: E402
from bots.central import fabrica, obras, turno  # noqa: E402
from bots.estudio import estudio  # noqa: E402
from bots.juzgado import espera, tribunal  # noqa: E402

CLAVE = "barrio.prueba"
FALLOS = 0


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    if not vale:
        FALLOS += 1


# ───────────── 1. Quién juzga: Gemini de primera → suplentes gratis → Claude ─────────────
PEDIDOS = []
ESTADO = {"primera": False, "segunda": True, "claude": False}


def gemini_falso(texto, **kw):
    fila = kw.get("fila")
    PEDIDOS.append(("gemini", fila))
    if fila == "primera":
        if not ESTADO["primera"]:
            raise gemini.SinIA("Gemini no contesta: sin cupo hoy")
        gemini.QUIEN["servicio"] = "gemini"
        return {"quien": "gemini"}
    if not ESTADO["segunda"]:
        raise gemini.SinIA("los suplentes no contestan")
    gemini.QUIEN["servicio"] = "gemma"
    return {"quien": "gemma"}


def claude_falso(texto, papel, **kw):
    PEDIDOS.append(("claude", papel))
    claude.ULTIMO.clear()
    claude.ULTIMO.update(motor="claude", papel=papel)
    return {"quien": "claude"}


gemini.preguntar = gemini_falso
claude.preguntar = claude_falso
claude.puede = lambda papel, **k: ESTADO["claude"]
claude.primero = lambda papel, a=None: papel in ("guionista", "ideas", "arreglo")
claude.de_reserva = lambda papel, a=None: papel in ("juez", "jurado")
claude.ajustes = lambda: {}

r = ia.preguntar("juzga", papel="juez", solo_bueno=True)
comprobar("sin Gemini de primera juzga un suplente gratis, y a Claude no se le gasta",
          r == {"quien": "gemma"} and PEDIDOS == [("gemini", "primera"), ("gemini", "segunda")] and ia.es_suplente())
PEDIDOS.clear()
ESTADO.update(segunda=False, claude=True)
r = ia.preguntar("juzga", papel="juez", solo_bueno=True)
comprobar("si tampoco hay suplentes, juzga Claude (que es de primera)", r == {"quien": "claude"} and not ia.es_suplente())
PEDIDOS.clear()
ESTADO.update(segunda=True, claude=False)
try:
    ia.preguntar("confirma", papel="juez", solo_primera=True)
    comprobar("«solo de primera» no acepta suplentes", False)
except gemini.SinIA:
    comprobar("«solo de primera» no acepta suplentes", PEDIDOS == [("gemini", "primera")])
ESTADO.update(primera=True)
r = ia.preguntar("juzga", papel="juez", solo_bueno=True)
comprobar("con Gemini de primera, juzga él", r == {"quien": "gemini"} and not ia.es_suplente())
ESTADO.update(primera=False)
gemini.primera_agotada = lambda: not ESTADO["primera"]
comprobar("sin Gemini de primera ni Claude no hay juez de primera", ia.hay_de_primera("juez") is False)
ESTADO.update(claude=True)
comprobar("con presupuesto de Claude sí lo hay", ia.hay_de_primera("juez") is True)

# ───────────── 2. El Juzgado: el aprobado de un suplente no vale sin un juez de primera ─────────────
SALA = {"suplente": 92, "primera": None}        # la nota que pone cada uno (None = no contesta)
PREGUNTAS = []


def votos(nota):
    return {"consejo": f"consejo del {nota}", "votos": [{"juez": k, "voto": "sube" if nota >= 90 else "no", "nota": nota,
                                                         "razon": "razón"} for k in tribunal.JUECES]}


def ia_del_juzgado(texto, papel=None, solo_primera=False, **kw):
    PREGUNTAS.append("primera" if solo_primera else "cualquiera")
    alegatos = "FISCAL" in texto.upper() and "votos" not in texto.lower()[:0] and texto.startswith(tribunal.ABOGADOS[:20])
    quien = "primera" if solo_primera else ("suplente" if SALA["suplente"] is not None else "primera")
    if SALA[quien] is None:
        raise gemini.SinIA("no hay juez")
    ia.ULTIMO.clear()
    ia.ULTIMO.update(motor="claude" if quien == "primera" else "gemma", papel=papel)
    return {"defensa": "engancha", "fiscalia": "va lento", "fallos_graves": []} if alegatos else votos(SALA[quien])


def fotogramas_falsos(cmd, **kw):
    carpeta = cmd[cmd.index("--salida") + 1]
    os.makedirs(carpeta, exist_ok=True)
    json.dump({"fotogramas": [], "duracion": 20.0}, open(os.path.join(carpeta, "datos.json"), "w"))


tribunal.subprocess.run = fotogramas_falsos
tribunal.juez_guardia.medidas_para = lambda datos, canal, guion=None: {"duracion": 20.0}
tribunal.publico.mirar = lambda *a, **k: None
tribunal._pruebas = lambda clave, canal: ""
tribunal.ia.preguntar = ia_del_juzgado
rapidos = []
tribunal.juez_guardia.juzgar = lambda *a, **k: rapidos.append(1) or {"veredicto": "sin_juicio", "fallos_graves": []}
CANAL = dict(privado.canal(CLAVE), clave=CLAVE, nota_minima=90)
GUION = {"titulo": "Vídeo", "narracion": "Uno. Dos.", "texto_pantalla": "Uno"}
carpeta = os.path.join(PRIVADO, "juicio")


def un_juicio(suplente, primera, **kw):
    SALA.update(suplente=suplente, primera=primera)
    PREGUNTAS.clear()
    return tribunal.juzgar("video.mp4", GUION, CANAL, "", carpeta, **kw)


v = un_juicio(92, None)
comprobar("suplente aprueba y no hay juez de primera → no hay sentencia: el vídeo espera (preaprobado)",
          v["veredicto"] == "sin_juicio" and v.get("preaprobado") and v.get("nota_suplente") == 92
          and v.get("suplente") == "gemma" and PREGUNTAS == ["cualquiera", "cualquiera", "primera"])
v = un_juicio(92, 91)
comprobar("suplente aprueba y el juez de primera lo confirma → aprobado con la nota del de primera",
          v["veredicto"] == "aprobado" and v["total"] == 91 and v["cerebro"] == "claude"
          and v.get("instruccion") == {"cerebro": "gemma", "total": 92})
v = un_juicio(92, 80)
comprobar("suplente aprueba pero el juez de primera no → suspendido (manda el de primera)",
          v["veredicto"] == "suspendido" and v["total"] == 80 and v["cerebro"] == "claude")
v = un_juicio(80, 95)
comprobar("suplente suspende → suspendido, sin gastar al juez de primera",
          v["veredicto"] == "suspendido" and v["total"] == 80 and v.get("suplente") == "gemma"
          and PREGUNTAS == ["cualquiera", "cualquiera"])
v = un_juicio(None, 93)
comprobar("juez de primera aprueba directamente → aprobado, sin más vueltas",
          v["veredicto"] == "aprobado" and v["total"] == 93 and PREGUNTAS == ["cualquiera", "cualquiera"])
rapidos.clear()
v = un_juicio(92, None, confirmar=True)
comprobar("la confirmación solo vale de un juez de primera: si no está, sigue esperando (y no hay juicio rápido)",
          v["veredicto"] == "sin_juicio" and v.get("preaprobado") and PREGUNTAS == ["primera"] and not rapidos)
v = un_juicio(60, 91, confirmar=True)
comprobar("la confirmación ni mira al suplente", v["veredicto"] == "aprobado" and v["total"] == 91
          and PREGUNTAS == ["primera", "primera"])
v = un_juicio(92, None, prueba=True)
comprobar("en las pruebas del dueño no hay esperas (no se publica nada)", v["veredicto"] == "aprobado")

# ───────────── 3. El turno y la Sala de espera ─────────────
ESTANTE = {}


def guardar_falso(etiqueta, ruta, nombre=None):
    ESTANTE[(etiqueta, nombre or os.path.basename(ruta))] = open(ruta, "rb").read()
    return f"https://example.invalid/{etiqueta}/{nombre}"


def bajar_falso(etiqueta, nombre, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, nombre)
    open(ruta, "wb").write(ESTANTE[(etiqueta, nombre)])
    return ruta


almacen.guardar, almacen.bajar = guardar_falso, bajar_falso
almacen.borrar = lambda etiqueta, nombre: ESTANTE.pop((etiqueta, nombre), None)


class Formato:
    n = 0

    @classmethod
    def guionizar(cls, canal, lecciones, arreglar=None):
        cls.n += 1
        return {"formato": "pictos", "titulo": f"Vídeo {cls.n}", "descripcion": "d", "hashtags": ["#a"],
                "texto_tiktok": "t", "texto_instagram": "i",
                "escenas": [{"voz": "Uno.", "texto": "Uno."}, {"voz": "Dos.", "texto": "Dos."}]}


def hacer(canal, lecciones="", formato=None, carpeta=None, avisar=print, guion=None):
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "video.mp4")
    open(ruta, "wb").write(("vídeo de " + guion["titulo"]).encode())
    g = json.loads(json.dumps(guion))
    g["duracion"] = 4.0
    return ruta, g


SENTENCIAS, JUZGADOS = [], []


def juzgar(video, guion, canal, lecciones, carpeta, audio=None, prueba=False, confirmar=False, publico_previo=None):
    s = SENTENCIAS.pop(0)
    JUZGADOS.append({"titulo": guion.get("titulo"), "confirmar": confirmar, "bytes": open(video, "rb").read().decode()})
    base = {"fallos_graves": [], "consejo": "c", "defensa": "d", "fiscalia": "f", "medidas": {}, "juez_mayor": "Juez",
            "tribunal": "juicio completo",
            "votos": [{"juez": "Jueza Carmen Gancho", "clave": "gancho", "voto": "sube", "nota": 0, "razon": "r"}]}
    if s == "espera":
        return dict(base, veredicto="sin_juicio", preaprobado=True, nota_suplente=92, suplente="gemma", total=92)
    if s is None:
        return {"veredicto": "sin_juicio", "preaprobado": bool(confirmar), "medidas": {}}
    return dict(base, veredicto="aprobado" if s >= 90 else "suspendido", total=s, cerebro="claude")


estudio.formato_de = lambda canal, pedido=None: ("pictos", Formato)
estudio.hacer = hacer
turno.tribunal.juzgar = juzgar
turno.montador.duracion = lambda video: 20.0
turno._jurado_guion = lambda clave, canal, g, paso, a, reescribir, alegatos=None, veces=2: (g, True)
turno._coliseo = lambda clave, canal, g, v, paso, a, resumen: g
cfg = privado.config()
cfg["barrios"][CLAVE].update(estudio="animacion", formato_estudio="pictos", nota_minima=90, intentos_estudio=1)
privado.escribir(os.path.join("config", "canales.json"), cfg)
PRIMERA = {"hay": False}
ia.hay_de_primera = lambda papel="juez": PRIMERA["hay"]


def en_espera():
    return [k for k in ESTANTE if k[0] == "espera"]


def un_turno(sentencias):
    time.sleep(1.1)                 # cada turno, su segundo (las fichas de la fábrica llevan la hora)
    SENTENCIAS[:] = sentencias
    JUZGADOS.clear()
    codigo = turno.main(["--canal", "barrio-1", "--salida", os.path.join(PRIVADO, "trabajo")])
    return codigo, privado.leer(os.path.join("estado", "central", f"{CLAVE}.json"), {})["ultimo_turno"]


def bandeja():
    carpeta = os.path.join(PRIVADO, "parasubir")
    return sorted(os.listdir(carpeta)) if os.path.isdir(carpeta) else []


codigo, t = un_turno(["espera"])
ficha = espera.siguiente(CLAVE) or {}
comprobar("un suplente lo da por bueno → el turno acaba bien, sin subir nada, y el vídeo queda en la Sala de espera",
          codigo == 0 and t.get("destino_resultado") == "espera_juez" and not bandeja() and espera.cuantos(CLAVE) == 1
          and ficha.get("nota") == 92 and ("espera", ficha.get("video")) in ESTANTE
          and (ficha.get("guion") or {}).get("titulo") == "Vídeo 1")
ob = (privado.leer(obras.ARCHIVO, {}).get("obras") or {}).get(t.get("obra")) or {}
comprobar("en «Ahora en la fábrica» sale esperando al juez de primera, no como terminado ni como fallo",
          ob.get("estado") == "esperando" and ob.get("en_sala") and "juez de primera" in ob.get("detalle", ""))
comprobar("esa ficha no la pisa el siguiente vídeo de la cuenta", obras.retomar(CLAVE) is None)

codigo, t2 = un_turno(["espera"])
comprobar("sin juez de primera y con sitio en la sala, la cuenta hace otro vídeo mientras tanto",
          codigo == 0 and espera.cuantos(CLAVE) == 2 and espera.llena(CLAVE) and JUZGADOS[0]["titulo"] == "Vídeo 2"
          and t2.get("obra") != t.get("obra"))
codigo, t3 = un_turno([])
comprobar("con la sala llena, la cuenta espera al juez en vez de hacer más (no gasta voz ni dibujos)",
          codigo == 0 and t3.get("destino_resultado") == "espera_juez" and not JUZGADOS and Formato.n == 2)
ajustes = privado.ajustes()
plan, esperan = fabrica.planear(ajustes, privado.config(), {}, solo=CLAVE)[:2]
comprobar("la fábrica no le da turno mientras la sala está llena y no hay juez de primera",
          CLAVE not in [p[0] for p in plan] and "Sala de espera" in str(esperan.get(CLAVE)))

PRIMERA["hay"] = True
plan, esperan = fabrica.planear(ajustes, privado.config(), {}, solo=CLAVE)[:2]
comprobar("en cuanto hay juez de primera, confirmar lo que espera va lo primero", CLAVE in [p[0] for p in plan])
codigo, t4 = un_turno([91])
comprobar("el juez de primera confirma el vídeo que más esperaba (el mismo archivo, sin rehacerlo) y va a «Para subir»",
          codigo == 0 and t4.get("destino_resultado") == "para_subir" and t4.get("nota") == 91 and t4.get("confirmacion")
          and JUZGADOS == [{"titulo": "Vídeo 1", "confirmar": True, "bytes": "vídeo de Vídeo 1"}]
          and espera.cuantos(CLAVE) == 1 and len(bandeja()) >= 1 and t4.get("obra") == t.get("obra") and Formato.n == 2)
ob = (privado.leer(obras.ARCHIVO, {}).get("obras") or {}).get(t.get("obra")) or {}
comprobar("y su ficha pasa de «esperando» a terminada", ob.get("estado") == "terminado" and not ob.get("en_sala"))
antes = len(bandeja())
codigo, t5 = un_turno([80])
comprobar("si el juez de primera no lo aprueba, no se sube y sale de la sala (queda para arreglar si está cerca)",
          codigo == 0 and t5.get("destino_resultado") == "suspendido" and t5.get("nota") == 80 and len(bandeja()) == antes
          and espera.cuantos(CLAVE) == 0 and not en_espera() and (turno.arreglo_pendiente(CLAVE) or {}).get("version") == 2)

# un vídeo que lleva demasiado esperando se quita solo
turno._guardar_arreglo(CLAVE, None)
codigo, _ = un_turno(["espera"])
d = privado.leer(espera._ruta(CLAVE), {})
d["videos"][0]["fecha"] = "2026-01-01T00:00:00Z"
privado.escribir(espera._ruta(CLAVE), d)
comprobar("lo que caduca en la sala se quita y se borra su archivo", len(en_espera()) == 1
          and espera.siguiente(CLAVE) is None and not en_espera())

# sin juez de ningún tipo sigue siendo una espera normal (no un suspenso)
PRIMERA["hay"] = False
codigo, t6 = un_turno([None])
comprobar("sin ningún juez (ni suplente) el turno espera como siempre", codigo == 1
          and str(t6.get("error", "")).startswith("SinIA") and espera.cuantos(CLAVE) == 0)

print("Simulacro de la Sala de espera: " + ("todo bien" if not FALLOS else f"{FALLOS} fallo(s)"))
sys.exit(1 if FALLOS else 0)
