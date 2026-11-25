"""Simulacro del Cerebro: sin IA de verdad (ia.preguntar de mentira), comprueba que aprende de los vídeos juzgados,
piensa un plan con su manual, mide sus planes (el que sube la media gana y pasa a «saber»; el que la baja, no), repara
la cuenta que se queda sin dibujos y, si un paso suyo falla, sigue con los demás.

    python pruebas/simulacro_cerebro.py
"""
import datetime as dt
import glob
import json
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
PRIVADO = os.path.join(tempfile.mkdtemp(prefix="cerebro-"), "privado")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), PRIVADO)
os.environ["PRIVADO"] = PRIVADO
os.environ["MEMORIA_DIR"] = os.path.join(PRIVADO, "memoria")
from bots.comun import ia, privado  # noqa: E402
from bots.cerebro import cerebro  # noqa: E402

CUENTA, CANAL, OTRO = "barrio.prueba", "terror", "gta"      # motivación (TikTok/Instagram), historias y noticias (YouTube)
FALLOS, N = 0, [0]


def comprobar(que, vale):
    global FALLOS
    print(("bien " if vale else "MAL  ") + que, flush=True)
    FALLOS += 0 if vale else 1


def juicio(clave, nota, minutos=-60, razon="el gancho tarda en llegar y el arranque es lento", cola="", **mas):
    """Un vídeo juzgado de mentira (minutos < 0: hace un rato; > 0: después de ahora, para que cuente tras un plan)."""
    N[0] += 1
    cuando = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutos, seconds=N[0])
    privado.guardar_estado(f"juzgado/juicios/{cuando.strftime('%Y%m%d-%H%M%S')}-{N[0]}-{privado.alias(clave)}{cola}.json", dict({
        "canal": clave, "tipo": "video", "titulo": f"Vídeo {N[0]}", "nota": nota, "fecha": cuando.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sentencia": "sube" if nota >= 90 else "suspendido", "consejo": "ve al grano", "prueba": False,
        "votos": [{"juez": "reloj", "nota": nota - 6, "razon": razon}, {"juez": "gancho", "nota": nota + 2, "razon": "bien"}]},
        **mas))


PREGUNTAS, PLAN, ROTA = [], {}, [None]


def cerebro_de_mentira(texto, **kw):
    PREGUNTAS.append(texto)
    if ROTA[0]:
        raise ROTA[0]
    return dict(PLAN)


def lee(ruta):
    return privado.leer(ruta, {})


ia.preguntar = cerebro_de_mentira
ia.quien = lambda: {"motor": "gemini"}
PLAN.update({"diagnostico": "Tarda en arrancar.",
             "reglas": ["Primera frase de 7 palabras como mucho.", "Máximo 10 palabras por escena.", "Acaba con una pregunta de dos opciones."],
             "no_hagas": ["Empezar por el contexto."], "repite": "El giro final.", "prueba": "Solo esta vez: gancho de reto con tiempo."})

# 0. El manual: siete ficheros cortos, y cada formato recibe lo suyo dentro del tope
ficheros = sorted(glob.glob(os.path.join(cerebro.SABER, "*.md")))
comprobar("el manual tiene sus 7 ficheros y ninguno pasa de 60 líneas",
          [os.path.basename(f)[:2] for f in ficheros] == [f"{i}-" for i in range(1, 8)]
          and all(len(open(f, encoding="utf-8").read().splitlines()) <= 60 for f in ficheros))
FORMATOS = {"historias": "Historias de terror", "datos": "Datos, curiosidades", "noticias": "Datos, curiosidades",
            "versus": "Versus", "bolas": "Mapas con bolas", "pictos": "Motivación y dinero", "ciencia": "Biografías y ciencia",
            "acertijos": "Datos, curiosidades", "clips": "Datos, curiosidades"}
