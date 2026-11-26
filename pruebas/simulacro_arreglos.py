"""Simulacro de los arreglos: un vídeo que el Juzgado suspende por poco no se tira, se rehace corrigiendo sus fallos
(lo pidió el dueño: «que vuelva a crear otro enseguida, mejorado con los fallos que ha tenido»). Todo de mentira: ni IA,
ni voz, ni dibujo. Comprueba el turno de una cuenta animada de punta a punta:

    python pruebas/simulacro_arreglos.py
"""
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PRIVADO = os.path.join(tempfile.mkdtemp(prefix="arreglos-"), "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
from bots.comun import almacen, gemini, privado  # noqa: E402
from bots.central import fabrica, obras, turno  # noqa: E402
from bots.estudio import estudio  # noqa: E402

CLAVE = "barrio.prueba"
FALLOS = 0


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    if not vale:
        FALLOS += 1


class Formato:
    """Un formato de mentira que apunta lo que le piden: guiones nuevos o la versión corregida de uno."""
    pedidos = []
    n = 0

    @classmethod
    def guionizar(cls, canal, lecciones, arreglar=None):
        cls.n += 1
        cls.pedidos.append({"lecciones": lecciones, "arreglar": json.loads(json.dumps(arreglar)) if arreglar else None})
        titulo = f"{arreglar['titulo']} (corregido)" if arreglar else f"Vídeo {cls.n}"
        return {"formato": "pictos", "titulo": titulo, "descripcion": "d", "hashtags": ["#a"],
                "texto_tiktok": "t", "texto_instagram": "i",
                "escenas": [{"voz": "Uno.", "texto": "Uno."}, {"voz": "Dos.", "texto": "Dos."}]}


NOTAS = []          # las notas que irá poniendo el Juzgado de mentira (None = no hay juez)
JUZGADOS = []


def juzgar(video, guion, canal, lecciones, carpeta, audio=None, prueba=False):
    nota = NOTAS.pop(0)
    JUZGADOS.append({"titulo": guion.get("titulo"), "version": guion.get("version"), "nota": nota})
    if nota is None:
        return {"veredicto": "sin_juicio", "fallos_graves": [], "motivo": "juicio sin IA", "medidas": {}}
    return {"veredicto": "aprobado" if nota >= 90 else "suspendido", "total": nota, "fallos_graves": [],
            "consejo": f"consejo del {nota}", "defensa": "el gancho funciona", "fiscalia": f"los rótulos se pisan ({nota})",
            "votos": [{"juez": "Jueza Carmen Gancho", "clave": "gancho", "voto": "no", "nota": nota, "razon": "texto cortado"},
                      {"juez": "Juez Ramón Reloj", "clave": "reloj", "voto": "no", "nota": nota, "razon": "va lento"},
                      {"juez": "Jueza Lola Calle", "clave": "calle", "voto": "no", "nota": nota, "razon": "título flojo"}],
            "juez_mayor": "Juez Ramón Reloj", "medidas": {"duracion": 20.0}, "tribunal": "juicio completo", "cerebro": "gemini"}


def hacer(canal, lecciones="", formato=None, carpeta=None, avisar=print, guion=None):
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, "video.mp4")
    open(ruta, "wb").write(b"video de mentira")
    g = json.loads(json.dumps(guion))
    for i, e in enumerate(g["escenas"]):
        e.update(inicio=i * 2.0, fin=i * 2.0 + 2.0, palabras=[{"p": "x", "a": i * 2.0, "b": i * 2.0 + 0.3}])
    g["duracion"] = 2.0 * len(g["escenas"])
    return ruta, g


gemini.preguntar = lambda texto, **kw: (_ for _ in ()).throw(gemini.SinIA("sin IA en el simulacro"))
almacen.guardar = lambda etiqueta, ruta, nombre=None: f"https://example.invalid/{etiqueta}/{nombre or os.path.basename(ruta)}"
estudio.formato_de = lambda canal, pedido=None: ("pictos", Formato)
estudio.hacer = hacer
turno.tribunal.juzgar = juzgar
turno.montador.duracion = lambda video: 20.0
turno._jurado_guion = lambda clave, canal, g, paso, a, reescribir, alegatos=None, veces=2: (g, True)
turno._coliseo = lambda clave, canal, g, v, paso, a, resumen: g
cfg = privado.config()
cfg["barrios"][CLAVE].update(estudio="animacion", formato_estudio="pictos", nota_minima=90)
privado.escribir(os.path.join("config", "canales.json"), cfg)


def un_turno(notas, intentos=3):
    cfg = privado.config()
    cfg["barrios"][CLAVE]["intentos_estudio"] = intentos
    privado.escribir(os.path.join("config", "canales.json"), cfg)
    NOTAS[:] = notas
    Formato.pedidos.clear()
    JUZGADOS.clear()
    codigo = turno.main(["--canal", "barrio-1", "--salida", os.path.join(PRIVADO, "trabajo")])
    return codigo, privado.leer(os.path.join("estado", "central", f"{CLAVE}.json"), {})["ultimo_turno"]


