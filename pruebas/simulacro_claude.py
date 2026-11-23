"""Simulacro del cerebro de pago (Claude) con un Claude de mentira: no gasta nada ni necesita llave de verdad.
Comprueba que guionista e ideas piensan con Claude y el juez con Gemini (Claude de reserva), que se apunta el gasto, que
cada día solo se gasta su parte de los créditos del mes, que sin saldo o con una negativa piensa Gemini y que dos turnos
a la vez no pierden gasto.

    python pruebas/simulacro_claude.py        (necesita el paquete anthropic: pip install -r requirements.txt)
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
TMP = tempfile.mkdtemp(prefix="simulacro-claude-")
shutil.copytree(os.path.join(RAIZ, "pruebas", "privado_ejemplo"), os.path.join(TMP, "privado"))
os.environ["PRIVADO"] = os.path.join(TMP, "privado")
os.environ["MEMORIA_DIR"] = os.path.join(TMP, "privado", "memoria")
os.environ["ANTHROPIC_API_KEY"] = "llave-de-mentira"      # nunca sale de aquí: el cliente es falso
import anthropic  # noqa: E402
import httpx2  # noqa: E402

from bots.comun import claude, gemini, ia, privado  # noqa: E402

PEDIDOS = []
MODO = {"que": "bien"}


def respuesta(texto, modelo="claude-opus-5-5", entrada=5000, salida=3000, parada="end_turn"):
    return SimpleNamespace(model=modelo, stop_reason=parada,
                           content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=texto)],
                           usage=SimpleNamespace(input_tokens=entrada, output_tokens=salida, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0, iterations=None))


def crear(**kw):
    PEDIDOS.append(kw)
    if MODO["que"] == "sin_saldo":
        r = httpx2.Response(400, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
        raise anthropic.BadRequestError("Your credit balance is too low to access the Anthropic API.", response=r,
                                        body=None)
    if MODO["que"] == "se_niega":
        return respuesta("", parada="refusal")
    return respuesta('Aquí va:\n```json\n{"titulo": "Interés compuesto", "escenas": [1, 2, 3]}\n```')


claude._cliente = lambda: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=crear)))
GEMINI = []


def falso_gemini(texto, imagenes=(), **kw):
    GEMINI.append({"texto": texto, "imagenes": list(imagenes), **kw})
    if MODO.get("gemini") == "agotado":
        raise gemini.SinIA("sin cupo hoy")
    return {"de": "gemini"}


gemini.preguntar = falso_gemini


def comprobar(cond, que):
    print(("bien  " if cond else "MAL   ") + que)
    if not cond:
        sys.exit(1)


# 1. El guionista piensa con Claude: petición bien hecha y gasto apuntado
g = ia.preguntar("Escribe el guion", papel="guionista", temperatura=0.95)
p = PEDIDOS[-1]
comprobar(g == {"titulo": "Interés compuesto", "escenas": [1, 2, 3]}, "el guion sale del JSON aunque venga con texto y ```")
comprobar(p["model"] == "claude-opus-5-5" and "temperature" not in p, "modelo Opus 5.5 y sin temperatura (Claude no la admite)")
comprobar(p["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in p["betas"], "reserva si se niega, encendida")
comprobar(p["output_config"] == {"effort": "high"}, "el guionista piensa con esfuerzo alto")
comprobar(ia.quien()["motor"] == "claude", "ia.quien() dice que pensó Claude")
estado = privado.leer("estado/claude.json")
coste = (5000 * 4 + 3000 * 20) / 1e6
comprobar(len(estado["gastos"]) == 1 and abs(estado["gastos"][0]["usd"] - coste) < 1e-6, f"gasto apuntado: {coste:.3f} $")
comprobar(estado["resumen"]["tope_hoy_usd"] == round(100 / 30, 4), "sin saber el día de los créditos: 1/30 del mes al día")

# 2. Las ideas, con Claude y esfuerzo medio
ia.preguntar("Propón ideas", papel="ideas", ligero_primero=True)
comprobar(PEDIDOS[-1]["output_config"] == {"effort": "medium"}, "las ideas piensan con esfuerzo medio")

# 3. El juez: primero Gemini (gratis y otro jurado); con fotos y audio, Gemini los recibe tal cual
foto = os.path.join(TMP, "f1.jpg")
from PIL import Image  # noqa: E402
Image.new("RGB", (1080, 1920), (40, 160, 120)).save(foto)
antes = len(PEDIDOS)
v = ia.preguntar("Juzga el vídeo", papel="juez", imagenes=[foto], solo_bueno=True, temperatura=0.3, audio="voz.mp3")
comprobar(v == {"de": "gemini"} and len(PEDIDOS) == antes, "el juez es Gemini mientras tenga cupo (Claude no gasta)")
comprobar(GEMINI[-1]["audio"] == "voz.mp3" and GEMINI[-1]["solo_bueno"], "a Gemini le llegan la voz y sus opciones")

# 4. Si Gemini se queda sin cupo, juzga Claude: con la foto achicada y avisado de que no oye
MODO["gemini"] = "agotado"
v = ia.preguntar("Juzga el vídeo", papel="juez", imagenes=[foto], solo_bueno=True, temperatura=0.3, audio="voz.mp3")
p = PEDIDOS[-1]
contenido = p["messages"][0]["content"]
comprobar(v["titulo"] == "Interés compuesto" and ia.quien()["motor"] == "claude", "sin cupo de Gemini, juzga Claude")
comprobar(contenido[0]["type"] == "image" and contenido[-1]["type"] == "text", "las fotos van antes que el texto")
comprobar("no te llega el audio" in contenido[-1]["text"], "Claude sabe que no oye la voz")
comprobar(p["output_config"] == {"effort": "medium"}, "el juez de reserva piensa con esfuerzo medio")
import base64, io  # noqa: E401,E402
lado = max(Image.open(io.BytesIO(base64.b64decode(contenido[0]["source"]["data"]))).size)
comprobar(lado <= 1280, f"la foto grande se achica antes de mandarla ({lado} px)")
MODO["gemini"] = None

# 5. La parte de hoy gastada: piensa Gemini aunque haya llave
hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
e = privado.leer("estado/claude.json")
e["gastos"].append({"id": "lleno", "dia": hoy, "fecha": hoy + "T00:00:00Z", "usd": 3.3, "papel": "guionista"})
privado.escribir("estado/claude.json", e)
antes = len(PEDIDOS)
r = ia.preguntar("Escribe el guion", papel="guionista")
comprobar(r == {"de": "gemini"} and len(PEDIDOS) == antes, "gastada la parte del día: escribe Gemini (gratis)")
e["gastos"] = [x for x in e["gastos"] if x["id"] != "lleno"]
privado.escribir("estado/claude.json", e)

# 6. Reparto del mes cuando se sabe el día en que llegan los créditos
comprobar(claude._ciclo(dt.date(2026, 11, 23), 15) == (dt.date(2026, 11, 15), dt.date(2026, 12, 15)), "mes de créditos 15→15")
comprobar(claude._ciclo(dt.date(2026, 11, 10), 15) == (dt.date(2026, 10, 15), dt.date(2026, 11, 15)), "antes del día 15")
comprobar(claude._ciclo(dt.date(2026, 12, 20), 15) == (dt.date(2026, 12, 15), dt.date(2027, 1, 15)), "cambio de año")
comprobar(claude._ciclo(dt.date(2026, 1, 31), 31) == (dt.date(2026, 1, 28), dt.date(2026, 2, 28)), "día 31 → 28")
hoy_real = claude._hoy
claude._hoy = lambda: dt.date(2026, 11, 23)
falsos = {"gastos": [{"id": f"d{i}", "dia": f"2026-11-{15 + i:02d}", "usd": 5.0} for i in range(8)], "dias": {}}
pres = claude.presupuesto(falsos, dict(claude.DEFECTO, renueva_dia=15))
comprobar(abs(pres["tope_hoy_usd"] - (100 - 5 * 8) / 22) < 1e-3 and pres["dias_para_creditos_nuevos"] == 22,
          f"lo que queda del mes entre los días que faltan: {pres['tope_hoy_usd']:.2f} $ hoy")
pres = claude.presupuesto({"gastos": [], "dias": {}}, dict(claude.DEFECTO, renueva_dia=24))
comprobar(pres["tope_hoy_usd"] == claude.DEFECTO["dia_max_usd"], "el último día del mes nunca pasa del tope diario")
claude._hoy = hoy_real

# 7. Se niega por sus normas (y su reserva también): escribe Gemini
MODO["que"] = "se_niega"
r = ia.preguntar("Escribe el guion", papel="guionista")
comprobar(r == {"de": "gemini"}, "si Claude se niega, escribe Gemini")

# 8. Sin saldo: se apunta, piensa Gemini y no se vuelve a probar en 20 horas
MODO["que"] = "sin_saldo"
r = ia.preguntar("Escribe el guion", papel="guionista")
e = privado.leer("estado/claude.json")
comprobar(r == {"de": "gemini"} and e.get("sin_saldo") and "sin saldo" in e.get("aviso", ""), "sin saldo: apuntado y Gemini")
claude.APAGADO = None                                   # un turno nuevo (otra ronda)
comprobar(not claude.puede("guionista"), "en las 20 horas siguientes ni se intenta")

# 9. Dos turnos a la vez: no se pierde el gasto de ninguno
a = {"gastos": [{"id": "x1", "dia": hoy, "fecha": "1", "usd": 0.1}], "dias": {hoy: 0.1}, "actualizado": "2026-11-23T10:00:00Z"}
b = {"gastos": [{"id": "x2", "dia": hoy, "fecha": "2", "usd": 0.2}], "dias": {hoy: 0.2}, "actualizado": "2026-11-23T11:00:00Z",
     "aviso": "nuevo"}
j = privado.fusionar("estado/claude.json", a, b)
comprobar(len(j["gastos"]) == 2 and abs(j["dias"][hoy] - 0.3) < 1e-9 and j["aviso"] == "nuevo", "se juntan los gastos")

# 10. Sin llave: ni se intenta
os.environ.pop("ANTHROPIC_API_KEY")
comprobar(not claude.puede("guionista") and ia.preguntar("x", papel="guionista") == {"de": "gemini"}, "sin llave: Gemini")
print(json.dumps(privado.leer("estado/claude.json")["resumen"], ensure_ascii=False))
shutil.rmtree(TMP, ignore_errors=True)
print("Simulacro del cerebro de pago: todo bien")