GENERALES = ("# Gancho", "# Retención", "# Final", "# Títulos", "# Experimentos", "# Diagnóstico")
textos = {f: cerebro.saber(f) for f in FORMATOS}
comprobar("cada formato recibe SU apartado (y no el de otro), lo general de los 6 ficheros y no pasa de 6.000 caracteres",
          all(f"# Su formato: {titulo}" in textos[f] and textos[f].count("# Su formato:") == 1 and len(textos[f]) <= cerebro.SABER_TOPE
              and all(t in textos[f] for t in GENERALES) for f, titulo in FORMATOS.items()))
comprobar("el apartado también se encuentra por el tipo del canal, y un formato desconocido se queda con lo general",
          "Biografías y ciencia" in cerebro.saber("otro", "biografias") and "# Su formato" not in cerebro.saber("vídeo corto")
          and len(cerebro.saber("vídeo corto")) > 3000)
con, sin = cerebro.saber("datos", foco=("2-",)), cerebro.saber("datos")
comprobar("el fichero del que más se quejan los jueces entra con más sitio",
          "Bucles abiertos" in con and "Bucles abiertos" not in sin and len(con) <= cerebro.SABER_TOPE)
comprobar("ningún trozo del manual acaba en un título colgando",
          not any(t.strip().splitlines()[-1].startswith("#") for texto in list(textos.values()) + [con] for t in texto.split("\n\n")))

# 1. Aprender: los vídeos juzgados entran en su memoria; las pruebas y las actas del Jurado, no
for nota in (78, 80, 82):
    juicio(CUENTA, nota, fiscalia="el final se queda flojo", publico_resumen="se van en el segundo 2")
for nota in (84, 86):
    juicio(CANAL, nota)
juicio(CANAL, 40, prueba=True)
juicio(CANAL, 30, cola="-jurado")
resumen = cerebro.Cerebro().pasada()
m = lee(cerebro.MEMORIA)
comprobar("aprende de cada vídeo juzgado (y no de las pruebas ni de las actas del Jurado)",
          len(m["cuentas"][CUENTA]["videos"]) == 3 and len(m["cuentas"][CANAL]["videos"]) == 2
          and resumen[CUENTA]["media"] == 80.0 and resumen[CANAL]["mejor"] == 86
          and "arranque es lento" in m["cuentas"][CUENTA]["videos"][0]["pegas"][0])

# 2. Pensar: un plan por cuenta, con el manual y el apartado de su formato en la pregunta, y la receta para el guionista
recetas = lee(cerebro.RECETAS)["cuentas"]
p_cuenta = next((p for p in PREGUNTAS if "«motivacion»" in p), "")
p_canal = next((p for p in PREGUNTAS if "«historias»" in p), "")
comprobar("piensa un plan para cada cuenta con vídeos nuevos y lo deja en las recetas",
          len(PREGUNTAS) == 2 and recetas[CUENTA]["reglas"] == PLAN["reglas"] and recetas[CANAL]["media_antes"] == 85.0
          and len(m["cuentas"][CUENTA]["planes"]) == 1)
comprobar("piensa con su manual: lo general y el apartado del formato de esa cuenta",
          "TU MANUAL" in p_cuenta and "# Su formato: Motivación y dinero" in p_cuenta and "# Gancho (los 2 primeros segundos)" in p_cuenta
          and "# Su formato: Historias de terror" in p_canal and "Motivación y dinero" not in p_canal)
comprobar("como los jueces se quejan del gancho, el fichero del gancho entra más largo (con sus plantillas)", "## Plantillas" in p_cuenta)
comprobar("la pregunta lleva los vídeos, las pegas y lo que dijo el público, y ningún nombre de cuenta",
          "78/100" in p_cuenta and "se van en el segundo 2" in p_cuenta and CUENTA not in p_cuenta)
receta = cerebro.receta(CUENTA)
comprobar("el guionista recibe la receta lista (haz, no hagas, mantén y la prueba)",
          all(x in receta for x in ("EL CEREBRO", "Primera frase de 7 palabras", "NO HAGAS: Empezar por el contexto",
                                    "MANTÉN: El giro final", "PRUEBA ESTA VEZ")) and cerebro.receta(OTRO) == "")