def limpiar():
    Formato.n = 0
    for carpeta in ("parasubir", os.path.join("estado", "arreglos")):
        shutil.rmtree(os.path.join(PRIVADO, carpeta), ignore_errors=True)
    privado.escribir(obras.ARCHIVO, {})


# 1. Se queda en 84: no se tira, se rehace con sus fallos y llega a 91
codigo, t = un_turno([84, 91])
segundo = Formato.pedidos[1]["arreglar"] or {}
comprobar("84 → se rehace el MISMO vídeo con lo que le vieron los jueces",
          len(Formato.pedidos) == 2 and Formato.pedidos[0]["arreglar"] is None and segundo.get("titulo") == "Vídeo 1"
          and segundo.get("version") == 2 and (segundo.get("veredicto") or {}).get("total") == 84
          and "se pisan" in (segundo.get("veredicto") or {}).get("fiscalia", "")
          and len((segundo.get("veredicto") or {}).get("votos") or []) == 3)
comprobar("el guion que recibe va sin los tiempos de la voz", "palabras" not in json.dumps(segundo.get("guion")))
comprobar("la versión corregida aprueba (91) y va a «Para subir»",
          codigo == 0 and t.get("destino_resultado") == "para_subir" and t.get("nota") == 91 and t.get("version") == 2)
comprobar("ya no queda ningún arreglo pendiente", turno.arreglo_pendiente(CLAVE) is None)
texto = estudio.bloque_arreglo(segundo)
comprobar("al guionista le llega el guion grabado, la nota y cada fallo",
          "VERSIÓN 2" in texto and "84/100" in texto and "Vídeo 1" in texto and "va lento" in texto and "se pisan" in texto)
juicios = sorted(f for f in os.listdir(os.path.join(PRIVADO, "estado", "juzgado", "juicios")) if not f.endswith("-jurado.json"))
ultimo = json.load(open(os.path.join(PRIVADO, "estado", "juzgado", "juicios", juicios[-1]), encoding="utf-8"))
comprobar("el juicio lleva su nota en número y la versión", ultimo.get("nota") == 91 and ultimo.get("version") == 2
          and ultimo.get("arreglo_de") == "Vídeo 1")
guardado = [f for f in os.listdir(os.path.join(PRIVADO, "estado", "guiones"))] if os.path.isdir(
    os.path.join(PRIVADO, "estado", "guiones")) else []
comprobar("el guion del vídeo aprobado queda guardado (para cambiarle la voz sin reescribirlo)", len([f for f in guardado if "video-1" in f]) == 1)

# 2. El arreglo sale peor (80): se vuelve a partir de la versión buena; a la tercera versión sin llegar, se deja
limpiar()
codigo, t = un_turno([84, 80, 86])
tercero = Formato.pedidos[2]["arreglar"] or {}
comprobar("un arreglo que sale peor no se usa de base: la versión 3 parte de la buena y sabe qué no repetir",
          tercero.get("titulo") == "Vídeo 1" and tercero.get("version") == 3 and len(tercero.get("no_repetir") or []) == 1
          and (tercero.get("veredicto") or {}).get("total") == 84)
comprobar("tres versiones sin llegar: no se publica y no queda pendiente",
          t.get("destino_resultado") == "suspendido" and turno.arreglo_pendiente(CLAVE) is None)

# 3. Lejos de la nota (60): ese se tira y se hace otro distinto; el que se queda cerca espera su arreglo en el turno siguiente
limpiar()
codigo, t = un_turno([60, 84, 88])
comprobar("60 → se tira y se pide otro vídeo distinto (con lo que dijeron los jueces)",
          Formato.pedidos[1]["arreglar"] is None and "otro vídeo distinto" in Formato.pedidos[1]["lecciones"]
          and "va lento" in Formato.pedidos[1]["lecciones"])
pendiente = turno.arreglo_pendiente(CLAVE) or {}
comprobar("se acaba el turno con 88: queda apuntado para arreglar (versión 3) en el siguiente",
          t.get("destino_resultado") == "suspendido" and pendiente.get("version") == 3
          and (t.get("arreglo_pendiente") or {}).get("version") == 3)
ob = [o for o in (privado.leer(obras.ARCHIVO, {}) or {}).get("obras", {}).values()]
comprobar("la app lo ve en el Juzgado, con su versión corregida anunciada",
          len(ob) == 1 and ob[0]["paso"] == "juzgado" and "versión corregida" in ob[0].get("detalle", ""))