antes = len(PREGUNTAS)
cerebro.Cerebro().pasada()
comprobar("sin vídeos nuevos no vuelve a pensar el mismo plan", len(PREGUNTAS) == antes)
juicio(OTRO, 70)
cerebro.Cerebro(prueba=True).pasada()
comprobar("con --prueba piensa pero no guarda nada", len(PREGUNTAS) == antes + 1 and OTRO not in lee(cerebro.RECETAS)["cuentas"]
          and not lee(cerebro.MEMORIA)["cuentas"].get(OTRO, {}).get("videos"))

# 3. Medir: el plan que sube la media gana y sus reglas pasan a «saber»; el que la baja pierde y no pasa
cerebro.Cerebro().pasada()                    # ahora de verdad: el tercer canal recibe su primer plan
for nota in (88, 92):
    juicio(CUENTA, nota, minutos=10)          # la cuenta sube de 80 a 90
for nota in (78, 80):
    juicio(CANAL, nota, minutos=10)           # el canal baja de 85 a 79
juicio(OTRO, 71, minutos=10)                  # un solo vídeo después del plan: todavía no se puede medir
PLAN["reglas"] = ["Regla del segundo plan."]
cerebro.Cerebro().pasada()
m = lee(cerebro.MEMORIA)
r_cuenta = m["cuentas"][CUENTA]["planes"][0].get("resultado") or {}
r_canal = m["cuentas"][CANAL]["planes"][0].get("resultado") or {}
comprobar("mide el plan que funcionó: la media sube de 80 a 90 y el veredicto es «mejor»",
          r_cuenta.get("veredicto") == "mejor" and r_cuenta.get("cambio") == 10.0 and r_cuenta.get("videos") == 2
          and r_cuenta.get("mejor") == 92)
comprobar("lo que funciona pasa a «saber», con su formato, para las demás cuentas",
          any(s["regla"] == "Primera frase de 7 palabras como mucho." and s["formato"] == "motivacion" and s["cambio"] == 10.0
              for s in m["saber"]) and len(m["saber"]) == 3)
comprobar("mide el plan que fue a peor (85 → 79) y sus reglas NO pasan a «saber»",
          r_canal.get("veredicto") == "peor" and r_canal.get("cambio") == -6.0 and all(s["formato"] != "historias" for s in m["saber"]))
comprobar("con un solo vídeo después del plan todavía no lo mide", "resultado" not in m["cuentas"][OTRO]["planes"][0])
p_cuenta2 = [p for p in PREGUNTAS if "«motivacion»" in p][-1]
p_otro = [p for p in PREGUNTAS if "«noticias»" in p][-1]
comprobar("al pensar el plan siguiente ve cómo salió el anterior, y otra cuenta del mismo idioma hereda lo que funcionó",
          "TUS PLANES ANTERIORES" in p_cuenta2 and "→ mejor (+10" in p_cuenta2
          and "LO QUE YA TE HA FUNCIONADO" in p_otro and "Primera frase de 7 palabras" in p_otro)
directo = lee(cerebro.DIRECTO)
comprobar("lo cuenta en directo para la app (qué midió y cuánto le falta a cada cuenta para el 100)",
          any(p["que"] == "mido mi plan" for p in directo["pasos"]) and directo["cuentas"][CUENTA]["falta_para_100"] > 0)

# 4. Reparar: 3 turnos seguidos sin dibujos → un día al formato animado; cuando caduca, se deshace solo
privado.guardar_estado(f"central/{CANAL}.json", {"turnos": [{"error": None}] + [{"error": "faltan dibujos (2 de 8)"}] * 3})
privado.guardar_estado(f"central/{OTRO}.json", {"turnos": [{"error": "faltan dibujos (2 de 8)"}] * 2 + [{"error": None}]})
cerebro.Cerebro().pasada()
aj = lee(cerebro.AJUSTES)["canales"]
comprobar("repara: la cuenta que lleva 3 turnos sin dibujos pasa un día al formato animado (y la que se recuperó, no)",
          aj.get(CANAL, {}).get("hipnotico_cada") == 1 and aj[CANAL]["_hasta"]["hipnotico_cada"] > cerebro._iso() and OTRO not in aj)
comprobar("el arreglo va en sus ajustes, nunca en config/",
          "hipnotico_cada" not in json.load(open(os.path.join(PRIVADO, "config", "canales.json"), encoding="utf-8"))["canales"][CANAL])
aj[CANAL]["_hasta"]["hipnotico_cada"] = "2020-01-01T00:00:00Z"
privado.escribir(cerebro.AJUSTES, {"canales": aj})
privado.guardar_estado(f"central/{CANAL}.json", {"turnos": [{"error": None}]})
cerebro.Cerebro().pasada()
comprobar("pasado el día, deshace el cambio solo y la cuenta vuelve a sus dibujos", CANAL not in lee(cerebro.AJUSTES)["canales"])

# 5. Si un paso falla, sigue: sin IA espera; con una respuesta rara o un paso roto, lo apunta y hace lo demás
juicio(CUENTA, 91, minutos=20)
ROTA[0] = ia.SinIA("nadie contesta")
planes_antes = len(lee(cerebro.MEMORIA)["cuentas"][CUENTA]["planes"])
cerebro.Cerebro().pasada()
m = lee(cerebro.MEMORIA)
comprobar("sin IA no inventa un plan: espera, guarda lo aprendido y la cuenta sigue con su plan de antes",
          len(m["cuentas"][CUENTA]["planes"]) == planes_antes and m["cuentas"][CUENTA]["videos"][-1]["nota"] == 91
          and m["averias"][-1]["de_fuera"] and lee(cerebro.DIRECTO)["pasos"][-1]["que"] == "espero a la IA"
          and lee(cerebro.RECETAS)["cuentas"][CUENTA]["reglas"] == ["Regla del segundo plan."])
ROTA[0] = None
PLAN["reglas"] = []
cerebro.Cerebro().pasada()
m = lee(cerebro.MEMORIA)
comprobar("un plan sin reglas no se guarda: lo apunta como avería suya y lo repite en la siguiente pasada",
          len(m["cuentas"][CUENTA]["planes"]) == planes_antes and not m["averias"][-1]["de_fuera"]
          and "sin reglas" in m["averias"][-1]["error"])
PLAN["reglas"] = ["Regla tras la avería."]
c = cerebro.Cerebro()
c.aprender = lambda: 1 / 0
c.medir = lambda: [][1]
juicio(CANAL, 83, minutos=30)
c.pasada()
m = lee(cerebro.MEMORIA)
comprobar("si se le rompen dos pasos (aprender y medir), los apunta y hace igualmente los demás (piensa y guarda)",
          [a["paso"] for a in m["averias"][-2:]] == ["aprender", "medir"]
          and len(m["cuentas"][CUENTA]["planes"]) == planes_antes + 1
          and lee(cerebro.RECETAS)["cuentas"][CUENTA]["reglas"] == ["Regla tras la avería."])
cerebro.Cerebro().pasada()
comprobar("y en la pasada siguiente recupera lo que se saltó (aprende el vídeo que faltaba)",
          lee(cerebro.MEMORIA)["cuentas"][CANAL]["videos"][-1]["nota"] == 83)

# 6. Nada privado en las preguntas a la IA
comprobar("en ninguna pregunta a la IA sale el nombre de la cuenta", PREGUNTAS and not any(CUENTA in p for p in PREGUNTAS))
shutil.rmtree(os.path.dirname(PRIVADO), ignore_errors=True)
print(f"\nSimulacro del Cerebro: {'TODO BIEN' if not FALLOS else f'{FALLOS} FALLO(S)'}")
sys.exit(1 if FALLOS else 0)