codigo, t = un_turno([93], intentos=1)
comprobar("el turno siguiente empieza por el arreglo pendiente y aprueba",
          (Formato.pedidos[0]["arreglar"] or {}).get("version") == 3 and t.get("destino_resultado") == "para_subir"
          and turno.arreglo_pendiente(CLAVE) is None)

# 4. No hay juez: nada sale sin juicio, no cuenta como suspenso y la app lo ve «esperando» en el Juzgado
limpiar()
codigo, t = un_turno([84, None])
pendiente = turno.arreglo_pendiente(CLAVE) or {}
ob = (privado.leer(obras.ARCHIVO, {}) or {}).get("obras", {})
ficha = list(ob.values())[0] if ob else {}
comprobar("sin juez: el turno espera (no es un suspenso) y el arreglo sigue pendiente",
          codigo == 1 and str(t.get("error", "")).startswith("SinIA") and t.get("destino_resultado") != "suspendido"
          and pendiente.get("version") == 2 and fabrica.de_fuera(t.get("error")))
comprobar("la app lo ve esperando en el Juzgado (no «atasco» ni «sale»)",
          len(ob) == 1 and ficha.get("estado") == "esperando" and ficha.get("paso") == "juzgado"
          and ficha.get("robot") == "juez_guardia")
codigo, t = un_turno([92], intentos=1)
ob2 = (privado.leer(obras.ARCHIVO, {}) or {}).get("obras", {})
comprobar("cuando vuelve la IA sigue en la misma ficha y termina", list(ob2) == list(ob) and
          list(ob2.values())[0].get("estado") == "terminado" and t.get("destino_resultado") == "para_subir")

# 5. La fábrica: quien tiene un arreglo pendiente va el primero aunque hoy haya gastado sus intentos
limpiar()
un_turno([85], intentos=1)
ajustes = dict(privado.ajustes(), intentos_fallidos_dia=1)
hoy = privado.ahora()
privado.guardar_estado("fabrica-cuentas.json", {"rondas": [{"empezada": hoy, "turnos": [
    {"canal": CLAVE, "destino": "suspendido"}]}]})
plan, esperan = fabrica.planear(ajustes, privado.config(), {}, linea="cuentas")
comprobar("planear: el arreglo pendiente entra en el plan aunque se haya pasado del tope del día",
          [k for k, _ in plan] == [CLAVE] and CLAVE not in esperan)
privado.guardar_estado("fabrica-cuentas.json", {"rondas": [{"empezada": hoy, "turnos": [
    {"canal": CLAVE, "destino": "suspendido"}, {"canal": CLAVE, "destino": "suspendido"}]}]})
plan, esperan = fabrica.planear(ajustes, privado.config(), {}, linea="cuentas")
comprobar("planear: pero con el doble del tope, también el arreglo pendiente espera a mañana (no hay bucle sin fin)",
          plan == [] and "mañana" in esperan.get(CLAVE, ""))
privado.guardar_estado("fabrica-cuentas.json", {"rondas": [{"empezada": hoy, "turnos": [
    {"canal": CLAVE, "destino": "suspendido"}]}]})
turno._guardar_arreglo(CLAVE, None)
plan, esperan = fabrica.planear(ajustes, privado.config(), {}, linea="cuentas")
comprobar("planear: sin arreglo pendiente, el tope del día sí frena", plan == [] and "mañana" in esperan.get(CLAVE, ""))

# 6. La pausa para la app
obras.pausar("La IA está saturada.", "2026-01-01T00:00:00Z")
p1 = (privado.leer(obras.ARCHIVO, {}) or {}).get("pausa") or {}
obras.pausar("Sigue saturada.", "2026-01-01T01:00:00Z")
p2 = (privado.leer(obras.ARCHIVO, {}) or {}).get("pausa") or {}
comprobar("pausa: se apunta con motivo y hasta cuándo, y no pierde desde cuándo",
          p1.get("activa") and p2.get("activa") and p2.get("desde") == p1.get("desde") and p2.get("hasta").endswith("01:00:00Z"))
obras.reanudar()
comprobar("pausa: se quita al volver a trabajar", (privado.leer(obras.ARCHIVO, {}) or {}).get("pausa", {}).get("activa") is False)
suyo = {"obras": {}, "actualizado": "2026-01-01T00:00:00Z", "pausa": {"activa": True, "actualizado": "2026-01-01T00:00:00Z"}}
nuestro = {"obras": {}, "actualizado": "2026-01-01T00:05:00Z", "pausa": {"activa": False, "actualizado": "2026-01-01T00:05:00Z"}}
junto = privado.fusionar("estado/obras.json", suyo, nuestro) if hasattr(privado, "fusionar") else {}
comprobar("pausa: al juntar dos turnos gana la última que se apuntó", (junto.get("pausa") or {}).get("activa") is False)

print("Simulacro de los arreglos: " + ("todo bien" if not FALLOS else f"{FALLOS} fallo(s)"))
sys.exit(1 if FALLOS else 0)
